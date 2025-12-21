"""
Comprehensive tests for models/match/services.py
Targeting 209 statements with 144 missed (31% coverage) for maximum impact toward 90% goal.
"""

import pytest
from unittest.mock import Mock, patch

from models.match.services import MatchService, RackService, MatchResultService
from models.status_enum import MatchStatus
from models.exceptions import InvalidTransitionError


class TestMatchService:
    """Comprehensive tests for MatchService."""

    @patch("models.match.services.db")
    @patch("models.match.services.Match")
    def test_create_match(self, mock_match_class, mock_db):
        """Test create_match method."""
        mock_match = Mock()
        mock_match_class.return_value = mock_match

        result = MatchService.create_match(
            gara_id=123, round_number=1, player1_id=456, player2_id=789, is_bye=False
        )

        assert result == mock_match
        mock_match_class.assert_called_once_with(
            gara_id=123,
            round_number=1,
            player1_id=456,
            player2_id=789,
            is_bye=False,
            status=MatchStatus.PENDING.value,
        )
        mock_db.session.add.assert_called_once_with(mock_match)
        mock_db.session.commit.assert_called_once()

    @patch("models.match.services.Match")
    def test_get_matches_by_gara(self, mock_match_class):
        """Test get_matches_by_gara method."""
        mock_matches = [Mock(), Mock(), Mock()]
        mock_match_class.query.filter_by.return_value.all.return_value = mock_matches

        result = MatchService.get_matches_by_gara(123)

        assert result == mock_matches
        mock_match_class.query.filter_by.assert_called_once_with(gara_id=123)

    @patch("models.match.services.db")
    @patch("models.match.services.TrioMatch")
    def test_create_trio_match(self, mock_trio_class, mock_db):
        """Test create_trio_match method."""
        mock_trio = Mock()
        mock_trio_class.return_value = mock_trio

        mock_match = Mock()
        mock_db.session.get.return_value = mock_match

        result = MatchService.create_trio_match(match_id=123, player3_id=789)

        assert result == mock_trio
        mock_trio_class.assert_called_once_with(match_id=123, waiting_player_id=789)
        mock_db.session.add.assert_any_call(mock_trio)
        mock_db.session.add.assert_any_call(mock_match)
        assert mock_match.is_trio is True
        mock_db.session.commit.assert_called_once()

    @patch("models.match.services.db")
    def test_to_playing_from_pending(self, mock_db):
        """Test to_playing transition from pending state."""
        mock_match = Mock()
        mock_match.status = MatchStatus.PENDING.value
        mock_db.session.get.return_value = mock_match

        result = MatchService.to_playing(123)

        assert result == mock_match
        assert mock_match.status == MatchStatus.PLAYING.value
        mock_db.session.add.assert_called_once_with(mock_match)
        mock_db.session.commit.assert_called_once()

    @patch("models.match.services.db")
    def test_to_playing_from_completed(self, mock_db):
        """Test to_playing transition from completed state."""
        mock_match = Mock()
        mock_match.status = MatchStatus.COMPLETED.value
        mock_db.session.get.return_value = mock_match

        result = MatchService.to_playing(123)

        assert result == mock_match
        assert mock_match.status == MatchStatus.PLAYING.value

    @patch("models.match.services.db")
    def test_to_playing_invalid_transition(self, mock_db):
        """Test to_playing with invalid transition."""
        mock_match = Mock()
        mock_match.status = MatchStatus.PLAYING.value
        mock_db.session.get.return_value = mock_match

        with pytest.raises(InvalidTransitionError):
            MatchService.to_playing(123)

    @patch("models.match.services.db")
    def test_to_playing_match_not_found(self, mock_db):
        """Test to_playing with non-existent match."""
        mock_db.session.get.return_value = None

        with pytest.raises(ValueError, match="Match 999 non trovato"):
            MatchService.to_playing(999)

    @patch("models.match.services.db")
    def test_to_completed_from_playing(self, mock_db):
        """Test to_completed transition from playing state."""
        mock_match = Mock()
        mock_match.status = MatchStatus.PLAYING.value
        mock_db.session.get.return_value = mock_match

        result = MatchService.to_completed(123)

        assert result == mock_match
        assert mock_match.status == MatchStatus.COMPLETED.value
        mock_db.session.add.assert_called_once_with(mock_match)
        mock_db.session.commit.assert_called_once()

    @patch("models.match.services.db")
    def test_to_completed_from_pending(self, mock_db):
        """Test to_completed transition from pending state."""
        mock_match = Mock()
        mock_match.status = MatchStatus.PENDING.value
        mock_db.session.get.return_value = mock_match

        result = MatchService.to_completed(123)

        assert result == mock_match
        assert mock_match.status == MatchStatus.COMPLETED.value

    @patch("models.match.services.db")
    def test_to_completed_invalid_transition(self, mock_db):
        """Test to_completed with invalid transition."""
        mock_match = Mock()
        mock_match.status = MatchStatus.COMPLETED.value
        mock_db.session.get.return_value = mock_match

        with pytest.raises(InvalidTransitionError):
            MatchService.to_completed(123)

    @patch("models.match.services.db")
    def test_reset_to_pending(self, mock_db):
        """Test reset_to_pending method."""
        mock_match = Mock()
        mock_match.status = MatchStatus.PLAYING.value
        mock_db.session.get.return_value = mock_match

        result = MatchService.reset_to_pending(123, clear_validation=True)

        assert result == mock_match
        assert mock_match.status == MatchStatus.PENDING.value
        mock_db.session.add.assert_called_once_with(mock_match)
        mock_db.session.commit.assert_called_once()

    @patch("models.match.services.db")
    def test_reset_to_pending_with_validation_clear(self, mock_db):
        """Test reset_to_pending with validation clearing."""
        mock_match = Mock()
        mock_match.status = MatchStatus.COMPLETED.value
        mock_match.validated_by_admin = True
        mock_db.session.get.return_value = mock_match

        result = MatchService.reset_to_pending(123, clear_validation=True)

        assert result == mock_match
        assert mock_match.status == MatchStatus.PENDING.value
        assert mock_match.validated_by_admin is False

    @patch("models.match.services.db")
    def test_reset_to_pending_validation_error(self, mock_db):
        """Test reset_to_pending with validation attribute error."""
        mock_match = Mock()
        mock_match.status = MatchStatus.COMPLETED.value
        # Mock hasattr to return True but accessing the attribute raises an exception
        with patch("builtins.hasattr", return_value=True):

            def side_effect(*args):
                if args == "validated_by_admin":
                    raise AttributeError("No such attribute")
                return getattr(mock_match, args)

            type(mock_match).validated_by_admin = property(side_effect)
            mock_db.session.get.return_value = mock_match

            # Should not raise exception, should handle gracefully
            result = MatchService.reset_to_pending(123, clear_validation=True)

            assert result == mock_match
            assert mock_match.status == MatchStatus.PENDING.value


class TestRackService:
    """Comprehensive tests for RackService."""

    @patch("models.match.services.db")
    @patch("models.match.services.Rack")
    def test_add_rack_result(self, mock_rack_class, mock_db):
        """Test add_rack_result method."""
        mock_rack = Mock()
        mock_rack_class.return_value = mock_rack

        mock_match = Mock()
        mock_match.status = MatchStatus.PENDING.value
        mock_db.session.get.return_value = mock_match

        result = RackService.add_rack_result(
            match_id=123,
            rack_number=1,
            winner_id=456,
            reported_by_id=789,
            confirmed_by_player=True,
            validated_by_admin=False,
        )

        assert result == mock_rack
        mock_rack_class.assert_called_once_with(
            match_id=123,
            rack_number=1,
            winner_id=456,
            reported_by_id=789,
            confirmed_by_player=True,
            validated_by_admin=False,
        )
        mock_db.session.add.assert_any_call(mock_rack)
        mock_db.session.add.assert_any_call(mock_match)
        assert mock_match.status == MatchStatus.PLAYING.value
        assert mock_db.session.commit.call_count == 2

    @patch("models.match.services.db")
    @patch("models.match.services.Rack")
    def test_add_rack_result_already_playing(self, mock_rack_class, mock_db):
        """Test add_rack_result when match is already playing."""
        mock_rack = Mock()
        mock_rack_class.return_value = mock_rack

        mock_match = Mock()
        mock_match.status = MatchStatus.PLAYING.value
        mock_db.session.get.return_value = mock_match

        result = RackService.add_rack_result(
            match_id=123, rack_number=1, winner_id=456, reported_by_id=789
        )

        assert result == mock_rack
        # Should not change status since already playing
        assert mock_db.session.commit.call_count == 1

    @patch.object(RackService, "add_rack_result")
    @patch("models.match.services.Rack")
    @patch("models.match.services.db")
    def test_add_rack_with_score_update_player1_wins(
        self, mock_db, mock_rack_class, mock_add_rack
    ):
        """Test add_rack_with_score_update when player1 wins."""
        # Mock match
        mock_match = Mock()
        mock_match.id = 123
        mock_match.player1_id = 456
        mock_match.player2_id = 789
        mock_match.player1_score = 2
        mock_match.player2_score = 1
        mock_db.session.get.return_value = mock_match

        # Mock gara with is_match_finished method
        mock_gara = Mock()
        mock_gara.is_match_finished.return_value = False
        mock_match.gara = mock_gara

        # Mock last rack
        mock_last_rack = Mock()
        mock_last_rack.rack_number = 3
        mock_rack_class.query.filter_by.return_value.order_by.return_value.first.return_value = (
            mock_last_rack
        )

        result = RackService.add_rack_with_score_update(
            match_id=123, winner_id=456, reported_by_id=999
        )

        assert result["success"] is True
        assert result["player1_score"] == 3  # Incremented
        assert result["player2_score"] == 1  # Unchanged
        mock_add_rack.assert_called_once_with(
            match_id=123,
            rack_number=4,
            winner_id=456,
            reported_by_id=999,
            validated_by_admin=True,
        )

    @patch.object(RackService, "add_rack_result")
    @patch("models.match.services.Rack")
    @patch("models.match.services.db")
    def test_add_rack_with_score_update_player2_wins(
        self, mock_db, mock_rack_class, mock_add_rack
    ):
        """Test add_rack_with_score_update when player2 wins."""
        mock_match = Mock()
        mock_match.id = 123
        mock_match.player1_id = 456
        mock_match.player2_id = 789
        mock_match.player1_score = 2
        mock_match.player2_score = 1
        mock_db.session.get.return_value = mock_match

        mock_gara = Mock()
        mock_gara.is_match_finished.return_value = False
        mock_match.gara = mock_gara

        # No previous racks
        mock_rack_class.query.filter_by.return_value.order_by.return_value.first.return_value = (
            None
        )

        result = RackService.add_rack_with_score_update(
            match_id=123, winner_id=789, reported_by_id=999
        )

        assert result["success"] is True
        assert result["player1_score"] == 2  # Unchanged
        assert result["player2_score"] == 2  # Incremented
        mock_add_rack.assert_called_once_with(
            match_id=123,
            rack_number=1,  # First rack
            winner_id=789,
            reported_by_id=999,
            validated_by_admin=True,
        )

    @patch("models.match.services.MatchResultService")
    @patch.object(RackService, "add_rack_result")
    @patch("models.match.services.Rack")
    @patch("models.match.services.db")
    def test_add_rack_with_score_update_match_finished(
        self, mock_db, mock_rack_class, mock_add_rack, mock_result_service
    ):
        """Test add_rack_with_score_update when match is finished."""
        mock_match = Mock()
        mock_match.id = 123
        mock_match.player1_id = 456
        mock_match.player2_id = 789
        mock_match.player1_score = 4
        mock_match.player2_score = 2
        mock_db.session.get.return_value = mock_match

        mock_gara = Mock()
        mock_gara.is_match_finished.return_value = True
        mock_match.gara = mock_gara

        mock_rack_class.query.filter_by.return_value.order_by.return_value.first.return_value = (
            None
        )

        result = RackService.add_rack_with_score_update(
            match_id=123, winner_id=456, reported_by_id=999
        )

        assert result["success"] is True
        assert result["player1_score"] == 5
        mock_result_service.submit_result.assert_called_once_with(123, 456)

    @patch("models.match.services.db")
    def test_add_rack_with_score_update_match_not_found(self, mock_db):
        """Test add_rack_with_score_update with non-existent match."""
        mock_db.session.get.return_value = None

        with pytest.raises(ValueError, match="Match 999 non trovato"):
            RackService.add_rack_with_score_update(999, 456, 789)

    @patch.object(RackService, "add_rack_result")
    @patch("models.match.services.Rack")
    @patch("models.match.services.db")
    def test_set_match_result_direct_best_of(
        self, mock_db, mock_rack_class, mock_add_rack
    ):
        """Test set_match_result_direct with best_of format."""
        mock_match = Mock()
        mock_match.id = 123
        mock_match.player1_id = 456
        mock_match.player2_id = 789
        mock_match.is_bye = False
        mock_db.session.get.return_value = mock_match

        mock_gara = Mock()
        mock_gara.is_race_to = True
        mock_gara.get_winning_score.return_value = 5
        mock_match.gara = mock_gara

        # Mock existing racks to be deleted
        mock_existing_racks = [Mock(), Mock()]
        mock_rack_class.query.filter_by.return_value.all.return_value = (
            mock_existing_racks
        )

        RackService.set_match_result_direct(123, 5, 3)

        # Verify existing racks were deleted
        for rack in mock_existing_racks:
            mock_db.session.delete.assert_any_call(rack)

        # Verify new racks were added (5 for player1, 3 for player2)
        assert mock_add_rack.call_count == 8

        # Verify match was updated
        assert mock_match.player1_score == 5
        assert mock_match.player2_score == 3
        assert mock_match.winner_id == 456

    @patch("models.match.services.db")
    def test_set_match_result_direct_bye_match(self, mock_db):
        """Test set_match_result_direct with bye match."""
        mock_match = Mock()
        mock_match.is_bye = True
        mock_db.session.get.return_value = mock_match

        with pytest.raises(ValueError, match="Non puoi modificare una partita bye!"):
            RackService.set_match_result_direct(123, 5, 3)

    @patch("models.match.services.db")
    def test_set_match_result_direct_negative_scores(self, mock_db):
        """Test set_match_result_direct with negative scores."""
        mock_match = Mock()
        mock_match.is_bye = False
        mock_db.session.get.return_value = mock_match

        with pytest.raises(ValueError, match="I punteggi non possono essere negativi!"):
            RackService.set_match_result_direct(123, -1, 3)

    @patch("models.match.services.db")
    def test_set_match_result_direct_invalid_best_of(self, mock_db):
        """Test set_match_result_direct with invalid best_of result."""
        mock_match = Mock()
        mock_match.is_bye = False
        mock_db.session.get.return_value = mock_match

        mock_gara = Mock()
        mock_gara.is_race_to = True
        mock_gara.distance = 9
        mock_gara.get_winning_score.return_value = 5
        mock_match.gara = mock_gara

        with pytest.raises(ValueError, match="deve raggiungere 5 punti"):
            RackService.set_match_result_direct(123, 3, 2)  # Neither reached 5

    @patch("models.match.services.db")
    def test_set_match_result_direct_invalid_exact_number(self, mock_db):
        """Test set_match_result_direct with invalid exact number result."""
        mock_match = Mock()
        mock_match.is_bye = False
        mock_db.session.get.return_value = mock_match

        mock_gara = Mock()
        mock_gara.is_race_to = False
        mock_gara.distance = 7
        mock_match.gara = mock_gara

        with pytest.raises(ValueError, match="la somma deve essere esattamente 7"):
            RackService.set_match_result_direct(123, 3, 2)  # Sum is 5, not 7

    @patch("models.match.services.db")
    def test_set_match_result_direct_tie(self, mock_db):
        """Test set_match_result_direct with tie score."""
        mock_match = Mock()
        mock_match.is_bye = False
        mock_db.session.get.return_value = mock_match

        mock_gara = Mock()
        mock_gara.is_race_to = True
        mock_gara.get_winning_score.return_value = 5
        mock_match.gara = mock_gara

        with pytest.raises(ValueError, match="Non può esserci un pareggio!"):
            RackService.set_match_result_direct(123, 5, 5)

    @patch("models.match.services.Rack")
    @patch("models.match.services.db")
    def test_reset_match_complete(self, mock_db, mock_rack_class):
        """Test reset_match_complete method."""
        mock_match = Mock()
        mock_match.is_bye = False
        mock_db.session.get.return_value = mock_match

        mock_existing_racks = [Mock(), Mock(), Mock()]
        mock_rack_class.query.filter_by.return_value.all.return_value = (
            mock_existing_racks
        )

        RackService.reset_match_complete(123)

        # Verify all racks were deleted
        for rack in mock_existing_racks:
            mock_db.session.delete.assert_any_call(rack)

        # Verify match was reset
        assert mock_match.player1_score == 0
        assert mock_match.player2_score == 0
        assert mock_match.winner_id is None
        mock_db.session.commit.assert_called_once()

    @patch("models.match.services.db")
    def test_reset_match_complete_bye_match(self, mock_db):
        """Test reset_match_complete with bye match."""
        mock_match = Mock()
        mock_match.is_bye = True
        mock_db.session.get.return_value = mock_match

        with pytest.raises(ValueError, match="Non puoi resettare una partita bye!"):
            RackService.reset_match_complete(123)

    @patch("models.match.services.abort")
    @patch("models.match.services.db")
    def test_remove_rack_admin_not_found(self, mock_db, mock_abort):
        """Test remove_rack_admin with non-existent rack."""
        mock_db.session.get.return_value = None

        RackService.remove_rack_admin(999)

        mock_abort.assert_called_once_with(404)

    @patch("models.match.services.db")
    def test_remove_rack_admin_completed_match_still_won(self, mock_db):
        """Test remove_rack_admin with completed match that's still won."""
        mock_rack = Mock()
        mock_rack.winner_id = 456
        mock_db.session.get.return_value = mock_rack

        mock_match = Mock()
        mock_match.status = MatchStatus.COMPLETED.value
        mock_match.player1_id = 456
        mock_match.player2_id = 789
        mock_match.player1_score = 5
        mock_match.player2_score = 3
        mock_rack.match = mock_match

        mock_gara = Mock()
        mock_gara.is_race_to = True
        mock_gara.get_winning_score.return_value = 5
        mock_match.gara = mock_gara

        result = RackService.remove_rack_admin(123)

        assert result["success"] is True
        assert result["player1_score"] == 4  # Decremented
        assert result["player2_score"] == 3  # Unchanged
        # Match should still be completed since player1 still has winning score
        mock_db.session.delete.assert_called_once_with(mock_rack)

    @patch("models.match.services.db")
    def test_validate_rack_admin(self, mock_db):
        """Test validate_rack_admin method."""
        mock_rack = Mock()
        mock_rack.validated_by_admin = False
        mock_rack.confirmed_by_player = False
        mock_db.session.get.return_value = mock_rack

        RackService.validate_rack_admin(123)

        assert mock_rack.validated_by_admin is True
        assert mock_rack.confirmed_by_player is True
        mock_db.session.commit.assert_called_once()

    @patch("models.match.services.Rack")
    @patch("models.match.services.db")
    def test_remove_last_rack_exists(self, mock_db, mock_rack_class):
        """Test remove_last_rack when rack exists."""
        mock_last_rack = Mock()
        mock_rack_class.query.filter_by.return_value.order_by.return_value.first.return_value = (
            mock_last_rack
        )

        result = RackService.remove_last_rack(123)

        assert result == mock_last_rack
        mock_db.session.delete.assert_called_once_with(mock_last_rack)
        mock_db.session.commit.assert_called_once()

    @patch("models.match.services.Rack")
    @patch("models.match.services.db")
    def test_remove_last_rack_none_exists(self, mock_db, mock_rack_class):
        """Test remove_last_rack when no rack exists."""
        mock_rack_class.query.filter_by.return_value.order_by.return_value.first.return_value = (
            None
        )

        result = RackService.remove_last_rack(123)

        assert result is None
        mock_db.session.delete.assert_not_called()
        mock_db.session.commit.assert_not_called()


class TestMatchResultService:
    """Comprehensive tests for MatchResultService."""

    @patch("models.match.services.db")
    def test_validate_by_admin(self, mock_db):
        """Test validate_by_admin method."""
        mock_match = Mock()
        mock_match.validated_by_admin = False
        mock_db.session.get.return_value = mock_match

        result = MatchResultService.validate_by_admin(123)

        assert result == mock_match
        assert mock_match.validated_by_admin is True
        mock_db.session.add.assert_called_once_with(mock_match)
        mock_db.session.commit.assert_called_once()

    @patch("models.match.services.db")
    def test_validate_by_admin_no_attribute(self, mock_db):
        """Test validate_by_admin when match has no validated_by_admin attribute."""
        mock_match = Mock()
        # Mock hasattr to return False
        with patch("builtins.hasattr", return_value=False):
            mock_db.session.get.return_value = mock_match

            result = MatchResultService.validate_by_admin(123)

            assert result == mock_match
            mock_db.session.commit.assert_called_once()

    @patch("models.match.services.db")
    def test_validate_by_admin_match_not_found(self, mock_db):
        """Test validate_by_admin with non-existent match."""
        mock_db.session.get.return_value = None

        with pytest.raises(ValueError, match="Match 999 non trovato"):
            MatchResultService.validate_by_admin(999)

    @patch("models.match.services.db")
    def test_submit_result_success(self, mock_db):
        """Test submit_result method successfully."""
        mock_match = Mock()
        mock_match.player1_id = 456
        mock_match.player2_id = 789
        mock_match.winner_id = None
        mock_db.session.get.return_value = mock_match

        result = MatchResultService.submit_result(123, 456)

        assert result == mock_match
        assert mock_match.winner_id == 456
        mock_db.session.add.assert_called_once_with(mock_match)
        assert (
            mock_db.session.commit.call_count == 2
        )  # Once for setting winner, once for transition

    @patch("models.match.services.db")
    def test_submit_result_match_not_found(self, mock_db):
        """Test submit_result with non-existent match."""
        mock_db.session.get.return_value = None

        with pytest.raises(ValueError, match="Match 999 non trovato"):
            MatchResultService.submit_result(999, 456)

    @patch("models.match.services.db")
    def test_submit_result_invalid_winner(self, mock_db):
        """Test submit_result with invalid winner_id."""
        mock_match = Mock()
        mock_match.player1_id = 456
        mock_match.player2_id = 789
        mock_db.session.get.return_value = mock_match

        with pytest.raises(
            ValueError, match="winner_id non appartiene ai giocatori del match"
        ):
            MatchResultService.submit_result(123, 999)  # Invalid winner_id
