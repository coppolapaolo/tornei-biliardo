"""
Unit tests for IndividualMatch forfeit functionality.

Tests the forfeit_match() method on IndividualMatch model and
MatchLifecycleService.forfeit_match() service method.
"""

import pytest
from datetime import datetime, timedelta

from models.individual_match.models import IndividualMatch
from models.status_enum import MatchStatus
from models.base import utc_now


class TestIndividualMatchForfeitModel:
    """Unit tests for IndividualMatch.forfeit_match() model method."""

    def test_forfeit_sets_winner_to_opponent_when_player1_forfeits(
        self, app, db_session, isolated_players
    ):
        """When player1 forfeits, player2 should be the winner."""
        player1, player2 = isolated_players[:2]

        # Create match in progress
        match = IndividualMatch(
            player1_id=player1.id,
            player2_id=player2.id,
            location="Test Hall",
            scheduled_at=utc_now() + timedelta(hours=1),
            status=MatchStatus.IN_PROGRESS,
            distance=5,
            is_race_to=True,
            player1_score=2,
            player2_score=1,
        )
        db_session.add(match)
        db_session.commit()

        # Player 1 forfeits
        match.forfeit_match(player1.id)

        assert match.winner_id == player2.id
        assert match.status == MatchStatus.COMPLETED

    def test_forfeit_sets_winner_to_opponent_when_player2_forfeits(
        self, app, db_session, isolated_players
    ):
        """When player2 forfeits, player1 should be the winner."""
        player1, player2 = isolated_players[:2]

        # Create match in progress
        match = IndividualMatch(
            player1_id=player1.id,
            player2_id=player2.id,
            location="Test Hall",
            scheduled_at=utc_now() + timedelta(hours=1),
            status=MatchStatus.IN_PROGRESS,
            distance=5,
            is_race_to=True,
            player1_score=1,
            player2_score=3,
        )
        db_session.add(match)
        db_session.commit()

        # Player 2 forfeits
        match.forfeit_match(player2.id)

        assert match.winner_id == player1.id
        assert match.status == MatchStatus.COMPLETED

    def test_forfeit_keeps_current_scores(self, app, db_session, isolated_players):
        """Forfeit should keep the forfeiting player's score (racks already won)."""
        player1, player2 = isolated_players[:2]

        # Create match with some racks played
        match = IndividualMatch(
            player1_id=player1.id,
            player2_id=player2.id,
            location="Test Hall",
            scheduled_at=utc_now() + timedelta(hours=1),
            status=MatchStatus.IN_PROGRESS,
            distance=5,
            is_race_to=True,
            player1_score=3,  # Player 1 has won 3 racks
            player2_score=2,  # Player 2 has won 2 racks
        )
        db_session.add(match)
        db_session.commit()

        # Player 1 forfeits
        match.forfeit_match(player1.id)

        # Player 1 keeps their 3 racks, player 2 gets winning score (5)
        assert match.player1_score == 3  # Unchanged
        assert match.player2_score == 5  # Gets winning score
        assert match.winner_id == player2.id

    def test_forfeit_winner_keeps_existing_score_if_higher(
        self, app, db_session, isolated_players
    ):
        """If winner already has score >= winning_score, keep it."""
        player1, player2 = isolated_players[:2]

        # Edge case: player 1 has high score but forfeits
        match = IndividualMatch(
            player1_id=player1.id,
            player2_id=player2.id,
            location="Test Hall",
            scheduled_at=utc_now() + timedelta(hours=1),
            status=MatchStatus.IN_PROGRESS,
            distance=5,
            is_race_to=True,
            player1_score=4,
            player2_score=4,  # Both have 4, but player 1 forfeits
        )
        db_session.add(match)
        db_session.commit()

        # Player 1 forfeits when losing 4-4
        match.forfeit_match(player1.id)

        # Player 2 gets winning score (5), player 1 keeps 4
        assert match.player1_score == 4
        assert match.player2_score == 5
        assert match.winner_id == player2.id

    def test_forfeit_sets_ended_at(self, app, db_session, isolated_players):
        """Forfeit should set ended_at timestamp."""
        player1, player2 = isolated_players[:2]

        match = IndividualMatch(
            player1_id=player1.id,
            player2_id=player2.id,
            location="Test Hall",
            scheduled_at=utc_now() + timedelta(hours=1),
            status=MatchStatus.IN_PROGRESS,
            distance=5,
            is_race_to=True,
        )
        db_session.add(match)
        db_session.commit()

        assert match.ended_at is None

        match.forfeit_match(player1.id)

        assert match.ended_at is not None

    def test_forfeit_fails_for_non_player(self, app, db_session, isolated_players):
        """Forfeit should raise ValueError for users not in the match."""
        player1, player2, other_user = isolated_players[:3]

        match = IndividualMatch(
            player1_id=player1.id,
            player2_id=player2.id,
            location="Test Hall",
            scheduled_at=utc_now() + timedelta(hours=1),
            status=MatchStatus.IN_PROGRESS,
            distance=5,
            is_race_to=True,
        )
        db_session.add(match)
        db_session.commit()

        with pytest.raises(ValueError, match="User is not a player"):
            match.forfeit_match(other_user.id)

    def test_forfeit_fails_for_completed_match(self, app, db_session, isolated_players):
        """Forfeit should raise ValueError for already completed matches."""
        player1, player2 = isolated_players[:2]

        match = IndividualMatch(
            player1_id=player1.id,
            player2_id=player2.id,
            location="Test Hall",
            scheduled_at=utc_now() + timedelta(hours=1),
            status=MatchStatus.COMPLETED,  # Already completed
            distance=5,
            is_race_to=True,
            winner_id=player1.id,
        )
        db_session.add(match)
        db_session.commit()

        with pytest.raises(ValueError, match="Can only forfeit"):
            match.forfeit_match(player1.id)

    def test_forfeit_fails_for_cancelled_match(self, app, db_session, isolated_players):
        """Forfeit should raise ValueError for cancelled matches."""
        player1, player2 = isolated_players[:2]

        match = IndividualMatch(
            player1_id=player1.id,
            player2_id=player2.id,
            location="Test Hall",
            scheduled_at=utc_now() + timedelta(hours=1),
            status=MatchStatus.CANCELLED,
            distance=5,
            is_race_to=True,
        )
        db_session.add(match)
        db_session.commit()

        with pytest.raises(ValueError, match="Can only forfeit"):
            match.forfeit_match(player1.id)

    def test_forfeit_works_for_scheduled_match(self, app, db_session, isolated_players):
        """Forfeit should work for SCHEDULED matches (before they start)."""
        player1, player2 = isolated_players[:2]

        match = IndividualMatch(
            player1_id=player1.id,
            player2_id=player2.id,
            location="Test Hall",
            scheduled_at=utc_now() + timedelta(hours=1),
            status=MatchStatus.SCHEDULED,  # Not started yet
            distance=5,
            is_race_to=True,
        )
        db_session.add(match)
        db_session.commit()

        match.forfeit_match(player1.id)

        assert match.winner_id == player2.id
        assert match.status == MatchStatus.COMPLETED
        # Winner gets winning score, loser has 0 (no racks played)
        assert match.player1_score == 0
        assert match.player2_score == 5


class TestIndividualMatchForfeitService:
    """Unit tests for MatchLifecycleService.forfeit_match() service method."""

    def test_service_forfeit_returns_updated_match(
        self, app, db_session, isolated_players
    ):
        """Service should return the updated match after forfeit."""
        from models.individual_match.match_lifecycle_service import (
            MatchLifecycleService,
        )

        player1, player2 = isolated_players[:2]

        match = IndividualMatch(
            player1_id=player1.id,
            player2_id=player2.id,
            location="Test Hall",
            scheduled_at=utc_now() + timedelta(hours=1),
            status=MatchStatus.IN_PROGRESS,
            distance=5,
            is_race_to=True,
            player1_score=2,
            player2_score=3,
        )
        db_session.add(match)
        db_session.commit()

        result = MatchLifecycleService.forfeit_match(match.id, player1.id)

        assert result.id == match.id
        assert result.winner_id == player2.id
        assert result.status == MatchStatus.COMPLETED

    def test_facade_forfeit_delegates_to_service(
        self, app, db_session, isolated_players
    ):
        """IndividualMatchService.forfeit_match should delegate to lifecycle service."""
        from models.individual_match.services import IndividualMatchService

        player1, player2 = isolated_players[:2]

        match = IndividualMatch(
            player1_id=player1.id,
            player2_id=player2.id,
            location="Test Hall",
            scheduled_at=utc_now() + timedelta(hours=1),
            status=MatchStatus.IN_PROGRESS,
            distance=5,
            is_race_to=True,
        )
        db_session.add(match)
        db_session.commit()

        result = IndividualMatchService.forfeit_match(match.id, player2.id)

        assert result.winner_id == player1.id
        assert result.status == MatchStatus.COMPLETED
