"""Lo storico tiene insieme tutto quello che il giocatore ha giocato.

Prima la scheda «Partite» interrogava la sola tabella ``match``, e per giunta
il solo stato ``CLOSED_UNILATERALLY``. Due buchi distinti, entrambi silenziosi:

- le **sfide individuali** stanno su ``individual_match`` e non comparivano in
  nessuno storico;
- le partite di torneo **chiuse dai due giocatori** con doppia conferma
  (``CONFIRMED_BY_BOTH``) sparivano, quindi chi gioca dove i risultati se li
  confermano fra loro aveva lo storico monco.

Nessuno dei due dava errore: la pagina funzionava, mostrava solo meno partite
di quelle giocate. È il motivo per cui questi test contano righe, non codici di
stato.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta

import pytest

from models import db, Challenge, Gara, Match, User
from models.campionato.models import Campionato
from models.challenge.services import ChallengeService
from models.individual_match.match_models import IndividualMatch
from models.player.history_service import HistoryFilters, PlayerHistoryService
from models.status_enum import Discipline, MatchStatus
from models.user.models import User
from models.user.role_enum import UserRole


def _utente(nome: str) -> User:
    user = User(
        username=f"{nome}_{uuid.uuid4().hex[:8]}",
        email=f"{nome}_{uuid.uuid4().hex[:8]}@test.com",
        role=UserRole.PLAYER.value,
    )
    user.set_password("prova123")
    db.session.add(user)
    db.session.flush()
    return user


@pytest.fixture
def due_giocatori(db_session):
    io_, avversario = _utente("io"), _utente("avv")
    db_session.commit()
    return io_, avversario


@pytest.fixture
def gara_di_campionato(db_session):
    campionato = Campionato(name=f"Camp {uuid.uuid4().hex[:6]}")
    db_session.add(campionato)
    db_session.flush()
    gara = Gara(
        name="Tappa uno",
        campionato_id=campionato.id,
        number=1,
        date=date(2026, 3, 10),
        discipline=Discipline.EIGHT_BALL.value,
        distance=5,
    )
    db_session.add(gara)
    db_session.flush()
    return gara


def _partita(gara, uno, due, status, vincitore):
    match = Match(
        gara_id=gara.id if gara else None,
        player1_id=uno.id,
        player2_id=due.id,
        player1_score=5,
        player2_score=2,
        status=status,
        winner_id=vincitore.id,
        round_number=1,
    )
    db.session.add(match)
    db.session.flush()
    return match


def _sfida(uno, due, quando: datetime, vincitore):
    sfida = IndividualMatch(
        player1_id=uno.id,
        player2_id=due.id,
        scheduled_at=quando,
        ended_at=quando,
        status=MatchStatus.CONFIRMED_BY_BOTH.value,
        player1_score=4,
        player2_score=1,
        winner_id=vincitore.id,
        location="Sala di prova",
    )
    db.session.add(sfida)
    db.session.flush()
    return sfida


class TestLeSfideIndividualiEntranoNelloStorico:
    def test_una_sfida_individuale_compare_fra_le_partite(
        self, db_session, due_giocatori
    ):
        io_, avversario = due_giocatori
        _sfida(io_, avversario, datetime(2026, 3, 12, 20, 0), io_)
        db_session.commit()

        pagina, stats = PlayerHistoryService.get_unified_match_history(
            io_.id, HistoryFilters()
        )

        assert stats.total_matches == 1
        assert pagina.items[0].context == "individuale"
        assert pagina.items[0].source == "individual"
        assert pagina.items[0].outcome == "won"

    def test_le_due_sorgenti_stanno_nello_stesso_elenco(
        self, db_session, due_giocatori, gara_di_campionato
    ):
        io_, avversario = due_giocatori
        _partita(
            gara_di_campionato,
            io_,
            avversario,
            MatchStatus.CLOSED_UNILATERALLY.value,
            io_,
        )
        _sfida(io_, avversario, datetime(2026, 3, 12, 20, 0), avversario)
        db_session.commit()

        _, stats = PlayerHistoryService.get_unified_match_history(
            io_.id, HistoryFilters()
        )

        assert stats.total_matches == 2
        assert stats.by_context["campionato"] == 1
        assert stats.by_context["individuale"] == 1


class TestIlBucoDegliStatiFinali:
    def test_una_partita_chiusa_dai_due_giocatori_compare(
        self, db_session, due_giocatori, gara_di_campionato
    ):
        """Regressione: `CONFIRMED_BY_BOTH` è chiusa **dai giocatori**.

        Filtrando il solo `CLOSED_UNILATERALLY` (la chiusura del direttore),
        chi gioca dove i risultati si confermano fra giocatori non vedeva
        niente — e non c'era nessun errore a dirlo.
        """
        io_, avversario = due_giocatori
        _partita(
            gara_di_campionato,
            io_,
            avversario,
            MatchStatus.CONFIRMED_BY_BOTH.value,
            io_,
        )
        db_session.commit()

        _, stats = PlayerHistoryService.get_unified_match_history(
            io_.id, HistoryFilters()
        )

        assert stats.total_matches == 1


class TestIlFiltroPerProvenienza:
    def test_seleziona_solo_le_sfide_individuali(
        self, db_session, due_giocatori, gara_di_campionato
    ):
        io_, avversario = due_giocatori
        _partita(
            gara_di_campionato,
            io_,
            avversario,
            MatchStatus.CLOSED_UNILATERALLY.value,
            io_,
        )
        _sfida(io_, avversario, datetime(2026, 3, 12, 20, 0), io_)
        db_session.commit()

        _, stats = PlayerHistoryService.get_unified_match_history(
            io_.id, HistoryFilters(context="individuale")
        )

        assert stats.total_matches == 1
        assert stats.by_context["individuale"] == 1

    def test_la_torta_guarda_le_partite_filtrate(
        self, db_session, due_giocatori, gara_di_campionato
    ):
        """La torta deve raccontare l'insieme elencato sotto, non tutto.

        Se contasse tutte le partite mentre l'elenco ne mostra una fetta, il
        disegno e la lista direbbero due cose diverse nella stessa schermata.
        """
        io_, avversario = due_giocatori
        _partita(
            gara_di_campionato,
            io_,
            avversario,
            MatchStatus.CLOSED_UNILATERALLY.value,
            io_,
        )
        _sfida(io_, avversario, datetime(2026, 3, 12, 20, 0), io_)
        db_session.commit()

        _, tutte = PlayerHistoryService.get_unified_match_history(
            io_.id, HistoryFilters()
        )
        _, solo_individuali = PlayerHistoryService.get_unified_match_history(
            io_.id, HistoryFilters(context="individuale")
        )

        torta_tutte = PlayerHistoryService.context_donut(tutte)
        torta_filtrata = PlayerHistoryService.context_donut(solo_individuali)

        assert torta_tutte["center"] == "2"
        assert len(torta_tutte["slices"]) == 2
        assert torta_filtrata["center"] == "1"
        assert len(torta_filtrata["slices"]) == 1

    def test_senza_partite_non_si_disegna_una_torta_vuota(
        self, db_session, due_giocatori
    ):
        """Un cerchio grigio senza fette sembra un errore di caricamento."""
        io_, _ = due_giocatori
        _, stats = PlayerHistoryService.get_unified_match_history(
            io_.id, HistoryFilters()
        )
        assert PlayerHistoryService.context_donut(stats) is None


class TestLoStoricoDegliEsercizi:
    @pytest.fixture
    def esercizio(self, db_session):
        challenge = Challenge(
            description="Serie da quindici per lo storico",
            image_path="/static/challenges/storico.jpg",
            pass_fail_only=False,
            max_score=15,
            is_active=True,
        )
        db_session.add(challenge)
        db_session.commit()
        return challenge

    def test_le_prove_compaiono_nello_storico(
        self, db_session, due_giocatori, esercizio
    ):
        io_, _ = due_giocatori
        for punteggio in (4, 9, 12):
            ChallengeService.record_attempt(
                user_id=io_.id, challenge_id=esercizio.id, score=punteggio
            )
        db_session.commit()

        pagina, stats = PlayerHistoryService.get_drill_history(io_.id, HistoryFilters())

        assert stats["total"] == 3
        assert stats["best_score"] == 12
        assert stats["distinct"] == 1
        # Ogni riga porta l'id della prova: senza, non si potrebbe cancellare.
        assert all(v["attempt_id"] for v in pagina.items)

    def test_l_andamento_vuole_almeno_due_prove(
        self, db_session, due_giocatori, esercizio
    ):
        """Una spezzata di un punto solo non è un andamento, è un punto."""
        io_, _ = due_giocatori
        ChallengeService.record_attempt(
            user_id=io_.id, challenge_id=esercizio.id, score=7
        )
        db_session.commit()

        punti = PlayerHistoryService.get_drill_trend(
            io_.id, esercizio.id, HistoryFilters()
        )
        assert PlayerHistoryService.trend_chart(punti) is None

    def test_l_andamento_e_in_ordine_cronologico(
        self, db_session, due_giocatori, esercizio
    ):
        """Si legge da sinistra a destra: dalla più vecchia alla più recente.

        L'elenco dello storico va nel verso opposto, ed è l'unica ragione per
        cui i due ordini divergono.
        """
        io_, _ = due_giocatori
        for punteggio in (3, 6, 11):
            ChallengeService.record_attempt(
                user_id=io_.id, challenge_id=esercizio.id, score=punteggio
            )
        db_session.commit()

        punti = PlayerHistoryService.get_drill_trend(
            io_.id, esercizio.id, HistoryFilters()
        )
        assert [p["score"] for p in punti] == [3, 6, 11]

        grafico = PlayerHistoryService.trend_chart(punti, max_score=15)
        assert grafico["first"] == 3
        assert grafico["last"] == 11
        assert grafico["delta"] == 8
        assert grafico["max"] == 15

    def test_il_fondoscala_e_il_massimo_dell_esercizio(
        self, db_session, due_giocatori, esercizio
    ):
        """Senza tetto dichiarato, 3-4-5 e 30-40-50 disegnerebbero la stessa
        linea, e il grafico direbbe che sono andate uguale."""
        punti = [
            {"score": 3, "attempted_at": None, "day": None},
            {"score": 5, "attempted_at": None, "day": None},
        ]
        con_tetto = PlayerHistoryService.trend_chart(punti, max_score=15)
        senza_tetto = PlayerHistoryService.trend_chart(punti)

        assert con_tetto["max"] == 15
        assert senza_tetto["max"] == 5
        # Col tetto la linea sta in basso; senza, il massimo tocca il soffitto.
        assert con_tetto["points"][-1]["y"] > senza_tetto["points"][-1]["y"]

    def test_il_filtro_date_restringe_l_andamento(
        self, db_session, due_giocatori, esercizio
    ):
        io_, _ = due_giocatori
        vecchia = ChallengeService.record_attempt(
            user_id=io_.id, challenge_id=esercizio.id, score=2
        )
        vecchia.attempted_at = datetime(2026, 1, 1, 12, 0)
        ChallengeService.record_attempt(
            user_id=io_.id, challenge_id=esercizio.id, score=13
        )
        db_session.commit()

        punti = PlayerHistoryService.get_drill_trend(
            io_.id,
            esercizio.id,
            HistoryFilters(date_from=date.today() - timedelta(days=1)),
        )
        assert [p["score"] for p in punti] == [13]


class TestCancellareUnaProvaDalloStorico:
    """La cancellazione dallo storico, e la differenza con l'annulla.

    L'annulla dell'allenamento toglie **l'ultima**, perché si sta giocando e
    l'errore da correggere è quello appena fatto. Qui si toglie una prova
    **qualsiasi**: è il gesto da scrivania, per il punteggio inserito sbagliato
    che ci si accorge di avere in elenco.
    """

    @pytest.fixture
    def esercizio(self, db_session):
        challenge = Challenge(
            description="Esercizio da cui cancellare",
            image_path="/static/challenges/canc.jpg",
            is_active=True,
        )
        db_session.add(challenge)
        db_session.commit()
        return challenge

    def test_si_cancella_una_prova_qualsiasi_non_solo_l_ultima(
        self, db_session, due_giocatori, esercizio
    ):
        io_, _ = due_giocatori
        prove = [
            ChallengeService.record_attempt(
                user_id=io_.id, challenge_id=esercizio.id, score=p
            )
            for p in (3, 8, 5)
        ]
        db_session.commit()

        # La prima, non l'ultima: è esattamente ciò che l'annulla non sa fare.
        ChallengeService.delete_attempt(attempt_id=prove[0].id, actor_id=io_.id)
        db_session.commit()

        pagina, stats = PlayerHistoryService.get_drill_history(io_.id, HistoryFilters())
        assert stats["total"] == 2
        assert sorted(v["score"] for v in pagina.items) == [5, 8]

    def test_la_route_cancella_e_torna_allo_storico(self, app, client):
        """Il percorso HTTP completo, con i dati creati fuori dalla fixture.

        `db_session` tiene una transazione sua: un utente creato lì non lo vede
        la richiesta, che gira in una sessione diversa — e Flask-Login la
        rimanda al login invece di eseguire. È una trappola dei test, non del
        codice, ma va aggirata scrivendo il caso come lo vive l'applicazione.
        """
        with app.app_context():
            giocatore = _utente("http")
            challenge = Challenge(
                description="Esercizio cancellabile via HTTP",
                image_path="/static/challenges/http.jpg",
                is_active=True,
            )
            db.session.add(challenge)
            db.session.commit()
            prova = ChallengeService.record_attempt(
                user_id=giocatore.id, challenge_id=challenge.id, score=6
            )
            db.session.commit()
            prova_id, giocatore_id = prova.id, giocatore.id

        with client.session_transaction() as sess:
            sess["_user_id"] = db.session.get(User, giocatore_id).get_id()
        risposta = client.post(f"/player/history/drill/{prova_id}/delete")

        assert risposta.status_code in (301, 302)
        assert "tab=esercizi" in risposta.headers["Location"]
        with app.app_context():
            from models.challenge.models import ChallengeAttempt

            assert db.session.get(ChallengeAttempt, prova_id) is None

    def test_non_si_cancella_la_prova_di_un_altro(
        self, client, db_session, due_giocatori, esercizio
    ):
        io_, altro = due_giocatori
        prova = ChallengeService.record_attempt(
            user_id=altro.id, challenge_id=esercizio.id, score=6
        )
        db_session.commit()

        with client.session_transaction() as sess:
            sess["_user_id"] = io_.get_id()
        client.post(f"/player/history/drill/{prova.id}/delete")

        _, stats = PlayerHistoryService.get_drill_history(altro.id, HistoryFilters())
        assert stats["total"] == 1
