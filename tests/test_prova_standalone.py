"""
Test suite for Prova standalone functionality (Sprint 2)

Tests the nullable tournament_id implementation for standalone competitions.
"""

import pytest
from datetime import datetime, timedelta
from models import db, User, Tournament, Prova
from models.competition.services import ProvaService
from models.user.models import TournamentDirector


class TestProvaStandalone:
    """Test Prova with nullable tournament_id."""
    
    def test_create_prova_with_tournament(self, app):
        """Test creating traditional prova with tournament."""
        with app.app_context():
            # Create tournament and director
            director = User(username="director1", email="dir1@test.com")
            director.set_password("password")
            db.session.add(director)
            db.session.commit()
            
            tournament = Tournament(name="Test Tournament")
            db.session.add(tournament)
            db.session.commit()
            
            # Create prova with tournament
            prova = ProvaService.create_prova(
                number=1,
                name="Test Prova",
                date=datetime.now().date(),
                discipline="palla_8",
                distance=9,
                tournament_id=tournament.id
            )
            
            assert prova.tournament_id == tournament.id
            assert prova.director_id is None
            assert not prova.is_standalone
            assert prova.tournament == tournament
    
    def test_create_prova_standalone(self, app):
        """Test creating standalone prova without tournament."""
        with app.app_context():
            # Create director
            director = User(username="director2", email="dir2@test.com")
            director.set_password("password")
            db.session.add(director)
            db.session.commit()
            
            # Create standalone prova
            prova = ProvaService.create_prova(
                number=1,
                name="Standalone Competition",
                date=datetime.now().date(),
                discipline="palla_9",
                distance=7,
                director_id=director.id
            )
            
            assert prova.tournament_id is None
            assert prova.director_id == director.id
            assert prova.is_standalone
            assert prova.director == director
    
    def test_create_prova_validation(self, app):
        """Test validation when creating prova."""
        with app.app_context():
            # Should fail without tournament_id or director_id
            with pytest.raises(ValueError) as exc:
                ProvaService.create_prova(
                    number=1,
                    name="Invalid Prova",
                    date=datetime.now().date(),
                    discipline="palla_8",
                    distance=9
                )
            assert "tournament_id or director_id" in str(exc.value)
    
    def test_get_organizer(self, app):
        """Test get_organizer for both types."""
        with app.app_context():
            # Setup
            admin = User(username="admin", email="admin@test.com", role="admin")
            admin.set_password("password")
            director = User(username="director3", email="dir3@test.com")
            director.set_password("password")
            db.session.add_all([admin, director])
            
            tournament = Tournament(name="Tournament with Director")
            db.session.add(tournament)
            db.session.commit()
            
            # Add director to tournament (assigned by admin)
            td = TournamentDirector(
                tournament_id=tournament.id,
                user_id=director.id,
                assigned_by_id=admin.id
            )
            db.session.add(td)
            db.session.commit()
            
            # Tournament prova
            prova_tournament = Prova(
                number=1,
                name="Tournament Prova",
                tournament_id=tournament.id,
                date=datetime.now().date(),
                discipline="palla_8",
                distance=9
            )
            
            # Standalone prova
            prova_standalone = Prova(
                number=2,
                name="Standalone Prova",
                director_id=director.id,
                date=datetime.now().date(),
                discipline="palla_8",
                distance=9
            )
            
            db.session.add_all([prova_tournament, prova_standalone])
            db.session.commit()
            
            # Test organizers
            assert prova_tournament.get_organizer() == director
            assert prova_standalone.get_organizer() == director
    
    def test_get_director_provas(self, app):
        """Test getting all provas for a director."""
        with app.app_context():
            # Setup
            admin = User(username="admin", email="admin@test.com", role="admin")
            admin.set_password("password")
            director = User(username="director4", email="dir4@test.com")
            director.set_password("password")
            other_director = User(username="other", email="other@test.com")
            other_director.set_password("password")
            db.session.add_all([admin, director, other_director])
            
            tournament = Tournament(name="Director Tournament")
            db.session.add(tournament)
            db.session.commit()
            
            # Make user a tournament director (assigned by admin)
            td = TournamentDirector(
                tournament_id=tournament.id,
                user_id=director.id,
                assigned_by_id=admin.id
            )
            db.session.add(td)
            db.session.commit()
            
            # Create provas
            prova_tournament = Prova(
                number=1,
                name="Tournament Prova",
                tournament_id=tournament.id,
                date=datetime.now().date(),
                discipline="palla_8",
                distance=9
            )
            
            prova_standalone = Prova(
                number=2,
                name="Standalone Prova",
                director_id=director.id,
                date=datetime.now().date(),
                discipline="palla_9",
                distance=7
            )
            
            prova_other = Prova(
                number=3,
                name="Other Director Prova",
                director_id=other_director.id,
                date=datetime.now().date(),
                discipline="palla_10",
                distance=8
            )
            
            db.session.add_all([prova_tournament, prova_standalone, prova_other])
            db.session.commit()
            
            # Test service
            director_provas = ProvaService.get_director_provas(director.id)
            
            assert len(director_provas) == 2
            assert prova_tournament in director_provas
            assert prova_standalone in director_provas
            assert prova_other not in director_provas
    
    def test_repr_methods(self, app):
        """Test __repr__ for both types."""
        with app.app_context():
            tournament = Tournament(name="Test Tournament")
            db.session.add(tournament)
            db.session.commit()
            
            prova_tournament = Prova(
                name="Tournament Prova",
                tournament_id=tournament.id,
                number=1,
                date=datetime.now().date(),
                discipline="palla_8",
                distance=9
            )
            
            prova_standalone = Prova(
                name="Standalone Prova",
                director_id=1,
                number=2,
                date=datetime.now().date(),
                discipline="palla_8",
                distance=9
            )
            
            assert "Torneo" in repr(prova_tournament)
            assert "Standalone" in repr(prova_standalone)
    
    def test_display_name(self, app):
        """Test get_display_name method."""
        with app.app_context():
            tournament = Tournament(name="Summer Tournament")
            db.session.add(tournament)
            db.session.commit()
            
            prova_tournament = Prova(
                name="Prova 1",
                tournament_id=tournament.id,
                number=1,
                date=datetime.now().date(),
                discipline="palla_8",
                distance=9
            )
            
            prova_standalone = Prova(
                name="Memorial 2025",
                director_id=1,
                number=2,
                date=datetime.now().date(),
                discipline="palla_8",
                distance=9
            )
            
            db.session.add_all([prova_tournament, prova_standalone])
            db.session.commit()
            
            assert prova_tournament.get_display_name() == "Prova 1 - Summer Tournament"
            assert prova_standalone.get_display_name() == "Memorial 2025 (Standalone)"