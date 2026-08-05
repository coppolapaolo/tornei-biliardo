"""Handicap mode: catena di ereditarietà Campionato → Gara → Match.

Feature (2026-06): un match "con handicap" non aggiorna i rating (Elo/Fargo).
Il flag è configurabile a 3 livelli con override nullable (NULL = eredita):

    Match.has_handicap  (NULL → Gara)
    Gara.has_handicap   (NULL → Campionato)
    Campionato.has_handicap (radice, default False)

Le property `effective_has_handicap` materializzano il fallback. Pattern
analogo agli override per turno di ADR-027 (effective_is_race_to ecc.).
"""

from __future__ import annotations

import uuid
from datetime import date, time

import pytest

from models.base import db
from models.campionato.models import Campionato
from models.competition.models import Gara
from models.match.models import Match
from models.status_enum import GaraStatus, MatchStatus


def _campionato(suffix, **overrides):
    base = dict(name=f"Camp {suffix}", campionato_type="amalfi")
    base.update(overrides)
    return Campionato(**base)


def _gara(suffix, **overrides):
    base = dict(
        number=1,
        name=f"Gara {suffix}",
        date=date(2026, 1, 1),
        time=time(18, 0),
        discipline="palla_8",
        distance=5,
        rounds_count=1,
        current_round=1,
        min_participants=2,
        max_participants=10,
        matchmaking_strategy="amalfi",
        status=GaraStatus.PLAYING.value,
    )
    base.update(overrides)
    return Gara(**base)


def _match(gara_id, **overrides):
    base = dict(
        gara_id=gara_id,
        round_number=1,
        player1_id=None,
        player2_id=None,
        status=MatchStatus.PLAYING.value,
    )
    base.update(overrides)
    return Match(**base)


@pytest.mark.unit
def test_match_inherits_handicap_from_gara(db_session):
    suffix = uuid.uuid4().hex[:8]
    gara = _gara(suffix, has_handicap=True)
    db.session.add(gara)
    db.session.flush()
    match = _match(gara.id, has_handicap=None)
    db.session.add(match)
    db.session.flush()

    assert match.effective_has_handicap is True


@pytest.mark.unit
def test_gara_inherits_handicap_from_campionato(db_session):
    suffix = uuid.uuid4().hex[:8]
    camp = _campionato(suffix, has_handicap=True)
    db.session.add(camp)
    db.session.flush()
    gara = _gara(suffix, campionato_id=camp.id, has_handicap=None)
    db.session.add(gara)
    db.session.flush()
    match = _match(gara.id, has_handicap=None)
    db.session.add(match)
    db.session.flush()

    # Match NULL → Gara NULL → Campionato True
    assert gara.effective_has_handicap is True
    assert match.effective_has_handicap is True


@pytest.mark.unit
def test_match_override_wins_over_gara(db_session):
    suffix = uuid.uuid4().hex[:8]
    gara = _gara(suffix, has_handicap=True)
    db.session.add(gara)
    db.session.flush()
    # Override esplicito a livello match: NO handicap, anche se la gara sì.
    match = _match(gara.id, has_handicap=False)
    db.session.add(match)
    db.session.flush()

    assert match.effective_has_handicap is False


@pytest.mark.unit
def test_gara_override_wins_over_campionato(db_session):
    suffix = uuid.uuid4().hex[:8]
    camp = _campionato(suffix, has_handicap=True)
    db.session.add(camp)
    db.session.flush()
    gara = _gara(suffix, campionato_id=camp.id, has_handicap=False)
    db.session.add(gara)
    db.session.flush()

    assert gara.effective_has_handicap is False


@pytest.mark.unit
def test_default_no_handicap(db_session):
    suffix = uuid.uuid4().hex[:8]
    camp = _campionato(suffix)  # default False
    db.session.add(camp)
    db.session.flush()
    gara = _gara(suffix, campionato_id=camp.id)  # NULL → camp False
    db.session.add(gara)
    db.session.flush()
    match = _match(gara.id)  # NULL → gara → camp False

    assert camp.has_handicap is False
    assert gara.effective_has_handicap is False
    assert match.effective_has_handicap is False


@pytest.mark.unit
def test_standalone_match_and_gara_default_false(db_session):
    suffix = uuid.uuid4().hex[:8]
    gara = _gara(suffix, campionato_id=None)  # standalone, NULL handicap
    db.session.add(gara)
    db.session.flush()
    match = _match(gara.id)

    assert gara.effective_has_handicap is False
    assert match.effective_has_handicap is False
