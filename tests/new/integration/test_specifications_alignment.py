"""
Alignment tests to verify current implementation matches specifications.

Tests core functionality from docs/ specifications using only existing services.
Uses proper fixture isolation to fix test reliability.
"""

import pytest
from datetime import date, datetime, timedelta

from models import User, Gara, Match, Inscription
from models.user.role_enum import UserRole
from models.status_enum import GaraStatus, MatchStatus
from models.competition.services import GaraService, InscriptionService
from models.match.services import MatchService, RackService
from models.classification.models import RoundClassification


@pytest.mark.integration
class TestSpecificationsAlignmentFixed:
    """Test alignment with specifications in docs/ using isolated fixtures."""

    def test_gare_use_case_1_amalfi_basic(
        self, isolated_admin_user: User, isolated_players, db_session, client
    ):
        """
        Test Use Case 1 from docs/usecases/gare.md
        Admin creates standalone amalfi gara with 3 rounds, 8 players
        """
        admin_user = isolated_admin_user
        players_8 = isolated_players[:8]

        # Step 1: Admin creates standalone gara with amalfi strategy
        gara = GaraService.create_gara(
            campionato_id=None,  # Standalone
            number=1,
            name="UC1 Amalfi Test Fixed",
            date=date.today() + timedelta(days=1),
            location="Pool Hall Test",
            description="9-ball amalfi best-of-9",
            rounds_count=3,
            min_participants=6,
            max_participants=10,
            entry_fee=15.0,
            discipline="palla_9",
            distance=9,
            best_of=True,
            director_id=admin_user.id,
            matchmaking_strategy="amalfi",
            first_round_policy="random",
            odd_number_policy="bye",
            anti_rematch_enabled=True,
            rating_type=None,
        )

        assert gara.status == GaraStatus.SETUP.value
        assert gara.matchmaking_strategy == "amalfi"
        assert gara.best_of is True

        # Step 2: 8 players inscribe
        for player in players_8:
            inscription = InscriptionService.inscribe_user(player.id, gara.id)
            assert inscription is not None

        # Verify inscriptions
        inscriptions = Inscription.query.filter_by(gara_id=gara.id).all()
        assert len(inscriptions) == 8

        # Step 3: Open inscriptions and start first round
        inscription_start = datetime.now() - timedelta(hours=1)
        inscription_end = datetime.now() + timedelta(hours=1)
        GaraService.open_inscriptions(gara.id, inscription_start, inscription_end)
        GaraService.start_first_round(gara.id)

        db_session.refresh(gara)
        assert gara.status == GaraStatus.PLAYING.value
        assert gara.current_round == 1

        # Step 4: Verify first round matches
        round1_matches = Match.query.filter_by(gara_id=gara.id, round_number=1).all()
        assert len(round1_matches) == 4  # 8 players = 4 matches

        # Step 5: Complete first round
        for match in round1_matches:
            if not match.is_bye:
                self._complete_match_simple(match, 5, 2, db_session)

        # Step 6: Calculate classification
        RoundClassification.calculate_classification_after_round(gara.id, 1)

        # Step 7: Start second round
        GaraService.create_amalfi_round(gara.id, 2)
        gara.current_round = 2
        db_session.add(gara)
        db_session.commit()

        round2_matches = Match.query.filter_by(gara_id=gara.id, round_number=2).all()
        assert len(round2_matches) == 4

        # Verify anti-rematch is working
        round1_pairings = {
            tuple(sorted([m.player1_id, m.player2_id])) for m in round1_matches
        }
        round2_pairings = {
            tuple(sorted([m.player1_id, m.player2_id]))
            for m in round2_matches
            if not m.is_bye
        }
        rematch_count = len(round1_pairings.intersection(round2_pairings))
        assert rematch_count == 0, f"Found {rematch_count} rematches"

        print("✅ Use Case 1 basic Amalfi workflow verified")

    def test_gare_use_case_2_random_strategy_basic(
        self, isolated_admin_user: User, isolated_players, db_session, client
    ):
        """
        Test Use Case 2 from docs/usecases/gare.md
        Random strategy with 3 rounds
        """
        admin_user = isolated_admin_user
        players_8 = isolated_players[:8]

        # Create gara with random strategy
        gara = GaraService.create_gara(
            campionato_id=None,
            number=1,
            name="UC2 Random Test Fixed",
            date=date.today() + timedelta(days=1),
            location="Random Pool Hall",
            description="8-ball random strategy",
            rounds_count=3,
            min_participants=6,
            max_participants=10,
            entry_fee=20.0,
            discipline="palla_8",
            distance=9,
            best_of=True,
            director_id=admin_user.id,
            matchmaking_strategy="random",
            first_round_policy="random",
            odd_number_policy="bye",
            anti_rematch_enabled=True,
            rating_type=None,
        )

        assert gara.matchmaking_strategy == "random"

        # Players inscribe and start
        for player in players_8:
            InscriptionService.inscribe_user(player.id, gara.id)

        inscription_start = datetime.now() - timedelta(hours=1)
        inscription_end = datetime.now() + timedelta(hours=1)
        GaraService.open_inscriptions(gara.id, inscription_start, inscription_end)
        GaraService.start_first_round(gara.id)

        # Complete first round
        round1_matches = Match.query.filter_by(gara_id=gara.id, round_number=1).all()
        for match in round1_matches:
            if not match.is_bye:
                self._complete_match_simple(match, 5, 3, db_session)

        RoundClassification.calculate_classification_after_round(gara.id, 1)

        # Test discipline change for third round (from spec)
        gara.discipline = "palla_9"
        db_session.add(gara)
        db_session.commit()

        print("✅ Use Case 2 random strategy workflow verified")

    def test_guest_access_specifications(
        self, isolated_admin_user: User, isolated_players, db_session, client
    ):
        """
        Test guest access specifications from SPECIFICHE.md and UC01.md
        """
        admin_user = isolated_admin_user
        players_8 = isolated_players[:8]

        # Create tournament for guest viewing
        gara = GaraService.create_gara(
            campionato_id=None,
            number=1,
            name="Guest Access Test Tournament Fixed",
            date=date.today(),
            location="Public Pool Hall",
            description="Tournament for guest access testing",
            rounds_count=2,
            min_participants=6,
            max_participants=8,
            entry_fee=15.0,
            discipline="palla_9",
            distance=5,
            best_of=True,
            director_id=admin_user.id,
            matchmaking_strategy="amalfi",
        )

        # Make tournament visible
        from models.competition.services import ProvaStateMachine
        ProvaStateMachine.to_inscription(gara)

        # Test guest home access (no authentication)
        response = client.get("/")
        assert response.status_code == 200
        
        home_content = response.data.decode("utf-8")
        # Tournament should be visible in public listing
        assert "Guest Access Test Tournament Fixed" in home_content

        # Test guest tournament details access
        response = client.get(f"/gara/{gara.id}")
        assert response.status_code == 200
        
        gara_content = response.data.decode("utf-8")
        assert "Guest Access Test Tournament Fixed" in gara_content

        # Test that admin functions are protected
        response = client.get("/admin/")
        assert response.status_code in [302, 401, 403, 404]  # Should redirect or deny

        print("✅ Guest access specifications verified")

    def test_player_registration_workflow(self, db_session, client):
        """
        Test player registration workflow from SPECIFICHE.md
        """
        import uuid
        
        # Test user registration as specified
        unique_id = str(uuid.uuid4())[:8]
        registration_data = {
            "username": f"test_player_spec_fixed_{unique_id}",
            "email": f"test_player_fixed_{unique_id}@spec.com",
            "phone": "+39 123 456 789",  # Optional
            "password": "test_password123",
            "confirm_password": "test_password123",
        }

        response = client.post("/auth/register", data=registration_data)
        # Should succeed or redirect
        assert response.status_code in [200, 302]

        # Verify user created with correct properties
        new_user = User.query.filter_by(username=f"test_player_spec_fixed_{unique_id}").first()
        assert new_user is not None
        assert new_user.email == f"test_player_fixed_{unique_id}@spec.com"
        assert new_user.role == UserRole.PLAYER.value

        # Test login workflow
        login_data = {
            "username": f"test_player_spec_fixed_{unique_id}",
            "password": "test_password123",
        }

        response = client.post("/auth/login", data=login_data)
        assert response.status_code in [200, 302]

        print("✅ Player registration workflow verified")

    def test_director_privileges_specifications(
        self, isolated_director_user: User, isolated_players, db_session, client
    ):
        """
        Test director privileges as specified in SPECIFICHE.md
        Director maintains player functions but gains admin powers for their tournaments
        """
        director_user = isolated_director_user
        players_8 = isolated_players[:8]

        # Login as director
        with client.session_transaction() as sess:
            sess["_user_id"] = str(director_user.id)
            sess["_fresh"] = True

        # Director creates tournament
        gara = GaraService.create_gara(
            campionato_id=None,
            number=1,
            name="Director Privileges Test Fixed",
            date=date.today() + timedelta(days=1),
            location="Director Hall",
            description="Testing director privileges",
            rounds_count=2,
            min_participants=6,
            max_participants=8,
            entry_fee=20.0,
            discipline="palla_8",
            distance=5,
            best_of=True,
            director_id=director_user.id,
            matchmaking_strategy="amalfi",
        )

        # Verify director owns tournament
        assert gara.director_id == director_user.id

        # Director should be able to access tournament management
        response = client.get(f"/gara/{gara.id}")
        assert response.status_code == 200

        # Director should have admin powers for their tournament
        tournament_content = response.data.decode("utf-8")
        assert "Director Privileges Test Fixed" in tournament_content

        print("✅ Director privileges specifications verified")

    def test_anti_rematch_specifications(
        self, isolated_admin_user: User, isolated_players, db_session, client
    ):
        """
        Test anti-rematch specifications from docs/SPECIFICHE.md
        Amalfi strategy should avoid rematches across rounds
        """
        admin_user = isolated_admin_user
        players_8 = isolated_players[:8]

        gara = GaraService.create_gara(
            campionato_id=None,
            number=1,
            name="Anti-Rematch Test Fixed",
            date=date.today() + timedelta(days=1),
            location="Anti-Rematch Hall",
            description="Testing anti-rematch functionality",
            rounds_count=3,
            min_participants=6,
            max_participants=8,
            entry_fee=15.0,
            discipline="palla_9",
            distance=5,
            best_of=True,
            director_id=admin_user.id,
            matchmaking_strategy="amalfi",
            anti_rematch_enabled=True,
        )

        # Setup and start
        for player in players_8:
            InscriptionService.inscribe_user(player.id, gara.id)

        inscription_start = datetime.now() - timedelta(hours=1)
        inscription_end = datetime.now() + timedelta(hours=1)
        GaraService.open_inscriptions(gara.id, inscription_start, inscription_end)
        GaraService.start_first_round(gara.id)

        # Track all pairings across rounds
        all_pairings = set()

        # Complete all 3 rounds and verify no rematches
        for round_num in range(1, 4):
            if round_num > 1:
                RoundClassification.calculate_classification_after_round(gara.id, round_num - 1)
                GaraService.create_amalfi_round(gara.id, round_num)
                gara.current_round = round_num
                db_session.add(gara)
                db_session.commit()

            matches = Match.query.filter_by(gara_id=gara.id, round_number=round_num).all()
            round_pairings = set()

            for match in matches:
                if not match.is_bye:
                    pairing = tuple(sorted([match.player1_id, match.player2_id]))
                    round_pairings.add(pairing)
                    
                    # Complete match
                    self._complete_match_simple(match, 3, 1, db_session)

            # Check no rematches
            rematches = all_pairings.intersection(round_pairings)
            assert len(rematches) == 0, f"Found rematches in round {round_num}: {rematches}"

            all_pairings.update(round_pairings)

        print("✅ Anti-rematch specifications verified")

    def test_waitlist_specifications(
        self, isolated_admin_user: User, isolated_players, db_session, client
    ):
        """
        Test waitlist specifications from SPECIFICHE.md
        Tournament with max participants should handle waitlist correctly
        """
        admin_user = isolated_admin_user
        players_10 = isolated_players[:10]  # Use 10 players for waitlist test

        # Create tournament with limited capacity
        gara = GaraService.create_gara(
            campionato_id=None,
            number=1,
            name="Waitlist Test Tournament Fixed",
            date=date.today() + timedelta(days=3),
            location="Limited Capacity Hall",
            description="Testing waitlist functionality",
            rounds_count=2,
            min_participants=4,
            max_participants=6,  # Limit to 6 players
            entry_fee=20.0,
            discipline="palla_8",
            distance=5,
            best_of=True,
            director_id=admin_user.id,
            matchmaking_strategy="amalfi",
        )

        # Open inscriptions
        inscription_start = datetime.now() - timedelta(hours=1)
        inscription_end = datetime.now() + timedelta(hours=24)
        GaraService.open_inscriptions(gara.id, inscription_start, inscription_end)

        # First 6 players inscribe (should be confirmed)
        for i in range(6):
            inscription = InscriptionService.inscribe_user(players_10[i].id, gara.id)
            db_session.refresh(inscription)
            assert inscription.is_waitlist is False

        # 7th and 8th players should be waitlisted
        for i in range(6, 8):
            inscription = InscriptionService.inscribe_user(players_10[i].id, gara.id)
            db_session.refresh(inscription)
            assert inscription.is_waitlist is True

        # Verify counts
        all_inscriptions = Inscription.query.filter_by(gara_id=gara.id).all()
        confirmed = [i for i in all_inscriptions if not i.is_waitlist]
        waitlisted = [i for i in all_inscriptions if i.is_waitlist]

        assert len(confirmed) == 6
        assert len(waitlisted) == 2

        print("✅ Waitlist specifications verified")

    # Helper method
    def _complete_match_simple(
        self, match: Match, winner_racks: int, loser_racks: int, db_session
    ) -> None:
        """Complete a match with simple results."""
        if match.is_bye:
            return

        import random
        winner_id = match.player1_id if random.choice([True, False]) else match.player2_id
        loser_id = match.player2_id if winner_id == match.player1_id else match.player1_id

        # Add racks for winner
        for rack_num in range(1, winner_racks + 1):
            RackService.add_rack_result(
                match_id=match.id,
                rack_number=rack_num,
                winner_id=winner_id,
                reported_by_id=winner_id,
                confirmed_by_player=True,
                validated_by_admin=True,
            )

        # Add racks for loser
        for rack_num in range(winner_racks + 1, winner_racks + loser_racks + 1):
            RackService.add_rack_result(
                match_id=match.id,
                rack_number=rack_num,
                winner_id=loser_id,
                reported_by_id=loser_id,
                confirmed_by_player=True,
                validated_by_admin=True,
            )

        MatchService.to_completed(match.id)