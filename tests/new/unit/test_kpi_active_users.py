"""Regression: get_active_users_count non deve contare due volte gli utenti.

Bug (code review 2026-06-09, HIGH correttezza) —
`models/kpi/metrics_service.py:169`:

get_active_users_count ritornava `active_p1 + active_p2`, dove i due termini
sono COUNT(DISTINCT) per-colonna. Un utente che nel periodo compare sia come
player1 sia come player2 veniva contato in entrambi → DAU/WAU/MAU gonfiati e
stickiness (dau/mau) potenzialmente > 100%.

Il fix conta gli utenti DISTINTI sull'unione di player1/player2.
"""

from __future__ import annotations

import uuid

import pytest

from models.user.models import User
from models.user.role_enum import UserRole
from models.match.models import Match
from models.status_enum import MatchStatus
from models.kpi.metrics_service import MetricsService


def _user(db_session) -> User:
    uid = uuid.uuid4().hex[:8]
    u = User(
        username=f"dau_{uid}",
        email=f"dau_{uid}@test.local",
        role=UserRole.PLAYER.value,
    )
    u.set_password("x")
    db_session.add(u)
    db_session.flush()
    return u


def _completed_match(db_session, p1, p2) -> Match:
    m = Match(
        gara_id=None,
        round_number=1,
        player1_id=p1.id,
        player2_id=p2.id,
        status=MatchStatus.COMPLETED.value,
        winner_id=p1.id,
        player1_score=5,
        player2_score=0,
    )
    db_session.add(m)
    db_session.flush()
    return m


@pytest.mark.unit
def test_user_active_as_both_p1_and_p2_counted_once(db_session):
    """A gioca come player1 in un match e player2 in un altro: conta 1 volta."""
    a = _user(db_session)
    b = _user(db_session)
    c = _user(db_session)

    _completed_match(db_session, a, b)  # A=p1, B=p2
    _completed_match(db_session, c, a)  # C=p1, A=p2 → A compare in entrambe le colonne
    db_session.commit()

    # Utenti distinti attivi = {A, B, C} = 3.
    # Prima del fix: active_p1={A,C}=2 + active_p2={B,A}=2 = 4 (A doppio).
    assert MetricsService.get_active_users_count(30) == 3


@pytest.mark.unit
def test_no_overlap_counts_each_once(db_session):
    """Nessuna sovrapposizione p1/p2: il conteggio resta corretto (no regressioni)."""
    a = _user(db_session)
    b = _user(db_session)
    c = _user(db_session)
    d = _user(db_session)

    _completed_match(db_session, a, b)
    _completed_match(db_session, c, d)
    db_session.commit()

    assert MetricsService.get_active_users_count(30) == 4
