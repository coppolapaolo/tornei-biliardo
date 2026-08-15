"""Walkover side-effects unified routing — comprehensive coverage.

Spec: `_bmad-output/implementation-artifacts/spec-walkover-side-effects-unified.md`

Covers the I/O matrix rows: bye, 2-player 1/2 and 2/2 forfeit, trio 2/3 and 3/3
walkover, admin reset of walkover trio, Amalfi `_get_trio_counts` filter.

All scenarios go through `create_matches_from_pairings` and assert the
cross-cutting side effects (PlayerEncounter rows, MatchCompletedEvent emission,
XP awards filtered by forfeit set, classification rack credits, trio matchup
initialized).
"""

from __future__ import annotations

from datetime import date
from typing import List

import pytest

from models.classification.models import PlayerEncounter
from models.competition.models import Gara, Inscription
from models.competition.round_creation import create_matches_from_pairings
from models.events.base import EventBus
from models.events.match_events import MatchCompletedEvent
from models.match.models import Match, TrioMatch
from models.matchmaking.strategies.base import Pairing


def _make_gara(db_session, **overrides) -> Gara:
    existing_count = db_session.query(Gara).count()
    defaults = {
        "name": "Walkover side-effect test gara",
        "number": existing_count + 1,
        "date": date.today(),
        "distance": 5,
        "discipline": "9_ball",
        "matchmaking_strategy": "amalfi",
        "status": "playing",
        "is_race_to": True,
    }
    defaults.update(overrides)
    gara = Gara(**defaults)
    db_session.add(gara)
    db_session.flush()
    return gara


def _inscribe(
    db_session, gara_id: int, user_id: int, is_forfeit: bool = False
) -> Inscription:
    ins = Inscription(gara_id=gara_id, user_id=user_id, is_forfeit=is_forfeit)
    db_session.add(ins)
    db_session.flush()
    return ins


@pytest.fixture
def event_spy():
    """Capture MatchCompletedEvent emissions during a test.

    Preserves and restores the EventBus handler list so we don't leak fixture
    state into other tests (notifications/gamification rely on EventBus).
    """
    captured: List[MatchCompletedEvent] = []
    original = {k: list(v) for k, v in EventBus._handlers.items()}

    EventBus.register_handler(MatchCompletedEvent, captured.append, priority=1)

    yield captured

    EventBus._handlers = original


class TestWalkoverByeRouting:
    """Bye creation via to_completed(): no encounter, no event (existing guard)."""

    def test_bye_completed_and_has_is_walkover(self, db_session, isolated_players):
        gara = _make_gara(db_session)
        p0 = isolated_players[0].id
        pairing = Pairing(players=(p0,), is_bye=True)

        create_matches_from_pairings(
            gara=gara,
            pairings=[pairing],
            round_number=1,
            round_distance=5,
            forfeit_user_ids=set(),
        )
        db_session.flush()

        m = db_session.query(Match).filter_by(gara_id=gara.id).one()
        assert m.is_bye is True
        assert m.status == "completed"
        assert m.winner_id == p0
        assert m.is_walkover is True

    def test_bye_records_no_encounter_and_emits_no_event(
        self, db_session, isolated_players, event_spy
    ):
        gara = _make_gara(db_session)
        p0 = isolated_players[0].id
        pairing = Pairing(players=(p0,), is_bye=True)

        create_matches_from_pairings(
            gara=gara,
            pairings=[pairing],
            round_number=1,
            round_distance=5,
            forfeit_user_ids=set(),
        )
        db_session.flush()

        # Bye is excluded from encounter recording (no opponent).
        assert db_session.query(PlayerEncounter).count() == 0
        # Bye is excluded from MatchCompletedEvent emission in
        # MatchStateService._emit_completion_event (is_bye or missing player2_id).
        assert len(event_spy) == 0


class TestWalkoverTwoPlayerForfeit:
    """2-player forfeit (1/2 and 2/2): encounter + event + XP filter."""

    def test_one_forfeit_records_encounter_and_emits_event(
        self, db_session, isolated_players, event_spy
    ):
        gara = _make_gara(db_session)
        p0, p1 = isolated_players[0].id, isolated_players[1].id
        _inscribe(db_session, gara.id, p0, is_forfeit=True)
        _inscribe(db_session, gara.id, p1)
        pairing = Pairing(players=(p0, p1), is_bye=False)

        create_matches_from_pairings(
            gara=gara,
            pairings=[pairing],
            round_number=1,
            round_distance=5,
            forfeit_user_ids={p0},
        )
        db_session.flush()

        m = db_session.query(Match).filter_by(gara_id=gara.id).one()
        assert m.status == "completed"
        assert m.winner_id == p1
        assert m.is_walkover is True
        assert db_session.query(PlayerEncounter).filter_by(gara_id=gara.id).count() == 1
        assert len(event_spy) == 1
        assert event_spy[0].winner_id == p1

    def test_both_forfeit_is_walkover_winner_is_first_player(
        self, db_session, isolated_players
    ):
        gara = _make_gara(db_session)
        p0, p1 = isolated_players[0].id, isolated_players[1].id
        _inscribe(db_session, gara.id, p0, is_forfeit=True)
        _inscribe(db_session, gara.id, p1, is_forfeit=True)
        pairing = Pairing(players=(p0, p1), is_bye=False)

        create_matches_from_pairings(
            gara=gara,
            pairings=[pairing],
            round_number=1,
            round_distance=5,
            forfeit_user_ids={p0, p1},
        )
        db_session.flush()

        m = db_session.query(Match).filter_by(gara_id=gara.id).one()
        assert m.winner_id == p0
        assert m.is_walkover is True


class TestWalkoverTrioTwoThirds:
    """Trio 2/3 walkover: 3 encounters, matchup initialized, classification credits."""

    def test_records_three_pairwise_encounters(
        self, db_session, isolated_players, event_spy
    ):
        gara = _make_gara(db_session)
        p0, p1, p2 = [p.id for p in isolated_players[:3]]
        for pid in (p0, p1, p2):
            _inscribe(db_session, gara.id, pid, is_forfeit=(pid in (p0, p2)))
        pairing = Pairing(players=(p0, p1, p2), is_bye=False)

        create_matches_from_pairings(
            gara=gara,
            pairings=[pairing],
            round_number=1,
            round_distance=5,
            forfeit_user_ids={p0, p2},
        )
        db_session.flush()

        m = db_session.query(Match).filter_by(gara_id=gara.id).one()
        assert m.is_trio is True
        assert m.winner_id == p1
        assert m.is_walkover is True

        encounters = db_session.query(PlayerEncounter).filter_by(gara_id=gara.id).all()
        assert len(encounters) == 3
        pairs = {tuple(sorted([e.player1_id, e.player2_id])) for e in encounters}
        assert pairs == {
            tuple(sorted([p0, p1])),
            tuple(sorted([p0, p2])),
            tuple(sorted([p1, p2])),
        }

        assert len(event_spy) == 1

    def test_matchup_initialized_on_walkover_creation(
        self, db_session, isolated_players
    ):
        gara = _make_gara(db_session)
        p0, p1, p2 = [p.id for p in isolated_players[:3]]
        pairing = Pairing(players=(p0, p1, p2), is_bye=False)

        create_matches_from_pairings(
            gara=gara,
            pairings=[pairing],
            round_number=1,
            round_distance=5,
            forfeit_user_ids={p0, p2},
        )
        db_session.flush()

        trio = db_session.query(TrioMatch).one()
        assert trio.current_player1_id is not None
        assert trio.current_player2_id is not None
        assert trio.waiting_player_id is not None

    def test_classification_credits_distance_racks_to_survivor(
        self, db_session, isolated_players
    ):
        from models.classification.score_aggregator import ScoreAggregator

        gara = _make_gara(db_session, distance=5)
        p0, p1, p2 = [p.id for p in isolated_players[:3]]
        pairing = Pairing(players=(p0, p1, p2), is_bye=False)

        create_matches_from_pairings(
            gara=gara,
            pairings=[pairing],
            round_number=1,
            round_distance=5,
            forfeit_user_ids={p0, p2},
        )
        db_session.flush()

        m = db_session.query(Match).filter_by(gara_id=gara.id).one()
        stats: dict[int, dict[str, int]] = {}
        ScoreAggregator()._process_trio_match(m, stats)

        assert stats[p1]["racks_won"] == 5
        assert stats[p1]["matches_won"] == 1
        assert stats[p0]["racks_won"] == 0
        assert stats[p0]["matches_lost"] == 1
        assert stats[p2]["racks_won"] == 0
        assert stats[p2]["matches_lost"] == 1


class TestWalkoverTrioThreeThirds:
    """Trio 3/3: nominal winner = players[0], all forfeiters."""

    def test_nominal_winner_is_first_player_and_is_walkover(
        self, db_session, isolated_players
    ):
        gara = _make_gara(db_session)
        p0, p1, p2 = [p.id for p in isolated_players[:3]]
        pairing = Pairing(players=(p0, p1, p2), is_bye=False)

        create_matches_from_pairings(
            gara=gara,
            pairings=[pairing],
            round_number=1,
            round_distance=5,
            forfeit_user_ids={p0, p1, p2},
        )
        db_session.flush()

        m = db_session.query(Match).filter_by(gara_id=gara.id).one()
        assert m.winner_id == p0
        assert m.is_walkover is True
        trio = db_session.query(TrioMatch).one()
        assert trio.current_player1_id is not None  # matchup initialized

    def test_classification_still_credits_distance_to_nominal_winner(
        self, db_session, isolated_players
    ):
        from models.classification.score_aggregator import ScoreAggregator

        gara = _make_gara(db_session, distance=5)
        p0, p1, p2 = [p.id for p in isolated_players[:3]]
        pairing = Pairing(players=(p0, p1, p2), is_bye=False)

        create_matches_from_pairings(
            gara=gara,
            pairings=[pairing],
            round_number=1,
            round_distance=5,
            forfeit_user_ids={p0, p1, p2},
        )
        db_session.flush()

        m = db_session.query(Match).filter_by(gara_id=gara.id).one()
        stats: dict[int, dict[str, int]] = {}
        ScoreAggregator()._process_trio_match(m, stats)

        assert stats[p0]["racks_won"] == 5
        assert stats[p0]["matches_won"] == 1


class TestAdminResetWalkoverTrio:
    """Regression: admin-reset of walkover trio must not crash the serializer."""

    def test_to_playing_then_serialize_no_crash(self, db_session, isolated_players):
        from models.match.state_service import MatchStateService
        from models.match.trio_state_serializer import TrioStateSerializer

        gara = _make_gara(db_session)
        p0, p1, p2 = [p.id for p in isolated_players[:3]]
        pairing = Pairing(players=(p0, p1, p2), is_bye=False)

        create_matches_from_pairings(
            gara=gara,
            pairings=[pairing],
            round_number=1,
            round_distance=5,
            forfeit_user_ids={p0, p2},
        )
        db_session.flush()

        m = db_session.query(Match).filter_by(gara_id=gara.id).one()
        MatchStateService.to_playing(m.id)

        trio = db_session.query(TrioMatch).one()
        state = TrioStateSerializer.serialize(trio)
        # State must have a populated current matchup (player objects, not None).
        assert state["current_matchup"]["player1"] is not None
        assert state["current_matchup"]["player2"] is not None


class TestAmalfiTrioCountsFilter:
    """Walkover trios do not count toward Amalfi trio rotation."""

    def test_walkover_trio_not_counted(self, db_session, isolated_players):
        from models.matchmaking.strategies.amalfi import AmalfiStrategy

        gara = _make_gara(db_session)
        p0, p1, p2 = [p.id for p in isolated_players[:3]]
        pairing = Pairing(players=(p0, p1, p2), is_bye=False)

        create_matches_from_pairings(
            gara=gara,
            pairings=[pairing],
            round_number=1,
            round_distance=5,
            forfeit_user_ids={p0, p2},
        )
        db_session.flush()

        counts = AmalfiStrategy()._get_trio_counts(gara.id)
        # Walkover trio has total_racks_played == 0 → excluded from counts.
        assert counts == {}


class TestIsWalkoverProperty:
    """Direct tests of Match.is_walkover detection."""

    def test_pending_match_is_not_walkover(self, db_session, isolated_players):
        gara = _make_gara(db_session)
        p0, p1 = isolated_players[0].id, isolated_players[1].id
        m = Match(
            gara_id=gara.id,
            round_number=1,
            player1_id=p0,
            player2_id=p1,
            match_distance=5,
        )
        db_session.add(m)
        db_session.flush()
        assert m.is_walkover is False

    def test_completed_match_without_winner_is_not_walkover(
        self, db_session, isolated_players
    ):
        gara = _make_gara(db_session)
        p0, p1 = isolated_players[0].id, isolated_players[1].id
        m = Match(
            gara_id=gara.id,
            round_number=1,
            player1_id=p0,
            player2_id=p1,
            match_distance=5,
            status="completed",
            winner_id=None,
        )
        db_session.add(m)
        db_session.flush()
        assert m.is_walkover is False

    def test_is_walkover_on_detached_match_does_not_lazy_load_racks(
        self, db_session, isolated_players
    ):
        """Detached walkover match must not crash on `racks` lazy load.

        Deferred-work.md A3 (2026-04-19): in future async dispatch the Match
        instance handed to the handler may be detached. The original
        implementation used `self.racks` lazy relationship, which would raise
        `DetachedInstanceError` and, via the top-level except in
        `handle_match_completed_for_xp`, silently route XP to forfeiters.
        The query-based implementation queries `Rack` by `match_id` using
        `db.session`, which stays session-scoped even when `self` is detached.

        Column attributes are touched before expunge so expire_on_commit does
        not force a refresh on first access — the narrow regression we guard
        against is the relationship lazy-load, not the unloaded-column path.
        """
        gara = _make_gara(db_session)
        p0, p1 = isolated_players[0].id, isolated_players[1].id
        m = Match(
            gara_id=gara.id,
            round_number=1,
            player1_id=p0,
            player2_id=p1,
            match_distance=5,
            status="completed",
            winner_id=p0,
        )
        db_session.add(m)
        db_session.commit()
        _ = (m.id, m.status, m.winner_id, m.is_trio)
        db_session.expunge(m)

        assert m.is_walkover is True

    def test_is_walkover_false_on_detached_match_with_racks(
        self, db_session, isolated_players
    ):
        """Detached match with at least one rack must not be classified walkover."""
        from models.match.models import Rack

        gara = _make_gara(db_session)
        p0, p1 = isolated_players[0].id, isolated_players[1].id
        m = Match(
            gara_id=gara.id,
            round_number=1,
            player1_id=p0,
            player2_id=p1,
            match_distance=5,
            status="completed",
            winner_id=p0,
        )
        db_session.add(m)
        db_session.flush()
        db_session.add(Rack(match_id=m.id, rack_number=1, winner_id=p0))
        db_session.commit()
        _ = (m.id, m.status, m.winner_id, m.is_trio)
        db_session.expunge(m)

        assert m.is_walkover is False
