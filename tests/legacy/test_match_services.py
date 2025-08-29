"""
Test module for models/match/services.py
"""

import pytest
from unittest.mock import Mock, patch
from models.match.services import MatchService, RackService, MatchResultService
from models.match.models import Match
from models.status_enum import MatchStatus
from models.exceptions import InvalidTransitionError


class TestMatchService:
    """Test cases for MatchService class."""

    def test_create_match(self):
        """Test creating a match."""
        with patch("models.match.services.db") as mock_db:
            mock_match = Mock()

            # Mock the Match constructor
            with patch(
                "models.match.services.Match", return_value=mock_match
            ) as mock_match_class:
                result = MatchService.create_match(
                    prova_id=1,
                    round_number=1,
                    player1_id=10,
                    player2_id=20,
                    is_bye=False,
                )

                # Verify the match was created with correct parameters
                mock_match_class.assert_called_once_with(
                    prova_id=1,
                    round_number=1,
                    player1_id=10,
                    player2_id=20,
                    is_bye=False,
                    status=MatchStatus.PENDING.value,
                )

                # Verify database operations
                mock_db.session.add.assert_called_once_with(mock_match)
                mock_db.session.commit.assert_called_once()

                # Verify the result
                assert result == mock_match

    def test_get_matches_by_prova(self):
        """Test getting matches by prova."""
        mock_matches = [Mock(), Mock(), Mock()]

        with patch("models.match.services.Match") as mock_match_class:
            # Set up the mock chain properly
            mock_query = Mock()
            mock_filtered_query = Mock()
            mock_filtered_query.all.return_value = mock_matches

            mock_match_class.query = mock_query
            mock_query.filter_by.return_value = mock_filtered_query

            result = MatchService.get_matches_by_prova(1)

            # Verify the query was called correctly
            mock_query.filter_by.assert_called_once_with(prova_id=1)
            mock_filtered_query.all.assert_called_once()

            # Verify the result
            assert result == mock_matches

    def test_create_trio_match(self):
        """Test creating a trio match."""
        with patch("models.match.services.db") as mock_db:
            mock_trio = Mock()
            mock_match = Mock()
            mock_match.is_trio = False

            mock_db.session.get.return_value = mock_match

            # Mock the TrioMatch constructor
            with patch(
                "models.match.services.TrioMatch", return_value=mock_trio
            ) as mock_trio_class:
                result = MatchService.create_trio_match(1, 30)

                # Verify the trio was created with correct parameters
                mock_trio_class.assert_called_once_with(
                    match_id=1, waiting_player_id=30
                )

                # Verify database operations - should be called twice
                # (once for trio, once for match)
                assert mock_db.session.add.call_count == 2
                mock_db.session.commit.assert_called_once()

                # Verify the match was updated
                assert mock_match.is_trio is True

                # Verify the result
                assert result == mock_trio

    def test_to_playing_success(self):
        """Test transitioning match to playing state successfully."""
        mock_match = Mock()
        mock_match.status = MatchStatus.PENDING.value

        with patch("models.match.services.db") as mock_db:
            mock_db.session.get.return_value = mock_match

            result = MatchService.to_playing(1)

            # Verify database operations
            mock_db.session.get.assert_called_once_with(Match, 1)
            mock_db.session.add.assert_called_once_with(mock_match)
            mock_db.session.commit.assert_called_once()

            # Verify the match status was updated
            assert mock_match.status == MatchStatus.PLAYING.value

            # Verify the result
            assert result == mock_match

    def test_to_playing_invalid_transition(self):
        """Test transitioning match to playing state with invalid current state."""
        mock_match = Mock()
        mock_match.status = MatchStatus.PLAYING.value  # Already playing

        with patch("models.match.services.db") as mock_db:
            mock_db.session.get.return_value = mock_match

            # Should raise InvalidTransitionError
            with pytest.raises(InvalidTransitionError):
                MatchService.to_playing(1)

    def test_to_playing_match_not_found(self):
        """Test transitioning match to playing state when match doesn't exist."""
        with patch("models.match.services.db") as mock_db:
            mock_db.session.get.return_value = None

            # Should raise ValueError
            with pytest.raises(ValueError, match="Match 1 non trovato"):
                MatchService.to_playing(1)

    def test_to_completed_success(self):
        """Test transitioning match to completed state successfully."""
        mock_match = Mock()
        mock_match.status = MatchStatus.PLAYING.value

        with patch("models.match.services.db") as mock_db:
            mock_db.session.get.return_value = mock_match

            result = MatchService.to_completed(1)

            # Verify database operations
            mock_db.session.get.assert_called_once_with(Match, 1)
            mock_db.session.add.assert_called_once_with(mock_match)
            mock_db.session.commit.assert_called_once()

            # Verify the match status was updated
            assert mock_match.status == MatchStatus.COMPLETED.value

            # Verify the result
            assert result == mock_match

    def test_to_completed_invalid_transition(self):
        """Test transitioning match to completed state with invalid current state."""
        mock_match = Mock()
        mock_match.status = MatchStatus.COMPLETED.value  # Already completed

        with patch("models.match.services.db") as mock_db:
            mock_db.session.get.return_value = mock_match

            # Should raise InvalidTransitionError
            with pytest.raises(InvalidTransitionError):
                MatchService.to_completed(1)

    def test_reset_to_pending_success(self):
        """Test resetting match to pending state successfully."""
        mock_match = Mock()
        mock_match.status = MatchStatus.PLAYING.value
        mock_match.validated_by_admin = True

        with patch("models.match.services.db") as mock_db:
            mock_db.session.get.return_value = mock_match

            result = MatchService.reset_to_pending(1)

            # Verify database operations
            mock_db.session.get.assert_called_once_with(Match, 1)
            mock_db.session.add.assert_called_once_with(mock_match)
            mock_db.session.commit.assert_called_once()

            # Verify the match status was updated
            assert mock_match.status == MatchStatus.PENDING.value

            # Verify the validation flag was cleared
            assert mock_match.validated_by_admin is False

            # Verify the result
            assert result == mock_match


class TestRackService:
    """Test cases for RackService class."""

    def test_add_rack_result(self):
        """Test adding a rack result."""
        with patch("models.match.services.db") as mock_db:
            mock_rack = Mock()
            mock_match = Mock()
            mock_match.status = MatchStatus.PENDING.value

            # For rack creation and match lookup
            mock_db.session.get.side_effect = [mock_match, mock_match]

            # Mock the Rack constructor
            with patch(
                "models.match.services.Rack", return_value=mock_rack
            ) as mock_rack_class:
                result = RackService.add_rack_result(
                    match_id=1,
                    rack_number=1,
                    winner_id=10,
                    reported_by_id=20,
                    confirmed_by_player=True,
                    validated_by_admin=True,
                )

                # Verify the rack was created with correct parameters
                mock_rack_class.assert_called_once_with(
                    match_id=1,
                    rack_number=1,
                    winner_id=10,
                    reported_by_id=20,
                    confirmed_by_player=True,
                    validated_by_admin=True,
                )

                # Verify database operations - should be called twice
                # (once for rack, once for match)
                assert mock_db.session.add.call_count == 2
                # Commit is called twice (once for rack creation, once for match update)
                assert mock_db.session.commit.call_count == 2

                # Verify the match status was updated
                assert mock_match.status == MatchStatus.PLAYING.value

                # Verify the result
                assert result == mock_rack

    def test_add_rack_with_score_update(self):
        """Test adding a rack with score update."""
        mock_match = Mock()
        mock_match.player1_id = 10
        mock_match.player2_id = 20
        mock_match.player1_score = 0
        mock_match.player2_score = 0
        mock_match.status = MatchStatus.PLAYING.value

        mock_rack = Mock()
        mock_rack.rack_number = 1

        mock_last_rack = Mock()
        mock_last_rack.rack_number = 0

        with patch("models.match.services.db") as mock_db:
            mock_db.session.get.return_value = mock_match

            with patch("models.match.services.Rack") as mock_rack_class:
                mock_query = Mock()
                mock_ordered_query = Mock()
                mock_ordered_query.first.return_value = mock_last_rack

                mock_rack_class.query = Mock()
                mock_rack_class.query.filter_by.return_value = mock_query
                mock_query.order_by.return_value = mock_ordered_query

                with patch.object(
                    RackService, "add_rack_result", return_value=mock_rack
                ):
                    # Mock the prova and its methods
                    mock_prova = Mock()
                    mock_prova.best_of = True
                    mock_prova.distance = 5
                    mock_match.prova = mock_prova

                    with patch.object(mock_prova, "get_winning_score", return_value=3):
                        with patch.object(
                            mock_prova, "is_match_finished", return_value=False
                        ):
                            result = RackService.add_rack_with_score_update(
                                match_id=1,
                                winner_id=10,
                                reported_by_id=30,
                                validated_by_admin=True,
                            )

                            # Verify the rack was added
                            RackService.add_rack_result.assert_called_once()

                            # Verify the match score was updated
                            assert mock_match.player1_score == 1
                            assert mock_match.player2_score == 0

                            # Verify the result
                            assert result["success"] is True
                            assert result["player1_score"] == 1
                            assert result["player2_score"] == 0
                            assert result["status"] == MatchStatus.PLAYING.value


class TestMatchResultService:
    """Test cases for MatchResultService class."""

    def test_submit_result_success(self):
        """Test submitting match result successfully."""
        mock_match = Mock()
        mock_match.player1_id = 10
        mock_match.player2_id = 20
        mock_match.winner_id = None
        mock_match.id = 1  # Add the id attribute

        with patch("models.match.services.db") as mock_db:
            mock_db.session.get.return_value = mock_match

            with patch.object(MatchService, "to_completed") as mock_to_completed:
                result = MatchResultService.submit_result(1, 10)

                # Verify database operations
                mock_db.session.get.assert_called_once_with(Match, 1)
                mock_db.session.add.assert_called_once_with(mock_match)
                mock_db.session.commit.assert_called_once()

                # Verify the winner was set
                assert mock_match.winner_id == 10

                # Verify the match was transitioned to completed
                mock_to_completed.assert_called_once_with(1)

                # Verify the result
                assert result == mock_match

    def test_submit_result_invalid_winner(self):
        """Test submitting match result with invalid winner."""
        mock_match = Mock()
        mock_match.player1_id = 10
        mock_match.player2_id = 20

        with patch("models.match.services.db") as mock_db:
            mock_db.session.get.return_value = mock_match

            # Should raise ValueError for invalid winner
            with pytest.raises(
                ValueError, match="winner_id non appartiene ai giocatori del match"
            ):
                MatchResultService.submit_result(
                    1, 30
                )  # 30 is not player1_id or player2_id

    def test_submit_result_match_not_found(self):
        """Test submitting match result when match doesn't exist."""
        with patch("models.match.services.db") as mock_db:
            mock_db.session.get.return_value = None

            # Should raise ValueError
            with pytest.raises(ValueError, match="Match 1 non trovato"):
                MatchResultService.submit_result(1, 10)
