"""Regressione issue #60 — campionato "Completato" fra una prova e l'altra.

`compute_campionato_status` ritornava COMPLETED non appena tutte le gare
*esistenti* erano completate. In un campionato in corso quella condizione è
vera nella finestra fra la fine di una prova e la creazione della successiva,
e la UI mostrava il campionato come concluso (badge "Completato",
esclusione dalle sezioni "attivi") per poi tornare indietro.

**Precisato dalla #242 (2026-08-29).** Il ramo "tutte le prove pianificate sono
finite" non ritorna più COMPLETED ma `AWAITING_CLOSURE`: le gare sono esaurite,
ma `terminated_at` è NULL e la classifica generale non è consolidata. È la stessa
preoccupazione della #60 portata fino in fondo — un campionato che nessuno ha
chiuso non è concluso — e `AWAITING_CLOSURE` **non è terminale**, quindi resta
nelle sezioni "attivi" invece di uscirne. Vedi la sezione «Stati di un
campionato» in `docs/reference/SPECIFICHE.md`.
"""

import uuid
from datetime import date

import pytest

from models import Campionato
from models.base import utc_now
from models.competition.models import Gara
from models.campionato.statistics_service import compute_campionato_status
from models.status_enum import GaraStatus, TournamentStatus


def _make_campionato(db_session, planned_gare_count):
    c = Campionato(
        name=f"Camp {uuid.uuid4().hex[:8]}",
        campionato_type="amalfi",
        is_active=True,
        planned_gare_count=planned_gare_count,
    )
    db_session.add(c)
    db_session.flush()
    return c


def _make_gara(db_session, campionato, number, status):
    g = Gara(
        campionato_id=campionato.id,
        number=number,
        name=f"Gara {number}",
        date=date(2026, 1, number),
        discipline="nine_ball",
        status=status,
        rounds_count=3,
        current_round=1,
        distance=5,
    )
    db_session.add(g)
    db_session.flush()
    return g


@pytest.mark.unit
class TestCampionatoStatusWithPlannedGare:

    def test_in_progress_while_planned_gare_remain(self, db_session):
        """3 prove su 10 pianificate, tutte completate → ancora in corso."""
        c = _make_campionato(db_session, planned_gare_count=10)
        for n in (1, 2, 3):
            _make_gara(db_session, c, n, GaraStatus.COMPLETED.value)
        db_session.commit()

        assert compute_campionato_status(c) == TournamentStatus.IN_PROGRESS.value

    def test_completed_when_all_planned_gare_are_done(self, db_session):
        """Tutte le prove pianificate create e completate → in attesa di chiusura.

        Non COMPLETED: manca l'atto del direttore. Vedi la nota #242 in testa.
        """
        c = _make_campionato(db_session, planned_gare_count=2)
        _make_gara(db_session, c, 1, GaraStatus.COMPLETED.value)
        _make_gara(db_session, c, 2, GaraStatus.COMPLETED.value)
        db_session.commit()

        assert compute_campionato_status(c) == TournamentStatus.AWAITING_CLOSURE.value

    def test_more_gare_than_planned_still_completes(self, db_session):
        """Il director ha creato più prove del previsto: non torna "in corso"."""
        c = _make_campionato(db_session, planned_gare_count=2)
        for n in (1, 2, 3):
            _make_gara(db_session, c, n, GaraStatus.COMPLETED.value)
        db_session.commit()

        assert compute_campionato_status(c) == TournamentStatus.AWAITING_CLOSURE.value

    def test_manual_termination_completes_regardless(self, db_session):
        """La chiusura deliberata del director chiude comunque il campionato,
        anche con prove pianificate mai create."""
        c = _make_campionato(db_session, planned_gare_count=10)
        _make_gara(db_session, c, 1, GaraStatus.COMPLETED.value)
        c.terminated_at = utc_now()
        db_session.commit()

        assert compute_campionato_status(c) == TournamentStatus.COMPLETED.value

    def test_playing_gara_still_wins(self, db_session):
        """Una prova in gioco resta il criterio dominante."""
        c = _make_campionato(db_session, planned_gare_count=10)
        _make_gara(db_session, c, 1, GaraStatus.COMPLETED.value)
        _make_gara(db_session, c, 2, GaraStatus.PLAYING.value)
        db_session.commit()

        assert compute_campionato_status(c) == TournamentStatus.IN_PROGRESS.value
