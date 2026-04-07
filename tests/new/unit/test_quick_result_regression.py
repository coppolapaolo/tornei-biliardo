"""Regression tests for Quick Result bugs found in manual testing (January 2026).

Bug 1: Quick Result 5-2 doesn't complete match (only 5-0 works)
Bug 2: Remove table from Trio shows wrong error / doesn't reset correctly
Bug 3: Trio Quick Result 5-0-0 fails silently (no error shown)
"""

import pytest

from models.match.models import Match, TrioMatch
from models.match.trio_scoring_service import TrioScoringService
from models.competition.models import Gara
from models.user.models import User
from models.status_enum import MatchStatus


def create_test_gara(db_session, name: str, **kwargs) -> Gara:
    """Helper to create a Gara with all required fields."""
    from datetime import date

    # Count existing garas to generate unique number
    existing_count = db_session.query(Gara).count()

    defaults = {
        "name": name,
        "number": existing_count + 1,
        "date": date.today(),
        "distance": 5,
        "discipline": "palla_9",
        "matchmaking_strategy": "random",
        "status": "playing",  # Set to playing so matches can be added
        "is_race_to": True,  # Race to N mode (first to N racks wins)
    }
    defaults.update(kwargs)

    gara = Gara(**defaults)
    db_session.add(gara)
    db_session.flush()
    return gara


class TestTrioQuickResultValidation:
    """Regression tests for Bug 3: Trio result validation.

    Bug: When entering an invalid trio result (e.g., 5-0-0), the system
    silently accepted it without showing an error to the user.

    Fix: set_result_direct now raises ValueError instead of returning False.
    """

    def test_trio_set_result_raises_error_on_invalid_total(self, db_session):
        """Regression: Invalid trio result (5-0-0) should raise ValueError.

        Bug: set_result_direct returned False silently, caller ignored return value.
        Fix: Now raises ValueError with descriptive message.
        """
        # GIVEN: A trio match with distance 5 (total should be 10 racks)
        user1 = User(username="trio_p1", email="p1@test.com", password_hash="x")
        user2 = User(username="trio_p2", email="p2@test.com", password_hash="x")
        user3 = User(username="trio_p3", email="p3@test.com", password_hash="x")
        db_session.add_all([user1, user2, user3])
        db_session.flush()

        gara = create_test_gara(
            db_session,
            "Test Trio Gara",
            odd_number_policy="trio",
        )

        match = Match(
            gara_id=gara.id,
            round_number=1,
            player1_id=user1.id,
            player2_id=user2.id,
            is_trio=True,
            status=MatchStatus.PLAYING.value,
        )
        db_session.add(match)
        db_session.flush()

        trio = TrioMatch(
            match_id=match.id,
            player1_id=user1.id,
            player2_id=user2.id,
            player3_id=user3.id,
        )
        db_session.add(trio)
        db_session.flush()

        # WHEN/THEN: Trying to set invalid result (5-0-0 total=5, should be 10)
        with pytest.raises(ValueError) as exc_info:
            TrioScoringService.set_result_direct(trio.id, 5, 0, 0)

        # THEN: Error message explains the issue
        assert "totale dei rack" in str(exc_info.value).lower() or "total" in str(
            exc_info.value
        ).lower()
        assert "6" in str(exc_info.value)  # Expected total for distance 5 trio

    def test_trio_set_result_succeeds_with_valid_total(self, db_session):
        """Verify valid trio results still work after the fix."""
        # GIVEN: A trio match with distance 5
        user1 = User(username="trio_v1", email="v1@test.com", password_hash="x")
        user2 = User(username="trio_v2", email="v2@test.com", password_hash="x")
        user3 = User(username="trio_v3", email="v3@test.com", password_hash="x")
        db_session.add_all([user1, user2, user3])
        db_session.flush()

        gara = create_test_gara(
            db_session,
            "Test Valid Trio",
            odd_number_policy="trio",
        )

        match = Match(
            gara_id=gara.id,
            round_number=1,
            player1_id=user1.id,
            player2_id=user2.id,
            is_trio=True,
            status=MatchStatus.PLAYING.value,
        )
        db_session.add(match)
        db_session.flush()

        trio = TrioMatch(
            match_id=match.id,
            player1_id=user1.id,
            player2_id=user2.id,
            player3_id=user3.id,
        )
        db_session.add(trio)
        db_session.flush()

        # WHEN: Setting valid result (3-2-1 = 6 total for distance 5 trio)
        # Distance 5: num_rounds=2, racks_per_round=3, total=6
        result = TrioScoringService.set_result_direct(trio.id, 3, 2, 1)

        # THEN: Result is applied successfully
        assert result is True
        # Refresh trio to see changes made by service
        db_session.refresh(trio)
        assert trio.is_completed is True
        assert trio.winner_id == user1.id  # Player with most racks


class TestTrioQuickResultScoreDistribution:
    """Regression: Trio quick result with asymmetric scores (e.g. 3-1-5)
    was distributed incorrectly by the greedy rack assignment algorithm.

    Bug: set_result_direct used a greedy "prefer P1, then P2, fallback P1"
    strategy that over-allocated racks to P1 when both players in a matchup
    had 0 remaining wins. E.g., entering 3-1-5 resulted in 4-1-4.

    Fix: Always assign each rack to the player with more remaining wins.
    """

    def test_asymmetric_scores_315_distance6(self, db_session):
        """Regression: 3-1-5 with distance 6 should produce exactly 3-1-5."""
        user1 = User(username="dist_p1", email="dist1@test.com", password_hash="x")
        user2 = User(username="dist_p2", email="dist2@test.com", password_hash="x")
        user3 = User(username="dist_p3", email="dist3@test.com", password_hash="x")
        db_session.add_all([user1, user2, user3])
        db_session.flush()

        gara = create_test_gara(
            db_session, "Test Trio Dist", distance=6, odd_number_policy="trio"
        )

        match = Match(
            gara_id=gara.id, round_number=1,
            player1_id=user1.id, player2_id=user2.id,
            is_trio=True, status=MatchStatus.PLAYING.value,
        )
        db_session.add(match)
        db_session.flush()

        trio = TrioMatch(
            match_id=match.id,
            player1_id=user1.id, player2_id=user2.id, player3_id=user3.id,
        )
        db_session.add(trio)
        db_session.flush()

        # WHEN: set 3-1-5
        TrioScoringService.set_result_direct(trio.id, 3, 1, 5)
        db_session.expire(trio)

        # THEN: racks should match exactly
        assert trio.player1_racks == 3
        assert trio.player2_racks == 1
        assert trio.player3_racks == 5

    def test_asymmetric_scores_510_distance5(self, db_session):
        """5-1-0 with distance 5 (6 total racks) should produce 5-1-0."""
        user1 = User(username="dist2_p1", email="dist2_1@test.com", password_hash="x")
        user2 = User(username="dist2_p2", email="dist2_2@test.com", password_hash="x")
        user3 = User(username="dist2_p3", email="dist2_3@test.com", password_hash="x")
        db_session.add_all([user1, user2, user3])
        db_session.flush()

        gara = create_test_gara(
            db_session, "Test Trio Dist2", distance=5, odd_number_policy="trio"
        )

        match = Match(
            gara_id=gara.id, round_number=1,
            player1_id=user1.id, player2_id=user2.id,
            is_trio=True, status=MatchStatus.PLAYING.value,
        )
        db_session.add(match)
        db_session.flush()

        trio = TrioMatch(
            match_id=match.id,
            player1_id=user1.id, player2_id=user2.id, player3_id=user3.id,
        )
        db_session.add(trio)
        db_session.flush()

        # Distance 5: 2 rounds, 6 total racks, max 4 per player
        # 5 exceeds max_per_player=4 — should raise ValueError
        with pytest.raises(ValueError, match="non può vincere più di 4"):
            TrioScoringService.set_result_direct(trio.id, 5, 1, 0)

    def test_equal_scores_333_distance6(self, db_session):
        """3-3-3 with distance 6 should work correctly."""
        user1 = User(username="eq_p1", email="eq1@test.com", password_hash="x")
        user2 = User(username="eq_p2", email="eq2@test.com", password_hash="x")
        user3 = User(username="eq_p3", email="eq3@test.com", password_hash="x")
        db_session.add_all([user1, user2, user3])
        db_session.flush()

        gara = create_test_gara(
            db_session, "Test Trio Equal", distance=6, odd_number_policy="trio"
        )

        match = Match(
            gara_id=gara.id, round_number=1,
            player1_id=user1.id, player2_id=user2.id,
            is_trio=True, status=MatchStatus.PLAYING.value,
        )
        db_session.add(match)
        db_session.flush()

        trio = TrioMatch(
            match_id=match.id,
            player1_id=user1.id, player2_id=user2.id, player3_id=user3.id,
        )
        db_session.add(trio)
        db_session.flush()

        TrioScoringService.set_result_direct(trio.id, 3, 3, 3)
        db_session.expire(trio)

        assert trio.player1_racks == 3
        assert trio.player2_racks == 3
        assert trio.player3_racks == 3

    def test_max_per_player_validation(self, db_session):
        """A player can't win more racks than they participate in."""
        user1 = User(username="max_p1", email="max1@test.com", password_hash="x")
        user2 = User(username="max_p2", email="max2@test.com", password_hash="x")
        user3 = User(username="max_p3", email="max3@test.com", password_hash="x")
        db_session.add_all([user1, user2, user3])
        db_session.flush()

        gara = create_test_gara(
            db_session, "Test Max", distance=6, odd_number_policy="trio"
        )

        match = Match(
            gara_id=gara.id, round_number=1,
            player1_id=user1.id, player2_id=user2.id,
            is_trio=True, status=MatchStatus.PLAYING.value,
        )
        db_session.add(match)
        db_session.flush()

        trio = TrioMatch(
            match_id=match.id,
            player1_id=user1.id, player2_id=user2.id, player3_id=user3.id,
        )
        db_session.add(trio)
        db_session.flush()

        # Distance 6: 3 rounds, max 6 per player. 7-1-1=9 but P1 > 6
        with pytest.raises(ValueError, match="non può vincere più di 6"):
            TrioScoringService.set_result_direct(trio.id, 7, 1, 1)


class TestTrioResetOnTableRemoval:
    """Regression tests for Bug 2: Trio reset when removing table.

    Bug: reset_match_complete didn't handle Trio matches, causing errors
    when trying to remove table assignment from a Trio match.

    Fix: reset_match_complete now delegates to TrioScoringService.reset() for Trio matches.
    """

    def test_reset_match_complete_handles_trio(self, db_session):
        """Regression: reset_match_complete should work for Trio matches.

        Bug: Function only handled regular Rack records, not TrioRack.
        Fix: Now delegates to TrioScoringService.reset() for Trio matches.
        """
        from models.match.models import TrioRack
        from models.match.services import RackService

        # GIVEN: A trio match with some racks
        user1 = User(username="reset_p1", email="reset1@test.com", password_hash="x")
        user2 = User(username="reset_p2", email="reset2@test.com", password_hash="x")
        user3 = User(username="reset_p3", email="reset3@test.com", password_hash="x")
        db_session.add_all([user1, user2, user3])
        db_session.flush()

        gara = create_test_gara(
            db_session,
            "Test Trio Reset",
            odd_number_policy="trio",
        )

        match = Match(
            gara_id=gara.id,
            round_number=1,
            player1_id=user1.id,
            player2_id=user2.id,
            is_trio=True,
            status=MatchStatus.PLAYING.value,
            table_assignment="Tavolo 1",
        )
        db_session.add(match)
        db_session.flush()

        trio = TrioMatch(
            match_id=match.id,
            player1_id=user1.id,
            player2_id=user2.id,
            player3_id=user3.id,
        )
        db_session.add(trio)
        db_session.flush()

        # Add some trio racks
        rack1 = TrioRack(
            trio_match_id=trio.id,
            rack_number=1,
            winner_id=user1.id,
            player1_id=user1.id,
            player2_id=user2.id,
            waiting_player_id=user3.id,
        )
        db_session.add(rack1)
        db_session.flush()

        # WHEN: Calling reset_match_complete on a Trio match
        RackService.reset_match_complete(match.id)
        db_session.flush()

        # THEN: Trio should be reset (delegated to TrioScoringService.reset())
        assert trio.is_completed is False
        assert trio.winner_id is None
        # Racks should be deleted
        racks_count = TrioRack.query.filter_by(trio_match_id=trio.id).count()
        assert racks_count == 0


class TestExactModeValidation:
    """Regression tests for Bug 1 root cause: Exact mode validation.

    Bug: In "esatto numero" mode (is_race_to=False), entering 5-2 didn't
    show an error - it just silently left the match incomplete.

    Root cause: _validate_score_limits didn't validate total racks in exact mode.
    Fix: Added validation that total racks must equal distance in exact mode.
    """

    def test_exact_mode_rejects_invalid_total(self, db_session):
        """Regression: Exact mode should reject scores where total != distance.

        Bug: 5-2 was accepted silently but match stayed incomplete.
        Fix: Now raises ValueError with clear message.
        """
        from models.match.scoring_service import ScoringService

        # GIVEN: A match in "exact number" mode (is_race_to=False)
        user1 = User(username="exact_e1", email="e1@test.com", password_hash="x")
        user2 = User(username="exact_e2", email="e2@test.com", password_hash="x")
        db_session.add_all([user1, user2])
        db_session.flush()

        gara = create_test_gara(
            db_session,
            "Test Exact Mode",
            is_race_to=False,  # Exact mode, not race-to
        )

        match = Match(
            gara_id=gara.id,
            round_number=1,
            player1_id=user1.id,
            player2_id=user2.id,
            status=MatchStatus.PLAYING.value,
        )
        db_session.add(match)
        db_session.flush()

        # WHEN/THEN: Trying to set 5-2 (total=7, should be 5) raises error
        with pytest.raises(ValueError) as exc_info:
            ScoringService.set_match_result_direct(match.id, 5, 2)

        # THEN: Error message explains the issue
        assert "esatto numero" in str(exc_info.value).lower()
        assert "7" in str(exc_info.value)  # Actual total
        assert "5" in str(exc_info.value)  # Expected total

    def test_exact_mode_accepts_valid_total(self, db_session):
        """Verify valid exact mode result (total=distance) works."""
        from models.match.scoring_service import ScoringService

        # GIVEN: A match in "exact number" mode
        user1 = User(username="exact_v1", email="ev1@test.com", password_hash="x")
        user2 = User(username="exact_v2", email="ev2@test.com", password_hash="x")
        db_session.add_all([user1, user2])
        db_session.flush()

        gara = create_test_gara(
            db_session,
            "Test Exact Valid",
            is_race_to=False,
        )

        match = Match(
            gara_id=gara.id,
            round_number=1,
            player1_id=user1.id,
            player2_id=user2.id,
            status=MatchStatus.PLAYING.value,
        )
        db_session.add(match)
        db_session.flush()

        # WHEN: Setting valid result 3-2 (total=5, equals distance)
        ScoringService.set_match_result_direct(match.id, 3, 2)
        db_session.flush()

        # Refresh from DB
        match = db_session.get(Match, match.id)

        # THEN: Match should be completed with player1 as winner
        assert match.status == MatchStatus.COMPLETED.value
        assert match.winner_id == user1.id
        assert match.player1_score == 3
        assert match.player2_score == 2


class TestQuickResultNonCleanWin:
    """Tests for race-to-N mode with non-clean wins (e.g., 5-2).

    These tests verify that race-to-N mode correctly completes
    matches when a player reaches the winning score.
    """

    def test_set_match_result_direct_completes_on_5_2(self, db_session):
        """Verify that 5-2 quick result properly completes the match.

        This test validates the backend logic is correct.
        If this passes but the bug persists in the UI, the issue is frontend.
        """
        from models.match.scoring_service import ScoringService

        # GIVEN: A race-to-5 match
        user1 = User(username="quick_p1", email="qp1@test.com", password_hash="x")
        user2 = User(username="quick_p2", email="qp2@test.com", password_hash="x")
        db_session.add_all([user1, user2])
        db_session.flush()

        gara = create_test_gara(db_session, "Test Quick Result")

        match = Match(
            gara_id=gara.id,
            round_number=1,
            player1_id=user1.id,
            player2_id=user2.id,
            status=MatchStatus.PLAYING.value,
        )
        db_session.add(match)
        db_session.flush()

        # WHEN: Setting result to 5-2 (player1 wins race to 5)
        ScoringService.set_match_result_direct(match.id, 5, 2)
        db_session.flush()

        # Refresh from DB
        match = db_session.get(Match, match.id)

        # THEN: Match should be completed with player1 as winner
        assert match.status == MatchStatus.COMPLETED.value, (
            f"Match should be COMPLETED but is {match.status}"
        )
        assert match.winner_id == user1.id
        assert match.player1_score == 5
        assert match.player2_score == 2

    def test_set_match_result_direct_completes_on_5_0(self, db_session):
        """Verify that 5-0 quick result works (baseline - known to work)."""
        from models.match.scoring_service import ScoringService

        # GIVEN: A race-to-5 match
        user1 = User(username="quick_z1", email="qz1@test.com", password_hash="x")
        user2 = User(username="quick_z2", email="qz2@test.com", password_hash="x")
        db_session.add_all([user1, user2])
        db_session.flush()

        gara = create_test_gara(db_session, "Test 5-0 Result")

        match = Match(
            gara_id=gara.id,
            round_number=1,
            player1_id=user1.id,
            player2_id=user2.id,
            status=MatchStatus.PLAYING.value,
        )
        db_session.add(match)
        db_session.flush()

        # WHEN: Setting result to 5-0
        ScoringService.set_match_result_direct(match.id, 5, 0)
        db_session.flush()

        # Refresh from DB
        match = db_session.get(Match, match.id)

        # THEN: Match should be completed
        assert match.status == MatchStatus.COMPLETED.value
        assert match.winner_id == user1.id

    def test_set_match_result_direct_completes_on_4_5(self, db_session):
        """Verify that player2 winning 5-4 works correctly."""
        from models.match.scoring_service import ScoringService

        # GIVEN: A race-to-5 match
        user1 = User(username="quick_r1", email="qr1@test.com", password_hash="x")
        user2 = User(username="quick_r2", email="qr2@test.com", password_hash="x")
        db_session.add_all([user1, user2])
        db_session.flush()

        gara = create_test_gara(db_session, "Test 4-5 Result")

        match = Match(
            gara_id=gara.id,
            round_number=1,
            player1_id=user1.id,
            player2_id=user2.id,
            status=MatchStatus.PLAYING.value,
        )
        db_session.add(match)
        db_session.flush()

        # WHEN: Setting result to 4-5 (player2 wins)
        ScoringService.set_match_result_direct(match.id, 4, 5)
        db_session.flush()

        # Refresh from DB
        match = db_session.get(Match, match.id)

        # THEN: Match should be completed with player2 as winner
        assert match.status == MatchStatus.COMPLETED.value
        assert match.winner_id == user2.id
        assert match.player1_score == 4
        assert match.player2_score == 5
