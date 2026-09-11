"""Il playoff nella classifica finale: peso della prova e modalita' di ordinamento.

Tre cose, tutte introdotte insieme perche' rispondono alla stessa domanda del
direttore — «come finisce il campionato?»:

* il **peso** di una prova moltiplica il suo contributo alla classifica
  generale prima che venga sommato (issue #64). Con tutti i pesi a 1 il
  risultato deve restare identico a prima: e' la condizione che rende
  innocua la migration su ogni campionato esistente;
* la modalita' **solo playoff** fa decidere le prime posizioni alla gara di
  playoff, lasciando sotto tutti gli altri nell'ordine del campionato;
* il **direttore** puo' registrare la risposta all'invito per conto del
  giocatore, e resta scritto che e' stato lui.
"""

import uuid
from datetime import date, time

import pytest

from models.base import db, utc_now
from models.campionato.models import Campionato
from models.classification.campionato_classification import ClassificationService
from models.classification.models import GaraClassification
from models.classification.score_aggregator import ScoreAggregator
from models.competition.models import Gara
from models.match.models import Match
from models.playoff.models import (
    PlayoffConfiguration,
    PlayoffQualification,
    PlayoffRankingMode,
    PlayoffType,
    QualificationStatus,
)
from models.playoff.services import PlayoffService
from models.status_enum import Discipline, GaraStatus, MatchStatus
from models.user.models import User


def _suffix():
    return uuid.uuid4().hex[:8]


def _make_user(db_session, prefix, role="player"):
    s = _suffix()
    u = User(username=f"{prefix}_{s}", email=f"{prefix}_{s}@test.com", role=role)
    u.set_password("test1234")
    db_session.add(u)
    db_session.flush()
    return u


def _make_campionato(db_session):
    c = Campionato(
        name=f"Camp {_suffix()}",
        campionato_type="amalfi",
        is_active=True,
        planned_gare_count=2,
        default_rounds_count=1,
    )
    db_session.add(c)
    db_session.flush()
    return c


def _make_gara(db_session, campionato, number, day, **kwargs):
    g = Gara(
        campionato_id=campionato.id,
        number=number,
        name=f"Gara {number}",
        date=date(2026, 1, day),
        time=time(18, 0),
        discipline=Discipline.NINE_BALL.value,
        distance=5,
        rounds_count=1,
        current_round=1,
        status=GaraStatus.COMPLETED.value,
        **kwargs,
    )
    db_session.add(g)
    db_session.flush()
    return g


def _make_match(db_session, gara, winner, loser, score=(5, 2)):
    match = Match(
        gara_id=gara.id,
        round_number=1,
        player1_id=winner.id,
        player2_id=loser.id,
        player1_score=score[0],
        player2_score=score[1],
        status=MatchStatus.CLOSED_UNILATERALLY.value,
        winner_id=winner.id,
    )
    db_session.add(match)
    db_session.flush()
    return match


def _make_config(db_session, campionato, **kwargs):
    cfg = PlayoffConfiguration(
        campionato_id=campionato.id,
        name=kwargs.pop("name", "Elite"),
        playoff_type=PlayoffType.TOP_N,
        max_participants=kwargs.pop("max_participants", 4),
        positions_from=kwargs.pop("positions_from", 1),
        positions_to=kwargs.pop("positions_to", 4),
        is_active=True,
        min_garas_played=0,
        **kwargs,
    )
    db_session.add(cfg)
    db_session.flush()
    return cfg


def _score_for(scores, player_id):
    for s in scores:
        if s.player_id == player_id:
            return s
    raise AssertionError(f"giocatore {player_id} assente dall'aggregato")


# ── Peso della prova ────────────────────────────────────────────────


class TestPesoDellaProva:
    def test_peso_uno_e_la_somma_di_sempre(self, db_session):
        """Il default non deve cambiare nessuna classifica esistente.

        E' la condizione che rende la migration innocua: ogni gara nasce con
        peso 1, e con tutti i pesi a 1 la somma pesata coincide con la somma
        piatta che l'aggregatore faceva prima.
        """
        camp = _make_campionato(db_session)
        a = _make_user(db_session, "a")
        b = _make_user(db_session, "b")
        g1 = _make_gara(db_session, camp, 1, 10)
        g2 = _make_gara(db_session, camp, 2, 20)
        _make_match(db_session, g1, a, b, (5, 2))
        _make_match(db_session, g2, a, b, (5, 3))
        db_session.commit()

        scores = ScoreAggregator().aggregate_campionato_scores(camp.id)

        punteggio_a = _score_for(scores, a.id)
        assert punteggio_a.matches_won == 2
        assert punteggio_a.racks_won == 10
        assert punteggio_a.rack_difference == 5

    def test_il_peso_moltiplica_il_contributo_della_prova(self, db_session):
        """Peso 3 sulla seconda prova: quella prova conta il triplo.

        Vittorie **e** triangoli, perche' il peso deve funzionare sia con la
        classifica a vittorie sia con quella a triangoli (issue #64).
        """
        camp = _make_campionato(db_session)
        a = _make_user(db_session, "a")
        b = _make_user(db_session, "b")
        g1 = _make_gara(db_session, camp, 1, 10)
        g2 = _make_gara(db_session, camp, 2, 20, weight=3)
        _make_match(db_session, g1, a, b, (5, 2))
        _make_match(db_session, g2, a, b, (5, 3))
        db_session.commit()

        scores = ScoreAggregator().aggregate_campionato_scores(camp.id)

        punteggio_a = _score_for(scores, a.id)
        # 1 vittoria + 3 x 1 vittoria
        assert punteggio_a.matches_won == 4
        # 5 triangoli + 3 x 5 triangoli
        assert punteggio_a.racks_won == 20
        # (5-2) + 3 x (5-3)
        assert punteggio_a.rack_difference == 9

        punteggio_b = _score_for(scores, b.id)
        assert punteggio_b.matches_lost == 4
        assert punteggio_b.racks_won == 2 + 3 * 3

    def test_il_peso_ribalta_la_classifica(self, db_session):
        """Il senso della funzione: l'ultima prova puo' valere piu' delle altre.

        Chi ha vinto le prime due prove finisce dietro a chi ha vinto solo
        l'ultima, se quella pesa 3. Senza il peso sarebbe 2 a 1 per il primo.
        """
        camp = _make_campionato(db_session)
        a = _make_user(db_session, "a")
        b = _make_user(db_session, "b")
        g1 = _make_gara(db_session, camp, 1, 10)
        g2 = _make_gara(db_session, camp, 2, 15)
        g3 = _make_gara(db_session, camp, 3, 20, weight=3)
        _make_match(db_session, g1, a, b, (5, 0))
        _make_match(db_session, g2, a, b, (5, 0))
        _make_match(db_session, g3, b, a, (5, 0))
        db_session.commit()

        righe = ClassificationService.update_campionato_classification(camp.id)
        per_utente = {r.user_id: r for r in righe}

        assert per_utente[b.id].position == 1
        assert per_utente[a.id].position == 2

    def test_le_statistiche_non_guardano_il_peso(self, db_session):
        """Issue #64: Elo e percentuale vittorie restano sui fatti.

        Il peso vive solo nell'aggregazione di classifica; la conta delle
        partite giocate e' un'altra domanda e non deve moltiplicarsi.
        """
        from models.dashboard.view_models import _compute_user_stats

        camp = _make_campionato(db_session)
        a = _make_user(db_session, "a")
        b = _make_user(db_session, "b")
        g1 = _make_gara(db_session, camp, 1, 10, weight=5)
        _make_match(db_session, g1, a, b, (5, 2))
        db_session.commit()

        stats = _compute_user_stats(a.id)
        assert stats["total_matches"] == 1
        assert stats["won_matches"] == 1


# ── Modalita' di classifica finale ──────────────────────────────────


def _campionato_con_playoff(db_session, mode, weight=1):
    """Campionato a quattro giocatori con una gara di playoff conclusa.

    Il campionato ordina A > B > C > D; il playoff lo ribalta in D > C.
    Cosi' le due modalita' danno risultati diversi in modo visibile.
    """
    camp = _make_campionato(db_session)
    a = _make_user(db_session, "a")
    b = _make_user(db_session, "b")
    c = _make_user(db_session, "c")
    d = _make_user(db_session, "d")

    g1 = _make_gara(db_session, camp, 1, 10)
    _make_match(db_session, g1, a, d, (5, 0))
    _make_match(db_session, g1, b, c, (5, 0))
    g2 = _make_gara(db_session, camp, 2, 15)
    _make_match(db_session, g2, a, c, (5, 0))
    _make_match(db_session, g2, b, d, (5, 0))

    cfg = _make_config(
        db_session,
        camp,
        max_participants=2,
        positions_to=2,
        final_ranking_mode=mode.value,
        playoff_weight=weight,
    )
    playoff = _make_gara(
        db_session, camp, 3, 20, playoff_config_id=cfg.id, weight=weight
    )
    # Nel playoff vince D, che in campionato e' ultimo.
    _make_match(db_session, playoff, d, c, (5, 4))

    db_session.add_all(
        [
            GaraClassification(gara_id=playoff.id, user_id=d.id, position=1),
            GaraClassification(gara_id=playoff.id, user_id=c.id, position=2),
        ]
    )
    db_session.commit()
    return {"campionato": camp, "a": a, "b": b, "c": c, "d": d, "playoff": playoff}


class TestClassificaFinale:
    def test_default_e_il_comportamento_storico(self, db_session):
        """Somma campionato + playoff: e' cio' che l'app faceva gia'.

        La gara di playoff nasce con `campionato_id` valorizzato, quindi
        l'aggregatore la contava da sempre. Il default della colonna nuova non
        deve cambiare quel risultato.
        """
        cfg = PlayoffConfiguration(
            campionato_id=_make_campionato(db_session).id,
            name="Elite",
            playoff_type=PlayoffType.TOP_N,
            max_participants=4,
        )
        db_session.add(cfg)
        db_session.flush()

        assert cfg.ranking_mode is PlayoffRankingMode.CAMPIONATO_PLUS_PLAYOFF
        assert cfg.decides_final_ranking is False
        assert cfg.playoff_weight == 1

    def test_somma_il_vincitore_del_campionato_resta_primo(self, db_session):
        """Con la somma, una sola gara di playoff non ribalta due prove."""
        dati = _campionato_con_playoff(
            db_session, PlayoffRankingMode.CAMPIONATO_PLUS_PLAYOFF
        )
        righe = ClassificationService.update_campionato_classification(
            dati["campionato"].id
        )
        per_utente = {r.user_id: r.position for r in righe}

        assert per_utente[dati["a"].id] == 1
        assert per_utente[dati["d"].id] > per_utente[dati["a"].id]

    def test_solo_playoff_il_vincitore_del_playoff_e_primo(self, db_session):
        """La modalita' che il direttore chiede: decide il playoff."""
        dati = _campionato_con_playoff(db_session, PlayoffRankingMode.PLAYOFF_ONLY)
        righe = ClassificationService.update_campionato_classification(
            dati["campionato"].id
        )
        per_utente = {r.user_id: r.position for r in righe}

        assert per_utente[dati["d"].id] == 1
        assert per_utente[dati["c"].id] == 2

    def test_solo_playoff_chi_non_ha_giocato_resta_in_classifica(self, db_session):
        """Nessuno sparisce, e sotto vale l'ordine del campionato.

        A e B non sono andati al playoff: seguono i due finalisti nell'ordine
        che avevano in campionato (A davanti a B, che e' come le due prove li
        avevano lasciati).
        """
        dati = _campionato_con_playoff(db_session, PlayoffRankingMode.PLAYOFF_ONLY)
        righe = ClassificationService.update_campionato_classification(
            dati["campionato"].id
        )
        per_utente = {r.user_id: r.position for r in righe}

        assert len(righe) == 4
        assert per_utente[dati["a"].id] == 3
        assert per_utente[dati["b"].id] == 4

    def test_solo_playoff_non_somma_il_punteggio_della_finale(self, db_session):
        """Peso efficace 0: il playoff decide l'ordine, non sposta i totali.

        Se si sommasse anche il punteggio, i cinque triangoli vinti da D in
        finale sposterebbero la posizione di A e B — che al playoff non sono
        nemmeno andati.
        """
        dati = _campionato_con_playoff(db_session, PlayoffRankingMode.PLAYOFF_ONLY)
        playoff = db.session.get(Gara, dati["playoff"].id)
        assert playoff.classification_weight == 0

        scores = ScoreAggregator().aggregate_campionato_scores(dati["campionato"].id)
        # D ha perso entrambe le prove di campionato e vinto solo il playoff.
        assert _score_for(scores, dati["d"].id).matches_won == 0

    def test_playoff_non_ancora_concluso_lascia_la_classifica_del_campionato(
        self, db_session
    ):
        """Senza classifica di gara non c'e' niente da sovrapporre.

        E' il caso normale fra l'avvio dei playoff e la fine della finale: la
        classifica generale deve restare quella del campionato, non svuotarsi.
        """
        dati = _campionato_con_playoff(db_session, PlayoffRankingMode.PLAYOFF_ONLY)
        GaraClassification.query.filter_by(gara_id=dati["playoff"].id).delete()
        db_session.commit()

        righe = ClassificationService.update_campionato_classification(
            dati["campionato"].id
        )
        per_utente = {r.user_id: r.position for r in righe}
        assert per_utente[dati["a"].id] == 1

    def test_update_scoring_cambia_anche_il_peso_della_gara(self, db_session):
        """`Gara.weight` e' la fonte letta: la sola configurazione non basta.

        Cambiare il peso senza propagarlo alla gara gia' creata sarebbe un
        comando che sembra funzionare e non sposta niente.
        """
        dati = _campionato_con_playoff(
            db_session, PlayoffRankingMode.CAMPIONATO_PLUS_PLAYOFF
        )
        playoff = db.session.get(Gara, dati["playoff"].id)
        cfg = playoff.playoff_config

        PlayoffService.update_scoring(cfg.id, playoff_weight=4)

        assert db.session.get(Gara, playoff.id).weight == 4
        assert db.session.get(PlayoffConfiguration, cfg.id).playoff_weight == 4

    def test_update_scoring_rifiuta_un_peso_non_positivo(self, db_session):
        dati = _campionato_con_playoff(
            db_session, PlayoffRankingMode.CAMPIONATO_PLUS_PLAYOFF
        )
        cfg = db.session.get(Gara, dati["playoff"].id).playoff_config

        with pytest.raises(ValueError):
            PlayoffService.update_scoring(cfg.id, playoff_weight=0)

    def test_normalize_ripiega_sul_default(self, db_session):
        """Un valore storto non deve far sparire la classifica di un campionato."""
        assert (
            PlayoffRankingMode.normalize("chissa")
            is PlayoffRankingMode.CAMPIONATO_PLUS_PLAYOFF
        )
        assert (
            PlayoffRankingMode.normalize("playoff_only")
            is PlayoffRankingMode.PLAYOFF_ONLY
        )
        assert (
            PlayoffRankingMode.normalize(PlayoffRankingMode.PLAYOFF_ONLY)
            is PlayoffRankingMode.PLAYOFF_ONLY
        )


# ── Risposta registrata dal direttore ───────────────────────────────


def _qualificazione(db_session, campionato, user, position=1, **cfg_kwargs):
    cfg = _make_config(db_session, campionato, **cfg_kwargs)
    qual = PlayoffQualification(
        configuration_id=cfg.id,
        user_id=user.id,
        qualifying_position=position,
        qualification_reason=f"Posizione {position}",
        status=QualificationStatus.PENDING,
        invited_at=utc_now(),
    )
    db_session.add(qual)
    db_session.flush()
    return cfg, qual


class TestRispostaPerContoDelGiocatore:
    def test_il_direttore_conferma_e_resta_scritto_chi_ha_risposto(self, db_session):
        camp = _make_campionato(db_session)
        giocatore = _make_user(db_session, "player")
        direttore = _make_user(db_session, "dir", role="director")
        _cfg, qual = _qualificazione(db_session, camp, giocatore)
        db_session.commit()

        PlayoffService.respond_on_behalf(
            qual.id, accept=True, responded_by_id=direttore.id
        )

        aggiornata = db.session.get(PlayoffQualification, qual.id)
        assert aggiornata.status == QualificationStatus.CONFIRMED
        assert aggiornata.responded_by_id == direttore.id
        assert aggiornata.answered_on_behalf is True

    def test_il_giocatore_che_risponde_da_solo_non_risulta_delegato(self, db_session):
        camp = _make_campionato(db_session)
        giocatore = _make_user(db_session, "player")
        _cfg, qual = _qualificazione(db_session, camp, giocatore)
        db_session.commit()

        PlayoffService.confirm_qualification(qual.id, giocatore.id)

        aggiornata = db.session.get(PlayoffQualification, qual.id)
        assert aggiornata.responded_by_id == giocatore.id
        assert aggiornata.answered_on_behalf is False

    def test_il_rifiuto_registrato_dal_direttore_fa_partire_la_cascata(
        self, db_session
    ):
        """SPECIFICHE.md riga 188: il posto passa al primo degli esclusi.

        E' la ragione per cui questa strada serve: se la risposta arriva a
        voce e nessuno la registra, l'invito resta appeso e il sostituto non
        viene mai cercato.
        """
        camp = _make_campionato(db_session)
        primo = _make_user(db_session, "primo")
        secondo = _make_user(db_session, "secondo")
        direttore = _make_user(db_session, "dir", role="director")

        # Serve una classifica di campionato: e' da li' che si pesca il
        # sostituto.
        gara = _make_gara(db_session, camp, 1, 10)
        _make_match(db_session, gara, primo, secondo, (5, 3))
        db_session.commit()
        ClassificationService.update_campionato_classification(camp.id)

        cfg, qual = _qualificazione(
            db_session, camp, primo, position=1, max_participants=1, positions_to=1
        )
        db_session.commit()

        sostituto = PlayoffService.respond_on_behalf(
            qual.id, accept=False, responded_by_id=direttore.id
        )

        assert db.session.get(PlayoffQualification, qual.id).status == (
            QualificationStatus.DECLINED
        )
        assert sostituto is not None
        assert sostituto.user_id == secondo.id

    def test_non_si_risponde_due_volte(self, db_session):
        camp = _make_campionato(db_session)
        giocatore = _make_user(db_session, "player")
        direttore = _make_user(db_session, "dir", role="director")
        _cfg, qual = _qualificazione(db_session, camp, giocatore)
        db_session.commit()

        PlayoffService.respond_on_behalf(
            qual.id, accept=True, responded_by_id=direttore.id
        )
        with pytest.raises(ValueError):
            PlayoffService.respond_on_behalf(
                qual.id, accept=False, responded_by_id=direttore.id
            )


# ── La pagina del campionato ────────────────────────────────────────


def _righe_di_turno(db_session, campionato):
    """La pagina legge le `RoundClassification` dell'ultimo turno, non i match."""
    from models.classification.gara_classification import RoundClassificationService

    for g in Gara.query.filter_by(campionato_id=campionato.id).all():
        RoundClassificationService.calculate_and_save_round_classification(g.id, 1)
    db_session.commit()


def _classifica_in_pagina(campionato_id):
    from models.campionato.tournament_service import TournamentService

    righe = TournamentService().calculate_general_classification(campionato_id)
    return {dati["username"]: pos for pos, dati in righe}


class TestLaPaginaDelCampionato:
    """`calculate_general_classification` alimenta la pagina del campionato,
    la pagina pubblica, la vetrina e la homepage; le righe `Classification`
    alimentano profilo, export e avvio dei playoff. Fino all'11/09/2026 solo
    le seconde conoscevano peso e modalita' (ADR-053): il direttore sceglieva
    «solo playoff» e la pagina continuava a mostrare la classifica di stagione.
    """

    def _confronta(self, db_session, mode, weight=1):
        dati = _campionato_con_playoff(db_session, mode, weight)
        _righe_di_turno(db_session, dati["campionato"])
        persistite = ClassificationService.update_campionato_classification(
            dati["campionato"].id
        )
        per_id = {r.user_id: r.position for r in persistite}
        pagina = _classifica_in_pagina(dati["campionato"].id)
        for k in "abcd":
            assert pagina[dati[k].username] == per_id[dati[k].id], k
        return dati, pagina

    def test_solo_playoff_la_pagina_mette_primo_chi_ha_vinto_il_playoff(
        self, db_session
    ):
        dati, pagina = self._confronta(db_session, PlayoffRankingMode.PLAYOFF_ONLY)
        assert pagina[dati["d"].username] == 1
        assert pagina[dati["c"].username] == 2
        assert pagina[dati["a"].username] == 3
        assert pagina[dati["b"].username] == 4

    def test_il_peso_conta_anche_in_pagina(self, db_session):
        dati, pagina = self._confronta(
            db_session, PlayoffRankingMode.CAMPIONATO_PLUS_PLAYOFF, weight=3
        )
        # D ha una vittoria in campionato piu' una che vale tre: scavalca A.
        assert pagina[dati["d"].username] == 1

    def test_con_peso_uno_la_pagina_e_quella_di_sempre(self, db_session):
        dati, pagina = self._confronta(
            db_session, PlayoffRankingMode.CAMPIONATO_PLUS_PLAYOFF
        )
        assert pagina[dati["a"].username] == 1
        assert len(pagina) == 4


# ── Il campionato si chiude con la gara di playoff ──────────────────


class TestIlCampionatoSiChiudeConLaGaraDiPlayoff:
    """Lo stato derivato guardava `PlayoffTournament`, un modello che nessuna
    route chiude piu': il campionato restava «In attesa dei playoff» per
    sempre. La fonte e' la gara di playoff, che e' cio' che il direttore
    chiude davvero.
    """

    def test_in_attesa_finche_la_finale_e_aperta(self, db_session):
        from models.status_enum import TournamentStatus

        dati = _campionato_con_playoff(db_session, PlayoffRankingMode.PLAYOFF_ONLY)
        dati["campionato"].terminated_at = utc_now()
        dati["playoff"].status = GaraStatus.PLAYING.value
        db_session.commit()

        assert (
            dati["campionato"].get_status() == TournamentStatus.AWAITING_PLAYOFF.value
        )

    def test_completato_quando_la_finale_e_chiusa(self, db_session):
        from models.status_enum import TournamentStatus

        dati = _campionato_con_playoff(db_session, PlayoffRankingMode.PLAYOFF_ONLY)
        dati["campionato"].terminated_at = utc_now()
        db_session.commit()

        assert dati["campionato"].get_status() == TournamentStatus.COMPLETED.value


# ── La chiusura di una gara aggiorna le righe persistite ────────────


class TestLaChiusuraDellaGaraAggiornaLaClassificaPersistita:
    """Le righe `Classification` si ricalcolavano solo cambiando le regole di
    punteggio, riassegnando un partecipante, unendo due account o terminando
    il campionato: chiusa la finale, profilo ed export restavano alla
    classifica precedente.
    """

    def test_dopo_la_chiusura_le_righe_dicono_la_classifica_nuova(self, db_session):
        from models.classification.gara_classification import (
            RoundClassificationService,
        )
        from models.classification.models import Classification
        from models.competition.state_service import StateService

        camp = _make_campionato(db_session)
        a = _make_user(db_session, "a")
        b = _make_user(db_session, "b")
        c = _make_user(db_session, "c")
        g1 = _make_gara(db_session, camp, 1, 10)
        _make_match(db_session, g1, a, b, (5, 0))
        RoundClassificationService.calculate_and_save_round_classification(g1.id, 1)
        db_session.commit()

        righe = ClassificationService.update_campionato_classification(camp.id)
        assert {r.user_id: r.position for r in righe}[a.id] == 1

        g2 = _make_gara(db_session, camp, 2, 15)
        g2.status = GaraStatus.PLAYING.value
        _make_match(db_session, g2, b, a, (5, 0))
        _make_match(db_session, g2, b, c, (5, 0))
        RoundClassificationService.calculate_and_save_round_classification(g2.id, 1)
        db_session.commit()

        StateService.complete(g2)
        db_session.commit()

        per_id = {
            r.user_id: r.position
            for r in Classification.query.filter_by(campionato_id=camp.id).all()
        }
        assert per_id[b.id] == 1
        assert per_id[a.id] == 2
