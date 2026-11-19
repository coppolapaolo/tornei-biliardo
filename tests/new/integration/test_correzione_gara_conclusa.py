"""Correggere un risultato in una gara già conclusa, senza stati a metà.

Nato dalla Ronin Cup 2, gara 3 (18/11/2026): a gara chiusa si scopre che al
primo turno MARCO–MAX P era 3-2 e non 2-3. L'app non lo permette (issue #90),
e la correzione passa da `scripts/correggi_risultato_gara_conclusa.py`, che
usa `models/match/correzione_gara_conclusa.py`.

La gara di questi test, sei giocatori, «esattamente 5», due turni:

    turno 1   A–B 5-0   C–D 3-2 (sbagliato: era 2-3)   E–F 3-2
    turno 2   A–E 3-2   C–F 2-3                        B–D 3-2

Prima: A 1º; C, E, F 2º pari merito (una vinta, differenza 0); B 5º; D 6º.
Dopo:  A 1º; D, E, F 2º pari merito; B 5º; C 6º.

Il vincitore resta lo stesso, C esce dal podio e D ci entra: è il caso che
mette alla prova tutto, XP di podio compreso.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from models.base import db, utc_now
from models.status_enum import GaraStatus, MatchStatus

pytestmark = pytest.mark.integration

RISULTATI = [
    # (turno, giocatore1, giocatore2, triangoli1, triangoli2)
    (1, "A", "B", 5, 0),
    (1, "C", "D", 3, 2),
    (1, "E", "F", 3, 2),
    (2, "A", "E", 3, 2),
    (2, "C", "F", 2, 3),
    (2, "B", "D", 3, 2),
]


def _gara_conclusa(db_session, giocatori, campionato=None):
    from models.classification.gara_classification import (
        StrategyBasedClassificationService,
    )
    from models.classification.seeding_service import SeedingService
    from models.competition.models import Gara, Inscription
    from models.competition.state_service import StateService
    from models.match.models import Match, Rack
    from models.rating.calculation_service import RatingCalculationService

    nomi = dict(zip("ABCDEF", giocatori[:6]))
    gara = Gara(
        number=1,
        name="Gara da correggere",
        date=utc_now().date(),
        time=utc_now().time(),
        discipline="8_ball",
        distance=5,
        is_race_to=False,
        status=GaraStatus.PLAYING.value,
        current_round=2,
        rounds_count=2,
        matchmaking_strategy="amalfi",
        campionato_id=campionato.id if campionato else None,
    )
    db_session.add(gara)
    db_session.flush()
    for g in nomi.values():
        db_session.add(Inscription(gara_id=gara.id, user_id=g.id))
    SeedingService.ensure_seeding(gara.id, [g.id for g in nomi.values()])

    partite = {}
    quando = utc_now() - timedelta(days=1)
    for i, (turno, a, b, ta, tb) in enumerate(RISULTATI):
        p1, p2 = nomi[a], nomi[b]
        match = Match(
            gara_id=gara.id,
            round_number=turno,
            player1_id=p1.id,
            player2_id=p2.id,
            player1_score=ta,
            player2_score=tb,
            winner_id=p1.id if ta > tb else p2.id,
            match_distance=5,
            status=MatchStatus.CONFIRMED_BY_BOTH.value,
            ended_at=quando + timedelta(minutes=i),
        )
        db_session.add(match)
        db_session.flush()
        numero = 1
        for vincitore, quanti in ((p1, ta), (p2, tb)):
            for _ in range(quanti):
                db_session.add(
                    Rack(
                        match_id=match.id,
                        rack_number=numero,
                        winner_id=vincitore.id,
                        validated_by_admin=True,
                    )
                )
                numero += 1
        partite[(a, b)] = match
    db_session.commit()

    servizio = StrategyBasedClassificationService()
    servizio.calculate_round_classification(gara.id, 1)
    servizio.calculate_round_classification(gara.id, 2)
    servizio.calculate_gara_classification(gara.id)
    StateService.complete(gara)
    RatingCalculationService.recalculate_all_pools()
    db_session.commit()
    return gara, nomi, partite


@pytest.fixture
def gara(db_session, isolated_players):
    return _gara_conclusa(db_session, isolated_players)


@pytest.fixture
def autore(isolated_players):
    return isolated_players[11]


def _posizioni(gara_id):
    from models.classification.models import GaraClassification

    return {
        r.user_id: r.position
        for r in GaraClassification.query.filter_by(gara_id=gara_id).all()
    }


def _podi(gara_id):
    from models.match.correzione_gara_conclusa import _podi_registrati

    return _podi_registrati(gara_id)


def _correggi(gara_tuple, autore, *, scrivi):
    from models.match.correzione_gara_conclusa import correggi

    _gara, _nomi, partite = gara_tuple
    return correggi(
        partite[("C", "D")].id,
        2,
        3,
        autore.id,
        "segnalato dai giocatori",
        scrivi=scrivi,
    )


class TestLaSituazioneDiPartenza:
    def test_la_gara_e_quella_descritta(self, gara):
        g, n, _ = gara
        pos = _posizioni(g.id)
        assert pos[n["A"].id] == 1
        assert pos[n["C"].id] == pos[n["E"].id] == pos[n["F"].id] == 2
        # La chiusura premia le prime tre righe, vincitore escluso: dei tre
        # pari al secondo posto ne entrano due, scelti dall'ordine di
        # elencazione. È la regola dell'app, e il registro la rispecchia.
        podi = _podi(g.id)
        assert len(podi) == 2 and podi < {n["C"].id, n["E"].id, n["F"].id}


class TestLaProvaNonScriveNiente:
    def test_dice_cosa_succederebbe_e_lascia_tutto_com_era(
        self, db_session, gara, autore
    ):
        from models.match.models import MatchCorrection, Rack

        g, n, partite = gara
        match = partite[("C", "D")]
        triangoli_prima = [
            (r.rack_number, r.winner_id)
            for r in Rack.query.filter_by(match_id=match.id).order_by(Rack.rack_number)
        ]

        podi_prima = _podi(g.id)

        rapporto = _correggi(gara, autore, scrivi=False)

        assert rapporto["scritto"] is False
        assert rapporto["punteggio_dopo"] == (2, 3)
        db_session.expire_all()
        assert (match.player1_score, match.player2_score) == (3, 2)
        assert match.status == MatchStatus.CONFIRMED_BY_BOTH.value
        assert MatchCorrection.query.count() == 0
        assert [
            (r.rack_number, r.winner_id)
            for r in Rack.query.filter_by(match_id=match.id).order_by(Rack.rack_number)
        ] == triangoli_prima
        assert _posizioni(g.id)[n["C"].id] == 2
        assert _podi(g.id) == podi_prima


class TestLaCorrezione:
    def test_la_partita_cambia_e_resta_la_traccia(self, db_session, gara, autore):
        from models.match.models import MatchCorrection

        _g, n, partite = gara
        _correggi(gara, autore, scrivi=True)

        db_session.expire_all()
        match = partite[("C", "D")]
        assert (match.player1_score, match.player2_score) == (2, 3)
        assert match.winner_id == n["D"].id
        assert match.status == MatchStatus.CLOSED_UNILATERALLY.value
        traccia = MatchCorrection.query.filter_by(match_id=match.id).one()
        assert (traccia.previous_player1_score, traccia.previous_player2_score) == (
            3,
            2,
        )
        assert traccia.corrected_by_id == autore.id
        assert traccia.note == "segnalato dai giocatori"

    def test_si_gira_un_triangolo_solo(self, db_session, gara, autore):
        from models.match.models import Rack

        _g, n, partite = gara
        match = partite[("C", "D")]
        prima = {
            r.rack_number: r.winner_id
            for r in Rack.query.filter_by(match_id=match.id).all()
        }

        rapporto = _correggi(gara, autore, scrivi=True)

        db_session.expire_all()
        dopo = {
            r.rack_number: r.winner_id
            for r in Rack.query.filter_by(match_id=match.id).all()
        }
        cambiati = [k for k in prima if prima[k] != dopo[k]]
        assert len(cambiati) == 1
        assert dopo[cambiati[0]] == n["D"].id
        assert [t["rack_number"] for t in rapporto["triangoli_girati"]] == cambiati

    def test_la_classifica_tiene_il_pari_merito(self, db_session, gara, autore):
        g, n, _ = gara
        _correggi(gara, autore, scrivi=True)

        pos = _posizioni(g.id)
        assert pos[n["A"].id] == 1
        assert pos[n["D"].id] == pos[n["E"].id] == pos[n["F"].id] == 2
        assert pos[n["B"].id] == 5
        assert pos[n["C"].id] == 6

    def test_il_podio_passa_da_c_a_d(self, db_session, gara, autore):
        from models.gamification.models import UserLevel, XPTransaction
        from sqlalchemy import func

        g, n, _ = gara
        _correggi(gara, autore, scrivi=True)

        assert _podi(g.id) == {n["D"].id, n["E"].id, n["F"].id}
        # Il livello torna con il registro, per chi ha perso e per chi ha preso.
        for chi in ("C", "D"):
            uid = n[chi].id
            somma = (
                db.session.query(func.coalesce(func.sum(XPTransaction.xp_amount), 0))
                .filter(XPTransaction.user_id == uid)
                .scalar()
            )
            livello = db.session.get(UserLevel, uid)
            assert (livello.total_xp if livello else 0) == max(0, somma)

    def test_dopo_la_correzione_il_ricalcolo_non_cambia_niente(
        self, db_session, gara, autore
    ):
        """Lo stato finale è un punto fisso: classifiche, ELO e podi sono quelli
        che il codice produrrebbe da zero sui risultati corretti. È la
        definizione operativa di «nessuno stato a metà»."""
        from models.match.correzione_gara_conclusa import (
            _differenze,
            _fotografia,
            _podio_atteso,
            _ricalcola,
        )

        g, _n, _ = gara
        _correggi(gara, autore, scrivi=True)

        prima = _fotografia(g)
        _ricalcola(g)
        dopo = _fotografia(g)
        assert _differenze(prima, dopo) == []
        assert dopo["podi"] == _podio_atteso(g)
        db_session.rollback()


class TestQuandoSiRifiuta:
    def _rifiuta(self, db_session, gara, autore, **kwargs):
        from models.match.correzione_gara_conclusa import (
            CorrezioneRifiutata,
            correggi,
        )
        from models.match.models import MatchCorrection

        _g, _n, partite = gara
        argomenti = {
            "match_id": partite[("C", "D")].id,
            "player1_score": 2,
            "player2_score": 3,
            "corrected_by_id": autore.id,
            "scrivi": True,
        }
        argomenti.update(kwargs)
        with pytest.raises(CorrezioneRifiutata) as errore:
            correggi(**argomenti)
        db_session.expire_all()
        assert MatchCorrection.query.count() == 0
        assert (
            partite[("C", "D")].player1_score,
            partite[("C", "D")].player2_score,
        ) == (
            3,
            2,
        )
        return str(errore.value)

    def test_gara_non_conclusa(self, db_session, gara, autore):
        g, _n, _ = gara
        g.status = GaraStatus.PLAYING.value
        db_session.commit()
        assert "non è conclusa" in self._rifiuta(db_session, gara, autore)

    def test_numero_di_triangoli_diverso(self, db_session, gara, autore):
        messaggio = self._rifiuta(
            db_session, gara, autore, player1_score=1, player2_score=3
        )
        assert "numero di triangoli" in messaggio

    def test_vincitore_della_gara_diverso(self, db_session, gara, autore):
        _g, _n, partite = gara
        # A–B 5-0 diventa 0-5: B arriva a due vinte e +6, A scende.
        messaggio = self._rifiuta(
            db_session,
            gara,
            autore,
            match_id=partite[("A", "B")].id,
            player1_score=0,
            player2_score=5,
        )
        assert "vincitore della gara" in messaggio

    def test_stato_salvato_diverso_dal_ricalcolo(self, db_session, gara, autore):
        """Se lo stato salvato non è quello che il codice rifarebbe, non si
        corregge sopra: si mescolerebbero due cambiamenti."""
        from models.classification.models import GaraClassification

        g, n, _ = gara
        riga = GaraClassification.query.filter_by(gara_id=g.id, user_id=n["B"].id).one()
        riga.position = 4
        db_session.commit()

        messaggio = self._rifiuta(db_session, gara, autore)
        assert "non coincide" in messaggio
        db_session.expire_all()
        assert riga.position == 4  # nemmeno il ricalcolo di prova è rimasto


@pytest.fixture
def gara_di_campionato(db_session, isolated_players):
    from models.campionato.models import Campionato

    campionato = Campionato(name="Campionato da correggere", planned_gare_count=4)
    db_session.add(campionato)
    db_session.commit()
    return _gara_conclusa(db_session, isolated_players, campionato)


class TestDentroUnCampionato:
    def test_le_righe_della_classifica_generale_seguono(
        self, db_session, gara_di_campionato, autore
    ):
        from models.classification.models import Classification

        g, n, _ = gara_di_campionato

        def vinte(chi):
            return (
                Classification.query.filter_by(
                    campionato_id=g.campionato_id, user_id=n[chi].id
                )
                .one()
                .total_matches_won
            )

        assert (vinte("C"), vinte("D")) == (1, 0)
        _correggi(gara_di_campionato, autore, scrivi=True)
        db_session.expire_all()
        assert (vinte("C"), vinte("D")) == (0, 1)

    def test_con_gli_inviti_ai_playoff_partiti_si_rifiuta(
        self, db_session, gara_di_campionato, autore
    ):
        from models.match.correzione_gara_conclusa import CorrezioneRifiutata
        from models.match.models import MatchCorrection
        from models.playoff.models import (
            PlayoffConfiguration,
            PlayoffQualification,
            PlayoffType,
        )

        g, n, _ = gara_di_campionato
        configurazione = PlayoffConfiguration(
            campionato_id=g.campionato_id,
            name="Finale",
            playoff_type=PlayoffType.TOP_N,
            max_participants=4,
            positions_from=1,
            positions_to=4,
            is_active=True,
            auto_generate=True,
            min_garas_played=0,
        )
        db_session.add(configurazione)
        db_session.flush()
        db_session.add(
            PlayoffQualification(
                configuration_id=configurazione.id,
                user_id=n["A"].id,
                qualifying_position=1,
                qualification_reason="primo",
            )
        )
        db_session.commit()

        with pytest.raises(CorrezioneRifiutata, match="inviti ai playoff"):
            _correggi(gara_di_campionato, autore, scrivi=True)
        assert MatchCorrection.query.count() == 0
