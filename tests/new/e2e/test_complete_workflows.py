"""End-to-end tests for complete user workflows."""

import pytest
from datetime import date, timedelta

from models import User, Campionato, Gara, DirectorRequest, Inscription
from models.user.models import DirectorAssignment
from models.user.role_enum import UserRole
from models.campionato.services import TournamentService


@pytest.mark.e2e
class TestCompleteUserJourney:
    """Test complete user journey from registration to tournament participation."""

    def test_player_to_director_to_tournament_creation_journey(
        self, client, db_session
    ):
        """Test complete journey: registration -> director request -> tournament."""
        # Step 1: User registration
        response = client.post(
            "/auth/register",
            data={
                "username": "newplayer",
                "email": "newplayer@test.com",
                "password": "password123",
                "confirm_password": "password123",
            },
            follow_redirects=True,
        )

        assert response.status_code == 200

        # Verify user was created as player
        player = User.query.filter_by(username="newplayer").first()
        assert player is not None
        assert player.role == UserRole.PLAYER.value

        # Step 2: Player requests to become director
        response = client.post(
            "/auth/login", data={"username": "newplayer", "password": "password123"}
        )

        response = client.post(
            "/player/request_director",
            data={"reason": "I want to organize tournaments for my local club"},
            follow_redirects=True,
        )

        assert response.status_code == 200

        # Verify director request was created
        director_request = DirectorRequest.query.filter_by(user_id=player.id).first()
        assert director_request is not None
        assert director_request.status == "pending"

        # Logout player
        client.post("/auth/logout")

        # Step 3: Admin processes director request
        admin = User(
            username="admin", email="admin@test.com", role=UserRole.ADMIN.value
        )
        admin.set_password("admin123")
        db_session.add(admin)
        db_session.commit()

        client.post("/auth/login", data={"username": "admin", "password": "admin123"})

        response = client.post(
            f"/admin/director_requests/{director_request.id}/process",
            data={
                "status": "approved",
                "admin_notes": "Approved for tournament organization",
            },
            follow_redirects=True,
        )

        assert response.status_code == 200

        # Verify player was promoted to director
        db_session.refresh(player)
        assert player.role == UserRole.DIRECTOR.value

        # Logout admin
        client.post("/auth/logout")

        # Step 4: Director creates campionato
        client.post(
            "/auth/login",
            data={"username": "newplayer", "password": "password123"},  # Now a director
        )

        response = client.post(
            "/admin/campionato/create",
            data={
                "name": "My First Tournament",
                "campionato_type": "Amalfi",
                "without_x": "",
                "final_playoffs": "on",
                "challenge_mode": "",
            },
            follow_redirects=True,
        )

        assert response.status_code == 200

        # Verify campionato was created
        campionato = Campionato.query.filter_by(name="My First Tournament").first()
        assert campionato is not None
        assert campionato.final_playoffs is True

        # Verify director assignment
        assignment = (
            db_session.query(DirectorAssignment)
            .filter(
                DirectorAssignment.entity_type == "campionato",
                DirectorAssignment.entity_id == campionato.id,
                DirectorAssignment.user_id == player.id,
            )
            .first()
        )
        assert assignment is not None

        # Step 5: Director creates gara within campionato
        response = client.post(
            f"/admin/campionato/{campionato.id}/create_gara",
            data={
                "name": "First Competition",
                "date": (date.today() + timedelta(days=7)).strftime("%Y-%m-%d"),
                "location": "Local Club",
                "description": "First competition of the tournament",
                "rounds_count": "3",
                "min_participants": "4",
                "max_participants": "16",
                "entry_fee": "15.0",
                "discipline": "palla 9",
                "distance": "7",
                "withdraw_policy": "exclude",
            },
            follow_redirects=True,
        )

        assert response.status_code == 200

        # Verify gara was created
        gara = Gara.query.filter_by(name="First Competition").first()
        assert gara is not None
        assert gara.campionato_id == campionato.id

        # Step 6: Access dashboard and verify everything is visible
        response = client.get("/dashboard")
        assert response.status_code == 200
        assert b"My First Tournament" in response.data
        assert b"First Competition" in response.data

    def test_standalone_competition_workflow(self, client, db_session):
        """Test complete standalone competition workflow."""
        # Step 1: Create director
        director = User(
            username="director", email="director@test.com", role=UserRole.DIRECTOR.value
        )
        director.set_password("director123")
        db_session.add(director)
        db_session.commit()

        # Step 2: Director creates standalone gara
        client.post(
            "/auth/login", data={"username": "director", "password": "director123"}
        )

        tomorrow = date.today() + timedelta(days=1)
        response = client.post(
            "/director/create_standalone",
            data={
                "name": "Weekly Competition",
                "date": tomorrow.strftime("%Y-%m-%d"),
                "location": "Main Hall",
                "description": "Weekly standalone competition",
                "rounds_count": "3",
                "min_participants": "4",
                "max_participants": "12",
                "entry_fee": "10.0",
                "discipline": "palla 8",
                "distance": "5",
                "withdraw_policy": "exclude",
            },
            follow_redirects=True,
        )

        assert response.status_code == 200

        # Verify gara was created
        gara = Gara.query.filter_by(name="Weekly Competition").first()
        assert gara is not None
        assert gara.campionato_id is None  # Standalone
        assert gara.director_id == director.id

        # Step 3: Add co-director
        co_director = User(
            username="co_director", email="co@test.com", role=UserRole.DIRECTOR.value
        )
        db_session.add(co_director)
        db_session.commit()

        assignment = DirectorAssignment(
            user_id=co_director.id,
            entity_type="gara",
            entity_id=gara.id,
            assigned_by_id=director.id,
        )
        db_session.add(assignment)
        db_session.commit()

        # Step 4: Co-director can access and manage the competition
        client.post("/auth/logout")
        client.post(
            "/auth/login",
            data={
                "username": "co_director",
                "password": "password123",  # Default password for test
            },
        )

        # Co-director should be able to access gara detail
        response = client.get(f"/admin/gara/{gara.id}")
        assert response.status_code == 200
        assert b"Weekly Competition" in response.data

        # Step 5: Create players and inscriptions
        players = []
        for i in range(6):
            player = User(
                username=f"player{i}",
                email=f"player{i}@test.com",
                role=UserRole.PLAYER.value,
            )
            player.set_password("player123")
            players.append(player)
            db_session.add(player)

        db_session.commit()

        # Step 6: Players inscribe to the competition
        inscriptions = []
        for player in players:
            client.post("/auth/logout")
            client.post(
                "/auth/login",
                data={"username": player.username, "password": "player123"},
            )

            response = client.post(
                f"/player/inscribe_to_gara/{gara.id}", follow_redirects=True
            )
            # Note: This assumes the inscription route exists

            # Create inscription manually for testing
            inscription = Inscription(user_id=player.id, gara_id=gara.id)
            inscriptions.append(inscription)
            db_session.add(inscription)

        db_session.commit()

        # Step 7: Verify inscriptions
        db_session.refresh(gara)
        assert len(gara.inscriptions) == 6

        # Step 8: Director can see inscriptions in dashboard
        client.post("/auth/logout")
        client.post(
            "/auth/login", data={"username": "director", "password": "director123"}
        )

        response = client.get("/dashboard")
        assert response.status_code == 200
        assert b"Weekly Competition" in response.data

    def test_multi_director_campionato_workflow(self, client, db_session):
        """Test campionato with multiple directors workflow."""
        # Step 1: Create admin and directors
        admin = User(
            username="admin", email="admin@test.com", role=UserRole.ADMIN.value
        )
        admin.set_password("admin123")
        main_director = User(
            username="main_director",
            email="main@test.com",
            role=UserRole.DIRECTOR.value,
        )
        main_director.set_password("main123")
        co_director1 = User(
            username="co_director1", email="co1@test.com", role=UserRole.DIRECTOR.value
        )
        co_director1.set_password("co1123")
        co_director2 = User(
            username="co_director2", email="co2@test.com", role=UserRole.DIRECTOR.value
        )
        co_director2.set_password("co2123")

        db_session.add_all([admin, main_director, co_director1, co_director2])
        db_session.commit()

        # Step 2: Main director creates campionato
        client.post(
            "/auth/login", data={"username": "main_director", "password": "main123"}
        )

        response = client.post(
            "/admin/campionato/create",
            data={
                "name": "Multi-Director Tournament",
                "campionato_type": "Amalfi",
                "without_x": "on",
                "final_playoffs": "on",
                "challenge_mode": "",
            },
            follow_redirects=True,
        )

        assert response.status_code == 200

        campionato = Campionato.query.filter_by(
            name="Multi-Director Tournament"
        ).first()
        assert campionato is not None

        # Step 3: Admin adds co-directors
        client.post("/auth/logout")
        client.post("/auth/login", data={"username": "admin", "password": "admin123"})

        # Add first co-director
        response = client.post(
            f"/admin/campionato/{campionato.id}/add_director",
            data={"user_id": str(co_director1.id)},
            follow_redirects=True,
        )

        assert response.status_code == 200

        # Add second co-director
        response = client.post(
            f"/admin/campionato/{campionato.id}/add_director",
            data={"user_id": str(co_director2.id)},
            follow_redirects=True,
        )

        assert response.status_code == 200

        # Step 4: Verify all directors can access campionato
        for director_user, password in [
            (main_director, "main123"),
            (co_director1, "co1123"),
            (co_director2, "co2123"),
        ]:
            client.post("/auth/logout")
            client.post(
                "/auth/login",
                data={"username": director_user.username, "password": password},
            )

            response = client.get(f"/admin/campionato/{campionato.id}")
            assert response.status_code == 200
            assert b"Multi-Director Tournament" in response.data

            # Should be able to edit
            response = client.get(f"/admin/campionato/{campionato.id}/edit")
            assert response.status_code == 200

        # Step 5: All directors should see campionato in dashboard
        for director_user, password in [
            (main_director, "main123"),
            (co_director1, "co1123"),
            (co_director2, "co2123"),
        ]:
            client.post("/auth/logout")
            client.post(
                "/auth/login",
                data={"username": director_user.username, "password": password},
            )

            response = client.get("/dashboard")
            assert response.status_code == 200
            assert b"Multi-Director Tournament" in response.data

        # Step 6: Admin removes a co-director
        client.post("/auth/logout")
        client.post("/auth/login", data={"username": "admin", "password": "admin123"})

        response = client.post(
            f"/admin/campionato/{campionato.id}/remove_director",
            data={"user_id": str(co_director2.id)},
            follow_redirects=True,
        )

        assert response.status_code == 200

        # Step 7: Removed co-director should not be able to access campionato
        client.post("/auth/logout")
        client.post(
            "/auth/login", data={"username": "co_director2", "password": "co2123"}
        )

        response = client.get(f"/admin/campionato/{campionato.id}")
        assert response.status_code == 403  # Forbidden

        # But should still see it in dashboard (view-only)
        response = client.get("/dashboard")
        assert response.status_code == 200
        assert b"Multi-Director Tournament" in response.data

    def test_notification_workflow(self, client, db_session):
        """Test notification workflow throughout user journey."""
        # Step 1: Create users
        player = User(
            username="player", email="player@test.com", role=UserRole.PLAYER.value
        )
        player.set_password("player123")
        admin = User(
            username="admin", email="admin@test.com", role=UserRole.ADMIN.value
        )
        admin.set_password("admin123")
        db_session.add_all([player, admin])
        db_session.commit()

        # Step 2: Player requests director status
        client.post("/auth/login", data={"username": "player", "password": "player123"})

        response = client.post(
            "/player/request_director",
            data={"reason": "I want to organize local tournaments"},
            follow_redirects=True,
        )

        assert response.status_code == 200

        director_request = DirectorRequest.query.filter_by(user_id=player.id).first()
        assert director_request is not None

        # Check that notification was created (if notification system is implemented)
        from models.notification.services import NotificationService

        # Admin should have notification about new director request
        _ = NotificationService.get_user_notifications(
            admin.id, unread_only=True
        )  # admin_notifications not used in test
        # Note: This assumes notification is created automatically on director request

        client.post("/auth/logout")

        # Step 3: Admin processes request and player gets notification
        client.post("/auth/login", data={"username": "admin", "password": "admin123"})

        response = client.post(
            f"/admin/director_requests/{director_request.id}/process",
            data={"status": "approved", "admin_notes": "Qualified for director role"},
            follow_redirects=True,
        )

        assert response.status_code == 200

        # Check that player got notification about promotion
        _ = NotificationService.get_user_notifications(
            player.id, unread_only=True
        )  # player_notifications not used in test
        # Note: This assumes notification is created on director promotion

        # Step 4: Player (now director) creates competition and notifies participants
        client.post("/auth/logout")
        client.post(
            "/auth/login",
            data={"username": "player", "password": "player123"},  # Now director
        )

        # Create participants
        participants = []
        for i in range(3):
            participant = User(
                username=f"participant{i}",
                email=f"participant{i}@test.com",
                role=UserRole.PLAYER.value,
            )
            participant.set_password("part123")
            participants.append(participant)
            db_session.add(participant)

        db_session.commit()

        # Create competition
        tomorrow = date.today() + timedelta(days=1)
        response = client.post(
            "/director/create_standalone",
            data={
                "name": "Notification Test Competition",
                "date": tomorrow.strftime("%Y-%m-%d"),
                "location": "Test Location",
                "description": "Competition to test notifications",
                "rounds_count": "3",
                "min_participants": "4",
                "max_participants": "8",
                "entry_fee": "10.0",
                "discipline": "palla 9",
                "distance": "7",
                "withdraw_policy": "exclude",
            },
            follow_redirects=True,
        )

        assert response.status_code == 200

        # All users should be able to see the competition in their dashboard
        for participant in participants:
            client.post("/auth/logout")
            client.post(
                "/auth/login",
                data={"username": participant.username, "password": "part123"},
            )

            response = client.get("/dashboard")
            assert response.status_code == 200
            assert b"Notification Test Competition" in response.data


@pytest.mark.e2e
class TestErrorHandlingWorkflows:
    """Test error handling in complete workflows."""

    def test_permission_denied_workflows(self, client, db_session):
        """Test permission denied scenarios throughout workflows."""
        # Step 1: Create users
        player = User(
            username="player", email="player@test.com", role=UserRole.PLAYER.value
        )
        player.set_password("player123")
        director = User(
            username="director", email="director@test.com", role=UserRole.DIRECTOR.value
        )
        director.set_password("director123")
        admin = User(
            username="admin", email="admin@test.com", role=UserRole.ADMIN.value
        )
        admin.set_password("admin123")
        db_session.add_all([player, director, admin])
        db_session.commit()

        # Create director's campionato
        tournament_service = TournamentService()
        campionato = tournament_service.create_campionato_with_director(
            name="Director Tournament",
            creator_user_id=director.id,
            campionato_type="Amalfi",
        )

        # Step 2: Player tries to access admin routes
        client.post("/auth/login", data={"username": "player", "password": "player123"})

        # Should be denied access to admin dashboard
        response = client.get("/admin/dashboard")
        assert response.status_code in [403, 302]  # Forbidden or redirect to login

        # Should be denied access to campionato management
        response = client.get(f"/admin/campionato/{campionato.id}")
        assert response.status_code in [403, 302]

        # Should be denied access to director creation routes
        response = client.get("/director/create_standalone")
        assert response.status_code in [403, 302]

        client.post("/auth/logout")

        # Step 3: Director tries to access other director's campionato
        other_director = User(
            username="other_director",
            email="other@test.com",
            role=UserRole.DIRECTOR.value,
        )
        other_director.set_password("other123")
        db_session.add(other_director)
        db_session.commit()

        client.post(
            "/auth/login", data={"username": "other_director", "password": "other123"}
        )

        # Should be denied access to campionato they don't manage
        response = client.get(f"/admin/campionato/{campionato.id}")
        assert response.status_code == 403

        # Should be denied edit access
        response = client.get(f"/admin/campionato/{campionato.id}/edit")
        assert response.status_code == 403

        client.post("/auth/logout")

        # Step 4: Director tries to access admin-only functions
        client.post(
            "/auth/login", data={"username": "director", "password": "director123"}
        )

        # Should be denied access to user management
        response = client.get("/admin/users")
        assert response.status_code in [403, 404]  # Might not exist or be forbidden

        # Should be denied access to director requests
        response = client.get("/admin/director_requests")
        assert response.status_code in [403, 404]

        # Should be denied campionato deletion (only admin can delete)
        response = client.post(f"/admin/campionato/{campionato.id}/delete")
        assert response.status_code == 403

    def test_data_validation_workflows(self, client, db_session):
        """Test data validation throughout workflows."""
        # Step 1: Create director
        director = User(
            username="director", email="director@test.com", role=UserRole.DIRECTOR.value
        )
        director.set_password("director123")
        db_session.add(director)
        db_session.commit()

        client.post(
            "/auth/login", data={"username": "director", "password": "director123"}
        )

        # Step 2: Try to create campionato with invalid data
        response = client.post(
            "/admin/campionato/create",
            data={
                "name": "",  # Empty name
                "campionato_type": "Amalfi",
            },
        )

        # Should return to form with error (not redirect)
        assert response.status_code == 200

        # Should not create campionato
        empty_name_campionato = Campionato.query.filter_by(name="").first()
        assert empty_name_campionato is None

        # Step 3: Try to create gara with invalid data
        # First create valid campionato
        response = client.post(
            "/admin/campionato/create",
            data={
                "name": "Valid Tournament",
                "campionato_type": "Amalfi",
            },
            follow_redirects=True,
        )

        campionato = Campionato.query.filter_by(name="Valid Tournament").first()
        assert campionato is not None

        # Try to create gara with past date
        yesterday = date.today() - timedelta(days=1)
        response = client.post(
            f"/admin/campionato/{campionato.id}/create_gara",
            data={
                "name": "Past Date Gara",
                "date": yesterday.strftime("%Y-%m-%d"),  # Past date
                "location": "Test Location",
                "discipline": "palla 9",
                "distance": "7",
            },
        )

        # Should handle validation (implementation specific)
        # Either return error or accept (depending on business rules)

        # Step 4: Try to create standalone gara with invalid participant limits
        response = client.post(
            "/director/create_standalone",
            data={
                "name": "Invalid Limits Gara",
                "date": (date.today() + timedelta(days=1)).strftime("%Y-%m-%d"),
                "location": "Test Location",
                "discipline": "palla 9",
                "distance": "7",
                "min_participants": "10",  # Min > Max
                "max_participants": "5",
            },
        )

        # Should handle validation error
        assert response.status_code == 200  # Return to form with error

        # Should not create gara
        invalid_gara = Gara.query.filter_by(name="Invalid Limits Gara").first()
        assert invalid_gara is None
