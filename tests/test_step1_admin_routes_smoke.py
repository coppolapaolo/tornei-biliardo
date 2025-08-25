# tests/test_step1_admin_routes_smoke.py
"""
Smoke tests for Step 1 refactoring - Admin routes blueprint decomposition.

These tests verify that all critical admin endpoints remain functional
after the blueprint refactoring from monolithic admin.py to domain-specific files.
"""

import pytest
from flask import url_for
from models import User


class TestAdminRoutesSmokeTests:
    """Smoke tests to verify admin blueprint refactoring preserved functionality."""

    def test_admin_blueprint_imports_successfully(self, app):
        """Test that the new admin blueprint structure imports without errors."""
        with app.app_context():
            # Test that the admin blueprint is registered
            from routes import register_blueprints
            
            # Only register if not already registered (avoid duplicate registration)
            if 'admin' not in [bp.name for bp in app.blueprints.values()]:
                register_blueprints(app)
            
            # Verify blueprint registration worked
            assert any(bp.name == 'admin' for bp in app.blueprints.values())

    def test_admin_dashboard_redirect(self, client, admin_user):
        """Test that /admin/ redirects correctly."""
        with client.session_transaction() as sess:
            sess['_user_id'] = str(admin_user.id)
            sess['_fresh'] = True
        
        # Should redirect to dashboard
        response = client.get('/admin/')
        assert response.status_code in [200, 302]  # Allow redirect or direct success

    def test_tournament_routes_accessible(self, client, admin_user):
        """Test that tournament management routes are accessible."""
        with client.session_transaction() as sess:
            sess['_user_id'] = str(admin_user.id)
            sess['_fresh'] = True
        
        # Test tournament creation endpoint exists
        response = client.post('/admin/tournament/create', 
                             data={'name': 'Test Tournament'})
        # Should not be 404 (route exists) or 500 (blueprint error)
        assert response.status_code != 404
        assert response.status_code != 500

    def test_competition_routes_accessible(self, client, admin_user):
        """Test that competition (prova) management routes are accessible."""
        with client.session_transaction() as sess:
            sess['_user_id'] = str(admin_user.id)
            sess['_fresh'] = True
        
        # Test prova creation endpoint exists
        response = client.get('/admin/prova/create_standalone')
        # Should not be 404 (route exists) or 500 (blueprint error)
        assert response.status_code != 404
        assert response.status_code != 500

    def test_user_management_routes_accessible(self, client, admin_user):
        """Test that user management routes are accessible."""
        with client.session_transaction() as sess:
            sess['_user_id'] = str(admin_user.id)
            sess['_fresh'] = True
        
        # Test users list endpoint exists
        response = client.get('/admin/users')
        # Should not be 404 (route exists) or 500 (blueprint error)  
        assert response.status_code != 404
        assert response.status_code != 500
        
        # Test director requests endpoint exists
        response = client.get('/admin/director_requests')
        assert response.status_code != 404
        assert response.status_code != 500

    def test_match_routes_accessible(self, client, admin_user, sample_match):
        """Test that match management routes are accessible."""
        with client.session_transaction() as sess:
            sess['_user_id'] = str(admin_user.id)
            sess['_fresh'] = True
        
        # Test match detail endpoint exists
        response = client.get(f'/admin/match/{sample_match.id}')
        # Should not be 404 (route exists) or 500 (blueprint error)
        assert response.status_code != 404
        assert response.status_code != 500

    def test_url_preservation(self, app):
        """Test that all expected admin URLs are preserved."""
        with app.app_context():
            # Configure SERVER_NAME for URL generation outside request context
            app.config['SERVER_NAME'] = 'localhost'
            
            # Create test client and request context for URL generation
            with app.test_request_context('/'):
                # Test that URL generation works for all major admin routes
                urls_to_test = [
                    ('admin.dashboard.dashboard',),
                    ('admin.tournament.create_tournament',),
                    ('admin.competition.create_prova_standalone',),
                    ('admin.user.users_list',),
                    ('admin.user.director_requests',),
                ]
                
                for url_args in urls_to_test:
                    try:
                        url = url_for(*url_args)
                        assert url.startswith('/admin/')
                    except Exception as e:
                        pytest.fail(f"URL generation failed for {url_args}: {e}")

    def test_blueprint_structure_exists(self):
        """Test that all domain-specific blueprint files exist."""
        import os
        admin_dir = 'routes/admin'
        
        expected_files = [
            '__init__.py',
            'tournament.py', 
            'competition.py',
            'match.py',
            'user.py',
            'dashboard.py'
        ]
        
        for file in expected_files:
            file_path = os.path.join(admin_dir, file)
            assert os.path.exists(file_path), f"Missing blueprint file: {file_path}"

    def test_no_circular_imports(self, app):
        """Test that the blueprint structure doesn't create circular imports."""
        try:
            # This should not raise any import errors
            from routes.admin import admin_bp
            from routes.admin.tournament import tournament_bp
            from routes.admin.competition import competition_bp
            from routes.admin.match import match_bp
            from routes.admin.user import user_bp
            from routes.admin.dashboard import dashboard_bp
            
            # Verify blueprints are properly initialized
            assert admin_bp.name == 'admin'
            assert tournament_bp.name == 'tournament'
            assert competition_bp.name == 'competition'
            assert match_bp.name == 'match'
            assert user_bp.name == 'user'
            assert dashboard_bp.name == 'dashboard'
            
        except ImportError as e:
            pytest.fail(f"Circular import or missing import detected: {e}")


# Pytest fixtures for testing
@pytest.fixture
def admin_user(db_session):
    """Create an admin user for testing."""
    user = User(
        username='test_admin',
        email='admin@test.com',
        role='admin'
    )
    user.set_password('password123')
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture  
def sample_match(db_session, admin_user):
    """Create a sample match for testing."""
    from models import Tournament, Prova, Match, Inscription
    from datetime import date
    
    # Create test data
    tournament = Tournament(name='Test Tournament', is_active=True)
    db_session.add(tournament)
    db_session.flush()
    
    prova = Prova(
        tournament_id=tournament.id,
        number=1,
        name='Test Prova',
        date=date.today(),
        discipline='9-ball',
        distance=5,
        rounds_count=3
    )
    db_session.add(prova)
    db_session.flush()
    
    # Create test players
    player1 = User(username='player1', email='p1@test.com', role='player')
    player2 = User(username='player2', email='p2@test.com', role='player')
    player1.set_password('pass')
    player2.set_password('pass')
    db_session.add_all([player1, player2])
    db_session.flush()
    
    match = Match(
        prova_id=prova.id,
        player1_id=player1.id,
        player2_id=player2.id,
        round_number=1
    )
    db_session.add(match)
    db_session.commit()
    db_session.refresh(match)
    
    return match