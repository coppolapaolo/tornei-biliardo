"""
Additional test module for models/individual_match/services.py
This module aims to improve test coverage for IndividualMatchService.
"""

import pytest
from unittest.mock import Mock, patch
from datetime import datetime, timedelta
from models.individual_match.services import IndividualMatchService
from models.individual_match.models import (
    ProposalType,
    ProposalStatus,
    MatchStatus,
    IndividualMatch,
    MatchProposal,
    ProposalInvitation,
    PlayerAvailability,
)


class TestIndividualMatchServiceAdditional:
    """Additional test cases for IndividualMatchService class."""

    def test_get_user_proposals_with_expired(self):
        """Test getting user proposals including expired ones."""
        mock_proposal1 = Mock()
        mock_proposal2 = Mock()
        mock_proposal3 = Mock()
        
        with patch("models.individual_match.services.MatchProposal") as mock_proposal_class:
            with patch("models.individual_match.services.ProposalInvitation") as mock_invitation_class:
                with patch("models.individual_match.services.PlayerAvailability") as mock_availability_class:
                    with patch("models.individual_match.services.IndividualMatch") as mock_match_class:
                        # Mock query chain for created proposals
                        mock_query = Mock()
                        mock_proposal_class.query.filter_by.return_value = mock_query
                        mock_query.all.return_value = [mock_proposal1]
                        
                        # Mock query chain for received invitations
                        mock_join_query = Mock()
                        mock_join_filter = Mock()
                        mock_query.join.return_value = mock_join_query
                        mock_join_query.filter.return_value = mock_join_filter
                        mock_join_filter.all.return_value = [mock_proposal2]
                        
                        # Mock query for open proposals
                        mock_open_query = Mock()
                        mock_open_filter1 = Mock()
                        mock_open_filter2 = Mock()
                        mock_query.filter.return_value = mock_open_query
                        mock_open_query.filter_by.return_value = mock_open_filter1
                        mock_open_filter1.filter.return_value = mock_open_filter2
                        mock_open_filter2.all.return_value = [mock_proposal3]
                        
                        # Mock availability records
                        mock_availability = Mock()
                        mock_availability.location = "Test Location"
                        mock_availability_class.query.filter_by.return_value.all.return_value = [mock_availability]
                        
                        # Mock played matches
                        mock_played_match = Mock()
                        mock_played_match.location = "Played Location"
                        mock_filter_query = Mock()
                        mock_match_class.query.filter.return_value = mock_filter_query
                        mock_filter_query.all.return_value = [mock_played_match]
                        
                        result = IndividualMatchService.get_user_proposals(1, include_expired=True)
                        
                        # Verify result structure
                        assert "created" in result
                        assert "received" in result
                        assert "available" in result
                        assert len(result["created"]) == 1
                        assert len(result["received"]) == 1
                        assert len(result["available"]) == 1

    def test_accept_proposal_not_found(self):
        """Test accepting a proposal that doesn't exist."""
        with patch("models.individual_match.services.db") as mock_db:
            mock_db.session.get.return_value = None
            
            with pytest.raises(Exception):  # Flask abort raises an exception
                IndividualMatchService.accept_proposal(1, 999)

    def test_accept_proposal_cannot_accept(self):
        """Test accepting a proposal that user cannot accept."""
        mock_proposal = Mock()
        mock_proposal.can_be_accepted_by.return_value = False
        
        with patch("models.individual_match.services.db") as mock_db:
            mock_db.session.get.return_value = mock_proposal
            
            with pytest.raises(ValueError, match="User cannot accept this proposal"):
                IndividualMatchService.accept_proposal(1, 1)

    def test_reject_invitation_not_found(self):
        """Test rejecting an invitation that doesn't exist."""
        with patch("models.individual_match.services.ProposalInvitation") as mock_invitation_class:
            mock_query = Mock()
            mock_invitation_class.query.filter_by.return_value = mock_query
            mock_query.first_or_404.side_effect = Exception("Not found")
            
            with pytest.raises(Exception):
                IndividualMatchService.reject_invitation(1, 1)

    def test_cancel_proposal_not_found(self):
        """Test canceling a proposal that doesn't exist."""
        with patch("models.individual_match.services.db") as mock_db:
            mock_db.session.get.return_value = None
            
            with pytest.raises(Exception):  # Flask abort raises an exception
                IndividualMatchService.cancel_proposal(1, 999)

    def test_cancel_proposal_not_proposer(self):
        """Test canceling a proposal when user is not the proposer."""
        mock_proposal = Mock()
        mock_proposal.proposer_id = 2  # Different user
        
        with patch("models.individual_match.services.db") as mock_db:
            mock_db.session.get.return_value = mock_proposal
            
            with pytest.raises(ValueError, match="Only the proposer can cancel the proposal"):
                IndividualMatchService.cancel_proposal(1, 1)

    def test_cancel_proposal_not_pending(self):
        """Test canceling a proposal that is not pending."""
        mock_proposal = Mock()
        mock_proposal.proposer_id = 1
        mock_proposal.status = ProposalStatus.ACCEPTED  # Not pending
        
        with patch("models.individual_match.services.db") as mock_db:
            mock_db.session.get.return_value = mock_proposal
            
            with pytest.raises(ValueError, match="Proposal cannot be cancelled - it's not pending"):
                IndividualMatchService.cancel_proposal(1, 1)

    def test_submit_rack_result_match_not_found(self):
        """Test submitting rack result for a match that doesn't exist."""
        with patch("models.individual_match.services.db") as mock_db:
            mock_db.session.get.return_value = None
            
            with pytest.raises(Exception):  # Flask abort raises an exception
                IndividualMatchService.submit_rack_result(999, 1, 1, 1)

    def test_submit_rack_result_user_not_in_match(self):
        """Test submitting rack result when user is not part of the match."""
        mock_match = Mock()
        mock_match.player1_id = 2
        mock_match.player2_id = 3  # User 1 is not in this match
        
        with patch("models.individual_match.services.db") as mock_db:
            mock_db.session.get.return_value = mock_match
            
            with pytest.raises(ValueError, match="User is not part of this match"):
                IndividualMatchService.submit_rack_result(1, 1, 1, 1)

    def test_submit_rack_result_invalid_winner(self):
        """Test submitting rack result with invalid winner."""
        mock_match = Mock()
        mock_match.player1_id = 1
        mock_match.player2_id = 2
        
        with patch("models.individual_match.services.db") as mock_db:
            mock_db.session.get.return_value = mock_match
            
            with pytest.raises(ValueError, match="Invalid winner ID"):
                IndividualMatchService.submit_rack_result(1, 1, 3, 1)  # Winner 3 is not in match

    def test_submit_rack_result_duplicate_rack(self):
        """Test submitting rack result for a rack that already exists."""
        mock_match = Mock()
        mock_match.player1_id = 1
        mock_match.player2_id = 2
        mock_match.is_complete.return_value = False
        
        mock_existing_rack = Mock()
        
        with patch("models.individual_match.services.db") as mock_db:
            mock_db.session.get.return_value = mock_match
            
            with patch("models.individual_match.services.IndividualRack") as mock_rack_class:
                mock_query = Mock()
                mock_rack_class.query.filter_by.return_value = mock_query
                mock_query.first.return_value = mock_existing_rack
                
                with pytest.raises(ValueError, match="Rack 1 already recorded"):
                    IndividualMatchService.submit_rack_result(1, 1, 1, 1)

    def test_update_user_availability(self):
        """Test updating user availability settings."""
        availability_data = [
            {
                "location": "Location 1",
                "day_of_week": "Monday",
                "start_time": "09:00",
                "end_time": "12:00",
                "is_available": True,
            },
            {
                "location": "Location 2",
                "day_of_week": "Tuesday",
                "start_time": "14:00",
                "end_time": "18:00",
                "is_available": False,
            }
        ]
        
        with patch("models.individual_match.services.PlayerAvailability") as mock_availability_class:
            with patch("models.individual_match.services.db") as mock_db:
                # Mock the delete operation
                mock_query = Mock()
                mock_availability_class.query.filter_by.return_value = mock_query
                
                IndividualMatchService.update_user_availability(1, availability_data)
                
                # Verify delete was called
                mock_query.delete.assert_called_once()
                
                # Verify two new availability records were added
                assert mock_db.session.add.call_count == 2
                mock_db.session.commit.assert_called_once()

    def test_get_user_matches(self):
        """Test getting user matches."""
        mock_match1 = Mock()
        mock_match2 = Mock()
        
        with patch("models.individual_match.services.IndividualMatch") as mock_match_class:
            mock_query = Mock()
            mock_match_class.query.filter.return_value = mock_query
            mock_query.order_by.return_value.all.return_value = [mock_match1, mock_match2]
            
            result = IndividualMatchService.get_user_matches(1)
            
            assert len(result) == 2
            assert result[0] == mock_match1
            assert result[1] == mock_match2

    def test_start_match_not_found(self):
        """Test starting a match that doesn't exist."""
        with patch("models.individual_match.services.db") as mock_db:
            mock_db.session.get.return_value = None
            
            with pytest.raises(Exception):  # Flask abort raises an exception
                IndividualMatchService.start_match(999, 1)

    def test_start_match_user_not_player(self):
        """Test starting a match when user is not a player."""
        mock_match = Mock()
        mock_match.player1_id = 2
        mock_match.player2_id = 3  # User 1 is not a player
        
        with patch("models.individual_match.services.db") as mock_db:
            mock_db.session.get.return_value = mock_match
            
            with pytest.raises(ValueError, match="Only match players can start the match"):
                IndividualMatchService.start_match(1, 1)

    def test_add_rack_result_not_found(self):
        """Test adding rack result to a match that doesn't exist."""
        with patch("models.individual_match.services.db") as mock_db:
            mock_db.session.get.return_value = None
            
            with pytest.raises(Exception):  # Flask abort raises an exception
                IndividualMatchService.add_rack_result(999, 1, 1)

    def test_add_rack_result_user_not_player(self):
        """Test adding rack result when user is not a player."""
        mock_match = Mock()
        mock_match.player1_id = 2
        mock_match.player2_id = 3  # User 1 is not a player
        
        with patch("models.individual_match.services.db") as mock_db:
            mock_db.session.get.return_value = mock_match
            
            with pytest.raises(ValueError, match="Only match players can add rack results"):
                IndividualMatchService.add_rack_result(1, 1, 1)

    def test_complete_match_not_found(self):
        """Test completing a match that doesn't exist."""
        with patch("models.individual_match.services.db") as mock_db:
            mock_db.session.get.return_value = None
            
            with pytest.raises(Exception):  # Flask abort raises an exception
                IndividualMatchService.complete_match(999, 1, 1)

    def test_complete_match_user_not_player(self):
        """Test completing a match when user is not a player."""
        mock_match = Mock()
        mock_match.player1_id = 2
        mock_match.player2_id = 3  # User 1 is not a player
        
        with patch("models.individual_match.services.db") as mock_db:
            mock_db.session.get.return_value = mock_match
            
            with pytest.raises(ValueError, match="Only match players can complete the match"):
                IndividualMatchService.complete_match(1, 1, 1)

    def test_cancel_match_not_found(self):
        """Test canceling a match that doesn't exist."""
        with patch("models.individual_match.services.db") as mock_db:
            mock_db.session.get.return_value = None
            
            with pytest.raises(Exception):  # Flask abort raises an exception
                IndividualMatchService.cancel_match(999, 1, "Test reason")

    def test_cancel_match_user_not_player(self):
        """Test canceling a match when user is not a player."""
        mock_match = Mock()
        mock_match.player1_id = 2
        mock_match.player2_id = 3  # User 1 is not a player
        
        with patch("models.individual_match.services.db") as mock_db:
            mock_db.session.get.return_value = mock_match
            
            with pytest.raises(ValueError, match="Only match players can cancel the match"):
                IndividualMatchService.cancel_match(1, 1, "Test reason")


if __name__ == "__main__":
    pytest.main([__file__])