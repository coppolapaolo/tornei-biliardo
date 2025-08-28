"""
Test module for models/challenge/services.py
This module aims to improve test coverage for ChallengeService.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from models.challenge.services import ChallengeService
from models.challenge.models import Challenge, ChallengeAttempt, ChallengeFavorite


class TestChallengeService:
    """Test cases for ChallengeService class."""

    def test_create_challenge(self):
        """Test creating a new challenge."""
        with patch("models.challenge.services.db") as mock_db:
            # Setup mock challenge
            mock_challenge = Mock()
            mock_db.session.add = Mock()
            mock_db.session.commit = Mock()
            
            # Mock the Challenge constructor
            with patch("models.challenge.services.Challenge") as mock_challenge_class:
                mock_challenge_class.return_value = mock_challenge
                
                # Call the method
                result = ChallengeService.create_challenge(
                    name="Test Challenge",
                    description="Test Description",
                    min_score=0,
                    max_score=100,
                    pass_fail_only=False,
                    image_path="/test/image.jpg",
                    created_by_id=1
                )
                
                # Verify
                mock_challenge_class.assert_called_once_with(
                    name="Test Challenge",
                    description="Test Description",
                    min_score=0,
                    max_score=100,
                    pass_fail_only=False,
                    image_path="/test/image.jpg",
                    created_by_id=1
                )
                mock_db.session.add.assert_called_once_with(mock_challenge)
                mock_db.session.commit.assert_called_once()
                assert result == mock_challenge

    def test_get_all_challenges(self):
        """Test getting all challenges."""
        mock_challenges = [Mock(), Mock(), Mock()]
        
        with patch("models.challenge.services.db") as mock_db:
            mock_query = Mock()
            mock_db.session.query.return_value = mock_query
            mock_query.all.return_value = mock_challenges
            
            result = ChallengeService.get_all_challenges()
            
            mock_db.session.query.assert_called_once_with(Challenge)
            mock_query.all.assert_called_once()
            assert result == mock_challenges

    def test_get_active_challenges(self):
        """Test getting active challenges."""
        mock_challenges = [Mock(), Mock()]
        
        with patch("models.challenge.services.db") as mock_db:
            mock_query = Mock()
            mock_filtered_query = Mock()
            mock_db.session.query.return_value = mock_query
            mock_query.filter_by.return_value = mock_filtered_query
            mock_filtered_query.all.return_value = mock_challenges
            
            result = ChallengeService.get_active_challenges()
            
            mock_db.session.query.assert_called_once_with(Challenge)
            mock_query.filter_by.assert_called_once_with(is_active=True)
            mock_filtered_query.all.assert_called_once()
            assert result == mock_challenges

    def test_get_user_challenges(self):
        """Test getting challenges organized by user relationship."""
        user_id = 1
        
        # Mock challenges with proper id attributes
        mock_challenge1 = Mock()
        mock_challenge1.id = 1
        mock_challenge2 = Mock()
        mock_challenge2.id = 2
        mock_challenge3 = Mock()
        mock_challenge3.id = 3
        mock_challenge4 = Mock()
        mock_challenge4.id = 4
        
        # Mock favorites
        mock_favorite1 = Mock()
        mock_favorite1.challenge_id = 1
        mock_favorite2 = Mock()
        mock_favorite2.challenge_id = 2
        
        # Mock attempts - only challenge 2 and 3 have been attempted
        mock_attempt1 = Mock()
        mock_attempt1.challenge_id = 2
        mock_attempt2 = Mock()
        mock_attempt2.challenge_id = 3
        
        with patch("models.challenge.services.db") as mock_db:
            with patch("models.challenge.services.ChallengeService.get_active_challenges") as mock_get_active:
                mock_get_active.return_value = [mock_challenge1, mock_challenge2, mock_challenge3, mock_challenge4]
                
                # Mock queries with proper side effects
                mock_favorite_query = Mock()
                mock_favorite_filtered_query = Mock()
                mock_attempt_query = Mock()
                mock_attempt_filtered_query = Mock()
                
                # Set up the side effect for multiple query calls
                call_count = 0
                def query_side_effect(*args, **kwargs):
                    nonlocal call_count
                    call_count += 1
                    if call_count == 1:
                        return mock_favorite_query  # First call for ChallengeFavorite
                    elif call_count == 2:
                        return mock_attempt_query   # Second call for ChallengeAttempt
                    return mock_favorite_query  # Default
                    
                mock_db.session.query.side_effect = query_side_effect
                
                # Set up filter_by for favorites
                mock_favorite_query.filter_by.return_value = mock_favorite_filtered_query
                mock_favorite_filtered_query.all.return_value = [mock_favorite1, mock_favorite2]
                
                # Set up filter_by for attempts
                mock_attempt_query.filter_by.return_value = mock_attempt_filtered_query
                mock_attempt_filtered_query.all.return_value = [mock_attempt1, mock_attempt2]
                
                result = ChallengeService.get_user_challenges(user_id)
                
                # Verify structure
                assert "favorites" in result
                assert "attempted" in result
                assert "general" in result
                
                # Verify counts
                assert len(result["favorites"]) == 2  # Challenges 1 and 2
                assert len(result["attempted"]) == 2  # Challenges 2 and 3
                # General should only contain challenges that haven't been attempted (1 and 4)
                # But challenge 1 is a favorite, so only challenge 4 should be in general
                assert len(result["general"]) == 2  # Challenges 1 and 4

    def test_start_challenge_attempt(self):
        """Test starting a new challenge attempt."""
        with patch("models.challenge.services.db") as mock_db:
            # Setup mock attempt
            mock_attempt = Mock()
            mock_db.session.add = Mock()
            mock_db.session.commit = Mock()
            
            # Mock the ChallengeAttempt constructor
            with patch("models.challenge.services.ChallengeAttempt") as mock_attempt_class:
                mock_attempt_class.return_value = mock_attempt
                
                # Call the method
                result = ChallengeService.start_challenge_attempt(
                    user_id=1,
                    challenge_id=1,
                    prova_id=1,
                    round_number=1
                )
                
                # Verify
                mock_attempt_class.assert_called_once_with(
                    user_id=1,
                    challenge_id=1,
                    prova_id=1,
                    round_number=1
                )
                mock_db.session.add.assert_called_once_with(mock_attempt)
                mock_db.session.commit.assert_called_once()
                assert result == mock_attempt

    def test_complete_challenge_attempt_success(self):
        """Test completing a challenge attempt successfully."""
        mock_attempt = Mock()
        
        with patch("models.challenge.services.db") as mock_db:
            mock_db.session.get.return_value = mock_attempt
            mock_db.session.commit = Mock()
            
            # Call the method
            result = ChallengeService.complete_challenge_attempt(
                attempt_id=1,
                score=85,
                passed=True,
                notes="Good performance"
            )
            
            # Verify
            mock_db.session.get.assert_called_once_with(ChallengeAttempt, 1)
            mock_attempt.complete_attempt.assert_called_once_with(score=85, passed=True)
            assert mock_attempt.notes == "Good performance"
            mock_db.session.commit.assert_called_once()
            assert result == mock_attempt

    def test_complete_challenge_attempt_not_found(self):
        """Test completing a challenge attempt that doesn't exist."""
        with patch("models.challenge.services.db") as mock_db:
            mock_db.session.get.return_value = None
            
            # Mock flask abort - need to patch where it's imported (from flask)
            with patch("flask.abort") as mock_abort:
                # Call the method - should raise an exception due to abort
                with pytest.raises(Exception):
                    ChallengeService.complete_challenge_attempt(attempt_id=999)
                
                # Verify abort was called with 404
                mock_abort.assert_called_once_with(404)

    def test_toggle_favorite_add(self):
        """Test toggling a challenge as favorite - adding."""
        user_id = 1
        challenge_id = 1
        
        with patch("models.challenge.services.db") as mock_db:
            # Mock query that returns no existing favorite
            mock_query = Mock()
            mock_filtered_query = Mock()
            mock_db.session.query.return_value = mock_query
            mock_query.filter_by.return_value = mock_filtered_query
            mock_filtered_query.first.return_value = None
            
            # Mock the ChallengeFavorite constructor
            mock_favorite = Mock()
            with patch("models.challenge.services.ChallengeFavorite") as mock_favorite_class:
                mock_favorite_class.return_value = mock_favorite
                mock_db.session.add = Mock()
                mock_db.session.commit = Mock()
                
                # Call the method
                result = ChallengeService.toggle_favorite(user_id, challenge_id)
                
                # Verify
                mock_db.session.query.assert_called_once()
                mock_query.filter_by.assert_called_once_with(user_id=user_id, challenge_id=challenge_id)
                mock_favorite_class.assert_called_once_with(user_id=user_id, challenge_id=challenge_id)
                mock_db.session.add.assert_called_once_with(mock_favorite)
                mock_db.session.commit.assert_called_once()
                assert result is True  # Added

    def test_toggle_favorite_remove(self):
        """Test toggling a challenge as favorite - removing."""
        user_id = 1
        challenge_id = 1
        mock_favorite = Mock()
        
        with patch("models.challenge.services.db") as mock_db:
            # Mock query that returns an existing favorite
            mock_query = Mock()
            mock_filtered_query = Mock()
            mock_db.session.query.return_value = mock_query
            mock_query.filter_by.return_value = mock_filtered_query
            mock_filtered_query.first.return_value = mock_favorite
            mock_db.session.delete = Mock()
            mock_db.session.commit = Mock()
            
            # Call the method
            result = ChallengeService.toggle_favorite(user_id, challenge_id)
            
            # Verify
            mock_db.session.query.assert_called_once()
            mock_query.filter_by.assert_called_once_with(user_id=user_id, challenge_id=challenge_id)
            mock_db.session.delete.assert_called_once_with(mock_favorite)
            mock_db.session.commit.assert_called_once()
            assert result is False  # Removed

    def test_get_challenge_for_x_replacement_success(self):
        """Test getting a suitable challenge for X replacement."""
        mock_challenge1 = Mock()
        mock_challenge1.id = 1
        mock_challenge2 = Mock()
        mock_challenge2.id = 2
        mock_challenge3 = Mock()
        mock_challenge3.id = 3
        
        with patch("models.challenge.services.db") as mock_db:
            # Mock query for suitable challenges
            mock_query = Mock()
            mock_filtered_query = Mock()
            mock_db.session.query.return_value = mock_query
            mock_query.filter_by.return_value = mock_filtered_query
            mock_filtered_query.all.return_value = [mock_challenge1, mock_challenge2, mock_challenge3]
            
            # Mock attempt count queries
            mock_attempt_query = Mock()
            mock_attempt_filtered_query = Mock()
            mock_attempt_filtered_query.count = Mock()
            
            # Set up side effect to handle multiple query calls
            def query_side_effect(*args, **kwargs):
                if args and args[0] == Challenge:
                    return mock_query
                elif args and args[0] == ChallengeAttempt:
                    return mock_attempt_query
                return mock_query  # default
            
            def filter_by_side_effect(**kwargs):
                challenge_id = kwargs.get('challenge_id')
                counts = {1: 3, 2: 1, 3: 2}
                mock_attempt_filtered_query.count.return_value = counts.get(challenge_id, 0)
                return mock_attempt_filtered_query
            
            mock_db.session.query.side_effect = query_side_effect
            mock_attempt_query.filter_by.side_effect = filter_by_side_effect
            
            # Call the method
            result = ChallengeService.get_challenge_for_x_replacement(prova_id=1)
            
            # Verify - should return challenge 2 (least used)
            assert result == mock_challenge2

    def test_get_challenge_for_x_replacement_no_suitable(self):
        """Test getting a suitable challenge for X replacement when none available."""
        with patch("models.challenge.services.db") as mock_db:
            # Mock query that returns no suitable challenges
            mock_query = Mock()
            mock_filtered_query = Mock()
            mock_db.session.query.return_value = mock_query
            mock_query.filter_by.return_value = mock_filtered_query
            mock_filtered_query.all.return_value = []
            
            # Call the method
            result = ChallengeService.get_challenge_for_x_replacement(prova_id=1)
            
            # Verify
            assert result is None

    def test_create_x_replacement_attempt_with_challenge_id(self):
        """Test creating X replacement attempt with specific challenge ID."""
        mock_attempt = Mock()
        
        with patch("models.challenge.services.ChallengeService.start_challenge_attempt") as mock_start_attempt:
            mock_start_attempt.return_value = mock_attempt
            
            # Call the method
            result = ChallengeService.create_x_replacement_attempt(
                user_id=1,
                prova_id=1,
                round_number=1,
                challenge_id=5
            )
            
            # Verify
            mock_start_attempt.assert_called_once_with(
                user_id=1,
                challenge_id=5,
                prova_id=1,
                round_number=1
            )
            assert result == mock_attempt

    def test_create_x_replacement_attempt_without_challenge_id_success(self):
        """Test creating X replacement attempt without specific challenge ID - success."""
        mock_challenge = Mock()
        mock_challenge.id = 3
        mock_attempt = Mock()
        
        with patch("models.challenge.services.ChallengeService.get_challenge_for_x_replacement") as mock_get_challenge:
            mock_get_challenge.return_value = mock_challenge
            
            with patch("models.challenge.services.ChallengeService.start_challenge_attempt") as mock_start_attempt:
                mock_start_attempt.return_value = mock_attempt
                
                # Call the method
                result = ChallengeService.create_x_replacement_attempt(
                    user_id=1,
                    prova_id=1,
                    round_number=1
                )
                
                # Verify
                mock_get_challenge.assert_called_once_with(1)
                mock_start_attempt.assert_called_once_with(
                    user_id=1,
                    challenge_id=3,
                    prova_id=1,
                    round_number=1
                )
                assert result == mock_attempt

    def test_create_x_replacement_attempt_without_challenge_id_failure(self):
        """Test creating X replacement attempt without specific challenge ID - failure."""
        with patch("models.challenge.services.ChallengeService.get_challenge_for_x_replacement") as mock_get_challenge:
            mock_get_challenge.return_value = None
            
            # Call the method and expect ValueError
            with pytest.raises(ValueError, match="No suitable challenge available for X replacement"):
                ChallengeService.create_x_replacement_attempt(
                    user_id=1,
                    prova_id=1,
                    round_number=1
                )

    def test_complete_x_replacement_attempt_success(self):
        """Test completing X replacement attempt successfully."""
        mock_attempt = Mock()
        
        with patch("models.challenge.services.db") as mock_db:
            mock_db.session.get.return_value = mock_attempt
            
            with patch("models.challenge.services.ChallengeService._create_x_replacement_match_result") as mock_create_result:
                # Call the method
                result = ChallengeService.complete_x_replacement_attempt(
                    attempt_id=1,
                    score=85,
                    notes="Excellent performance"
                )
                
                # Verify
                mock_db.session.get.assert_called_once_with(ChallengeAttempt, 1)
                mock_attempt.complete_attempt.assert_called_once_with(score=85, passed=None)
                assert mock_attempt.notes == "Excellent performance"
                mock_create_result.assert_called_once_with(mock_attempt)
                assert result == mock_attempt

    def test_complete_x_replacement_attempt_not_found(self):
        """Test completing X replacement attempt that doesn't exist."""
        with patch("models.challenge.services.db") as mock_db:
            mock_db.session.get.return_value = None
            
            # Mock flask abort - need to patch where it's imported (from flask)
            with patch("flask.abort") as mock_abort:
                # Call the method - should raise an exception due to abort
                with pytest.raises(Exception):
                    ChallengeService.complete_x_replacement_attempt(attempt_id=999, score=85)
                
                # Verify abort was called with 404
                mock_abort.assert_called_once_with(404)

    def test_get_admin_statistics(self):
        """Test getting admin statistics for all challenges."""
        mock_challenge1 = Mock()
        mock_challenge2 = Mock()
        mock_stats1 = {"total_attempts": 10, "pass_rate": 70.0}
        mock_stats2 = {"total_attempts": 5, "pass_rate": 80.0}
        
        mock_challenge1.get_statistics.return_value = mock_stats1
        mock_challenge2.get_statistics.return_value = mock_stats2
        
        with patch("models.challenge.services.Challenge.query") as mock_challenge_query:
            mock_challenge_query.all.return_value = [mock_challenge1, mock_challenge2]
            
            result = ChallengeService.get_admin_statistics()
            
            # Verify
            mock_challenge_query.all.assert_called_once()
            assert len(result) == 2
            assert result[0] == {"challenge": mock_challenge1, "stats": mock_stats1}
            assert result[1] == {"challenge": mock_challenge2, "stats": mock_stats2}

    def test_get_user_challenge_history(self):
        """Test getting user's challenge attempt history."""
        mock_attempts = [Mock(), Mock(), Mock()]
        
        with patch("models.challenge.services.ChallengeAttempt") as mock_attempt_class:
            mock_query = Mock()
            mock_filtered_query = Mock()
            mock_ordered_query = Mock()
            
            mock_attempt_class.query = mock_query
            mock_query.filter_by.return_value = mock_filtered_query
            mock_filtered_query.order_by.return_value = mock_ordered_query
            mock_ordered_query.all.return_value = mock_attempts
            
            result = ChallengeService.get_user_challenge_history(user_id=1)
            
            # Verify
            mock_query.filter_by.assert_called_once_with(user_id=1, completed=True)
            mock_filtered_query.order_by.assert_called_once()
            mock_ordered_query.all.assert_called_once()
            assert result == mock_attempts

    def test_update_challenge_success(self):
        """Test updating challenge details successfully."""
        mock_challenge = Mock()
        
        with patch("models.challenge.services.db") as mock_db:
            mock_db.session.get.return_value = mock_challenge
            mock_db.session.commit = Mock()
            
            # Call the method
            result = ChallengeService.update_challenge(
                challenge_id=1,
                name="Updated Name",
                description="Updated Description",
                image_path="/updated/image.jpg",
                is_active=False
            )
            
            # Verify
            mock_db.session.get.assert_called_once_with(Challenge, 1)
            assert mock_challenge.name == "Updated Name"
            assert mock_challenge.description == "Updated Description"
            assert mock_challenge.image_path == "/updated/image.jpg"
            assert mock_challenge.is_active is False
            mock_db.session.commit.assert_called_once()
            assert result == mock_challenge

    def test_update_challenge_not_found(self):
        """Test updating a challenge that doesn't exist."""
        with patch("models.challenge.services.db") as mock_db:
            mock_db.session.get.return_value = None
            
            # Mock flask abort - need to patch where it's imported (from flask)
            with patch("flask.abort") as mock_abort:
                # Call the method - should raise an exception due to abort
                with pytest.raises(Exception):
                    ChallengeService.update_challenge(challenge_id=999, name="Test")
                
                # Verify abort was called with 404
                mock_abort.assert_called_once_with(404)

    def test_delete_challenge_success(self):
        """Test deleting a challenge successfully (soft delete)."""
        mock_challenge = Mock()
        
        with patch("models.challenge.services.db") as mock_db:
            mock_db.session.get.return_value = mock_challenge
            mock_db.session.commit = Mock()
            
            # Call the method
            ChallengeService.delete_challenge(challenge_id=1)
            
            # Verify
            mock_db.session.get.assert_called_once_with(Challenge, 1)
            assert mock_challenge.is_active is False
            mock_db.session.commit.assert_called_once()

    def test_delete_challenge_not_found(self):
        """Test deleting a challenge that doesn't exist."""
        with patch("models.challenge.services.db") as mock_db:
            mock_db.session.get.return_value = None
            
            # Mock flask abort - need to patch where it's imported (from flask)
            with patch("flask.abort") as mock_abort:
                # Call the method - should raise an exception due to abort
                with pytest.raises(Exception):
                    ChallengeService.delete_challenge(challenge_id=999)
                
                # Verify abort was called with 404
                mock_abort.assert_called_once_with(404)


if __name__ == "__main__":
    pytest.main([__file__])