"""
Test routes for Prova standalone functionality (Sprint 2)
"""

from datetime import datetime, timedelta
from models import User, Prova


class TestProvaStandaloneRoutes:
    """Test routes for standalone Prova functionality."""

    def test_create_prova_standalone_get(self, client, director_user):
        """Test GET request to create standalone prova page."""
        # Login as director
        client.post(
            "/auth/login",
            data={"username": director_user.username, "password": "password"},
        )

        response = client.get("/admin/prova/create_standalone")
        assert response.status_code == 200
        assert b"Crea Gara Singola" in response.data

    def test_create_prova_standalone_post(self, client, director_user):
        """Test POST request to create standalone prova."""
        # Login as director
        client.post(
            "/auth/login",
            data={"username": director_user.username, "password": "password"},
        )

        # Create standalone prova
        response = client.post(
            "/admin/prova/create_standalone",
            data={
                "number": "1",
                "name": "Test Standalone Competition",
                "date": (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d"),
                "discipline": "palla_8",
                "distance": "9",
                "location": "Test Club",
                "description": "Test description",
                "rounds_count": "1",
                "min_participants": "4",
                "max_participants": "16",
                "entry_fee": "10.0",
            },
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b"creata con successo" in response.data

        # Verify prova was created
        prova = Prova.query.filter_by(name="Test Standalone Competition").first()
        assert prova is not None
        assert prova.is_standalone
        assert prova.director_id == director_user.id
        assert prova.tournament_id is None

    def test_director_dashboard(self, client, director_user, db_session):
        """Test director dashboard shows standalone provas."""
        # Create a standalone prova
        prova = Prova(
            number=1,
            name="My Standalone",
            director_id=director_user.id,
            date=datetime.now().date() + timedelta(days=10),
            discipline="palla_9",
            distance=7,
        )
        db_session.add(prova)
        db_session.commit()

        # Login and check dashboard
        client.post(
            "/auth/login",
            data={"username": director_user.username, "password": "password"},
        )

        response = client.get("/dashboard", follow_redirects=True)
        assert response.status_code == 200
        assert (
            b"Standalone" in response.data
            or b"gare singole" in response.data
        )

    def test_player_cannot_create_standalone(self, client, player_user):
        """Test that regular players cannot create standalone provas."""
        client.post(
            "/auth/login",
            data={"username": player_user.username, "password": "password"},
        )

        response = client.get("/admin/prova/create_standalone")
        assert response.status_code == 302  # Redirect

        response = client.get("/admin/prova/create_standalone", follow_redirects=True)
        assert b"Non hai i permessi" in response.data

    def test_prova_manager_permission_standalone(self, client, db_session):
        """Test prova_manager_required works for standalone provas."""
        # Create two directors
        director1 = User(username="dir1", email="dir1@test.com", role="director")
        director1.set_password("password")
        director2 = User(username="dir2", email="dir2@test.com", role="director")
        director2.set_password("password")
        db_session.add_all([director1, director2])
        db_session.commit()

        # Director1 creates standalone prova
        prova = Prova(
            number=1,
            name="Director1 Prova",
            director_id=director1.id,
            date=datetime.now().date(),
            discipline="palla_8",
            distance=9,
        )
        db_session.add(prova)
        db_session.commit()

        # Login as director2 (wrong director)
        client.post("/auth/login", data={"username": "dir2", "password": "password"})

        # Try to access prova detail
        response = client.get(f"/admin/prova/{prova.id}")
        assert response.status_code == 403  # Forbidden

        # Login as director1 (correct director)
        client.post("/auth/logout")
        client.post("/auth/login", data={"username": "dir1", "password": "password"})

        # Should have access
        response = client.get(f"/admin/prova/{prova.id}")
        assert response.status_code == 200
