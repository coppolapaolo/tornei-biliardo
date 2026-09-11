"""Gli stati del campionato dicono cosa manca, e nessuno sta fuori dai filtri.

Presidia la sezione «Stati di un campionato» di `docs/reference/SPECIFICHE.md`
(issue #242). Il difetto riparato era che `COMPLETED` rispondeva a due domande
diverse — «si può ancora giocare?» e «il direttore ha chiuso?» — quindi un
campionato con le gare esaurite ma mai chiuso era indistinguibile da uno
consolidato, e finiva in archivio portandosi via il pulsante «Termina».

I test non elencano gli stati a mano dove possono chiederli all'enum: uno stato
nuovo senza etichetta, o dimenticato dai filtri pubblici, deve accendere la
suite invece di sparire in silenzio.
"""

import uuid
from datetime import date, timedelta

import pytest

from models import Campionato
from models.base import utc_now
from models.dashboard.campionato_cards import (
    STATI_CONCLUSI as _TERMINAL_CAMPIONATO_STATUSES,
)
from models.campionato.statistics_service import (
    _TERMINAL_TOURNAMENT_STATUSES,
    compute_campionato_status,
)
from models.competition.models import Gara
from models.status_enum import Discipline, GaraStatus, TournamentStatus
from utils.status_ui import StatusPresenter


def _make_campionato(db_session, planned=2):
    c = Campionato(
        name=f"Camp {str(uuid.uuid4())[:8]}",
        campionato_type="amalfi",
        is_active=True,
        planned_gare_count=planned,
    )
    db_session.add(c)
    db_session.flush()
    return c


def _make_gara(
    db_session,
    campionato,
    number,
    status,
    inscription_start=None,
    inscription_end=None,
):
    g = Gara(
        campionato_id=campionato.id,
        number=number,
        name=f"Gara {number}",
        date=date(2026, 1, number),
        discipline=Discipline.NINE_BALL.value,
        status=status,
        rounds_count=3,
        current_round=1,
        distance=5,
        inscription_start=inscription_start,
        inscription_end=inscription_end,
    )
    db_session.add(g)
    db_session.flush()
    return g


class TestGareEsauriteMaNonChiuso:
    """SPECIFICHE.md, «Stati di un campionato»: riga `AWAITING_CLOSURE`."""

    def test_tutte_le_gare_previste_finite_e_nessuna_chiusura(self, db_session):
        c = _make_campionato(db_session, planned=2)
        for n in (1, 2):
            _make_gara(db_session, c, n, GaraStatus.COMPLETED.value)
        db_session.flush()

        assert c.terminated_at is None
        assert compute_campionato_status(c) == TournamentStatus.AWAITING_CLOSURE.value

    def test_dopo_la_chiusura_diventa_completato(self, db_session):
        """Senza playoff, chiudere porta a COMPLETED: è l'unico stato finale."""
        c = _make_campionato(db_session, planned=1)
        _make_gara(db_session, c, 1, GaraStatus.COMPLETED.value)
        c.terminated_at = utc_now()
        db_session.flush()

        assert compute_campionato_status(c) == TournamentStatus.COMPLETED.value

    def test_restano_gare_da_creare_e_ancora_in_corso(self, db_session):
        """Il ramo della issue #60 non deve regredire: mancano gare → in corso."""
        c = _make_campionato(db_session, planned=3)
        _make_gara(db_session, c, 1, GaraStatus.COMPLETED.value)
        db_session.flush()

        assert compute_campionato_status(c) == TournamentStatus.IN_PROGRESS.value


class TestIscrizioniProgrammateNonSonoAperte:
    """SPECIFICHE.md, «Stati di un campionato»: riga `REGISTRATION_OPEN`.

    Lo stato vale quando almeno una gara **raccoglie** iscrizioni. Una gara con
    l'apertura programmata per la settimana prossima ha `status = INSCRIPTION`
    e non raccoglie niente: la distinzione la fa la finestra
    (`inscription_start`/`inscription_end`), ed è la stessa che il badge della
    gara mostra già come «Iscrizioni programmate» via `get_real_status()`.

    Il difetto, visto in produzione il 2026-09-04: nella stessa schermata il
    campionato diceva «Iscrizioni aperte» e le sue due gare «Iscrizioni
    programmate». Una delle due risposte non aveva chiesto l'orario.
    """

    def test_apertura_futura_non_e_registration_open(self, db_session):
        c = _make_campionato(db_session, planned=2)
        _make_gara(
            db_session,
            c,
            1,
            GaraStatus.INSCRIPTION.value,
            inscription_start=utc_now() + timedelta(days=7),
        )
        db_session.flush()

        assert compute_campionato_status(c) != TournamentStatus.REGISTRATION_OPEN.value

    def test_iscrizioni_gia_chiuse_non_sono_aperte(self, db_session):
        c = _make_campionato(db_session, planned=2)
        _make_gara(
            db_session,
            c,
            1,
            GaraStatus.INSCRIPTION.value,
            inscription_end=utc_now() - timedelta(days=1),
        )
        db_session.flush()

        assert compute_campionato_status(c) != TournamentStatus.REGISTRATION_OPEN.value

    def test_finestra_aperta_adesso_e_registration_open(self, db_session):
        c = _make_campionato(db_session, planned=2)
        _make_gara(
            db_session,
            c,
            1,
            GaraStatus.INSCRIPTION.value,
            inscription_start=utc_now() - timedelta(days=1),
            inscription_end=utc_now() + timedelta(days=1),
        )
        db_session.flush()

        assert compute_campionato_status(c) == TournamentStatus.REGISTRATION_OPEN.value

    def test_senza_finestra_resta_registration_open(self, db_session):
        """Nessuna data = nessun limite: è il comportamento storico e resta."""
        c = _make_campionato(db_session, planned=2)
        _make_gara(db_session, c, 1, GaraStatus.INSCRIPTION.value)
        db_session.flush()

        assert compute_campionato_status(c) == TournamentStatus.REGISTRATION_OPEN.value

    def test_campionato_cominciato_con_le_prossime_ancora_da_aprire(self, db_session):
        """Il caso di produzione: 2 gare giocate, 2 in calendario non aperte.

        Non è `REGISTRATION_OPEN` — non si può iscrivere nessuno — ma nemmeno
        `SETUP`: metà campionato è stato giocato. Sta ancora succedendo, quindi
        `IN_PROGRESS`, che è anche ciò che lo tiene fra i «Campionati in corso»
        della homepage invece di spedirlo fra quelli «in preparazione».
        """
        c = _make_campionato(db_session, planned=4)
        for n in (1, 2):
            _make_gara(db_session, c, n, GaraStatus.COMPLETED.value)
        for n in (3, 4):
            _make_gara(
                db_session,
                c,
                n,
                GaraStatus.INSCRIPTION.value,
                inscription_start=utc_now() + timedelta(days=n),
            )
        db_session.flush()

        assert compute_campionato_status(c) == TournamentStatus.IN_PROGRESS.value

    def test_nessuna_gara_giocata_e_niente_di_aperto_resta_setup(self, db_session):
        """Il ramo opposto: se il campionato non è mai cominciato, è ancora Setup."""
        c = _make_campionato(db_session, planned=2)
        for n in (1, 2):
            _make_gara(
                db_session,
                c,
                n,
                GaraStatus.INSCRIPTION.value,
                inscription_start=utc_now() + timedelta(days=7),
            )
        db_session.flush()

        assert compute_campionato_status(c) == TournamentStatus.SETUP.value


class TestNonEUnoStatoTerminale:
    """Regola 3 della specifica: resta fra gli attivi, non va in archivio.

    È il punto di tutto lo stato: se fosse terminale, un campionato da chiudere
    scomparirebbe dalla dashboard del direttore portandosi via il pulsante che
    serve a chiuderlo.
    """

    def test_dashboard(self):
        assert (
            TournamentStatus.AWAITING_CLOSURE.value not in _TERMINAL_TOURNAMENT_STATUSES
        )

    def test_homepage(self):
        assert (
            TournamentStatus.AWAITING_CLOSURE.value not in _TERMINAL_CAMPIONATO_STATUSES
        )

    def test_gli_altri_due_lo_sono(self):
        for stato in (
            TournamentStatus.COMPLETED,
            TournamentStatus.AWAITING_PLAYOFF,
        ):
            assert stato.value in _TERMINAL_TOURNAMENT_STATUSES
            assert stato.value in _TERMINAL_CAMPIONATO_STATUSES


class TestNessunoStatoCadeFuoriDaiFiltriPubblici:
    """La lista pubblica ha tre secchielli: insieme devono coprire l'enum.

    `AWAITING_CLOSURE` prima si spacciava per COMPLETED, quindi finiva in
    «completati». Aggiungendolo senza toccare i filtri sarebbe stato visibile
    solo con «Tutti» — invisibile, e senza errori.
    """

    @pytest.mark.parametrize("stato", list(TournamentStatus))
    def test_ogni_stato_e_citato_da_un_filtro(self, stato):
        import inspect

        import routes.main

        sorgente = inspect.getsource(routes.main)
        assert (
            f"TournamentStatus.{stato.name}.value" in sorgente
        ), f"{stato.name} non compare in nessun secchiello di /campionati"


class TestEtichetteDistinteEParlanti:
    def test_ogni_stato_ha_la_sua_etichetta(self, app):
        with app.test_request_context():
            senza = [
                s.name
                for s in TournamentStatus
                if StatusPresenter.campionato(s.value)[1] == "Sconosciuto"
            ]
        assert senza == []

    def test_nessuna_etichetta_e_ripetuta(self, app):
        """Due stati con la stessa parola sono il difetto di partenza."""
        with app.test_request_context():
            etichette = [
                StatusPresenter.campionato(s.value)[1] for s in TournamentStatus
            ]
        assert len(etichette) == len(set(etichette)), etichette

    def test_i_due_stati_non_finali_dicono_cosa_si_aspetta(self, app):
        with app.test_request_context():
            assert (
                StatusPresenter.campionato(TournamentStatus.AWAITING_CLOSURE.value)[1]
                == "In attesa di chiusura"
            )
            assert (
                StatusPresenter.campionato(TournamentStatus.AWAITING_PLAYOFF.value)[1]
                == "In attesa dei playoff"
            )
