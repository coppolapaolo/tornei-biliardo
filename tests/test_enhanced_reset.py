import pytest
from app import create_app


def test_enhanced_reset_functionality(app):
    """Test that enhanced reset creates all expected data"""
    with app.app_context():
        from utils_reset.reset_data import create_enhanced_reset_data

        # Create enhanced data
        data = create_enhanced_reset_data()

        # Verify users were created
        assert data['users']['admin'] is not None
        assert data['users']['admin'].username == 'admin'
        assert data['users']['admin'].role == 'admin'

        assert len(data['users']['directors']) == 2
        assert data['users']['directors'][0].role == 'director'
        assert data['users']['directors'][1].role == 'director'

        assert len(data['users']['players']) == 10
        for player in data['users']['players']:
            assert player.role == 'player'

        # Verify pending director request
        assert data['users']['pending_request_user'] is not None
        assert data['users']['pending_request_user'].role == 'player'

        # Verify tournaments
        assert len(data['tournaments']) == 3
        assert data['tournaments'][0].name == "Torneo Primavera 2025"
        assert data['tournaments'][1].name == "Coppa Estate 2025"
        assert data['tournaments'][2].name == "Championship Elite 2025"

        # Verify provas
        assert len(data['provas']) == 4

        # Verify inscriptions
        assert len(data['inscriptions']) == 28

        # Verify tournament director assignments
        assert len(data['assignments']) == 4


def test_enhanced_reset_database(app):
    """Test the complete enhanced reset function"""
    with app.app_context():
        from utils_reset.reset_data import reset_database_enhanced

        # This will reset the database and create all data
        data = reset_database_enhanced()

        # Verify the data was created
        assert data is not None
        assert 'users' in data
        assert 'tournaments' in data
        assert 'provas' in data
        assert 'inscriptions' in data
        assert 'assignments' in data

        # Verify we can query the data
        from models.user.models import User
        from models.legacy_models import Tournament, Prova, Inscription

        # Check users
        admin_users = User.query.filter_by(role='admin').all()
        assert len(admin_users) == 1
        assert admin_users[0].username == 'admin'

        director_users = User.query.filter_by(role='director').all()
        assert len(director_users) == 2

        player_users = User.query.filter_by(role='player').all()
        assert len(player_users) == 11  # 10 players + 1 pending request

        # Check tournaments
        tournaments = Tournament.query.all()
        assert len(tournaments) == 3

        # Check provas
        provas = Prova.query.all()
        assert len(provas) == 4

        # Check inscriptions
        inscriptions = Inscription.query.all()
        assert len(inscriptions) == 28
 