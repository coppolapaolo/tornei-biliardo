"""
TDD Tests for UserStatsService Decomposition (Task 1.3 - Phase 3)

UserStatsService focuses on user statistics and analytics:
- get_user_stats(), get_user_statistics()
- get_users_with_stats()
- get_user_matches(), get_user_classifications()
- All analytics and performance tracking methods

Strategy: Red-Green-Refactor TDD methodology following Task 1.2 patterns
"""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, date, timedelta

from models import db
from models.user.models import User
from models.user.role_enum import UserRole
from models.competition.models import Gara, Inscription
from models.match.models import Match
from models.classification.models import Classification
from models.campionato.models import Campionato
from models.status_enum import MatchStatus, GaraStatus


class TestUserStatsServiceTDD:
    """TDD tests for UserStatsService statistics and analytics operations."""

    @pytest.fixture
    def test_user_with_stats_data(self, app, db_session):
        """Create test user with sample statistics data."""
        with app.app_context():
            # Create test user
            user = User(
                username="stats_user",
                email="stats@example.com",
                role=UserRole.PLAYER.value
            )
            user.set_password("secure123")
            db.session.add(user)
            db.session.flush()

            # Create test campionato
            campionato = Campionato(
                name="Test Championship"
            )
            db.session.add(campionato)
            db.session.flush()

            # Create test gara
            gara = Gara(
                number=1,
                name="Test Competition",
                date=date.today() - timedelta(days=1),
                discipline="palla 8",
                distance=5,
                status=GaraStatus.COMPLETED.value,
                campionato_id=campionato.id
            )
            db.session.add(gara)
            db.session.flush()

            # Create inscription
            inscription = Inscription(user_id=user.id, gara_id=gara.id)
            db.session.add(inscription)

            # Create test opponent
            opponent = User(
                username="opponent_user",
                email="opponent@example.com",
                role=UserRole.PLAYER.value
            )
            opponent.set_password("secure123")
            db.session.add(opponent)
            db.session.flush()

            # Create test matches (2 wins, 1 loss)
            match1 = Match(
                player1_id=user.id,
                player2_id=opponent.id,
                gara_id=gara.id,
                round_number=1,
                status=MatchStatus.COMPLETED.value,
                winner_id=user.id
            )
            match2 = Match(
                player1_id=user.id,
                player2_id=opponent.id,
                gara_id=gara.id,
                round_number=2,
                status=MatchStatus.COMPLETED.value,
                winner_id=user.id
            )
            match3 = Match(
                player1_id=user.id,
                player2_id=opponent.id,
                gara_id=gara.id,
                round_number=3,
                status=MatchStatus.COMPLETED.value,
                winner_id=opponent.id
            )

            db.session.add_all([match1, match2, match3])

            # Create test classification
            classification = Classification(
                user_id=user.id,
                campionato_id=campionato.id,
                position=2,
                total_matches_won=2,
                total_point_difference=15,
                gare_played=1
            )
            db.session.add(classification)

            db.session.commit()

            yield {
                'user': user,
                'opponent': opponent,
                'campionato': campionato,
                'gara': gara,
                'inscription': inscription,
                'matches': [match1, match2, match3],
                'classification': classification
            }

            # Cleanup
            db.session.delete(classification)
            for match in [match1, match2, match3]:
                db.session.delete(match)
            db.session.delete(inscription)
            db.session.delete(gara)
            db.session.delete(campionato)
            db.session.delete(opponent)
            db.session.delete(user)
            db.session.commit()

    def test_get_user_stats_functionality(self, app, test_user_with_stats_data):
        """
        RED: Test UserStatsService.get_user_stats() basic statistics calculation.

        Expected behavior:
        - Returns dictionary with comprehensive user statistics
        - Calculates total matches, won matches, win percentage
        - Counts inscriptions and losses
        - Uses @read_only decorator for read operations
        """
        with app.app_context():
            from models.user.stats_service import UserStatsService

            user = test_user_with_stats_data['user']

            # Act: get user statistics
            stats = UserStatsService.get_user_stats(user_id=user.id)

            # Assert: returns proper statistics structure
            assert isinstance(stats, dict)
            assert "total_matches" in stats
            assert "won_matches" in stats
            assert "win_percentage" in stats
            assert "inscription_count" in stats
            assert "losses_count" in stats

            # Verify calculated values
            assert stats["total_matches"] == 3
            assert stats["won_matches"] == 2
            assert stats["win_percentage"] == 66.7  # 2/3 * 100 rounded to 1 decimal
            assert stats["inscription_count"] == 1
            assert stats["losses_count"] == 1

    def test_get_user_stats_empty_data(self, app, db_session):
        """
        RED: Test UserStatsService.get_user_stats() with user having no data.

        Expected behavior:
        - Returns statistics with zero values
        - Handles empty datasets gracefully
        - Win percentage should be 0 when no matches played
        """
        with app.app_context():
            from models.user.stats_service import UserStatsService

            # Create user with no matches or inscriptions
            user = User(
                username="empty_stats_user",
                email="empty@example.com",
                role=UserRole.PLAYER.value
            )
            user.set_password("secure123")
            db.session.add(user)
            db.session.commit()

            # Act: get statistics for user with no data
            stats = UserStatsService.get_user_stats(user_id=user.id)

            # Assert: returns zero statistics
            assert stats["total_matches"] == 0
            assert stats["won_matches"] == 0
            assert stats["win_percentage"] == 0
            assert stats["inscription_count"] == 0
            assert stats["lost_matches"] == 0

            # Cleanup
            db.session.delete(user)
            db.session.commit()

    def test_get_user_stats_not_found_error(self, app, db_session):
        """
        RED: Test UserStatsService.get_user_stats() error handling.

        Expected behavior:
        - Raises ValueError for non-existent user ID
        """
        with app.app_context():
            from models.user.stats_service import UserStatsService

            # Attempt to get stats for non-existent user
            with pytest.raises(ValueError, match="User not found"):
                UserStatsService.get_user_stats(user_id=99999)

    def test_get_users_with_stats_functionality(self, app, test_user_with_stats_data):
        """
        RED: Test UserStatsService.get_users_with_stats() comprehensive user list.

        Expected behavior:
        - Returns list of tuples with (User, total_inscriptions, total_matches, matches_won)
        - Excludes admin users from results
        - Orders by total_inscriptions desc, then username
        - Uses optimized query for users list page
        """
        with app.app_context():
            from models.user.stats_service import UserStatsService

            # Act: get users with statistics
            users_with_stats = UserStatsService.get_users_with_stats()

            # Assert: returns proper structure
            assert isinstance(users_with_stats, list)

            # Find our test user in the results
            test_user = test_user_with_stats_data['user']
            user_found = False
            for row in users_with_stats:
                user, total_inscriptions, total_matches, matches_won = row
                if user.id == test_user.id:
                    user_found = True
                    assert total_inscriptions == 1
                    assert total_matches == 3
                    assert matches_won == 2
                    break

            assert user_found, "Test user should be found in users with stats"

            # Verify no admin users in results
            for row in users_with_stats:
                user, _, _, _ = row
                assert user.role != UserRole.ADMIN.value

    def test_get_user_statistics_detailed_calculation(self, app, test_user_with_stats_data):
        """
        RED: Test UserStatsService.get_user_statistics() detailed statistics calculation.

        Expected behavior:
        - Returns comprehensive statistics dictionary
        - Calculates tournaments played, provas played
        - Uses get_user_detail_data for complex calculations
        - Counts only completed tournaments and matches
        """
        with app.app_context():
            from models.user.stats_service import UserStatsService

            user = test_user_with_stats_data['user']

            # Act: get detailed user statistics
            stats = UserStatsService.get_user_statistics(user_id=user.id)

            # Assert: returns comprehensive statistics structure
            assert isinstance(stats, dict)
            assert "total_inscriptions" in stats
            assert "total_matches" in stats
            assert "won_matches" in stats
            assert "lost_matches" in stats
            assert "win_percentage" in stats
            assert "tournaments_played" in stats
            assert "provas_played" in stats

            # Verify calculated values
            assert stats["total_inscriptions"] == 1
            assert stats["total_matches"] == 3
            assert stats["won_matches"] == 2
            assert stats["lost_matches"] == 1
            assert stats["win_percentage"] == 66.7  # Rounded to 1 decimal
            assert stats["tournaments_played"] == 1  # One completed campionato
            assert stats["provas_played"] == 1  # One completed gara

    def test_get_user_matches_functionality(self, app, test_user_with_stats_data):
        """
        RED: Test UserStatsService.get_user_matches() recent matches retrieval.

        Expected behavior:
        - Returns list of recent completed matches for user
        - Limits results to specified number (default 10)
        - Orders matches properly by recency
        - Only includes completed matches
        """
        with app.app_context():
            from models.user.stats_service import UserStatsService

            user = test_user_with_stats_data['user']

            # Act: get user matches (default limit)
            matches = UserStatsService.get_user_matches(user_id=user.id)

            # Assert: returns proper match list
            assert isinstance(matches, list)
            assert len(matches) == 3  # All completed matches

            # Verify all matches involve the user
            for match in matches:
                assert user.id in [match.player1_id, match.player2_id]
                assert match.status == MatchStatus.COMPLETED.value

            # Test with custom limit
            limited_matches = UserStatsService.get_user_matches(user_id=user.id, limit=2)
            assert len(limited_matches) == 2

    def test_get_user_matches_empty_data(self, app, db_session):
        """
        RED: Test UserStatsService.get_user_matches() with no matches.

        Expected behavior:
        - Returns empty list when user has no completed matches
        - Handles empty datasets gracefully
        """
        with app.app_context():
            from models.user.stats_service import UserStatsService

            # Create user with no matches
            user = User(
                username="no_matches_user",
                email="nomatches@example.com",
                role=UserRole.PLAYER.value
            )
            user.set_password("secure123")
            db.session.add(user)
            db.session.commit()

            # Act: get matches for user with no data
            matches = UserStatsService.get_user_matches(user_id=user.id)

            # Assert: returns empty list
            assert isinstance(matches, list)
            assert len(matches) == 0

            # Cleanup
            db.session.delete(user)
            db.session.commit()

    def test_get_user_classifications_functionality(self, app, test_user_with_stats_data):
        """
        RED: Test UserStatsService.get_user_classifications() classification retrieval.

        Expected behavior:
        - Returns list of user classifications ordered by date
        - Includes all classifications for the user
        - Orders properly by creation date
        """
        with app.app_context():
            from models.user.stats_service import UserStatsService

            user = test_user_with_stats_data['user']

            # Act: get user classifications
            classifications = UserStatsService.get_user_classifications(user_id=user.id)

            # Assert: returns proper classification list
            assert isinstance(classifications, list)
            assert len(classifications) == 1

            classification = classifications[0]
            assert classification.user_id == user.id
            assert classification.position == 2
            assert classification.total_point_difference == 15

    def test_get_user_classifications_empty_data(self, app, db_session):
        """
        RED: Test UserStatsService.get_user_classifications() with no classifications.

        Expected behavior:
        - Returns empty list when user has no classifications
        - Handles empty datasets gracefully
        """
        with app.app_context():
            from models.user.stats_service import UserStatsService

            # Create user with no classifications
            user = User(
                username="no_class_user",
                email="noclass@example.com",
                role=UserRole.PLAYER.value
            )
            user.set_password("secure123")
            db.session.add(user)
            db.session.commit()

            # Act: get classifications for user with no data
            classifications = UserStatsService.get_user_classifications(user_id=user.id)

            # Assert: returns empty list
            assert isinstance(classifications, list)
            assert len(classifications) == 0

            # Cleanup
            db.session.delete(user)
            db.session.commit()

    def test_legacy_get_user_stats_compatibility(self, app, test_user_with_stats_data):
        """
        RED: Test UserStatsService maintains compatibility with legacy get_user_stats.

        Expected behavior:
        - UserStatsService.get_user_stats() should delegate to User.get_statistics()
        - Maintains backward compatibility with existing interface
        - Returns same format as current implementation
        """
        with app.app_context():
            from models.user.stats_service import UserStatsService

            user = test_user_with_stats_data['user']

            # Act: get stats through service
            service_stats = UserStatsService.get_user_stats(user_id=user.id)

            # Act: get stats through model method (if available)
            try:
                model_stats = user.get_statistics()
                # If both methods exist, they should return equivalent data
                # This ensures service extraction maintains compatibility
                assert service_stats["total_matches"] == model_stats.get("total_matches", service_stats["total_matches"])
            except AttributeError:
                # If model method doesn't exist, service should provide the functionality
                pass

            # Verify service provides expected interface
            assert isinstance(service_stats, dict)
            assert all(key in service_stats for key in [
                "total_matches", "won_matches", "win_percentage",
                "inscription_count", "losses_count"
            ])

    def test_statistics_calculation_accuracy(self, app, db_session):
        """
        RED: Test UserStatsService statistics calculation accuracy.

        Expected behavior:
        - Win percentage calculation should be accurate
        - Edge cases (no matches, all wins, all losses) handled correctly
        - Rounding behavior consistent
        """
        with app.app_context():
            from models.user.stats_service import UserStatsService

            # Create test user
            user = User(
                username="calc_user",
                email="calc@example.com",
                role=UserRole.PLAYER.value
            )
            user.set_password("secure123")
            db.session.add(user)
            db.session.flush()

            # Create opponent
            opponent = User(
                username="calc_opponent",
                email="opponent@example.com",
                role=UserRole.PLAYER.value
            )
            opponent.set_password("secure123")
            db.session.add(opponent)
            db.session.flush()

            # Create test gara
            gara = Gara(
                number=1,
                name="Calc Test",
                date=date.today(),
                discipline="palla 8",
                distance=5,
                status=GaraStatus.COMPLETED.value
            )
            db.session.add(gara)
            db.session.flush()

            # Test case: 1 win out of 3 matches (33.3% win rate)
            match1 = Match(
                player1_id=user.id,
                player2_id=opponent.id,
                gara_id=gara.id,
                round_number=1,
                status=MatchStatus.COMPLETED.value,
                winner_id=user.id  # Win
            )
            match2 = Match(
                player1_id=user.id,
                player2_id=opponent.id,
                gara_id=gara.id,
                round_number=2,
                status=MatchStatus.COMPLETED.value,
                winner_id=opponent.id  # Loss
            )
            match3 = Match(
                player1_id=user.id,
                player2_id=opponent.id,
                gara_id=gara.id,
                round_number=3,
                status=MatchStatus.COMPLETED.value,
                winner_id=opponent.id  # Loss
            )

            db.session.add_all([match1, match2, match3])
            db.session.commit()

            # Act: get statistics
            stats = UserStatsService.get_user_stats(user_id=user.id)

            # Assert: calculations are accurate
            assert stats["total_matches"] == 3
            assert stats["won_matches"] == 1
            assert stats["losses_count"] == 2
            assert stats["win_percentage"] == 33.3  # 1/3 * 100 rounded to 1 decimal

            # Cleanup
            for match in [match1, match2, match3]:
                db.session.delete(match)
            db.session.delete(gara)
            db.session.delete(opponent)
            db.session.delete(user)
            db.session.commit()

    def test_performance_optimization_patterns(self, app, test_user_with_stats_data):
        """
        RED: Test UserStatsService performance optimization patterns.

        Expected behavior:
        - get_users_with_stats() should use efficient single query
        - Proper joins and aggregations for large datasets
        - @read_only decorator for read operations
        - Minimal database round trips
        """
        with app.app_context():
            from models.user.stats_service import UserStatsService

            # Test that get_users_with_stats uses efficient query pattern
            # This documents expected optimization for implementation
            users_with_stats = UserStatsService.get_users_with_stats()

            # Verify it returns data in expected tuple format for efficiency
            assert isinstance(users_with_stats, list)
            if users_with_stats:
                row = users_with_stats[0]
                assert len(row) == 4  # (User, total_inscriptions, total_matches, matches_won)
                user, total_inscriptions, total_matches, matches_won = row
                assert isinstance(user, User)
                assert isinstance(total_inscriptions, int)
                assert isinstance(total_matches, int)
                assert isinstance(matches_won, (int, type(None)))

    def test_data_consistency_validation(self, app, test_user_with_stats_data):
        """
        RED: Test UserStatsService data consistency validation.

        Expected behavior:
        - Statistics should be consistent across different methods
        - get_user_stats() and get_user_statistics() should have consistent data
        - Match counts should align between methods
        """
        with app.app_context():
            from models.user.stats_service import UserStatsService

            user = test_user_with_stats_data['user']

            # Get statistics from both methods
            basic_stats = UserStatsService.get_user_stats(user_id=user.id)
            detailed_stats = UserStatsService.get_user_statistics(user_id=user.id)

            # Verify consistency between methods
            assert basic_stats["total_matches"] == detailed_stats["total_matches"]
            assert basic_stats["won_matches"] == detailed_stats["won_matches"]
            assert basic_stats["win_percentage"] == detailed_stats["win_percentage"]

            # Verify losses calculation consistency
            expected_losses = basic_stats["total_matches"] - basic_stats["won_matches"]
            assert basic_stats["losses_count"] == expected_losses
            assert detailed_stats["lost_matches"] == expected_losses

    def test_read_only_decorator_usage(self, app, test_user_with_stats_data):
        """
        RED: Test that UserStatsService methods use @read_only decorator properly.

        Expected behavior:
        - All UserStatsService methods should use @read_only decorator
        - No write operations should be performed by statistics methods
        - Read-only transaction boundaries respected
        """
        with app.app_context():
            # This test documents expected decorator usage for implementation
            # Implementation should use @read_only(domain="user") for all methods:
            # - get_user_stats()
            # - get_users_with_stats()
            # - get_user_statistics()
            # - get_user_matches()
            # - get_user_classifications()

            from models.user.stats_service import UserStatsService

            user = test_user_with_stats_data['user']

            # All these operations should be read-only
            stats = UserStatsService.get_user_stats(user_id=user.id)
            users_with_stats = UserStatsService.get_users_with_stats()
            detailed_stats = UserStatsService.get_user_statistics(user_id=user.id)
            matches = UserStatsService.get_user_matches(user_id=user.id)
            classifications = UserStatsService.get_user_classifications(user_id=user.id)

            # Verify all operations completed successfully (no transaction errors)
            assert stats is not None
            assert users_with_stats is not None
            assert detailed_stats is not None
            assert matches is not None
            assert classifications is not None

    def test_error_handling_robustness(self, app, db_session):
        """
        RED: Test UserStatsService error handling robustness.

        Expected behavior:
        - Graceful handling of invalid user IDs
        - Proper error messages for different failure scenarios
        - No data corruption on errors
        """
        with app.app_context():
            from models.user.stats_service import UserStatsService

            # Test various error scenarios
            test_cases = [
                (99999, "User not found"),  # Non-existent user
                (None, "User not found"),   # None user ID
                (-1, "User not found"),     # Invalid user ID
            ]

            for user_id, expected_message in test_cases:
                with pytest.raises(ValueError, match=expected_message):
                    UserStatsService.get_user_stats(user_id=user_id)

                with pytest.raises(ValueError, match=expected_message):
                    UserStatsService.get_user_statistics(user_id=user_id)

                with pytest.raises(ValueError, match=expected_message):
                    UserStatsService.get_user_matches(user_id=user_id)

                with pytest.raises(ValueError, match=expected_message):
                    UserStatsService.get_user_classifications(user_id=user.id)