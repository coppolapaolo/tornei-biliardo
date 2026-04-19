"""Regression tests for trio+forfeit handling in create_matches_from_pairings.

Bug (ECH #7, 2026-04-07): The `len(pairing.players) == 3` branch in
models/competition/round_creation.py ignored `forfeit_user_ids`. Players
already marked `is_forfeit=True` were placed into trio matches as if they
were going to play.

Semantics implemented (see spec-trio-forfeit-round-creation.md):
- 0/3 forfeits: normal pending TrioMatch (baseline, unchanged).
- 1/3 forfeits: convert to 2-player pending Match between non-forfeit
  players, no TrioMatch row.
- 2/3 forfeits: walkover — completed trio Match+TrioMatch, winner = survivor,
  no TrioRack rows.
- 3/3 forfeits: same as 2/3 but winner = pairing.players[0].
"""

from __future__ import annotations

from datetime import date
from typing import List

import pytest

from models.competition.models import Gara
from models.competition.round_creation import create_matches_from_pairings
from models.match.models import Match, TrioMatch
from models.matchmaking.strategies.base import Pairing


def _make_gara(db_session, **overrides) -> Gara:
    existing_count = db_session.query(Gara).count()
    defaults = {
        "name": "Test gara trio forfeit",
        "number": existing_count + 1,
        "date": date.today(),
        "distance": 5,
        "discipline": "palla_9",
        "matchmaking_strategy": "amalfi",
        "status": "playing",
        "is_race_to": True,
    }
    defaults.update(overrides)
    gara = Gara(**defaults)
    db_session.add(gara)
    db_session.flush()
    return gara


def _trio_pairing(players: List[int]) -> Pairing:
    assert len(players) == 3
    return Pairing(players=tuple(players), is_bye=False)


def _get_match_rows(db_session, gara_id: int, round_number: int) -> List[Match]:
    return (
        db_session.query(Match)
        .filter_by(gara_id=gara_id, round_number=round_number)
        .all()
    )


def _get_trio_row(db_session, match_id: int):
    return db_session.query(TrioMatch).filter_by(match_id=match_id).first()


@pytest.mark.unit
class TestTrioForfeitZero:
    """Baseline: no forfeits — existing trio creation path must be unchanged."""

    def test_zero_forfeits_creates_pending_trio(self, db_session, isolated_players):
        gara = _make_gara(db_session)
        p0, p1, p2 = [p.id for p in isolated_players[:3]]
        pairing = _trio_pairing([p0, p1, p2])

        create_matches_from_pairings(
            gara=gara,
            pairings=[pairing],
            round_number=1,
            round_distance=5,
            forfeit_user_ids=set(),
        )
        db_session.flush()

        matches = _get_match_rows(db_session, gara.id, 1)
        assert len(matches) == 1
        m = matches[0]
        assert m.is_trio is True
        assert m.is_bye is False
        assert m.status == "pending"
        assert m.winner_id is None
        assert m.player1_id == p0
        assert m.player2_id == p1

        trio = _get_trio_row(db_session, m.id)
        assert trio is not None
        assert trio.player1_id == p0
        assert trio.player2_id == p1
        assert trio.player3_id == p2
        assert trio.is_completed is False
        # initialize_matchup was called
        assert trio.current_player1_id is not None
        assert trio.current_player2_id is not None
        assert trio.waiting_player_id is not None


@pytest.mark.unit
class TestTrioForfeitOne:
    """1/3 forfeit: convert to 2-player pending Match between survivors."""

    def test_first_player_in_forfeit_produces_2p_match(
        self, db_session, isolated_players
    ):
        gara = _make_gara(db_session)
        p0, p1, p2 = [p.id for p in isolated_players[:3]]
        pairing = _trio_pairing([p0, p1, p2])

        create_matches_from_pairings(
            gara=gara,
            pairings=[pairing],
            round_number=1,
            round_distance=5,
            forfeit_user_ids={p0},
        )
        db_session.flush()

        matches = _get_match_rows(db_session, gara.id, 1)
        assert len(matches) == 1
        m = matches[0]
        assert m.is_trio is False
        assert m.is_bye is False
        assert m.status == "pending"
        assert m.winner_id is None
        # Survivors preserve their original order from pairing.players
        assert m.player1_id == p1
        assert m.player2_id == p2

        assert _get_trio_row(db_session, m.id) is None

    def test_middle_player_in_forfeit_preserves_order(
        self, db_session, isolated_players
    ):
        gara = _make_gara(db_session)
        p0, p1, p2 = [p.id for p in isolated_players[:3]]
        pairing = _trio_pairing([p0, p1, p2])

        create_matches_from_pairings(
            gara=gara,
            pairings=[pairing],
            round_number=1,
            round_distance=5,
            forfeit_user_ids={p1},
        )
        db_session.flush()

        matches = _get_match_rows(db_session, gara.id, 1)
        assert len(matches) == 1
        m = matches[0]
        assert m.is_trio is False
        assert m.player1_id == p0
        assert m.player2_id == p2
        assert _get_trio_row(db_session, m.id) is None

    def test_last_player_in_forfeit(self, db_session, isolated_players):
        gara = _make_gara(db_session)
        p0, p1, p2 = [p.id for p in isolated_players[:3]]
        pairing = _trio_pairing([p0, p1, p2])

        create_matches_from_pairings(
            gara=gara,
            pairings=[pairing],
            round_number=1,
            round_distance=5,
            forfeit_user_ids={p2},
        )
        db_session.flush()

        matches = _get_match_rows(db_session, gara.id, 1)
        assert len(matches) == 1
        m = matches[0]
        assert m.is_trio is False
        assert m.player1_id == p0
        assert m.player2_id == p1
        assert _get_trio_row(db_session, m.id) is None


@pytest.mark.unit
class TestTrioForfeitTwo:
    """2/3 forfeit: walkover for the survivor. Completed trio with no racks."""

    def test_two_forfeits_winner_is_survivor(self, db_session, isolated_players):
        gara = _make_gara(db_session, distance=5)
        p0, p1, p2 = [p.id for p in isolated_players[:3]]
        pairing = _trio_pairing([p0, p1, p2])

        create_matches_from_pairings(
            gara=gara,
            pairings=[pairing],
            round_number=1,
            round_distance=5,
            forfeit_user_ids={p0, p2},
        )
        db_session.flush()

        matches = _get_match_rows(db_session, gara.id, 1)
        assert len(matches) == 1
        m = matches[0]
        assert m.is_trio is True
        assert m.status == "completed"
        assert m.winner_id == p1
        assert m.player1_score == 5
        assert m.player2_score == 0

        trio = _get_trio_row(db_session, m.id)
        assert trio is not None
        assert trio.is_completed is True
        assert trio.winner_id == p1
        # No TrioRack rows created for walkover
        assert trio.total_racks_played == 0
        # current_* not initialized for walkover (no rack to play)
        assert trio.current_player1_id is None
        assert trio.current_player2_id is None

    def test_two_forfeits_other_pair(self, db_session, isolated_players):
        gara = _make_gara(db_session)
        p0, p1, p2 = [p.id for p in isolated_players[:3]]
        pairing = _trio_pairing([p0, p1, p2])

        create_matches_from_pairings(
            gara=gara,
            pairings=[pairing],
            round_number=1,
            round_distance=7,
            forfeit_user_ids={p1, p2},
        )
        db_session.flush()

        matches = _get_match_rows(db_session, gara.id, 1)
        m = matches[0]
        assert m.winner_id == p0
        assert m.player1_score == 7
        trio = _get_trio_row(db_session, m.id)
        assert trio.winner_id == p0


@pytest.mark.unit
class TestTrioForfeitAll:
    """3/3 forfeit: degenerate walkover. Winner deterministically = players[0]."""

    def test_all_forfeit_winner_is_first_player(self, db_session, isolated_players):
        gara = _make_gara(db_session)
        p0, p1, p2 = [p.id for p in isolated_players[:3]]
        pairing = _trio_pairing([p0, p1, p2])

        create_matches_from_pairings(
            gara=gara,
            pairings=[pairing],
            round_number=1,
            round_distance=5,
            forfeit_user_ids={p0, p1, p2},
        )
        db_session.flush()

        matches = _get_match_rows(db_session, gara.id, 1)
        assert len(matches) == 1
        m = matches[0]
        assert m.is_trio is True
        assert m.status == "completed"
        assert m.winner_id == p0
        assert m.player1_score == 5
        assert m.player2_score == 0

        trio = _get_trio_row(db_session, m.id)
        assert trio.is_completed is True
        assert trio.winner_id == p0
        assert trio.total_racks_played == 0
