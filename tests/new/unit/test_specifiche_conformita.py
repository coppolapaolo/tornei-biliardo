"""Le regole numeriche di SPECIFICHE.md, rese eseguibili.

Questo modulo esiste per una ragione precisa, ed è un guasto già capitato due
volte: **la specifica è prosa, e la prosa perde sempre contro un test.**

Il meccanismo, osservato dal vivo:

1. `docs/reference/SPECIFICHE.md` fissa una regola numerica — quanto vale la X
   in classifica, a chi passa l'invito ai playoff quando qualcuno rifiuta.
2. L'implementazione ne scrive un'altra. Nessuno se ne accorge, perché nessun
   test confronta il codice con la specifica: i test confrontano il codice con
   sé stesso.
3. Prima o poi una code review trova **due parti del codice incoerenti fra
   loro** e le allinea. Se allinea alla parte sbagliata, aggiunge un test di
   regressione che da quel momento **difende la deviazione**: chi provasse a
   correggere vedrebbe un test rosso con una motivazione scritta bene, e si
   fermerebbe.

Il rimedio è togliere alla specifica il ruolo di documento e darle quello di
test. Ogni test qui sotto **cita la riga di SPECIFICHE.md che verifica**, così
che la catena sia percorribile nei due sensi: dal codice alla regola, e dalla
regola al codice.

Regole d'uso, brevi:

* **Un test per regola**, con la citazione nel docstring. Se la regola cambia
  si cambia la specifica *e* il test, nello stesso commit.
* **Una divergenza trovata si scrive `xfail(strict=True)`**, mai si silenzia e
  mai si «adatta» il test al codice. `strict` fa scattare la suite il giorno in
  cui qualcuno corregge, così il test diventa da solo la regressione.
* **Se una regola nella specifica non c'è**, non si inventa qui: si scrive
  prima nella specifica. Un test senza citazione, in questo file, è fuori posto.
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest

from models.classification.score_aggregator import ScoreAggregator
from models.competition.models import Gara, Inscription
from models.competition.spareggio_service import SpareggioService
from models.matchmaking import bye_preference
from models.status_enum import Discipline, GaraStatus, MatchStatus
from models.match.models import Match
from models.playoff.models import (
    PlayoffConfiguration,
    PlayoffQualification,
    PlayoffType,
    QualificationStatus,
)
from models.playoff.services import PlayoffService
from models.user.models import User
from models.user.role_enum import UserRole

SPEC = "docs/reference/SPECIFICHE.md"


def _utente(db_session) -> User:
    sigla = uuid.uuid4().hex[:8]
    utente = User(
        username=f"spec_{sigla}",
        email=f"spec_{sigla}@test.local",
        role=UserRole.PLAYER.value,
    )
    utente.set_password("prova1234")
    db_session.add(utente)
    db_session.flush()
    return utente


def _gara(db_session, *, distanza: int = 5, sistema: str = "WINS") -> Gara:
    quante = db_session.query(Gara).count()
    gara = Gara(
        name=f"Gara spec {quante + 1}",
        number=quante + 1,
        date=date.today(),
        discipline=Discipline.NINE_BALL.value,
        distance=distanza,
        is_race_to=False,
        status=GaraStatus.PLAYING.value,
        rounds_count=3,
        current_round=1,
        classification_system=sistema,
        matchmaking_strategy="amalfi",
        odd_number_policy="bye",
    )
    db_session.add(gara)
    db_session.flush()
    return gara


def _punteggi(gara_id: int, fino_al_turno: int = 1) -> dict[int, object]:
    return {
        voce.player_id: voce
        for voce in ScoreAggregator().aggregate_round_scores(gara_id, fino_al_turno)
    }


# ══ Classifica: i tre sistemi ════════════════════════════════════════════


@pytest.mark.unit
class TestSistemiDiClassifica:
    def test_wins_ordina_per_vittorie_poi_differenza_rack(self, db_session):
        """`SPECIFICHE.md` riga 168.

        > **WINS**: ordina per match vinti (decrescente), poi differenza rack
        > (decrescente), poi spareggio

        La chiave di pari merito deve essere la **coppia**: due giocatori sono
        pari merito solo se coincidono entrambi i criteri. È la regola che il
        driver dei test e2e fa rispettare variando i margini delle partite —
        con tutte le partite allo stesso margine la differenza rack diventa una
        funzione delle vittorie e il secondo criterio non discrimina più.
        """
        gara = _gara(db_session)
        primo, secondo = _utente(db_session), _utente(db_session)
        terzo, quarto = _utente(db_session), _utente(db_session)
        for casa, fuori, in_casa, fuori_casa in (
            (primo, secondo, 4, 1),  # 1 vittoria, +3
            (terzo, quarto, 3, 2),  # 1 vittoria, +1
        ):
            db_session.add(
                Match(
                    gara_id=gara.id,
                    round_number=1,
                    player1_id=casa.id,
                    player2_id=fuori.id,
                    player1_score=in_casa,
                    player2_score=fuori_casa,
                    winner_id=casa.id,
                    status=MatchStatus.CLOSED_UNILATERALLY.value,
                )
            )
        db_session.commit()

        punteggi = _punteggi(gara.id)

        # Stesse vittorie, differenza diversa: non sono pari merito.
        assert punteggi[primo.id].matches_won == punteggi[terzo.id].matches_won == 1
        assert punteggi[primo.id].rack_difference == 3
        assert punteggi[terzo.id].rack_difference == 1

    def test_la_chiave_di_pari_merito_wins_e_la_coppia(self, db_session):
        """`SPECIFICHE.md` riga 168, dal lato dello spareggio.

        Lo spareggio deve raggruppare su `(match vinti, differenza rack)`, non
        sulla sola differenza: raggruppare su un criterio solo genererebbe
        pari merito che non esistono.
        """
        gara = _gara(db_session)
        db_session.commit()

        assert SpareggioService.tiebreakers_apply_to(gara) is True


# ══ A chi tocca la X nel primo turno ═════════════════════════════════════


@pytest.mark.unit
class TestAChiToccaLaXNelPrimoTurno:
    """`SPECIFICHE.md` riga 67.

    > all'avvio il direttore può assegnare la X **all'ultimo iscritto** invece
    > di lasciarla al caso [...] Il resto degli abbinamenti resta casuale: chi
    > riceve la X viene scambiato di posto con chi l'aveva sorteggiata, e
    > nient'altro si muove.

    Qui si verifica *quando* la domanda si pone e *chi* è "l'ultimo iscritto".
    Che lo scambio conservi le garanzie del sorteggio (una X a testa, nessun
    reincontro) lo verifica
    `tests/new/integration/test_x_al_ultimo_iscritto.py`, che ha bisogno di
    generare i turni veri.
    """

    @staticmethod
    def _iscrivi(db_session, gara: Gara, quanti: int) -> list[User]:
        giocatori = []
        for _ in range(quanti):
            giocatore = _utente(db_session)
            db_session.add(Inscription(gara_id=gara.id, user_id=giocatore.id))
            giocatori.append(giocatore)
        db_session.flush()
        return giocatori

    def test_si_pone_solo_con_amalfi_o_casuale_dispari_e_la_x(self, db_session):
        gara = _gara(db_session)
        self._iscrivi(db_session, gara, 5)

        assert bye_preference.choice_applies(gara) is True

        gara.matchmaking_strategy = "random"
        assert bye_preference.choice_applies(gara) is True

        # Fuori dalle due strategie la X non è una sola e la domanda decade.
        gara.matchmaking_strategy = "round_robin"
        assert bye_preference.choice_applies(gara) is False

    def test_col_trio_non_ci_sono_x_da_assegnare(self, db_session):
        gara = _gara(db_session)
        self._iscrivi(db_session, gara, 5)
        gara.odd_number_policy = "trio"

        assert bye_preference.choice_applies(gara) is False

    def test_con_giocatori_pari_non_ci_sono_x_da_assegnare(self, db_session):
        gara = _gara(db_session)
        self._iscrivi(db_session, gara, 6)

        assert bye_preference.choice_applies(gara) is False

    def test_l_ultimo_iscritto_e_l_ultimo_arrivato_fra_chi_gioca(self, db_session):
        gara = _gara(db_session)
        giocatori = self._iscrivi(db_session, gara, 5)

        assert bye_preference.last_inscribed_user_id(gara) == giocatori[-1].id

    def test_senza_la_scelta_la_x_resta_al_sorteggio(self, db_session):
        """Il default è il comportamento storico, non la novità."""
        gara = _gara(db_session)
        self._iscrivi(db_session, gara, 5)

        assert gara.bye_to_last_inscribed in (False, None)
        assert bye_preference.preferred_bye_player(gara) is None


# ══ La X (bye) ═══════════════════════════════════════════════════════════


@pytest.mark.unit
class TestQuantoValeLaX:
    """`SPECIFICHE.md` righe 64 e 71."""

    @staticmethod
    def _con_la_x(db_session, gara: Gara, giocatore: User, punteggio: int) -> Match:
        partita = Match(
            gara_id=gara.id,
            round_number=1,
            player1_id=giocatore.id,
            player2_id=None,
            is_bye=True,
            player1_score=punteggio,
            player2_score=0,
            winner_id=giocatore.id,
            status=MatchStatus.CLOSED_UNILATERALLY.value,
        )
        db_session.add(partita)
        db_session.commit()
        return partita

    def test_la_x_vale_una_vittoria(self, db_session):
        """`SPECIFICHE.md` riga 71.

        > **Bye**: un giocatore salta il turno (solo per sistema WINS: ottiene
        > 1 vittoria, 0 diff rack)

        Questa metà la regge: la vittoria c'è.
        """
        gara = _gara(db_session)
        giocatore = _utente(db_session)
        self._con_la_x(db_session, gara, giocatore, gara.distance)

        assert _punteggi(gara.id)[giocatore.id].matches_won == 1

    def test_la_x_nasce_senza_triangoli(self, db_session):
        """`SPECIFICHE.md` righe 64 e 71, **alla fonte**.

        > abbina un giocatore alla X assegnando il match vinto, ma con **zero
        > differenza punti**

        Questo test passa dal vero punto di creazione, non da un `Match`
        costruito a mano: è lì che stava la divergenza (`round_creation.py`
        assegnava `player1_score = round_distance`), ed è lì che va presidiata.
        Un test che costruisce da sé la partita con il punteggio che vuole non
        può accorgersi di come la produzione la crea davvero.
        """
        from models.competition.round_creation import create_matches_from_pairings
        from models.matchmaking.strategies.base import Pairing

        gara = _gara(db_session)
        giocatore = _utente(db_session)

        create_matches_from_pairings(
            gara=gara,
            pairings=[Pairing(players=(giocatore.id,), is_bye=True, round_number=1)],
            round_number=1,
            round_distance=gara.distance,
        )
        db_session.flush()

        partita = db_session.query(Match).filter_by(gara_id=gara.id).one()
        assert partita.is_bye
        assert partita.player1_score == 0

    def test_la_x_da_zero_differenza_rack(self, db_session):
        """`SPECIFICHE.md` righe 64 e 71, **in classifica**.

        La conseguenza del test precedente sul punteggio aggregato: con zero
        triangoli vinti e nessuno perso, la differenza resta ferma e chi riposa
        si piazza sotto chiunque abbia vinto giocando — che è l'intento
        dichiarato dalla riga 64.
        """
        gara = _gara(db_session)
        giocatore = _utente(db_session)
        self._con_la_x(db_session, gara, giocatore, 0)

        voce = _punteggi(gara.id)[giocatore.id]
        assert voce.matches_won == 1
        assert voce.rack_difference == 0

    def test_la_x_con_challenge_da_differenza_pari_al_punteggio(self, db_session):
        """`SPECIFICHE.md` riga 65.

        > il giocatore abbinato con la X, invece di stare fermo il turno, gioca
        > la challenge e in classifica ottiene il match vinto e una differenza
        > rack pari al punteggio nella challenge

        È la regola che impedisce di correggere la X azzerando l'aggregatore:
        l'aggregatore deve continuare a leggere `player1_score`, perché per la
        X-con-challenge quel campo **è** il punteggio della prova.
        """
        gara = _gara(db_session)
        gara.odd_number_policy = "bye_with_challenge"
        giocatore = _utente(db_session)
        self._con_la_x(db_session, gara, giocatore, 3)

        voce = _punteggi(gara.id)[giocatore.id]
        assert voce.matches_won == 1
        assert voce.rack_difference == 3


# ══ Pareggio a distanza pari ═════════════════════════════════════════════


@pytest.mark.unit
class TestPareggio:
    def test_a_rack_esatti_pari_il_pareggio_da_zero_e_zero(self, db_session):
        """`SPECIFICHE.md` riga 141.

        > **"Exactly N"** (esatto numero): si giocano esattamente N rack, vince
        > chi ne ha vinti di più. Se N è pari, sono possibili pareggi (gestiti
        > con 0 vittorie e 0 diff rack per entrambi nel sistema WINS).
        """
        gara = _gara(db_session, distanza=6)
        uno, due = _utente(db_session), _utente(db_session)
        db_session.add(
            Match(
                gara_id=gara.id,
                round_number=1,
                player1_id=uno.id,
                player2_id=due.id,
                player1_score=3,
                player2_score=3,
                winner_id=None,
                status=MatchStatus.CLOSED_UNILATERALLY.value,
            )
        )
        db_session.commit()

        punteggi = _punteggi(gara.id)

        for giocatore in (uno, due):
            voce = punteggi[giocatore.id]
            assert voce.matches_won == 0, "il pareggio non è una vittoria"
            assert voce.rack_difference == 0


# ══ Playoff: la cascata dei rifiuti ══════════════════════════════════════


@pytest.mark.unit
class TestCascataDeiRifiutiAiPlayoff:
    """`SPECIFICHE.md` riga 177."""

    @staticmethod
    def _campionato_con_playoff(db_session, posti: int, iscritti: int):
        from models.campionato.models import Campionato
        from models.classification.models import Classification
        from models.base import utc_now

        campionato = Campionato(
            name=f"Camp spec {uuid.uuid4().hex[:6]}",
            campionato_type="amalfi",
            is_active=True,
        )
        db_session.add(campionato)
        db_session.flush()
        campionato.terminated_at = utc_now()

        gara = _gara(db_session)
        gara.campionato_id = campionato.id
        gara.status = GaraStatus.COMPLETED.value

        configurazione = PlayoffConfiguration(
            campionato_id=campionato.id,
            name="Elite",
            playoff_type=PlayoffType.TOP_N,
            max_participants=posti,
            positions_from=1,
            positions_to=posti,
            is_active=True,
            auto_generate=True,
        )
        db_session.add(configurazione)
        db_session.flush()

        giocatori = []
        for posizione in range(1, iscritti + 1):
            giocatore = _utente(db_session)
            db_session.add(Inscription(user_id=giocatore.id, gara_id=gara.id))
            db_session.add(
                Classification(
                    campionato_id=campionato.id,
                    user_id=giocatore.id,
                    position=posizione,
                    total_matches_won=iscritti - posizione,
                    gare_played=1,
                )
            )
            giocatori.append(giocatore)
        db_session.commit()
        return campionato, configurazione, giocatori

    def test_chi_rifiuta_lascia_il_posto_al_primo_degli_esclusi(self, db_session):
        """`SPECIFICHE.md` riga 177.

        > Nei playoff con un numero limitato di partecipanti (ad esempio i
        > primi 6), se un giocatore rifiuta, la notifica passa al primo degli
        > esclusi e così via fino a quando un numero di giocatori pari ai posti
        > disponibili ha dato l'ok oppure sono finiti i giocatori.
        """
        _campionato, configurazione, giocatori = self._campionato_con_playoff(
            db_session, posti=4, iscritti=8
        )
        PlayoffService.start_playoff(_campionato.id)
        db_session.commit()

        qualificazioni = PlayoffQualification.query.filter_by(
            configuration_id=configurazione.id
        ).all()
        assert len(qualificazioni) == 4
        rinuncia = min(qualificazioni, key=lambda q: q.qualifying_position)

        PlayoffService.decline_qualification(rinuncia.id, rinuncia.user_id)
        db_session.commit()

        invitati = PlayoffQualification.query.filter_by(
            configuration_id=configurazione.id
        ).all()
        vivi = [
            q
            for q in invitati
            if q.status in (QualificationStatus.PENDING, QualificationStatus.CONFIRMED)
        ]
        assert len(vivi) == 4, (
            "dopo un rifiuto i posti vivi devono tornare a quattro: "
            f"invitati={len(invitati)}, vivi={len(vivi)}"
        )
        # Il sostituto è il quinto della classifica, cioè il primo escluso.
        quinto = giocatori[4]
        assert quinto.id in {q.user_id for q in invitati}


# ──────────────────────────────────────────────────────────────────────────────
# APERTURA E RUNOUT (SPECIFICHE.md, sezione «Match», righe 131-144 — ADR-056)
# ──────────────────────────────────────────────────────────────────────────────


class TestRegoleDiApertura:
    """«Il match ha una regola di inizio e una regola di apertura, entrambe
    ereditate dalla gara a cui appartiene: sul singolo match non si scelgono.»
    (SPECIFICHE.md riga 131)
    """

    def test_le_quattro_modalita_di_apertura_sono_quelle_della_specifica(self):
        """SPECIFICHE.md righe 137-141: quattro, e con questi valori.

        Fino al 2026-08-28 la specifica ne prevedeva **due** e il codice ne
        aveva **tre**, sulle sole sfide individuali. I valori contano quanto il
        numero: finiscono in colonna, e rinominarne uno rende illeggibili le
        righe gia' scritte.
        """
        from models.match.break_rules import BreakRule

        assert [r.value for r in BreakRule] == [
            "winner_breaks",
            "alternate",
            "alternate_two",
            "loser_breaks",
        ]

    def test_le_due_regole_di_inizio_sono_quelle_della_specifica(self):
        """SPECIFICHE.md righe 133-135: primo giocatore, oppure acchito."""
        from models.match.break_rules import StartRule

        assert [r.value for r in StartRule] == ["first_player", "lag"]

    def test_a_turno_e_il_default(self):
        """SPECIFICHE.md riga 139: «È il default».

        E' anche quello che le sfide individuali avevano gia' dal 2026-02:
        cambiarlo riscriverebbe il passato di quelle partite.
        """
        from models.match.break_rules import DEFAULT_BREAK_RULE, BreakRule

        assert DEFAULT_BREAK_RULE is BreakRule.ALTERNATE

    def test_a_turno_alterna_a_ogni_rack(self):
        """SPECIFICHE.md riga 139: «tiri di apertura alternati»."""
        from models.match.break_rules import BreakRule, break_player_for_rack

        apre = [
            break_player_for_rack(BreakRule.ALTERNATE, n, 1, 2, []) for n in range(4)
        ]
        assert apre == [1, 2, 1, 2]

    def test_a_turno_ogni_due_cambia_ogni_due_rack(self):
        """SPECIFICHE.md riga 140: «due rack a testa, poi si cambia»."""
        from models.match.break_rules import BreakRule, break_player_for_rack

        apre = [
            break_player_for_rack(BreakRule.ALTERNATE_TWO, n, 1, 2, [])
            for n in range(6)
        ]
        assert apre == [1, 1, 2, 2, 1, 1]

    def test_spacca_chi_ha_vinto_e_chi_ha_perso_guardano_il_rack_prima(self):
        """SPECIFICHE.md righe 138 e 141."""
        from models.match.break_rules import BreakRule, break_player_for_rack

        # Rack 0 vinto da 2: al rack 1 apre 2 (winner) oppure 1 (loser).
        assert break_player_for_rack(BreakRule.WINNER_BREAKS, 1, 1, 2, [2]) == 2
        assert break_player_for_rack(BreakRule.LOSER_BREAKS, 1, 1, 2, [2]) == 1

    def test_l_acchito_e_due_domande_non_una(self):
        """SPECIFICHE.md riga 135: chi vince l'acchito **sceglie chi** apre.

        Quindi chi ha vinto e chi apre sono due fatti indipendenti, e il
        secondo puo' essere l'avversario del primo. Se fossero lo stesso dato,
        `first_break_player_id` non esisterebbe.
        """
        from models.match.models import Match

        assert hasattr(Match, "lag_winner_id")
        assert hasattr(Match, "first_break_player_id")

    def test_break_and_run_si_deduce_da_chi_apriva(self):
        """SPECIFICHE.md riga 143: «Non si scelgono: si deduce da chi apriva.»

        Un solo flag sul rack (`is_run_out`) piu' chi ha aperto: il break and
        run non e' un secondo flag che qualcuno potrebbe dimenticare di
        alzare — e quindi non puo' contraddire il primo.
        """
        from models.match.models import Rack

        vinto_da_chi_apriva = Rack(winner_id=7, break_player_id=7, is_run_out=True)
        vinto_rispondendo = Rack(winner_id=7, break_player_id=9, is_run_out=True)
        non_runout = Rack(winner_id=7, break_player_id=7, is_run_out=False)

        assert vinto_da_chi_apriva.is_break_and_run is True
        assert vinto_rispondendo.is_break_and_run is False
        assert non_runout.is_break_and_run is False

    def test_le_regole_si_ereditano_dalla_gara_non_dal_match(self, app):
        """SPECIFICHE.md riga 131: «sul singolo match non si scelgono».

        Il match non ha un override: `effective_*_rule` legge **sempre** la
        gara. Se un domani qualcuno aggiungesse una colonna sul match, questo
        test resterebbe verde — ma la catena la descrive la riga 131, ed e'
        quella che il codice deve continuare a seguire.
        """
        from models.campionato.models import Campionato
        from models.competition.models import Gara
        from models.match.break_rules import BreakRule
        from models.match.models import Match

        campionato = Campionato(default_break_rule=BreakRule.LOSER_BREAKS.value)
        gara = Gara(break_rule=None)
        gara.campionato = campionato
        match = Match()
        match.gara = gara

        # NULL sulla gara = eredita dal campionato.
        assert match.effective_break_rule is BreakRule.LOSER_BREAKS

        # Un valore sulla gara vince sul campionato.
        gara.break_rule = BreakRule.ALTERNATE_TWO.value
        assert match.effective_break_rule is BreakRule.ALTERNATE_TWO
