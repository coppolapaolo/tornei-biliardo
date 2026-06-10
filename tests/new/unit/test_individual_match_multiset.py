"""
Unit tests for IndividualMatch multi-set functionality.

Tests the multi-set match workflow for IndividualMatch including:
- Creating first set when match starts
- Adding racks to sets
- Set completion and match score updates
- Starting next set after current completes
- Match completion when all sets are won
"""

import pytest
from datetime import datetime, timedelta

from models.individual_match.models import (
    IndividualMatch,
    IndividualSet,
)
from models.status_enum import MatchStatus
from models.base import utc_now


class TestMultiSetMatchStart:
    """Tests for starting a multi-set match."""

    def test_start_match_creates_first_set(self, app, db_session, isolated_players):
        """Starting a multi-set match should create the first set."""
        player1, player2 = isolated_players[:2]

        match = IndividualMatch(
            player1_id=player1.id,
            player2_id=player2.id,
            location="Test Hall",
            scheduled_at=utc_now() + timedelta(hours=1),
            status=MatchStatus.SCHEDULED,
            discipline="palla_8",
            distance=5,  # Each set is race-to-5
            is_race_to=True,
            is_multi_set=True,
            match_distance=3,  # First to win 3 sets
            is_race_to_sets=True,
        )
        db_session.add(match)
        db_session.commit()

        # Start the match
        match.start_match()

        assert match.status == MatchStatus.IN_PROGRESS
        assert match.started_at is not None
        assert len(match.sets) == 1  # type: ignore[arg-type]

        first_set = match.sets[0]  # type: ignore[index]
        assert first_set.set_number == 1
        assert first_set.status == "playing"
        assert first_set.distance == 5
        assert first_set.is_race_to is True

    def test_start_match_single_set_does_not_create_set(
        self, app, db_session, isolated_players
    ):
        """Starting a single-set match should NOT create any set."""
        player1, player2 = isolated_players[:2]

        match = IndividualMatch(
            player1_id=player1.id,
            player2_id=player2.id,
            location="Test Hall",
            scheduled_at=utc_now() + timedelta(hours=1),
            status=MatchStatus.SCHEDULED,
            distance=5,
            is_race_to=True,
            is_multi_set=False,
        )
        db_session.add(match)
        db_session.commit()

        match.start_match()

        assert match.status == MatchStatus.IN_PROGRESS
        assert len(match.sets) == 0


class TestMultiSetRackScoring:
    """Tests for adding racks in multi-set matches."""

    def test_add_rack_updates_set_score(self, app, db_session, isolated_players):
        """Adding a rack should update the current set's score."""
        player1, player2 = isolated_players[:2]

        match = IndividualMatch(
            player1_id=player1.id,
            player2_id=player2.id,
            location="Test Hall",
            scheduled_at=utc_now() + timedelta(hours=1),
            status=MatchStatus.SCHEDULED,
            distance=5,
            is_race_to=True,
            is_multi_set=True,
            match_distance=3,
            is_race_to_sets=True,
        )
        db_session.add(match)
        db_session.commit()

        match.start_match()

        # Add racks to current set
        match.add_rack_result(player1.id)
        match.add_rack_result(player2.id)
        match.add_rack_result(player1.id)

        current_set = match.get_current_set()
        assert current_set.player1_racks == 2
        assert current_set.player2_racks == 1
        # Match score (sets) should still be 0-0
        assert match.player1_score == 0
        assert match.player2_score == 0

    def test_set_completion_updates_match_score(
        self, app, db_session, isolated_players
    ):
        """Completing a set should update the match's set score."""
        player1, player2 = isolated_players[:2]

        match = IndividualMatch(
            player1_id=player1.id,
            player2_id=player2.id,
            location="Test Hall",
            scheduled_at=utc_now() + timedelta(hours=1),
            status=MatchStatus.SCHEDULED,
            distance=3,  # Race to 3 racks per set
            is_race_to=True,
            is_multi_set=True,
            match_distance=2,  # First to 2 sets
            is_race_to_sets=True,
        )
        db_session.add(match)
        db_session.commit()

        match.start_match()

        # Player 1 wins first set 3-1
        match.add_rack_result(player1.id)
        match.add_rack_result(player1.id)
        match.add_rack_result(player2.id)
        match.add_rack_result(player1.id)  # This completes the set

        # Verify set completion
        first_set = match.sets[0]  # type: ignore[index]
        assert first_set.status == "completed"
        assert first_set.winner_id == player1.id
        assert first_set.player1_racks == 3
        assert first_set.player2_racks == 1

        # Verify match score (sets won)
        assert match.player1_score == 1  # Player 1 won 1 set
        assert match.player2_score == 0

    def test_rack_belongs_to_set(self, app, db_session, isolated_players):
        """Racks should be linked to their set via individual_set_id."""
        player1, player2 = isolated_players[:2]

        match = IndividualMatch(
            player1_id=player1.id,
            player2_id=player2.id,
            location="Test Hall",
            scheduled_at=utc_now() + timedelta(hours=1),
            status=MatchStatus.SCHEDULED,
            distance=5,
            is_race_to=True,
            is_multi_set=True,
            match_distance=3,
            is_race_to_sets=True,
        )
        db_session.add(match)
        db_session.commit()

        match.start_match()
        rack = match.add_rack_result(player1.id)

        assert rack.individual_set_id is not None
        assert rack.individual_set_id == match.get_current_set().id


class TestMultiSetTransitions:
    """Tests for transitioning between sets in multi-set matches."""

    def test_start_next_set_after_set_completion(
        self, app, db_session, isolated_players
    ):
        """Should be able to start the next set after current set completes."""
        player1, player2 = isolated_players[:2]

        match = IndividualMatch(
            player1_id=player1.id,
            player2_id=player2.id,
            location="Test Hall",
            scheduled_at=utc_now() + timedelta(hours=1),
            status=MatchStatus.SCHEDULED,
            distance=2,  # Race to 2 racks per set
            is_race_to=True,
            is_multi_set=True,
            match_distance=3,  # First to 3 sets
            is_race_to_sets=True,
        )
        db_session.add(match)
        db_session.commit()

        match.start_match()

        # Complete first set (player 1 wins 2-0)
        match.add_rack_result(player1.id)
        match.add_rack_result(player1.id)

        # First set should be completed
        assert match.sets[0].status == "completed"  # type: ignore[index]
        assert match.get_current_set() is None  # No active set

        # Start next set
        second_set = match.start_next_set()

        assert second_set.set_number == 2
        assert second_set.status == "playing"
        assert len(match.sets) == 2

    def test_cannot_start_next_set_while_current_in_progress(
        self, app, db_session, isolated_players
    ):
        """Cannot start a new set while current set is still playing."""
        player1, player2 = isolated_players[:2]

        match = IndividualMatch(
            player1_id=player1.id,
            player2_id=player2.id,
            location="Test Hall",
            scheduled_at=utc_now() + timedelta(hours=1),
            status=MatchStatus.SCHEDULED,
            distance=5,
            is_race_to=True,
            is_multi_set=True,
            match_distance=3,
            is_race_to_sets=True,
        )
        db_session.add(match)
        db_session.commit()

        match.start_match()

        # Try to start next set while first is playing
        with pytest.raises(ValueError, match="still in progress"):
            match.start_next_set()

    def test_cannot_start_next_set_when_match_complete(
        self, app, db_session, isolated_players
    ):
        """Cannot start a new set when match is already complete."""
        player1, player2 = isolated_players[:2]

        match = IndividualMatch(
            player1_id=player1.id,
            player2_id=player2.id,
            location="Test Hall",
            scheduled_at=utc_now() + timedelta(hours=1),
            status=MatchStatus.SCHEDULED,
            distance=2,
            is_race_to=True,
            is_multi_set=True,
            match_distance=2,  # First to 2 sets
            is_race_to_sets=True,
        )
        db_session.add(match)
        db_session.commit()

        match.start_match()

        # Player 1 wins two sets
        match.add_rack_result(player1.id)
        match.add_rack_result(player1.id)  # Set 1 complete
        match.start_next_set()
        match.add_rack_result(player1.id)
        match.add_rack_result(player1.id)  # Set 2 complete

        # Match should be ready for validation
        assert match.player1_score == 2

        # Cannot start another set
        with pytest.raises(ValueError, match="already complete"):
            match.start_next_set()


class TestMultiSetCompletion:
    """Tests for multi-set match completion."""

    def test_match_ready_for_validation_when_sets_won(
        self, app, db_session, isolated_players
    ):
        """Match should be ready for validation when player wins enough sets."""
        player1, player2 = isolated_players[:2]

        match = IndividualMatch(
            player1_id=player1.id,
            player2_id=player2.id,
            location="Test Hall",
            scheduled_at=utc_now() + timedelta(hours=1),
            status=MatchStatus.SCHEDULED,
            distance=2,
            is_race_to=True,
            is_multi_set=True,
            match_distance=2,  # First to 2 sets
            is_race_to_sets=True,
        )
        db_session.add(match)
        db_session.commit()

        match.start_match()

        # Win first set
        match.add_rack_result(player1.id)
        match.add_rack_result(player1.id)

        assert not match.is_ready_for_validation()

        # Win second set
        match.start_next_set()
        match.add_rack_result(player1.id)
        match.add_rack_result(player1.id)

        assert match.is_ready_for_validation()

    def test_bilateral_confirmation_for_multiset(
        self, app, db_session, isolated_players
    ):
        """Multi-set match should require bilateral confirmation like single-set."""
        player1, player2 = isolated_players[:2]

        match = IndividualMatch(
            player1_id=player1.id,
            player2_id=player2.id,
            location="Test Hall",
            scheduled_at=utc_now() + timedelta(hours=1),
            status=MatchStatus.SCHEDULED,
            distance=2,
            is_race_to=True,
            is_multi_set=True,
            match_distance=2,
            is_race_to_sets=True,
        )
        db_session.add(match)
        db_session.commit()

        match.start_match()

        # Player 1 wins 2 sets
        match.add_rack_result(player1.id)
        match.add_rack_result(player1.id)
        match.start_next_set()
        match.add_rack_result(player1.id)
        match.add_rack_result(player1.id)

        # Both players confirm
        result1 = match.confirm_result(player1.id)
        assert result1 is False  # First confirmation

        result2 = match.confirm_result(player2.id)
        assert result2 is True  # Second confirmation completes

        assert match.status == MatchStatus.VALIDATED
        assert match.winner_id == player1.id


class TestIndividualSetModel:
    """Tests for IndividualSet model directly."""

    def test_set_cannot_be_started_twice(self, app, db_session, isolated_players):
        """Set can only be started from pending status."""
        player1, player2 = isolated_players[:2]

        match = IndividualMatch(
            player1_id=player1.id,
            player2_id=player2.id,
            location="Test Hall",
            scheduled_at=utc_now(),
            status=MatchStatus.IN_PROGRESS,
            started_at=utc_now(),
            distance=5,
            is_race_to=True,
            is_multi_set=True,
            match_distance=3,
        )
        db_session.add(match)
        db_session.commit()

        individual_set = IndividualSet(
            match_id=match.id,
            set_number=1,
            distance=5,
            is_race_to=True,
            status="playing",  # Already playing
            started_at=utc_now(),
        )
        db_session.add(individual_set)
        db_session.commit()

        with pytest.raises(ValueError, match="pending status"):
            individual_set.start_set()

    def test_remove_last_rack_from_set(self, app, db_session, isolated_players):
        """Removing last rack should update set scores."""
        player1, player2 = isolated_players[:2]

        match = IndividualMatch(
            player1_id=player1.id,
            player2_id=player2.id,
            location="Test Hall",
            scheduled_at=utc_now() + timedelta(hours=1),
            status=MatchStatus.SCHEDULED,
            distance=5,
            is_race_to=True,
            is_multi_set=True,
            match_distance=3,
        )
        db_session.add(match)
        db_session.commit()

        match.start_match()

        # Add some racks
        match.add_rack_result(player1.id)
        match.add_rack_result(player1.id)
        match.add_rack_result(player2.id)

        current_set = match.get_current_set()
        assert current_set.player1_racks == 2
        assert current_set.player2_racks == 1

        # Remove last rack
        current_set.remove_last_rack(player1.id)

        assert current_set.player1_racks == 2
        assert current_set.player2_racks == 0

    def test_remove_rack_reopens_completed_set(self, app, db_session, isolated_players):
        """Removing a rack from completed set should reopen it."""
        player1, player2 = isolated_players[:2]

        match = IndividualMatch(
            player1_id=player1.id,
            player2_id=player2.id,
            location="Test Hall",
            scheduled_at=utc_now() + timedelta(hours=1),
            status=MatchStatus.SCHEDULED,
            distance=2,  # Race to 2
            is_race_to=True,
            is_multi_set=True,
            match_distance=3,
        )
        db_session.add(match)
        db_session.commit()

        match.start_match()

        # Complete the set
        match.add_rack_result(player1.id)
        match.add_rack_result(player1.id)

        first_set = match.sets[0]  # type: ignore[index]
        assert first_set.status == "completed"
        assert match.player1_score == 1  # 1 set won

        # Remove last rack
        first_set.remove_last_rack(player1.id)

        assert first_set.status == "playing"
        assert first_set.winner_id is None
        assert match.player1_score == 0  # Set score reverted


class TestGetCurrentSet:
    """Tests for get_current_set() method."""

    def test_returns_none_for_single_set_match(self, app, db_session, isolated_players):
        """get_current_set should return None for single-set matches."""
        player1, player2 = isolated_players[:2]

        match = IndividualMatch(
            player1_id=player1.id,
            player2_id=player2.id,
            location="Test Hall",
            scheduled_at=utc_now(),
            status=MatchStatus.IN_PROGRESS,
            distance=5,
            is_race_to=True,
            is_multi_set=False,
        )
        db_session.add(match)
        db_session.commit()

        assert match.get_current_set() is None

    def test_returns_playing_set(self, app, db_session, isolated_players):
        """get_current_set should return the set that is currently playing."""
        player1, player2 = isolated_players[:2]

        match = IndividualMatch(
            player1_id=player1.id,
            player2_id=player2.id,
            location="Test Hall",
            scheduled_at=utc_now() + timedelta(hours=1),
            status=MatchStatus.SCHEDULED,
            distance=5,
            is_race_to=True,
            is_multi_set=True,
            match_distance=3,
        )
        db_session.add(match)
        db_session.commit()

        match.start_match()

        current = match.get_current_set()
        assert current is not None
        assert current.set_number == 1
        assert current.status == "playing"

    def test_returns_none_when_no_active_set(self, app, db_session, isolated_players):
        """get_current_set should return None when current set is completed."""
        player1, player2 = isolated_players[:2]

        match = IndividualMatch(
            player1_id=player1.id,
            player2_id=player2.id,
            location="Test Hall",
            scheduled_at=utc_now() + timedelta(hours=1),
            status=MatchStatus.SCHEDULED,
            distance=2,
            is_race_to=True,
            is_multi_set=True,
            match_distance=3,
        )
        db_session.add(match)
        db_session.commit()

        match.start_match()

        # Complete the set
        match.add_rack_result(player1.id)
        match.add_rack_result(player1.id)

        # No current playing set
        assert match.get_current_set() is None
