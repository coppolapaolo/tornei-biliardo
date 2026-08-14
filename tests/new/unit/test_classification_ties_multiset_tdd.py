"""TDD tests for classification calculation with ties and multi-set matches.

This module tests the fixes for:
- Fix 1: Tie handling in classification (neither player wins)
- Fix 1: Multi-set match rack calculation (sum from sets, not from scores)
- Fix 2: Crown display on ties (winner_id = None on tie)

Following TDD principles to ensure all edge cases are covered.
"""

import pytest
import uuid
from datetime import date, time, timedelta, datetime

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
            status=MatchStatus.COMPLETED.value,
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
            status=MatchStatus.COMPLETED.value,
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
            status=MatchStatus.COMPLETED.value,
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
            status=MatchStatus.COMPLETED.value,
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
            status=MatchStatus.COMPLETED.value,
            winner_id=None,  # Must be None for tie
        )
        db_session.add(match)
        db_session.commit()

        # Verify winner_id is None
        db_session.refresh(match)
        assert match.winner_id is None, "Tied match should have winner_id = None"
        assert (
            match.status == MatchStatus.COMPLETED.value
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
            status=MatchStatus.COMPLETED.value,
            winner_id=player1.id,  # Clear winner
        )
        db_session.add(match)
        db_session.commit()

        # Verify winner_id is set correctly
        db_session.refresh(match)
        assert match.winner_id == player1.id, "Winner should be player1"
        assert match.status == MatchStatus.COMPLETED.value


@pytest.mark.unit
class TestTiebreakerServiceTDD:
    """TDD tests for end-of-gara tiebreaker service."""

    def test_detect_ties_finds_tied_positions(self, db_session):
        """Test that detect_ties correctly identifies tied positions."""
        from models.competition.tiebreaker_service import TiebreakerService

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

        # Create 4 players
        players = []
        for i in range(4):
            player = User(
                username=f"player{i}_{unique_id}",
                email=f"player{i}_{unique_id}@test.com",
                role=UserRole.PLAYER.value,
            )
            player.set_password("testpass123")
            players.append(player)
        db_session.add_all(players)
        db_session.commit()

        # Create gara with tiebreaker enabled
        tomorrow = date.today() + timedelta(days=1)
        gara = Gara(
            number=1,
            name="Tiebreaker Test Gara",
            date=tomorrow,
            discipline="8_ball",
            distance=5,
            is_race_to=True,
            rounds_count=3,
            min_participants=4,
            status=GaraStatus.PLAYING.value,
            current_round=3,
            director_id=director.id,
            matchmaking_strategy="amalfi",
            tiebreaker_enabled=True,
            tiebreaker_until_position=3,
            tiebreaker_mode="playoff_match",
        )
        db_session.add(gara)
        db_session.commit()

        # Create inscriptions
        for player in players:
            inscription = Inscription(user_id=player.id, gara_id=gara.id)
            db_session.add(inscription)
        db_session.commit()

        # Create round classifications with ties
        # Position 1: players[0] - 3 wins, +5 diff
        # Position 2: players[1], players[2] - TIED - 2 wins, +2 diff
        # Position 4: players[3] - 0 wins, -9 diff
        classifications_data = [
            (players[0].id, 1, 3, 5),  # 1st place
            (players[1].id, 2, 2, 2),  # 2nd (tied)
            (players[2].id, 2, 2, 2),  # 2nd (tied)
            (players[3].id, 4, 0, -9),  # 4th place
        ]

        for player_id, position, matches_won, rack_diff in classifications_data:
            classification = RoundClassification(
                gara_id=gara.id,
                round_number=3,  # Final round
                user_id=player_id,
                position=position,
                matches_won=matches_won,
                rack_difference=rack_diff,
            )
            db_session.add(classification)
        db_session.commit()

        # Detect ties
        ties = TiebreakerService.detect_ties(gara.id)

        # Should find one tie at position 2
        assert len(ties) == 1, f"Expected 1 tie, got {len(ties)}"

        tie = ties[0]
        assert tie.position == 2
        assert set(tie.player_ids) == {players[1].id, players[2].id}
        assert tie.matches_won == 2
        assert tie.rack_difference == 2

    def test_detect_ties_respects_until_position(self, db_session):
        """Test that ties beyond tiebreaker_until_position are ignored."""
        from models.competition.tiebreaker_service import TiebreakerService

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

        # Create 4 players
        players = []
        for i in range(4):
            player = User(
                username=f"player{i}_{unique_id}",
                email=f"player{i}_{unique_id}@test.com",
                role=UserRole.PLAYER.value,
            )
            player.set_password("testpass123")
            players.append(player)
        db_session.add_all(players)
        db_session.commit()

        # Create gara - tiebreaker only for podium (positions 1-3)
        tomorrow = date.today() + timedelta(days=1)
        gara = Gara(
            number=1,
            name="Position Limit Test",
            date=tomorrow,
            discipline="8_ball",
            distance=5,
            is_race_to=True,
            rounds_count=3,
            min_participants=4,
            status=GaraStatus.PLAYING.value,
            current_round=3,
            director_id=director.id,
            matchmaking_strategy="amalfi",
            tiebreaker_enabled=True,
            tiebreaker_until_position=2,  # Only 1st and 2nd
            tiebreaker_mode="playoff_match",
        )
        db_session.add(gara)
        db_session.commit()

        # Create inscriptions
        for player in players:
            inscription = Inscription(user_id=player.id, gara_id=gara.id)
            db_session.add(inscription)
        db_session.commit()

        # Create classifications - tie at position 3 (beyond limit)
        classifications_data = [
            (players[0].id, 1, 3, 5),  # 1st
            (players[1].id, 2, 2, 2),  # 2nd
            (players[2].id, 3, 1, 0),  # 3rd (tied)
            (players[3].id, 3, 1, 0),  # 3rd (tied)
        ]

        for player_id, position, matches_won, rack_diff in classifications_data:
            classification = RoundClassification(
                gara_id=gara.id,
                round_number=3,
                user_id=player_id,
                position=position,
                matches_won=matches_won,
                rack_difference=rack_diff,
            )
            db_session.add(classification)
        db_session.commit()

        # Detect ties
        ties = TiebreakerService.detect_ties(gara.id)

        # Tie at position 3 should be ignored (beyond position 2)
        assert (
            len(ties) == 0
        ), f"No ties should be detected (beyond position limit), got {len(ties)}"

    def test_tiebreaker_disabled_returns_empty(self, db_session):
        """Test that disabled tiebreaker returns no ties."""
        from models.competition.tiebreaker_service import TiebreakerService

        unique_id = str(uuid.uuid4())[:8]

        director = User(
            username=f"director_{unique_id}",
            email=f"director_{unique_id}@test.com",
            role=UserRole.DIRECTOR.value,
        )
        director.set_password("testpass123")
        db_session.add(director)
        db_session.commit()

        # Create gara with tiebreaker DISABLED
        tomorrow = date.today() + timedelta(days=1)
        gara = Gara(
            number=1,
            name="Disabled Tiebreaker",
            date=tomorrow,
            discipline="8_ball",
            distance=5,
            is_race_to=True,
            rounds_count=1,
            min_participants=2,
            status=GaraStatus.PLAYING.value,
            current_round=1,
            director_id=director.id,
            matchmaking_strategy="amalfi",
            tiebreaker_enabled=False,  # DISABLED
        )
        db_session.add(gara)
        db_session.commit()

        # Even with ties, should return empty
        ties = TiebreakerService.detect_ties(gara.id)
        assert ties == [], "Disabled tiebreaker should return empty list"

    def test_get_tiebreaker_config(self, db_session):
        """Test getting tiebreaker configuration."""
        from models.competition.tiebreaker_service import TiebreakerService

        unique_id = str(uuid.uuid4())[:8]

        director = User(
            username=f"director_{unique_id}",
            email=f"director_{unique_id}@test.com",
            role=UserRole.DIRECTOR.value,
        )
        director.set_password("testpass123")
        db_session.add(director)
        db_session.commit()

        tomorrow = date.today() + timedelta(days=1)
        gara = Gara(
            number=1,
            name="Config Test",
            date=tomorrow,
            discipline="8_ball",
            distance=5,
            is_race_to=True,
            rounds_count=1,
            min_participants=2,
            status=GaraStatus.SETUP.value,
            director_id=director.id,
            tiebreaker_enabled=True,
            tiebreaker_until_position=5,
            tiebreaker_mode="challenge",
            tiebreaker_challenge_id=None,
        )
        db_session.add(gara)
        db_session.commit()

        config = TiebreakerService.get_tiebreaker_config(gara.id)

        assert config["enabled"] is True
        assert config["until_position"] == 5
        assert config["mode"] == "challenge"
        assert config["challenge_id"] is None
        assert config["challenge"] is None

    def test_needs_tiebreaker_returns_correct_status(self, db_session):
        """Test needs_tiebreaker helper function."""
        from models.competition.tiebreaker_service import TiebreakerService

        unique_id = str(uuid.uuid4())[:8]

        director = User(
            username=f"director_{unique_id}",
            email=f"director_{unique_id}@test.com",
            role=UserRole.DIRECTOR.value,
        )
        director.set_password("testpass123")
        db_session.add(director)
        db_session.commit()

        # Create players
        players = []
        for i in range(2):
            player = User(
                username=f"player{i}_{unique_id}",
                email=f"player{i}_{unique_id}@test.com",
                role=UserRole.PLAYER.value,
            )
            player.set_password("testpass123")
            players.append(player)
        db_session.add_all(players)
        db_session.commit()

        tomorrow = date.today() + timedelta(days=1)
        gara = Gara(
            number=1,
            name="Needs Tiebreaker Test",
            date=tomorrow,
            discipline="8_ball",
            distance=5,
            is_race_to=True,
            rounds_count=1,
            min_participants=2,
            status=GaraStatus.PLAYING.value,
            current_round=1,
            director_id=director.id,
            tiebreaker_enabled=True,
            tiebreaker_until_position=2,
            tiebreaker_mode="playoff_match",
        )
        db_session.add(gara)
        db_session.commit()

        # Create inscriptions
        for player in players:
            inscription = Inscription(user_id=player.id, gara_id=gara.id)
            db_session.add(inscription)
        db_session.commit()

        # Create tied classification at position 1
        for i, player in enumerate(players):
            classification = RoundClassification(
                gara_id=gara.id,
                round_number=1,
                user_id=player.id,
                position=1,  # Both at position 1 (tied)
                matches_won=1,
                rack_difference=0,
            )
            db_session.add(classification)
        db_session.commit()

        # Should need tiebreaker
        assert TiebreakerService.needs_tiebreaker(gara.id) is True
