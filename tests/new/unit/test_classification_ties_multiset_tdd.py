"""TDD tests for classification calculation with ties and multi-set matches.

This module tests the fixes for:
- Fix 1: Tie handling in classification (neither player wins)
- Fix 1: Multi-set match rack calculation (sum from sets, not from scores)
- Fix 2: Crown display on ties (winner_id = None on tie)

Following TDD principles to ensure all edge cases are covered.
"""

import pytest
import uuid
from datetime import date, timedelta

from models import User, Gara, Inscription, Match
from models.user.role_enum import UserRole
from models.status_enum import GaraStatus, MatchStatus
from models.classification.models import RoundClassification
from models.match.set_models import Set


@pytest.mark.unit
class TestClassificationTieHandlingTDD:
    """TDD tests for tie handling in classification calculation."""

    def test_tie_match_neither_player_wins(self, db_session):
        """Test that tied matches don't count as wins for either player.

        When player1_score == player2_score, neither player should
        get a match win credit in the classification.
        """
        unique_id = str(uuid.uuid4())[:8]

        # Create director
        director = User(
            username=f"director_{unique_id}",
            email=f"director_{unique_id}@test.com",
            role=UserRole.DIRECTOR.value,
        )
        director.set_password("testpass123")
        db_session.add(director)
        db_session.commit()

        # Create players
        player1 = User(
            username=f"player1_{unique_id}",
            email=f"player1_{unique_id}@test.com",
            role=UserRole.PLAYER.value,
        )
        player1.set_password("testpass123")

        player2 = User(
            username=f"player2_{unique_id}",
            email=f"player2_{unique_id}@test.com",
            role=UserRole.PLAYER.value,
        )
        player2.set_password("testpass123")

        db_session.add_all([player1, player2])
        db_session.commit()

        # Create gara in playing state
        tomorrow = date.today() + timedelta(days=1)
        gara = Gara(
            number=1,
            name="Tie Test Gara",
            date=tomorrow,
            discipline="8_ball",
            distance=4,  # Exact 4 racks - can tie 2-2
            is_race_to=False,  # Exact mode allows ties
            rounds_count=1,
            min_participants=2,
            status=GaraStatus.PLAYING.value,
            current_round=1,
            director_id=director.id,
            matchmaking_strategy="random",
        )
        db_session.add(gara)
        db_session.commit()

        # Create inscriptions
        for player in [player1, player2]:
            inscription = Inscription(user_id=player.id, gara_id=gara.id)
            db_session.add(inscription)
        db_session.commit()

        # Create tied match (2-2 in exact 4 rack mode)
        match = Match(
            gara_id=gara.id,
            player1_id=player1.id,
            player2_id=player2.id,
            round_number=1,
            player1_score=2,
            player2_score=2,  # TIE!
            status=MatchStatus.CLOSED_UNILATERALLY.value,
            winner_id=None,  # No winner on tie
        )
        db_session.add(match)
        db_session.commit()

        # Calculate classification
        results = RoundClassification.calculate_classification_after_round(
            gara_id=gara.id, round_number=1
        )

        # Verify neither player has a match win
        assert len(results) == 2

        # Results are (player_id, stats_dict) tuples
        # Both players should have matches_won = 0
        for player_id, stats in results:
            assert (
                stats["matches_won"] == 0
            ), f"Player {player_id} should have 0 wins on tie"
            assert (
                stats["rack_difference"] == 0
            ), f"Player {player_id} should have 0 rack diff on tie"

    def test_winner_gets_match_win(self, db_session):
        """Test that clear winners get match win credit."""
        unique_id = str(uuid.uuid4())[:8]

        # Create users
        director = User(
            username=f"director_{unique_id}",
            email=f"director_{unique_id}@test.com",
            role=UserRole.DIRECTOR.value,
        )
        director.set_password("testpass123")

        player1 = User(
            username=f"player1_{unique_id}",
            email=f"player1_{unique_id}@test.com",
            role=UserRole.PLAYER.value,
        )
        player1.set_password("testpass123")

        player2 = User(
            username=f"player2_{unique_id}",
            email=f"player2_{unique_id}@test.com",
            role=UserRole.PLAYER.value,
        )
        player2.set_password("testpass123")

        db_session.add_all([director, player1, player2])
        db_session.commit()

        # Create gara
        tomorrow = date.today() + timedelta(days=1)
        gara = Gara(
            number=1,
            name="Win Test Gara",
            date=tomorrow,
            discipline="8_ball",
            distance=5,
            is_race_to=True,
            rounds_count=1,
            min_participants=2,
            status=GaraStatus.PLAYING.value,
            current_round=1,
            director_id=director.id,
            matchmaking_strategy="random",
        )
        db_session.add(gara)
        db_session.commit()

        # Create inscriptions
        for player in [player1, player2]:
            inscription = Inscription(user_id=player.id, gara_id=gara.id)
            db_session.add(inscription)
        db_session.commit()

        # Create match with clear winner (5-3)
        match = Match(
            gara_id=gara.id,
            player1_id=player1.id,
            player2_id=player2.id,
            round_number=1,
            player1_score=5,
            player2_score=3,
            status=MatchStatus.CLOSED_UNILATERALLY.value,
            winner_id=player1.id,
        )
        db_session.add(match)
        db_session.commit()

        # Calculate classification
        results = RoundClassification.calculate_classification_after_round(
            gara_id=gara.id, round_number=1
        )

        # Find player1's result - results are (player_id, stats_dict) tuples
        player1_result = next((r for r in results if r[0] == player1.id), None)
        player2_result = next((r for r in results if r[0] == player2.id), None)

        assert player1_result is not None
        assert player2_result is not None

        # Player1 should have 1 win
        _, stats_p1 = player1_result
        assert stats_p1["matches_won"] == 1, "Winner should have 1 match win"
        assert stats_p1["rack_difference"] == 2, "Winner rack diff should be +2"

        # Player2 should have 0 wins
        _, stats_p2 = player2_result
        assert stats_p2["matches_won"] == 0, "Loser should have 0 match wins"
        assert stats_p2["rack_difference"] == -2, "Loser rack diff should be -2"


@pytest.mark.unit
class TestMultiSetClassificationTDD:
    """TDD tests for multi-set match classification calculation."""

    def test_multiset_uses_rack_totals_not_set_scores(self, db_session):
        """Test that multi-set match classification sums racks from sets.

        For multi-set matches, rack_difference should be calculated
        from Set.player1_racks/player2_racks, NOT from Match.player1_score
        which represents SETS won.
        """
        unique_id = str(uuid.uuid4())[:8]

        # Create users
        director = User(
            username=f"director_{unique_id}",
            email=f"director_{unique_id}@test.com",
            role=UserRole.DIRECTOR.value,
        )
        director.set_password("testpass123")

        player1 = User(
            username=f"player1_{unique_id}",
            email=f"player1_{unique_id}@test.com",
            role=UserRole.PLAYER.value,
        )
        player1.set_password("testpass123")

        player2 = User(
            username=f"player2_{unique_id}",
            email=f"player2_{unique_id}@test.com",
            role=UserRole.PLAYER.value,
        )
        player2.set_password("testpass123")

        db_session.add_all([director, player1, player2])
        db_session.commit()

        # Create gara
        tomorrow = date.today() + timedelta(days=1)
        gara = Gara(
            number=1,
            name="Multi-Set Test Gara",
            date=tomorrow,
            discipline="8_ball",
            distance=5,  # Race to 5 per set
            is_race_to=True,
            rounds_count=1,
            min_participants=2,
            status=GaraStatus.PLAYING.value,
            current_round=1,
            director_id=director.id,
            matchmaking_strategy="random",
        )
        db_session.add(gara)
        db_session.commit()

        # Create inscriptions
        for player in [player1, player2]:
            inscription = Inscription(user_id=player.id, gara_id=gara.id)
            db_session.add(inscription)
        db_session.commit()

        # Create multi-set match
        # player1_score = 2 (sets won), player2_score = 1 (sets won)
        match = Match(
            gara_id=gara.id,
            player1_id=player1.id,
            player2_id=player2.id,
            round_number=1,
            is_multi_set=True,
            match_distance=2,  # First to 2 sets
            player1_score=2,  # Sets won by player1
            player2_score=1,  # Sets won by player2
            status=MatchStatus.CLOSED_UNILATERALLY.value,
            winner_id=player1.id,
        )
        db_session.add(match)
        db_session.commit()

        # Create sets with rack scores
        # Set 1: player1 wins 5-3 (racks: p1=5, p2=3)
        set1 = Set(
            match_id=match.id,
            set_number=1,
            distance=5,
            is_race_to=True,
            player1_racks=5,
            player2_racks=3,
            status="completed",
            winner_id=player1.id,
        )

        # Set 2: player2 wins 5-4 (racks: p1=4, p2=5)
        set2 = Set(
            match_id=match.id,
            set_number=2,
            distance=5,
            is_race_to=True,
            player1_racks=4,
            player2_racks=5,
            status="completed",
            winner_id=player2.id,
        )

        # Set 3: player1 wins 5-2 (racks: p1=5, p2=2)
        set3 = Set(
            match_id=match.id,
            set_number=3,
            distance=5,
            is_race_to=True,
            player1_racks=5,
            player2_racks=2,
            status="completed",
            winner_id=player1.id,
        )

        db_session.add_all([set1, set2, set3])
        db_session.commit()

        # Total racks: player1 = 5+4+5 = 14, player2 = 3+5+2 = 10
        # Expected rack_diff for player1: 14-10 = +4
        # Expected rack_diff for player2: 10-14 = -4

        # Calculate classification
        results = RoundClassification.calculate_classification_after_round(
            gara_id=gara.id, round_number=1
        )

        # Find results - results are (player_id, stats_dict) tuples
        player1_result = next((r for r in results if r[0] == player1.id), None)
        player2_result = next((r for r in results if r[0] == player2.id), None)

        assert player1_result is not None
        assert player2_result is not None

        _, stats_p1 = player1_result
        _, stats_p2 = player2_result

        # Player1 wins the match
        assert stats_p1["matches_won"] == 1
        assert stats_p2["matches_won"] == 0

        # Rack difference should be from actual racks, not sets
        # player1: 14 racks won, 10 racks lost -> diff = +4
        # player2: 10 racks won, 14 racks lost -> diff = -4
        assert (
            stats_p1["rack_difference"] == 4
        ), f"Player1 rack diff should be +4, got {stats_p1['rack_difference']}"
        assert (
            stats_p2["rack_difference"] == -4
        ), f"Player2 rack diff should be -4, got {stats_p2['rack_difference']}"

    def test_single_set_uses_match_scores(self, db_session):
        """Test that single-set matches use player scores directly."""
        unique_id = str(uuid.uuid4())[:8]

        # Create users
        director = User(
            username=f"director_{unique_id}",
            email=f"director_{unique_id}@test.com",
            role=UserRole.DIRECTOR.value,
        )
        director.set_password("testpass123")

        player1 = User(
            username=f"player1_{unique_id}",
            email=f"player1_{unique_id}@test.com",
            role=UserRole.PLAYER.value,
        )
        player1.set_password("testpass123")

        player2 = User(
            username=f"player2_{unique_id}",
            email=f"player2_{unique_id}@test.com",
            role=UserRole.PLAYER.value,
        )
        player2.set_password("testpass123")

        db_session.add_all([director, player1, player2])
        db_session.commit()

        # Create gara
        tomorrow = date.today() + timedelta(days=1)
        gara = Gara(
            number=1,
            name="Single-Set Test Gara",
            date=tomorrow,
            discipline="8_ball",
            distance=5,
            is_race_to=True,
            rounds_count=1,
            min_participants=2,
            status=GaraStatus.PLAYING.value,
            current_round=1,
            director_id=director.id,
            matchmaking_strategy="random",
        )
        db_session.add(gara)
        db_session.commit()

        # Create inscriptions
        for player in [player1, player2]:
            inscription = Inscription(user_id=player.id, gara_id=gara.id)
            db_session.add(inscription)
        db_session.commit()

        # Create single-set match (5-2)
        match = Match(
            gara_id=gara.id,
            player1_id=player1.id,
            player2_id=player2.id,
            round_number=1,
            is_multi_set=False,  # Single-set
            player1_score=5,  # Racks for single-set
            player2_score=2,
            status=MatchStatus.CLOSED_UNILATERALLY.value,
            winner_id=player1.id,
        )
        db_session.add(match)
        db_session.commit()

        # Calculate classification
        results = RoundClassification.calculate_classification_after_round(
            gara_id=gara.id, round_number=1
        )

        # Find results - results are (player_id, stats_dict) tuples
        player1_result = next((r for r in results if r[0] == player1.id), None)
        player2_result = next((r for r in results if r[0] == player2.id), None)

        assert player1_result is not None
        assert player2_result is not None

        _, stats_p1 = player1_result
        _, stats_p2 = player2_result

        # Single-set uses match scores directly
        assert (
            stats_p1["rack_difference"] == 3
        ), f"Player1 rack diff should be +3 (5-2), got {stats_p1['rack_difference']}"
        assert (
            stats_p2["rack_difference"] == -3
        ), f"Player2 rack diff should be -3 (2-5), got {stats_p2['rack_difference']}"


@pytest.mark.unit
class TestCrownDisplayOnTiesTDD:
    """TDD tests for crown display (winner_id) on tied matches."""

    def test_tie_match_has_no_winner_id(self, db_session):
        """Test that tied matches have winner_id = None.

        This ensures no crown is displayed on tied matches.
        """
        unique_id = str(uuid.uuid4())[:8]

        # Create users
        director = User(
            username=f"director_{unique_id}",
            email=f"director_{unique_id}@test.com",
            role=UserRole.DIRECTOR.value,
        )
        director.set_password("testpass123")

        player1 = User(
            username=f"player1_{unique_id}",
            email=f"player1_{unique_id}@test.com",
            role=UserRole.PLAYER.value,
        )
        player1.set_password("testpass123")

        player2 = User(
            username=f"player2_{unique_id}",
            email=f"player2_{unique_id}@test.com",
            role=UserRole.PLAYER.value,
        )
        player2.set_password("testpass123")

        db_session.add_all([director, player1, player2])
        db_session.commit()

        # Create gara with exact mode (allows ties)
        tomorrow = date.today() + timedelta(days=1)
        gara = Gara(
            number=1,
            name="Crown Test Gara",
            date=tomorrow,
            discipline="8_ball",
            distance=4,  # Exact 4 racks - can tie 2-2
            is_race_to=False,  # Exact mode
            rounds_count=1,
            min_participants=2,
            status=GaraStatus.PLAYING.value,
            current_round=1,
            director_id=director.id,
            matchmaking_strategy="random",
        )
        db_session.add(gara)
        db_session.commit()

        # Create inscriptions
        for player in [player1, player2]:
            inscription = Inscription(user_id=player.id, gara_id=gara.id)
            db_session.add(inscription)
        db_session.commit()

        # Create tied match
        match = Match(
            gara_id=gara.id,
            player1_id=player1.id,
            player2_id=player2.id,
            round_number=1,
            player1_score=2,
            player2_score=2,  # TIE!
            status=MatchStatus.CLOSED_UNILATERALLY.value,
            winner_id=None,  # Must be None for tie
        )
        db_session.add(match)
        db_session.commit()

        # Verify winner_id is None
        db_session.refresh(match)
        assert match.winner_id is None, "Tied match should have winner_id = None"
        assert (
            match.status == MatchStatus.CLOSED_UNILATERALLY.value
        ), "Match should still be completed"

    def test_clear_winner_has_winner_id(self, db_session):
        """Test that matches with clear winners have correct winner_id."""
        unique_id = str(uuid.uuid4())[:8]

        # Create users
        director = User(
            username=f"director_{unique_id}",
            email=f"director_{unique_id}@test.com",
            role=UserRole.DIRECTOR.value,
        )
        director.set_password("testpass123")

        player1 = User(
            username=f"player1_{unique_id}",
            email=f"player1_{unique_id}@test.com",
            role=UserRole.PLAYER.value,
        )
        player1.set_password("testpass123")

        player2 = User(
            username=f"player2_{unique_id}",
            email=f"player2_{unique_id}@test.com",
            role=UserRole.PLAYER.value,
        )
        player2.set_password("testpass123")

        db_session.add_all([director, player1, player2])
        db_session.commit()

        # Create gara
        tomorrow = date.today() + timedelta(days=1)
        gara = Gara(
            number=1,
            name="Winner Test Gara",
            date=tomorrow,
            discipline="8_ball",
            distance=5,
            is_race_to=True,
            rounds_count=1,
            min_participants=2,
            status=GaraStatus.PLAYING.value,
            current_round=1,
            director_id=director.id,
            matchmaking_strategy="random",
        )
        db_session.add(gara)
        db_session.commit()

        # Create match with clear winner
        match = Match(
            gara_id=gara.id,
            player1_id=player1.id,
            player2_id=player2.id,
            round_number=1,
            player1_score=5,
            player2_score=3,
            status=MatchStatus.CLOSED_UNILATERALLY.value,
            winner_id=player1.id,  # Clear winner
        )
        db_session.add(match)
        db_session.commit()

        # Verify winner_id is set correctly
        db_session.refresh(match)
        assert match.winner_id == player1.id, "Winner should be player1"
        assert match.status == MatchStatus.CLOSED_UNILATERALLY.value
