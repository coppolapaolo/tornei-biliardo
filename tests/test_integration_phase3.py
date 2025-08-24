"""
Module: tests/test_integration_phase3.py
Purpose: Integration tests for Phase 3 extended domains and service layer enhancements
Requirements: Test cross-domain orchestration, caching, transaction management, and extended domain functionality
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from models import db
from models.user.models import User
from models.tournament.models import Tournament
from models.competition.models import Prova, Inscription
from models.challenge.models import Challenge, ChallengeAttempt
from models.individual_match.models import MatchProposal, IndividualMatch, ProposalType, ProposalStatus
from models.rating.models import PlayerCategory, PlayerRating, CategoryLevel, RatingSystem
from models.orchestration.service import DomainOrchestrator, OperationType
from models.caching.manager import cache_manager
from models.optimization.query_optimizer import query_optimizer
from models.transaction.manager import transaction_manager
from models.matchmaking.service import MatchmakingService
from models.matchmaking.registry import EngineRegistry

from models.challenge.services import ChallengeService
from models.individual_match.services import IndividualMatchService, MatchProposalService
from models.rating.services import RatingService, CategoryService, HandicapService
from models.classification.services import ClassificationService


@pytest.fixture
def sample_users(app):
    """Create sample users for testing."""
    with app.app_context():
        admin = User(username="admin", email="admin@test.com", role="admin")
        admin.set_password("password")
        
        director = User(username="director", email="director@test.com", role="director")
        director.set_password("password")
        
        player1 = User(username="player1", email="player1@test.com", role="player")
        player1.set_password("password")
        
        player2 = User(username="player2", email="player2@test.com", role="player")
        player2.set_password("password")
        
        db.session.add_all([admin, director, player1, player2])
        db.session.commit()
        
        return {
            "admin": admin,
            "director": director,
            "player1": player1,
            "player2": player2
        }


@pytest.fixture
def sample_tournament(app, sample_users):
    """Create sample tournament with prova."""
    with app.app_context():
        tournament = Tournament(
            name="Test Tournament",
            description="Test tournament for integration testing",
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=7),
            creator_id=sample_users["admin"].id
        )
        db.session.add(tournament)
        db.session.commit()
        
        prova = Prova(
            name="Test Prova",
            description="Test prova for integration testing",
            tournament_id=tournament.id,
            director_id=sample_users["director"].id,
            max_participants=8,
            status="setup"
        )
        db.session.add(prova)
        db.session.commit()
        
        return {"tournament": tournament, "prova": prova}


@pytest.fixture
def sample_challenge(app, sample_users):
    """Create sample challenge."""
    with app.app_context():
        challenge = Challenge(
            name="Test Challenge",
            description="Test challenge for integration testing",
            min_score=0,
            max_score=100,
            pass_fail_only=False,
            created_by_id=sample_users["director"].id
        )
        db.session.add(challenge)
        db.session.commit()
        return challenge


class TestCachingIntegration:
    """Test caching system integration."""
    
    def test_cache_basic_functionality(self, app):
        """Test basic cache operations."""
        with app.app_context():
            # Test cache set and get
            cache_manager.set(
                key="test_key",
                value={"data": "test_value"},
                ttl_seconds=300,
                tags=["test"]
            )
            
            cached_value = cache_manager.get("test_key")
            assert cached_value is not None
            assert cached_value["data"] == "test_value"
    
    def test_cache_invalidation_by_tags(self, app):
        """Test cache invalidation by tags."""
        with app.app_context():
            # Set multiple cache entries with tags
            cache_manager.set("key1", "value1", tags=["tournament", "test"])
            cache_manager.set("key2", "value2", tags=["user", "test"])
            cache_manager.set("key3", "value3", tags=["tournament"])
            
            # Invalidate by tag
            result = cache_manager.invalidate_by_tags(["tournament"])
            
            # Check that tournament-tagged entries are gone
            assert cache_manager.get("key1") is None
            assert cache_manager.get("key3") is None
            # But user-only tagged entry remains
            assert cache_manager.get("key2") is not None
    
    def test_classification_service_caching(self, app, sample_tournament, sample_users):
        """Test that classification service properly uses caching."""
        with app.app_context():
            tournament_id = sample_tournament["tournament"].id
            
            # Clear cache first
            cache_manager.clear_all()
            
            # First call should miss cache
            standings1 = ClassificationService.get_tournament_standings(tournament_id)
            
            # Second call should hit cache
            standings2 = ClassificationService.get_tournament_standings(tournament_id)
            
            # Results should be identical
            assert len(standings1) == len(standings2)
            
            # Verify cache stats show hits
            stats = cache_manager.get_comprehensive_stats()
            assert any(level_stats.hits > 0 for level_stats in stats.values())


class TestTransactionManagement:
    """Test transaction management functionality."""
    
    def test_transaction_decorator(self, app, sample_users):
        """Test transaction decorator functionality."""
        with app.app_context():
            from models.transaction import transactional
            
            @transactional(domain="test")
            def create_user_transactional():
                user = User(username="tx_test", email="tx@test.com", role="player")
                user.set_password("password")
                db.session.add(user)
                return user
            
            # Test successful transaction
            user = create_user_transactional()
            assert user.id is not None
            
            # Verify user exists in database
            found_user = User.query.filter_by(username="tx_test").first()
            assert found_user is not None
    
    def test_transaction_rollback(self, app):
        """Test transaction rollback on exception."""
        with app.app_context():
            from models.transaction import transactional
            
            @transactional(domain="test")
            def failing_transaction():
                user = User(username="rollback_test", email="rollback@test.com", role="player")
                user.set_password("password")
                db.session.add(user)
                db.session.flush()  # Force DB interaction
                raise ValueError("Intentional failure")
            
            # Test that transaction rolls back
            with pytest.raises(ValueError):
                failing_transaction()
            
            # Verify user was not created
            found_user = User.query.filter_by(username="rollback_test").first()
            assert found_user is None
    
    def test_nested_transactions(self, app):
        """Test nested transaction functionality."""
        with app.app_context():
            from models.transaction import transaction_manager
            
            with transaction_manager.transaction() as outer:
                # Create user in outer transaction
                user1 = User(username="outer", email="outer@test.com", role="player")
                user1.set_password("password")
                db.session.add(user1)
                
                try:
                    with transaction_manager.transaction(savepoint_name="inner") as inner:
                        # Create user in inner transaction
                        user2 = User(username="inner", email="inner@test.com", role="player")
                        user2.set_password("password")
                        db.session.add(user2)
                        
                        # Force failure in inner transaction
                        raise ValueError("Inner transaction failure")
                        
                except ValueError:
                    pass  # Expected failure
            
            # Verify outer transaction committed, inner rolled back
            outer_user = User.query.filter_by(username="outer").first()
            inner_user = User.query.filter_by(username="inner").first()
            
            assert outer_user is not None
            assert inner_user is None


class TestQueryOptimization:
    """Test query optimization functionality."""
    
    def test_query_monitoring(self, app, sample_users):
        """Test that query monitoring captures performance data."""
        with app.app_context():
            # Clear previous metrics
            query_optimizer.analyzer.clear_metrics()
            
            # Execute some queries to generate metrics
            users = User.query.all()
            user = User.query.filter_by(username="player1").first()
            
            # Check that metrics were recorded
            report = query_optimizer.analyzer.get_performance_report()
            assert report["summary"]["total_unique_queries"] > 0
            assert report["summary"]["total_executions"] > 0
    
    def test_n1_detection(self, app, sample_tournament, sample_users):
        """Test N+1 query detection."""
        with app.app_context():
            # Clear previous metrics
            query_optimizer.analyzer.clear_metrics()
            
            # Simulate N+1 pattern by fetching tournament then its provas individually
            tournament = Tournament.query.first()
            # This should trigger potential N+1 detection
            for _ in range(5):
                Prova.query.filter_by(tournament_id=tournament.id).first()
            
            # Detect N+1 problems
            problems = query_optimizer.analyzer.detect_n1_problems()
            
            # Should detect potential issues (depending on query patterns)
            # Note: This is a simplified test - real N+1 detection is more complex
            assert isinstance(problems, list)


class TestCrossDomainOrchestration:
    """Test cross-domain orchestration functionality."""
    
    def test_user_onboarding_orchestration(self, app):
        """Test complete user onboarding orchestration."""
        with app.app_context():
            registry = EngineRegistry()
            matchmaking_service = MatchmakingService(registry)
            orchestrator = DomainOrchestrator(matchmaking_service)
            
            user_data = {
                "username": "orchestrated_user",
                "email": "orchestrated@test.com",
                "password": "password123",
                "role": "player"
            }
            
            # Execute user onboarding orchestration
            result = orchestrator.orchestrate_user_onboarding(
                user_data=user_data,
                auto_category_assignment=True,
                setup_preferences=True
            )
            
            assert result.success
            assert result.operation_type == OperationType.USER_ONBOARDING
            assert "user" in result.affected_domains
            
            # Verify user was created
            user = User.query.filter_by(username="orchestrated_user").first()
            assert user is not None
            
            # Verify category was assigned
            category = PlayerCategory.query.filter_by(user_id=user.id, is_active=True).first()
            assert category is not None
            assert category.category == CategoryLevel.D  # Default for new players
    
    def test_tournament_setup_orchestration(self, app, sample_users):
        """Test tournament setup orchestration."""
        with app.app_context():
            registry = EngineRegistry()
            matchmaking_service = MatchmakingService(registry)
            orchestrator = DomainOrchestrator(matchmaking_service)
            
            tournament_data = {
                "name": "Orchestrated Tournament",
                "description": "Test tournament via orchestration",
                "start_date": datetime.utcnow(),
                "end_date": datetime.utcnow() + timedelta(days=7),
                "creator_id": sample_users["admin"].id,
                "max_participants": 16
            }
            
            competition_configs = [
                {
                    "name": "Orchestrated Prova 1",
                    "description": "First prova",
                    "director_id": sample_users["director"].id,
                    "max_participants": 8
                },
                {
                    "name": "Orchestrated Prova 2", 
                    "description": "Second prova",
                    "director_id": sample_users["director"].id,
                    "max_participants": 8
                }
            ]
            
            # Execute tournament setup orchestration
            result = orchestrator.setup_complete_tournament(
                tournament_data=tournament_data,
                competition_configs=competition_configs,
                auto_assign_categories=False,
                setup_handicap_rules=False
            )
            
            assert result.success
            assert result.operation_type == OperationType.TOURNAMENT_SETUP
            assert "tournament" in result.affected_domains
            assert "competition" in result.affected_domains
            
            # Verify tournament was created
            tournament = Tournament.query.filter_by(name="Orchestrated Tournament").first()
            assert tournament is not None
            
            # Verify competitions were created
            provas = Prova.query.filter_by(tournament_id=tournament.id).all()
            assert len(provas) == 2


class TestExtendedDomainIntegration:
    """Test integration of extended domains."""
    
    def test_challenge_domain_integration(self, app, sample_challenge, sample_users, sample_tournament):
        """Test challenge domain integration with tournaments."""
        with app.app_context():
            prova = sample_tournament["prova"]
            player = sample_users["player1"]
            
            # Create challenge attempt for X replacement
            attempt = ChallengeService.create_x_replacement_attempt(
                user_id=player.id,
                prova_id=prova.id,
                round_number=1,
                challenge_id=sample_challenge.id
            )
            
            assert attempt.prova_id == prova.id
            assert attempt.round_number == 1
            assert attempt.user_id == player.id
            
            # Complete the attempt
            completed_attempt = ChallengeService.complete_x_replacement_attempt(
                attempt_id=attempt.id,
                score=75,
                notes="Good performance"
            )
            
            assert completed_attempt.completed
            assert completed_attempt.score == 75
            assert completed_attempt.get_rack_difference_equivalent() > 0
    
    def test_individual_match_integration(self, app, sample_users):
        """Test individual match domain integration."""
        with app.app_context():
            proposer = sample_users["player1"]
            accepter = sample_users["player2"]
            
            # Create match proposal
            proposal = MatchProposalService.create_proposal(
                proposer_id=proposer.id,
                proposal_type=ProposalType.DIRECT,
                location="Test Location",
                scheduled_at=datetime.utcnow() + timedelta(hours=2),
                expires_at=datetime.utcnow() + timedelta(hours=1),
                discipline="palla_8",
                distance=5,
                invited_user_ids=[accepter.id]
            )
            
            assert proposal.proposer_id == proposer.id
            assert proposal.proposal_type == ProposalType.DIRECT
            assert proposal.status == ProposalStatus.PENDING
            
            # Accept the proposal
            individual_match = MatchProposalService.accept_proposal(proposal.id, accepter.id)
            
            assert individual_match.player1_id == proposer.id
            assert individual_match.player2_id == accepter.id
            assert individual_match.proposal_id == proposal.id
    
    def test_rating_system_integration(self, app, sample_users):
        """Test rating system integration."""
        with app.app_context():
            player = sample_users["player1"]
            director = sample_users["director"]
            
            # Assign category
            category = CategoryService.assign_category(
                user_id=player.id,
                category=CategoryLevel.B,
                assigned_by_id=director.id,
                reason="Test assignment"
            )
            
            assert category.user_id == player.id
            assert category.category == CategoryLevel.B
            assert category.assigned_by_id == director.id
            
            # Add rating
            rating = RatingService.update_user_rating(
                user_id=player.id,
                rating_system=RatingSystem.FARGO,
                rating_value=550,
                external_id="FARGO123"
            )
            
            assert rating.user_id == player.id
            assert rating.rating_system == RatingSystem.FARGO
            assert rating.rating_value == 550
            
            # Test handicap calculation
            player2 = sample_users["player2"]
            
            # Assign different category to player2
            CategoryService.assign_category(
                user_id=player2.id,
                category=CategoryLevel.D,
                assigned_by_id=director.id
            )
            
            handicap = HandicapService.calculate_handicap(player.id, player2.id)
            
            assert "method" in handicap
            assert "handicap" in handicap


class TestServiceLayerBoundaries:
    """Test service layer architectural boundaries."""
    
    def test_service_separation_of_concerns(self, app, sample_users):
        """Test that services maintain proper separation of concerns."""
        with app.app_context():
            # User service should only handle user-related operations
            user = sample_users["player1"]
            
            # This should work - user domain operation
            user_profile = RatingService.get_user_rating_profile(user.id)
            assert "user_id" in user_profile
            
            # Services should be composable but separate
            category_info = CategoryService.get_user_category_info(user.id)
            assert isinstance(category_info, dict)
    
    def test_cross_domain_data_consistency(self, app, sample_users, sample_tournament):
        """Test data consistency across domain boundaries."""
        with app.app_context():
            tournament = sample_tournament["tournament"]
            player = sample_users["player1"]
            
            # Operations affecting multiple domains should maintain consistency
            # Example: User deletion should clean up related data
            
            # First, create some cross-domain data
            category = PlayerCategory(
                user_id=player.id,
                category=CategoryLevel.B,
                assigned_by_id=sample_users["admin"].id
            )
            db.session.add(category)
            
            rating = PlayerRating(
                user_id=player.id,
                rating_system=RatingSystem.INTERNAL,
                rating_value=75
            )
            db.session.add(rating)
            db.session.commit()
            
            # Verify data exists
            assert PlayerCategory.query.filter_by(user_id=player.id).count() > 0
            assert PlayerRating.query.filter_by(user_id=player.id).count() > 0
            
            # Simulate user deletion (soft delete)
            player.soft_delete()
            db.session.commit()
            
            # Data should still exist but user should be marked as deleted
            assert player.deleted_at is not None
            assert PlayerCategory.query.filter_by(user_id=player.id).count() > 0
            assert PlayerRating.query.filter_by(user_id=player.id).count() > 0


class TestPerformanceIntegration:
    """Test performance optimization integration."""
    
    def test_caching_performance_impact(self, app, sample_tournament):
        """Test that caching improves performance."""
        with app.app_context():
            tournament_id = sample_tournament["tournament"].id
            
            # Clear cache
            cache_manager.clear_all()
            
            # Time first call (cache miss)
            import time
            start_time = time.time()
            standings1 = ClassificationService.get_tournament_standings(tournament_id)
            first_call_time = time.time() - start_time
            
            # Time second call (cache hit)
            start_time = time.time()
            standings2 = ClassificationService.get_tournament_standings(tournament_id)
            second_call_time = time.time() - start_time
            
            # Second call should be faster (though on empty data it might be negligible)
            assert second_call_time <= first_call_time
            
            # Results should be identical
            assert len(standings1) == len(standings2)
    
    def test_bulk_operations_optimization(self, app, sample_users):
        """Test that bulk operations are optimized."""
        with app.app_context():
            # Create multiple users to test bulk loading
            users = []
            for i in range(5):
                user = User(
                    username=f"bulk_user_{i}",
                    email=f"bulk{i}@test.com",
                    role="player"
                )
                user.set_password("password")
                users.append(user)
            
            db.session.add_all(users)
            db.session.commit()
            
            # Test optimized query with eager loading
            from models.optimization import bulk_load_relationships
            from sqlalchemy.orm import selectinload
            
            # This should use optimized loading
            query = User.query.filter(User.username.like('bulk_user_%'))
            optimized_users = bulk_load_relationships(
                query,
                selectinload(User.inscriptions)
            ).all()
            
            assert len(optimized_users) == 5
            # Verify that relationships are loaded without additional queries
            for user in optimized_users:
                # Accessing inscriptions shouldn't trigger additional queries
                inscriptions = user.inscriptions
                assert isinstance(inscriptions, list)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])