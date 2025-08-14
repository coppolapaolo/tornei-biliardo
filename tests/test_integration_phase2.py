"""
Test integration for Phase 2 refactoring

Verifies that separated domains work together correctly
and backward compatibility is maintained.

Author: Refactoring Phase 2 - Sprint 1
Created: 2025-08-06
"""

from datetime import date  # AGGIUNGI QUESTO IMPORT
from models import db, User, Tournament, Prova, Match, Classification
from utils.reset_data import reset_database_enhanced


def test_all_models_available(app):
    """Test that all models are importable from models package"""
    with app.app_context():
        # Import all models from main package (backward compatibility)
        from models import (
            # User domain
            User,
            TournamentDirector,
            DirectorRequest,
            # Tournament domain
            Tournament,
            # Competition domain
            Prova,
            Inscription,
            # Match domain
            Match,
            Rack,
            MatchResult,
            TrioMatch,
            # Classification domain
            Classification,
            RoundClassification,
            PlayerEncounter,
            # Legacy
            Playoff,
        )

        # Verify all models are SQLAlchemy models
        all_models = [
            User,
            TournamentDirector,
            DirectorRequest,
            Tournament,
            Prova,
            Inscription,
            Match,
            Rack,
            MatchResult,
            TrioMatch,
            Classification,
            RoundClassification,
            PlayerEncounter,
            Playoff,
        ]

        for model in all_models:
            assert hasattr(model, "__tablename__")
            assert hasattr(model, "query")


def test_reset_data_works_with_new_structure(app):
    """Test that reset_database_enhanced works with separated domains"""
    with app.app_context():
        # This should work without errors
        reset_database_enhanced()

        # Verify data was created
        from models import User, Tournament, Prova

        assert User.query.filter_by(role="admin").count() == 1
        assert User.query.filter_by(role="director").count() >= 2
        assert User.query.filter_by(role="player").count() >= 10
        assert Tournament.query.count() >= 2
        assert Prova.query.count() >= 3


def test_cross_domain_relationships(app):
    """Test relationships across separated domains"""
    with app.app_context():
        from models import (
            User,
            Tournament,
            Prova,
            Match,
            Classification,
            RoundClassification,
        )

        # Create interconnected data
        admin = User(username="admin", email="admin@test.com", role="admin")
        admin.set_password("test123")

        player1 = User(username="player1", email="p1@test.com", role="player")
        player1.set_password("test123")

        player2 = User(username="player2", email="p2@test.com", role="player")
        player2.set_password("test123")

        db.session.add_all([admin, player1, player2])
        db.session.commit()

        # Tournament from tournament domain - CORREGGI game_type -> tournament_type
        tournament = Tournament(
            name="Cross-Domain Test",
            tournament_type="Amalfi",  # CAMBIATO da game_type
            is_active=True,
        )
        db.session.add(tournament)
        db.session.commit()

        # Prova from competition domain
        prova = Prova(
            tournament_id=tournament.id,
            number=1,
            name="Test Prova",
            # Aggiungi campi obbligatori
            date=date.today(),
            discipline="palla 8",
            distance=5,
            rounds_count=3,
        )
        db.session.add(prova)
        db.session.commit()

        # Match from match domain
        match = Match(
            prova_id=prova.id,
            round_number=1,
            player1_id=player1.id,
            player2_id=player2.id,
            status="pending",
        )
        db.session.add(match)
        db.session.commit()

        # Classification from classification domain
        classification = Classification(
            tournament_id=tournament.id,
            user_id=player1.id,
            position=1,
            total_matches_won=0,
            total_point_difference=0,
            provas_played=0,
        )
        db.session.add(classification)
        db.session.commit()

        # Verify all relationships work
        assert tournament.provas[0] == prova
        assert prova.matches[0] == match
        assert match.player1 == player1
        assert classification.user == player1
        assert classification.tournament == tournament


def test_services_cross_domain_interaction(app):
    """Test that services from different domains work together"""
    with app.app_context():
        from models.user.services import UserService
        from models.tournament.services import TournamentService
        from models.competition.services import ProvaService
        from models.classification.services import (
            ClassificationService,
            PlayerEncounterService,
        )

        # Create admin
        admin = UserService.create_user("admin", "admin@test.com", "password", "admin")

        # Create players
        players = []
        for i in range(4):
            player = UserService.create_user(
                f"player{i}", f"p{i}@test.com", "password", "player"
            )
            players.append(player)

        # Create tournament - CORREGGI game_type -> tournament_type
        tournament = TournamentService.create_tournament(
            name="Service Test Tournament",
            tournament_type="Amalfi",  # CAMBIATO da game_type
        )

        # Create prova
        prova = ProvaService.create_prova(
            tournament_id=tournament.id,
            number=1,
            name="Service Test Prova",
            # Aggiungi campi obbligatori
            date=date.today(),
            discipline="palla 9",
            distance=7,
            rounds_count=3,
        )

        # Update classification
        ClassificationService.update_tournament_classification(tournament.id)

        # Verify all services worked
        assert admin.role == "admin"
        assert len(players) == 4
        assert tournament.name == "Service Test Tournament"
        assert prova.tournament_id == tournament.id

        # Check player encounters service
        encounters = PlayerEncounterService.get_player_encounters(
            prova.id, players[0].id
        )
        assert len(encounters) == 0  # No matches yet


def test_modular_imports_work(app):
    """Test that modular imports from specific domains work"""
    with app.app_context():
        # User domain imports
        from models.user.models import User, TournamentDirector, DirectorRequest
        from models.user.services import UserService, DirectorRequestService
        from models.user.permissions import PermissionChecker

        # Tournament domain imports
        from models.tournament.models import Tournament
        from models.tournament.services import TournamentService

        # Competition domain imports
        from models.competition.models import Prova, Inscription
        from models.competition.services import ProvaService, InscriptionService

        # Match domain imports
        from models.match.models import Match, Rack, MatchResult, TrioMatch
        from models.match.services import MatchService, RackService

        # Classification domain imports
        from models.classification.models import (
            Classification,
            RoundClassification,
            PlayerEncounter,
        )
        from models.classification.services import (
            ClassificationService,
            RoundClassificationService,
            PlayerEncounterService,
        )

        # All imports should work without errors
        assert User is not None
        assert Tournament is not None
        assert Prova is not None
        assert Match is not None
        assert Classification is not None


def test_app_routes_still_work(app):
    """Quick smoke test that routes still function"""
    client = app.test_client()

    # Test main routes
    routes_to_test = [
        "/",
        "/auth/login",
        "/auth/register",
    ]

    for route in routes_to_test:
        response = client.get(route)
        # Should not get 500 errors
        assert response.status_code != 500, f"Route {route} failed with 500"
        # Should get either 200 (OK) or 302 (redirect)
        assert response.status_code in [
            200,
            302,
        ], f"Route {route} returned {response.status_code}"
