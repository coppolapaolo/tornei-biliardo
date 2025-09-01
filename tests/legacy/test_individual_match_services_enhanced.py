"""
Enhanced comprehensive tests for models/individual_match/services.py
Targeting 256 statements with 196 missed (23% coverage) for maximum impact toward 90% goal.
"""

import pytest
from unittest.mock import Mock, patch
from datetime import datetime, timedelta

from models.individual_match.services import (
    MatchProposalService,
    IndividualMatchService,
)
from models.individual_match.models import ProposalType, ProposalStatus


class TestMatchProposalService:
    """Comprehensive tests for MatchProposalService."""

    @patch("models.individual_match.services.IndividualMatchService")
    def test_create_proposal_direct(self, mock_service):
        """Test creating direct proposal."""
        mock_proposal = Mock()
        mock_service.create_direct_proposal.return_value = mock_proposal

        result = MatchProposalService.create_proposal(
            proposer_id=123,
            proposal_type=ProposalType.DIRECT,
            location="Test Location",
            scheduled_at=datetime(2024, 1, 20, 15, 0),
            expires_at=datetime(2024, 1, 20, 13, 0),
            invited_user_ids=[456, 789],
        )

        assert result == mock_proposal
        mock_service.create_direct_proposal.assert_called_once()

    @patch("models.individual_match.services.IndividualMatchService")
    def test_create_proposal_open(self, mock_service):
        """Test creating open proposal."""
        mock_proposal = Mock()
        mock_service.create_open_proposal.return_value = mock_proposal

        result = MatchProposalService.create_proposal(
            proposer_id=123,
            proposal_type=ProposalType.OPEN,
            location="Test Location",
            scheduled_at=datetime(2024, 1, 20, 15, 0),
            expires_at=datetime(2024, 1, 20, 13, 0),
        )

        assert result == mock_proposal
        mock_service.create_open_proposal.assert_called_once()

    @patch("models.individual_match.services.datetime")
    @patch("models.individual_match.services.db")
    @patch("models.individual_match.services.MatchProposal")
    def test_expire_proposals(self, mock_proposal_class, mock_db, mock_datetime):
        """Test expiring old proposals."""
        mock_now = datetime(2024, 1, 20, 14, 0)
        mock_datetime.utcnow.return_value = mock_now

        mock_proposal1 = Mock()
        mock_proposal2 = Mock()

        # Mock the query chain properly
        mock_query = Mock()
        mock_proposal_class.query = mock_query
        mock_query.filter.return_value.all.return_value = [
            mock_proposal1,
            mock_proposal2,
        ]

        result = MatchProposalService.expire_proposals()

        assert result == 2
        mock_proposal1.expire.assert_called_once()
        mock_proposal2.expire.assert_called_once()
        mock_db.session.commit.assert_called_once()


class TestIndividualMatchService:
    """Comprehensive tests for IndividualMatchService."""

    @patch("models.individual_match.services.timedelta")
    @patch("models.individual_match.services.db")
    @patch("models.individual_match.services.MatchProposal")
    @patch("models.individual_match.services.ProposalInvitation")
    def test_create_direct_proposal_success(
        self, mock_invitation_class, mock_proposal_class, mock_db, mock_timedelta
    ):
        """Test successful direct proposal creation."""
        mock_proposal = Mock()
        mock_proposal.id = 123
        mock_proposal_class.return_value = mock_proposal

        mock_invitation = Mock()
        mock_invitation_class.return_value = mock_invitation

        mock_timedelta.return_value = timedelta(hours=2)

        result = IndividualMatchService.create_direct_proposal(
            proposer_id=123,
            invited_user_ids=[456, 789],
            location="Test Location",
            scheduled_at=datetime(2024, 1, 20, 15, 0),
        )

        assert result == mock_proposal
        # Verify proposal was created and added
        mock_db.session.add.assert_any_call(mock_proposal)
        mock_db.session.flush.assert_called_once()
        mock_db.session.commit.assert_called_once()

    @patch("models.individual_match.services.db")
    @patch("models.individual_match.services.MatchProposal")
    def test_create_open_proposal_success(self, mock_proposal_class, mock_db):
        """Test successful open proposal creation."""
        mock_proposal = Mock()
        mock_proposal_class.return_value = mock_proposal

        result = IndividualMatchService.create_open_proposal(
            proposer_id=123,
            location="Test Location",
            scheduled_at=datetime(2024, 1, 20, 15, 0),
        )

        assert result == mock_proposal
        mock_db.session.add.assert_called_once_with(mock_proposal)
        mock_db.session.commit.assert_called_once()

    @patch("models.individual_match.services.db")
    def test_accept_proposal_success(self, mock_db):
        """Test successful proposal acceptance."""
        mock_proposal = Mock()
        mock_proposal.can_be_accepted_by.return_value = True
        mock_match = Mock()
        mock_proposal.accept.return_value = mock_match
        mock_db.session.get.return_value = mock_proposal

        result = IndividualMatchService.accept_proposal(456, 123)

        assert result == mock_match
        mock_proposal.can_be_accepted_by.assert_called_once_with(456)
        mock_proposal.accept.assert_called_once_with(456)
        mock_db.session.commit.assert_called_once()

    @patch("flask.abort")
    @patch("models.individual_match.services.db")
    def test_accept_proposal_not_found(self, mock_db, mock_abort):
        """Test accepting non-existent proposal."""
        mock_db.session.get.return_value = None

        IndividualMatchService.accept_proposal(456, 999)
        mock_abort.assert_called_once_with(404)

    @patch("models.individual_match.services.db")
    def test_accept_proposal_cannot_accept(self, mock_db):
        """Test accepting proposal when user cannot accept."""
        mock_proposal = Mock()
        mock_proposal.can_be_accepted_by.return_value = False
        mock_db.session.get.return_value = mock_proposal

        with pytest.raises(ValueError, match="User cannot accept this proposal"):
            IndividualMatchService.accept_proposal(456, 123)

    @patch("models.individual_match.services.db")
    @patch("models.individual_match.services.ProposalInvitation")
    def test_reject_invitation_success(self, mock_invitation_class, mock_db):
        """Test successful invitation rejection."""
        mock_invitation = Mock()
        mock_invitation_class.query.filter_by.return_value.first_or_404.return_value = (
            mock_invitation
        )

        IndividualMatchService.reject_invitation(456, 123)

        mock_invitation.reject.assert_called_once()
        mock_db.session.commit.assert_called_once()

    @patch("models.individual_match.services.db")
    def test_cancel_proposal_success(self, mock_db):
        """Test successful proposal cancellation."""
        mock_proposal = Mock()
        mock_proposal.proposer_id = 123
        mock_proposal.status = ProposalStatus.PENDING
        mock_db.session.get.return_value = mock_proposal

        IndividualMatchService.cancel_proposal(123, 456)

        mock_proposal.cancel.assert_called_once()
        mock_db.session.commit.assert_called_once()

    @patch("models.individual_match.services.db")
    def test_cancel_proposal_not_proposer(self, mock_db):
        """Test cancelling proposal by non-proposer."""
        mock_proposal = Mock()
        mock_proposal.proposer_id = 999
        mock_db.session.get.return_value = mock_proposal

        with pytest.raises(
            ValueError, match="Only the proposer can cancel the proposal"
        ):
            IndividualMatchService.cancel_proposal(123, 456)

    @patch("models.individual_match.services.IndividualMatchService.get_user_proposals")
    @patch("models.individual_match.services.IndividualMatchService.get_user_matches")
    @patch(
        "models.individual_match.services.IndividualMatchService.get_user_availability"
    )
    @patch(
        "models.individual_match.services.IndividualMatchService.get_user_statistics"
    )
    def test_get_user_dashboard_data(
        self, mock_stats, mock_availability, mock_matches, mock_proposals
    ):
        """Test getting user dashboard data."""
        mock_proposals_data = {"created": [], "received": []}
        mock_matches_data = [Mock()]
        mock_availability_data = {"by_location": {}}
        mock_stats_data = {"total_matches": 5}

        mock_proposals.return_value = mock_proposals_data
        mock_matches.return_value = mock_matches_data
        mock_availability.return_value = mock_availability_data
        mock_stats.return_value = mock_stats_data

        result = IndividualMatchService.get_user_dashboard_data(123)

        assert result["proposals"] == mock_proposals_data
        assert result["matches"] == mock_matches_data
        assert result["availability"] == mock_availability_data
        assert result["statistics"] == mock_stats_data

    @patch("models.individual_match.services.PlayerAvailability")
    def test_get_user_availability(self, mock_availability_class):
        """Test getting user availability."""
        mock_record1 = Mock()
        mock_record1.location = "Location1"
        mock_record1.is_available = True
        mock_record2 = Mock()
        mock_record2.location = "Location2"
        mock_record2.is_available = False

        mock_availability_class.query.filter_by.return_value.all.return_value = [
            mock_record1,
            mock_record2,
        ]

        result = IndividualMatchService.get_user_availability(123)

        assert len(result["availability_records"]) == 2
        assert "Location1" in result["available_locations"]
        assert "Location2" not in result["available_locations"]

    @patch("models.individual_match.services.datetime")
    @patch("models.individual_match.services.db")
    @patch("models.individual_match.services.IndividualRack")
    def test_submit_rack_result_success(self, mock_rack_class, mock_db, mock_datetime):
        """Test successful rack result submission."""
        mock_now = datetime(2024, 1, 20, 15, 30)
        mock_datetime.utcnow.return_value = mock_now

        mock_match = Mock()
        mock_match.player1_id = 123
        mock_match.player2_id = 456
        mock_match.player1_score = 2
        mock_match.player2_score = 1
        mock_match.is_complete.return_value = False
        mock_db.session.get.return_value = mock_match

        mock_rack = Mock()
        mock_rack_class.return_value = mock_rack
        mock_rack_class.query.filter_by.return_value.first.return_value = None

        result = IndividualMatchService.submit_rack_result(789, 123, 123, 4)

        assert result == mock_rack
        assert mock_match.player1_score == 3
        mock_db.session.add.assert_called_once_with(mock_rack)
        mock_db.session.commit.assert_called_once()

    @patch("models.individual_match.services.db")
    def test_submit_rack_result_user_not_in_match(self, mock_db):
        """Test submitting rack result by user not in match."""
        mock_match = Mock()
        mock_match.player1_id = 123
        mock_match.player2_id = 456
        mock_db.session.get.return_value = mock_match

        with pytest.raises(ValueError, match="User is not part of this match"):
            IndividualMatchService.submit_rack_result(789, 999, 123, 4)

    @patch("models.individual_match.services.db")
    @patch("models.individual_match.services.PlayerAvailability")
    def test_update_user_availability(self, mock_availability_class, mock_db):
        """Test updating user availability."""
        availability_data = [
            {
                "location": "Location1",
                "day_of_week": "monday",
                "start_time": "09:00",
                "end_time": "17:00",
                "is_available": True,
            }
        ]

        mock_availability = Mock()
        mock_availability_class.return_value = mock_availability

        IndividualMatchService.update_user_availability(123, availability_data)

        mock_availability_class.query.filter_by.assert_called_once_with(user_id=123)
        mock_db.session.commit.assert_called_once()

    @patch("models.individual_match.services.IndividualMatch")
    def test_get_user_matches(self, mock_match_class):
        """Test getting user matches."""
        mock_matches = [Mock(), Mock()]
        mock_match_class.query.filter.return_value.order_by.return_value.all.return_value = (
            mock_matches
        )

        result = IndividualMatchService.get_user_matches(123)

        assert result == mock_matches

    @patch("models.individual_match.services.db")
    def test_start_match_success(self, mock_db):
        """Test successfully starting a match."""
        mock_match = Mock()
        mock_match.player1_id = 123
        mock_match.player2_id = 456
        mock_db.session.get.return_value = mock_match

        result = IndividualMatchService.start_match(789, 123)

        assert result == mock_match
        mock_match.start_match.assert_called_once()
        mock_db.session.commit.assert_called_once()

    @patch("models.individual_match.services.db")
    def test_start_match_not_player(self, mock_db):
        """Test starting match by non-player."""
        mock_match = Mock()
        mock_match.player1_id = 123
        mock_match.player2_id = 456
        mock_db.session.get.return_value = mock_match

        with pytest.raises(ValueError, match="Only match players can start the match"):
            IndividualMatchService.start_match(789, 999)

    @patch("models.individual_match.services.db")
    def test_get_user_statistics_complete(self, mock_db):
        """Test getting comprehensive user statistics."""
        mock_match1 = Mock()
        mock_match1.winner_id = 123
        mock_match1.get_user_score.return_value = 5
        mock_match1.player1_score = 5
        mock_match1.player2_score = 3
        mock_match1.location = "Location1"

        mock_match2 = Mock()
        mock_match2.winner_id = 456
        mock_match2.get_user_score.return_value = 2
        mock_match2.player1_score = 2
        mock_match2.player2_score = 5
        mock_match2.location = "Location1"

        with patch.object(
            IndividualMatchService, "get_user_matches"
        ) as mock_get_matches:
            mock_get_matches.return_value = [mock_match1, mock_match2]

            result = IndividualMatchService.get_user_statistics(123)

            assert result["total_matches"] == 2
            assert result["won_matches"] == 1
            assert result["lost_matches"] == 1
            assert result["win_percentage"] == 50.0
            assert result["total_racks_won"] == 7
            assert result["total_racks_played"] == 15
            assert "locations_played" in result

    @patch("models.individual_match.services.db")
    def test_set_player_availability_new(self, mock_db):
        """Test setting availability for new location."""
        with patch(
            "models.individual_match.services.PlayerAvailability"
        ) as mock_availability_class:
            mock_availability_class.query.filter_by.return_value.first.return_value = (
                None
            )
            mock_availability = Mock()
            mock_availability_class.return_value = mock_availability

            result = IndividualMatchService.set_player_availability(
                123, "Location1", True
            )

            assert result == mock_availability
            mock_db.session.add.assert_called_once_with(mock_availability)
            mock_db.session.commit.assert_called_once()

    @patch("models.individual_match.services.PlayerAvailability")
    def test_get_player_availability(self, mock_availability_class):
        """Test getting player availability."""
        mock_records = [Mock(), Mock()]
        mock_availability_class.query.filter_by.return_value.all.return_value = (
            mock_records
        )

        result = IndividualMatchService.get_player_availability(123)

        assert result == mock_records

    @patch("models.individual_match.services.db")
    def test_expire_old_proposals(self, mock_db):
        """Test expiring old proposals."""
        with patch(
            "models.individual_match.services.MatchProposal"
        ) as mock_proposal_class:
            with patch("models.individual_match.services.datetime") as mock_datetime:
                mock_datetime.utcnow.return_value = datetime(2024, 1, 20)

                mock_proposal = Mock()

                # Mock query chain properly
                mock_query = Mock()
                mock_proposal_class.query = mock_query
                mock_query.filter.return_value.all.return_value = [mock_proposal]

                result = IndividualMatchService.expire_old_proposals()

                assert result == 1
                mock_proposal.expire.assert_called_once()
                mock_db.session.commit.assert_called_once()
