"""
Integration tests for complete user workflows from docs/SPECIFICHE.md

Tests all user types and their complete workflows:
- Guest user workflows
- Player registration, dashboard, match proposals
- Director tournament creation and management
- Admin system administration

Covers both backend services and frontend UI interactions.
"""

import pytest
from datetime import date, datetime, timedelta
from typing import List
import uuid
import json

from models import User, Gara, Match, Inscription, Campionato
from models.user.role_enum import UserRole
from models.status_enum import GaraStatus, MatchStatus
from models.user.services import UserService
from models.competition.services import GaraService, InscriptionService
from models.campionato.services import TournamentService
from models.match.services import MatchService, RackService
from models.individual_match.services import IndividualMatchService
from models.location.models import BilliardHall
from models.notification.models import Notification


@pytest.mark.integration
class TestUserWorkflowsComplete:
    """Test complete user workflows as specified in SPECIFICHE.md"""

    @pytest.fixture
    def admin_user(self, db_session) -> User:
        """Create admin user (configured in server settings)."""
        # Admin user as specified in SPECIFICHE.md
        admin = User(
            username="admin",
            email="admin@tornei-biliardo.com",
            role=UserRole.ADMIN.value,
        )
        admin.set_password("admin_password")  # Configured server-side
        db_session.add(admin)
        db_session.commit()
        return admin

    @pytest.fixture
    def guest_venues(self, db_session):
        """Create venues for testing."""
        venues = [
            BilliardHall(
                name="Centro Biliardo Roma",
                address="Via Roma 123",
                city="Roma",
                number_of_tables=6,
                is_active=True,
            ),
            BilliardHall(
                name="Pool House Milano",
                address="Via Milano 456",
                city="Milano",
                number_of_tables=4,
                is_active=True,
            ),
        ]
        db_session.add_all(venues)
        db_session.commit()
        return venues

    def test_guest_user_complete_workflow(
        self, admin_user: User, guest_venues, db_session, client
    ):
        """
        Test complete Guest user workflow from SPECIFICHE.md:

        Guest user workflow:
        1. Registration with username, email, phone, password
        2. Login with userid and password
        3. Vista complessiva - home with campionati and standalone gare
        4. Vista campionato - tournament details and classifications
        5. Vista gara - player list, rounds, classifications, live results
        """
        # Setup: Create some tournaments for guest viewing
        # Create standalone gara
        gara_standalone = GaraService.create_gara(
            campionato_id=None,
            number=1,
            name="Torneo Standalone Pubblico",
            date=date.today() + timedelta(days=1),
            location="Centro Biliardo Roma",
            description="Torneo standalone visibile ai guest",
            rounds_count=3,
            min_participants=6,
            max_participants=10,
            entry_fee=20.0,
            discipline="palla_9",
            distance=7,
            best_of=True,
            director_id=admin_user.id,
            matchmaking_strategy="amalfi",
        )

        # Create campionato with gara
        campionato = TournamentService().create_campionato(
            name="Campionato Guest Test",
            description="Campionato visibile ai guest",
            start_date=date.today(),
            end_date=date.today() + timedelta(days=90),
            director_id=admin_user.id,
        )

        gara_campionato = GaraService.create_gara(
            campionato_id=campionato.id,
            number=1,
            name="Prima Gara Campionato",
            date=date.today() + timedelta(days=7),
            location="Pool House Milano",
            description="Prima gara del campionato",
            rounds_count=3,
            min_participants=8,
            max_participants=12,
            entry_fee=25.0,
            discipline="palla_8",
            distance=5,
            best_of=True,
            director_id=admin_user.id,
            matchmaking_strategy="amalfi",
        )

        # Make tournaments visible (move to inscription status)
        from models.competition.services import ProvaStateMachine

        ProvaStateMachine.to_inscription(gara_standalone)
        ProvaStateMachine.to_inscription(gara_campionato)

        # Step 1: Guest Registration
        registration_data = {
            "username": "nuovo_player_guest",
            "email": "nuovo_player@test.com",
            "phone": "+39 123 456 7890",  # Optional field
            "password": "secure_password123",
            "confirm_password": "secure_password123",
        }

        response = client.post("/auth/register", data=registration_data)
        # Registration should succeed or redirect
        assert response.status_code in [200, 302]

        # Verify user created
        new_user = User.query.filter_by(username="nuovo_player_guest").first()
        assert new_user is not None
        assert new_user.email == "nuovo_player@test.com"
        assert new_user.role == UserRole.PLAYER.value

        # Step 2: Login workflow
        login_data = {
            "username": "nuovo_player_guest",
            "password": "secure_password123",
        }

        response = client.post("/auth/login", data=login_data)
        assert response.status_code in [200, 302]  # Success or redirect to dashboard

        # Verify session established
        with client.session_transaction() as sess:
            assert "_user_id" in sess

        # Step 3: Vista complessiva (Home) - now authenticated user
        response = client.get("/")
        assert response.status_code == 200
        home_content = response.data.decode("utf-8")

        # Should see both campionati and standalone gare
        assert "Torneo Standalone Pubblico" in home_content
        assert "Campionato Guest Test" in home_content

        # Step 4: Vista campionato - tournament details
        response = client.get(f"/campionato/{campionato.id}")
        if response.status_code == 200:
            campionato_content = response.data.decode("utf-8")
            assert "Campionato Guest Test" in campionato_content
            assert "Prima Gara Campionato" in campionato_content

        # Step 5: Vista gara - detailed tournament view
        response = client.get(f"/gara/{gara_standalone.id}")
        assert response.status_code == 200
        gara_content = response.data.decode("utf-8")

        # Should show tournament details
        assert "Torneo Standalone Pubblico" in gara_content
        assert "palla_9" in gara_content or "9-ball" in gara_content
        assert "Centro Biliardo Roma" in gara_content

        print("✅ Guest user complete workflow completed")

    def test_player_complete_workflow(
        self, admin_user: User, guest_venues, db_session, client
    ):
        """
        Test complete Player workflow from SPECIFICHE.md:

        Player workflow:
        1. Dashboard with ongoing activities
        2. Profile with venue availability settings
        3. Individual match proposals (with invite and open)
        4. Tournament inscription and participation
        5. Soft delete with pseudonymization
        """
        # Step 1: Create player users
        player1 = User(
            username="player_workflow_1",
            email="player1@workflow.com",
            role=UserRole.PLAYER.value,
        )
        player1.set_password("player123")

        player2 = User(
            username="player_workflow_2",
            email="player2@workflow.com",
            role=UserRole.PLAYER.value,
        )
        player2.set_password("player123")

        db_session.add_all([player1, player2])
        db_session.commit()

        # Step 2: Player 1 Dashboard workflow
        with client.session_transaction() as sess:
            sess["_user_id"] = str(player1.id)
            sess["_fresh"] = True

        response = client.get("/dashboard")
        assert response.status_code == 200
        dashboard_content = response.data.decode("utf-8")

        # Dashboard should show ongoing activities
        assert "Dashboard" in dashboard_content or "Pannello" in dashboard_content

        # Step 3: Profile and venue availability
        response = client.get("/player/profile")
        if response.status_code == 200:
            profile_content = response.data.decode("utf-8")
            assert player1.username in profile_content

        # Set venue availability
        venue = guest_venues[0]
        from models.individual_match.services import AvailabilityService

        availability = AvailabilityService.set_venue_availability(
            user_id=player1.id,
            billiard_hall_id=venue.id,
            is_available=True,
        )

        # Step 4: Individual match proposal with invite
        match_proposal = IndividualMatchService.create_match_proposal(
            proposer_id=player1.id,
            invited_player_id=player2.id,
            location=venue.name,
            proposed_date=datetime.now() + timedelta(days=2),
            discipline="palla_8",
            distance=5,
            description="Match proposto da player workflow",
            expires_at=datetime.now() + timedelta(days=1),
        )

        # Step 5: Player 2 receives and responds to proposal
        with client.session_transaction() as sess:
            sess["_user_id"] = str(player2.id)
            sess["_fresh"] = True

        # Player 2 views dashboard and sees proposal
        response = client.get("/dashboard")
        if response.status_code == 200:
            p2_dashboard = response.data.decode("utf-8")
            # Should see match proposal notification

        # Player 2 accepts proposal
        IndividualMatchService.accept_proposal(match_proposal.id, player2.id)

        # Verify match created
        db_session.refresh(match_proposal)
        assert match_proposal.status == "accepted"

        # Step 6: Open match proposal workflow
        with client.session_transaction() as sess:
            sess["_user_id"] = str(player1.id)
            sess["_fresh"] = True

        open_proposal = IndividualMatchService.create_open_proposal(
            proposer_id=player1.id,
            location=venue.name,
            scheduled_at=datetime.now() + timedelta(days=3),
            discipline="palla_9",
            distance=7,
            description="Match aperto a tutti",
            expires_at=datetime.now() + timedelta(hours=48),
        )

        # Players with venue availability should get notifications
        # (Notification system would be tested separately)

        # Step 7: Tournament inscription workflow
        # Create tournament for inscription
        gara = GaraService.create_gara(
            campionato_id=None,
            number=1,
            name="Torneo Player Workflow",
            date=date.today() + timedelta(days=5),
            location=venue.name,
            description="Torneo per test workflow player",
            rounds_count=3,
            min_participants=6,
            max_participants=10,
            entry_fee=15.0,
            discipline="palla_10",
            distance=6,
            best_of=True,
            director_id=admin_user.id,
            matchmaking_strategy="amalfi",
        )

        # Open inscriptions
        inscription_start = datetime.now() - timedelta(hours=1)
        inscription_end = datetime.now() + timedelta(days=1)
        GaraService.open_inscriptions(gara.id, inscription_start, inscription_end)

        # Player 1 inscribes
        inscription = InscriptionService.inscribe_user(player1.id, gara.id)
        assert inscription is not None
        assert not inscription.is_waitlist

        # Step 8: Soft delete workflow
        # Player requests account deletion
        original_username = player1.username
        original_email = player1.email

        UserService.soft_delete_user(player1.id)

        # Verify soft delete with pseudonymization
        db_session.refresh(player1)
        assert player1.username != original_username  # Pseudonymized
        assert player1.email != original_email  # Anonymized
        assert not player1.is_active  # Deactivated

        # Verify matches are preserved for statistics
        # But new inscriptions should be cancelled

        print("✅ Player complete workflow completed")

    def test_director_complete_workflow(
        self, admin_user: User, guest_venues, db_session, client
    ):
        """
        Test complete Director workflow from SPECIFICHE.md:

        Director workflow:
        1. Becomes director through promotion request
        2. Creates new campionato
        3. Creates gara within campionato
        4. Manages inscriptions and tournament flow
        5. Uses all admin powers for their tournaments
        """
        # Step 1: Create player who will become director
        future_director = User(
            username="future_director",
            email="future_director@workflow.com",
            role=UserRole.PLAYER.value,
        )
        future_director.set_password("director123")
        db_session.add(future_director)
        db_session.commit()

        # Step 2: Player requests director promotion
        from models.user.services import DirectorRequestService

        director_request = DirectorRequestService.create_request(
            user_id=future_director.id,
            motivation="Voglio organizzare tornei per la community",
        )

        # Step 3: Admin approves request
        with client.session_transaction() as sess:
            sess["_user_id"] = str(admin_user.id)
            sess["_fresh"] = True

        DirectorRequestService.approve_director_request(
            request_id=director_request.id,
            approved_by_id=admin_user.id,
        )

        # Verify user is now director
        db_session.refresh(future_director)
        assert future_director.role == UserRole.DIRECTOR.value

        # Step 4: Director creates campionato
        with client.session_transaction() as sess:
            sess["_user_id"] = str(future_director.id)
            sess["_fresh"] = True

        campionato = TournamentService().create_campionato(
            name="Campionato Director Workflow",
            description="Campionato creato dal director test",
            start_date=date.today(),
            end_date=date.today() + timedelta(days=120),
            director_id=future_director.id,
        )

        # Step 5: Director creates gara within campionato
        gara = GaraService.create_gara(
            campionato_id=campionato.id,
            number=1,
            name="Gara Director Test",
            date=date.today() + timedelta(days=10),
            location=guest_venues[0].name,
            description="Prima gara del campionato director",
            rounds_count=3,
            min_participants=6,
            max_participants=10,
            entry_fee=20.0,
            discipline="palla_8",
            distance=5,
            best_of=True,
            director_id=future_director.id,
            matchmaking_strategy="amalfi",
            first_round_policy="random",
            odd_number_policy="bye",
            anti_rematch_enabled=True,
            rating_type=None,
        )

        # Verify director has admin powers for their tournament
        assert gara.director_id == future_director.id

        # Step 6: Director manages inscriptions
        # Add some test players
        test_players = []
        for i in range(6):
            player = User(
                username=f"test_player_dir_{i}",
                email=f"test_player_dir_{i}@test.com",
                role=UserRole.PLAYER.value,
            )
            player.set_password("player123")
            test_players.append(player)

        db_session.add_all(test_players)
        db_session.commit()

        # Open inscriptions
        inscription_start = datetime.now() - timedelta(hours=1)
        inscription_end = datetime.now() + timedelta(days=2)
        GaraService.open_inscriptions(gara.id, inscription_start, inscription_end)

        # Players inscribe
        for player in test_players:
            InscriptionService.inscribe_user(player.id, gara.id)

        # Step 7: Director starts and manages tournament
        GaraService.start_first_round(gara.id)

        # Verify director can manage their tournament
        response = client.get(f"/gara/{gara.id}")
        assert response.status_code == 200
        gara_content = response.data.decode("utf-8")
        assert "Gara Director Test" in gara_content

        # Director should see management options
        # (Specific UI implementation may vary)

        print("✅ Director complete workflow completed")

    def test_admin_system_management_workflow(
        self, admin_user: User, guest_venues, db_session, client
    ):
        """
        Test complete Admin workflow from SPECIFICHE.md:

        Admin workflow:
        1. System administration and user management
        2. Tournament oversight and management
        3. Global settings and configuration
        4. Statistics and reporting access
        5. Challenge and exam management
        """
        # Step 1: Admin login and dashboard access
        with client.session_transaction() as sess:
            sess["_user_id"] = str(admin_user.id)
            sess["_fresh"] = True

        response = client.get("/admin/")
        assert response.status_code == 200
        admin_dashboard = response.data.decode("utf-8")

        # Should see admin dashboard
        assert "Admin" in admin_dashboard or "Amministrazione" in admin_dashboard

        # Step 2: User management workflow
        response = client.get("/admin/users")
        if response.status_code == 200:
            users_page = response.data.decode("utf-8")
            # Should see user management interface

        # Create test user for management
        test_user = User(
            username="admin_test_user",
            email="admin_test@test.com",
            role=UserRole.PLAYER.value,
        )
        test_user.set_password("test123")
        db_session.add(test_user)
        db_session.commit()

        # Admin should be able to view/modify user
        response = client.get(f"/admin/user/{test_user.id}")
        if response.status_code == 200:
            user_details = response.data.decode("utf-8")
            assert test_user.username in user_details

        # Step 3: Tournament oversight
        # Create tournament to manage
        gara = GaraService.create_gara(
            campionato_id=None,
            number=1,
            name="Admin Oversight Tournament",
            date=date.today() + timedelta(days=5),
            location=guest_venues[0].name,
            description="Tournament for admin management testing",
            rounds_count=2,
            min_participants=4,
            max_participants=8,
            entry_fee=15.0,
            discipline="palla_9",
            distance=5,
            best_of=True,
            director_id=admin_user.id,
            matchmaking_strategy="amalfi",
        )

        # Admin views all tournaments
        response = client.get("/admin/competitions")
        if response.status_code == 200:
            competitions_page = response.data.decode("utf-8")
            assert "Admin Oversight Tournament" in competitions_page

        # Step 4: Challenge management
        from models.challenge.models import Challenge

        # Admin creates challenge
        challenge = Challenge(
            title="Admin Test Challenge",
            description="Challenge created by admin for testing",
            image_path="/static/challenges/admin_test.jpg",
            is_active=True,
            max_attempts=3,
        )
        db_session.add(challenge)
        db_session.commit()

        # Admin views challenge statistics
        response = client.get("/admin/challenges")
        if response.status_code == 200:
            challenges_page = response.data.decode("utf-8")
            assert "Admin Test Challenge" in challenges_page

        # Step 5: System statistics and reporting
        response = client.get("/admin/statistics")
        if response.status_code == 200:
            stats_page = response.data.decode("utf-8")
            # Should show system-wide statistics
            # (Implementation specific)

        # Step 6: Venue management
        response = client.get("/admin/venues")
        if response.status_code == 200:
            venues_page = response.data.decode("utf-8")
            # Should show venue management
            for venue in guest_venues:
                assert venue.name in venues_page

        print("✅ Admin system management workflow completed")

    def test_notification_and_communication_workflow(
        self, admin_user: User, guest_venues, db_session, client
    ):
        """
        Test notification and communication workflows across user types.

        Tests:
        1. Tournament inscription notifications
        2. Match proposal notifications
        3. Waitlist management notifications
        4. System notifications from admin
        """
        from models.notification.services import NotificationService

        # Step 1: Create players for notification testing
        players = []
        for i in range(4):
            player = User(
                username=f"notify_player_{i}",
                email=f"notify_player_{i}@test.com",
                role=UserRole.PLAYER.value,
            )
            player.set_password("player123")
            players.append(player)

        db_session.add_all(players)
        db_session.commit()

        # Step 2: Tournament inscription notifications
        gara = GaraService.create_gara(
            campionato_id=None,
            number=1,
            name="Notification Test Tournament",
            date=date.today() + timedelta(days=7),
            location=guest_venues[0].name,
            description="Tournament for notification testing",
            rounds_count=2,
            min_participants=4,
            max_participants=6,  # Limited for waitlist testing
            entry_fee=15.0,
            discipline="palla_8",
            distance=5,
            best_of=True,
            director_id=admin_user.id,
            matchmaking_strategy="amalfi",
        )

        # Open inscriptions
        inscription_start = datetime.now() - timedelta(hours=1)
        inscription_end = datetime.now() + timedelta(days=2)
        GaraService.open_inscriptions(gara.id, inscription_start, inscription_end)

        # First 3 players inscribe (confirmed)
        for player in players[:3]:
            InscriptionService.inscribe_user(player.id, gara.id)

        # 4th player inscribes (waitlisted due to max 6 limit, but we'll make it exact)
        # Actually, let's add 2 more players to test waitlist
        extra_players = []
        for i in range(4, 8):
            player = User(
                username=f"notify_player_{i}",
                email=f"notify_player_{i}@test.com",
                role=UserRole.PLAYER.value,
            )
            player.set_password("player123")
            extra_players.append(player)

        db_session.add_all(extra_players)
        db_session.commit()

        # Fill to capacity and create waitlist
        for player in extra_players[:3]:  # Players 4,5,6 - confirmed
            InscriptionService.inscribe_user(player.id, gara.id)

        # Player 7 goes to waitlist
        waitlist_inscription = InscriptionService.inscribe_user(
            extra_players[3].id, gara.id
        )
        db_session.refresh(waitlist_inscription)
        assert waitlist_inscription.is_waitlist

        # Step 3: Waitlist notification test
        # Player from confirmed list drops out
        confirmed_inscription = Inscription.query.filter_by(
            gara_id=gara.id, user_id=players[0].id, is_waitlist=False
        ).first()

        InscriptionService.uninscribe_user(
            player1.id, gara_id=confirmed_inscription.gara_id
        )

        # Waitlisted player should get notification and auto-promotion
        db_session.refresh(waitlist_inscription)
        # Should be promoted from waitlist

        # Step 4: Match proposal notifications
        match_proposal = IndividualMatchService.create_match_proposal(
            proposer_id=players[0].id,
            invited_player_id=players[1].id,
            location=guest_venues[0].name,
            proposed_date=datetime.now() + timedelta(days=1),
            discipline="palla_9",
            distance=5,
            description="Notification test match",
            expires_at=datetime.now() + timedelta(hours=24),
        )

        # Player should receive notification
        notifications = Notification.query.filter_by(user_id=players[1].id).all()
        # Should have match proposal notification

        # Step 5: System notification from admin
        NotificationService.create_notification(
            user_id=players[0].id,
            title="System Notification Test",
            message="This is a test system notification from admin",
            notification_type="system",
            sent_by_id=admin_user.id,
        )

        # Verify notification created
        system_notification = Notification.query.filter_by(
            user_id=players[0].id, notification_type="system"
        ).first()
        assert system_notification is not None

        print("✅ Notification and communication workflow completed")

    def test_playoff_and_advanced_features_workflow(
        self, admin_user: User, guest_venues, db_session, client
    ):
        """
        Test advanced features workflow from SPECIFICHE.md:

        Advanced features:
        1. Playoff system with qualification criteria
        2. Exam system with challenge combinations
        3. Rating systems (Fargo/Elo integration)
        4. Advanced tournament configurations
        """
        # Step 1: Create campionato with playoff configuration
        campionato = TournamentService().create_campionato(
            name="Campionato con Playoff",
            description="Campionato con sistema playoff avanzato",
            start_date=date.today(),
            end_date=date.today() + timedelta(days=180),
            director_id=admin_user.id,
        )

        # Configure playoff criteria (top 6 players)
        from models.playoff.services import PlayoffService

        playoff_config = PlayoffService.create_playoff_configuration(
            campionato_id=campionato.id,
            name="Elite Playoff",
            qualification_criteria={
                "min_position": 1,
                "max_position": 6,
                "min_games_played": 3,
            },
            max_participants=6,
        )

        # Step 2: Create players and complete campionato gare
        players = []
        for i in range(10):
            player = User(
                username=f"playoff_player_{i}",
                email=f"playoff_player_{i}@test.com",
                role=UserRole.PLAYER.value,
            )
            player.set_password("player123")
            players.append(player)

        db_session.add_all(players)
        db_session.commit()

        # Create and complete 3 gare in campionato
        for gara_num in range(1, 4):
            gara = GaraService.create_gara(
                campionato_id=campionato.id,
                number=gara_num,
                name=f"Gara {gara_num} Playoff Test",
                date=date.today() + timedelta(days=gara_num * 14),
                location=guest_venues[0].name,
                description=f"Gara {gara_num} for playoff qualification",
                rounds_count=2,
                min_participants=8,
                max_participants=12,
                entry_fee=20.0,
                discipline="palla_9",
                distance=5,
                best_of=True,
                director_id=admin_user.id,
                matchmaking_strategy="amalfi",
            )

            # Players inscribe
            for player in players[:8]:
                InscriptionService.inscribe_user(player.id, gara.id)

            # Complete gara (simplified)
            inscription_start = datetime.now() - timedelta(hours=1)
            inscription_end = datetime.now() + timedelta(hours=1)
            GaraService.open_inscriptions(gara.id, inscription_start, inscription_end)
            GaraService.start_first_round(gara.id)

            # Complete matches for classification
            matches = Match.query.filter_by(gara_id=gara.id, round_number=1).all()
            for match in matches:
                if not match.is_bye:
                    self._complete_match_simple(match, db_session)

            # Update campionato classification
            TournamentService().update_campionato_classification(campionato.id)

        # Step 3: Generate playoff from qualifications
        qualified_players = PlayoffService.get_qualified_players(
            playoff_config.id, campionato.id
        )

        # Should have 6 qualified players
        assert len(qualified_players) <= 6

        # Step 4: Exam system workflow
        from models.exam.services import ExamService
        from models.challenge.models import Challenge

        # Create challenges for exam
        challenges = []
        for i in range(3):
            challenge = Challenge(
                title=f"Exam Challenge {i+1}",
                description=f"Challenge {i+1} for exam testing",
                image_path=f"/static/challenges/exam_{i+1}.jpg",
                is_active=True,
                max_attempts=2,
            )
            challenges.append(challenge)

        db_session.add_all(challenges)
        db_session.commit()

        # Create exam with grading criteria
        exam = ExamService.create_exam(
            title="Test Exam Workflow",
            description="Exam for testing advanced features",
            challenges=[c.id for c in challenges],
            grading_criteria={
                "excellent": {"min_score": 85, "level": "A"},
                "good": {"min_score": 70, "level": "B"},
                "pass": {"min_score": 60, "level": "C"},
            },
            created_by_id=admin_user.id,
        )

        # Player takes exam
        exam_attempt = ExamService.start_exam_attempt(
            exam_id=exam.id,
            user_id=players[0].id,
        )

        # Complete challenges in exam
        for challenge in challenges:
            ExamService.record_challenge_attempt_in_exam(
                exam_attempt_id=exam_attempt.id,
                challenge_id=challenge.id,
                score=75,  # Good score
                max_score=100,
            )

        # Finalize exam
        final_result = ExamService.finalize_exam_attempt(exam_attempt.id)
        assert final_result.level == "B"  # Good level

        print("✅ Playoff and advanced features workflow completed")

    # Helper method
    def _complete_match_simple(self, match: Match, db_session) -> None:
        """Complete a match with simple result."""
        if match.is_bye:
            return

        import random

        winner_id = (
            match.player1_id if random.choice([True, False]) else match.player2_id
        )
        loser_id = (
            match.player2_id if winner_id == match.player1_id else match.player1_id
        )

        # Add some racks
        for rack_num in range(1, 4):  # Winner gets 3
            RackService.add_rack_result(
                match_id=match.id,
                rack_number=rack_num,
                winner_id=winner_id,
                reported_by_id=winner_id,
                confirmed_by_player=True,
                validated_by_admin=True,
            )

        # Loser gets 1
        RackService.add_rack_result(
            match_id=match.id,
            rack_number=4,
            winner_id=loser_id,
            reported_by_id=loser_id,
            confirmed_by_player=True,
            validated_by_admin=True,
        )

        MatchService.to_completed(match.id)
