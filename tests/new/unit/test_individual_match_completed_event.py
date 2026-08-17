"""Workstream A — emissione di IndividualMatchCompletedEvent (gated).

L'evento alimenta gamification (XP/streak/achievement) per i casual e deve essere
emesso SOLO alla validazione bilaterale (VALIDATED), MAI sui forfait o sul
complete_match unilaterale (COMPLETED). Vedi
`IndividualMatch._complete_match_after_confirmation`.
"""

from datetime import timedelta

import pytest

from models.individual_match.models import IndividualMatch
from models.events.base import EventBus
from models.events.match_events import IndividualMatchCompletedEvent
from models.status_enum import MatchStatus
from models.base import utc_now


@pytest.fixture
def captured_events():
    """Cattura gli IndividualMatchCompletedEvent senza toccare gli altri handler.

    Salva/ripristina EventBus._handlers (mai azzerarli, vedi tests/CLAUDE.md).
    """
    original = {k: list(v) for k, v in EventBus._handlers.items()}
    events: list[IndividualMatchCompletedEvent] = []

    EventBus.register_handler(
        IndividualMatchCompletedEvent, lambda e: events.append(e), priority=100
    )
    yield events
    EventBus._handlers = original


def _ready_match(db_session, p1, p2, s1, s2, distance=5):
    """Match IN_PROGRESS con punteggio che raggiunge la distance."""
    m = IndividualMatch(
        player1_id=p1,
        player2_id=p2,
        location="Hall",
        scheduled_at=utc_now() + timedelta(hours=1),
        status=MatchStatus.IN_PROGRESS,
        distance=distance,
        is_race_to=True,
        player1_score=s1,
        player2_score=s2,
    )
    db_session.add(m)
    db_session.commit()
    return m


def test_validated_emits_event(app, db_session, isolated_players, captured_events):
    """Conferma bilaterale → VALIDATED → evento emesso col vincitore corretto."""
    p1, p2 = isolated_players[:2]
    m = _ready_match(db_session, p1.id, p2.id, 5, 2)

    m.confirm_result(p1.id)
    m.confirm_result(p2.id)  # entrambi confermano → VALIDATED

    assert m.status == MatchStatus.CONFIRMED_BY_BOTH
    assert len(captured_events) == 1
    ev = captured_events[0]
    assert ev.match_id == m.id
    assert ev.winner_id == p1.id
    assert {ev.player1_id, ev.player2_id} == {p1.id, p2.id}


def test_forfeit_emits_no_event(app, db_session, isolated_players, captured_events):
    """Il forfait chiude COMPLETED senza conferma bilaterale → nessun evento."""
    p1, p2 = isolated_players[:2]
    m = _ready_match(db_session, p1.id, p2.id, 2, 1)

    m.forfeit_match(p1.id)

    assert m.status == MatchStatus.CLOSED_UNILATERALLY
    assert captured_events == []


def test_complete_match_emits_no_event(
    app, db_session, isolated_players, captured_events
):
    """complete_match unilaterale (legacy) → COMPLETED, nessun evento casual."""
    p1, p2 = isolated_players[:2]
    m = _ready_match(db_session, p1.id, p2.id, 5, 0)

    m.complete_match(p1.id)

    assert m.status == MatchStatus.CLOSED_UNILATERALLY
    assert captured_events == []


def test_tie_emits_event_without_winner(
    app, db_session, isolated_players, captured_events
):
    """Free format in pareggio: evento emesso ma winner_id=None."""
    p1, p2 = isolated_players[:2]
    m = IndividualMatch(
        player1_id=p1.id,
        player2_id=p2.id,
        location="Hall",
        scheduled_at=utc_now() + timedelta(hours=1),
        status=MatchStatus.IN_PROGRESS,
        distance=None,  # free format
        player1_score=3,
        player2_score=3,
    )
    db_session.add(m)
    db_session.commit()

    m.confirm_result(p1.id)
    m.confirm_result(p2.id)

    assert m.status == MatchStatus.CONFIRMED_BY_BOTH
    assert len(captured_events) == 1
    assert captured_events[0].winner_id is None
