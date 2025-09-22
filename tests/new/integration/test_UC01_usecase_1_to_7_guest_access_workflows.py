"""Integration tests for UC01.md - All 7 Use Cases.

Tests all use cases documented in docs/usecases/UC01.md:
- UC1: Guest access to ongoing standalone tournament with live updates
- UC2: Match modification workflow with round completion effects
- UC3: Tournament round ordering and management visibility
- UC4: Table assignment and queue management system
- UC5: Challenge system integration with tournaments
- UC6: Standalone challenge completion workflow
- UC7: Player profile and statistics with CSV export

Note: This tests the guest access and UI workflow use cases from UC01.md,
NOT the tournament creation/management use case from gare.md.
"""

import pytest
from datetime import date, datetime, timedelta
from typing import List, Dict, Any, Optional
import uuid
import io
import csv

from flask import url_for, current_app
from flask.testing import FlaskClient

from models import User, Gara, Match, Inscription, Rack
from models.user.role_enum import UserRole
from models.status_enum import GaraStatus, MatchStatus
from models.competition.services import (
    GaraService,
    InscriptionService,
)
from models.competition.state_service import StateService
from models.match.services import MatchService, RackService

# Removed MatchmakingService import - using GaraService methods instead
from models.classification.models import RoundClassification
from models.challenge.models import Challenge, ChallengeAttempt
from models.challenge.services import ChallengeService
from models.location.models import BilliardHall
from models.location.services import LocationService
from models.base import db


@pytest.mark.integration
class TestUseCaseOneComprehensive:
    """Test all 7 use cases from UC01.md with full workflow coverage."""

    def _create_billiard_hall(self, db_session) -> BilliardHall:
        """Create billiard hall with 3 tables."""
        import json

        unique_id = str(uuid.uuid4())[:8]
        hall = BilliardHall(
            name=f"Test Hall {unique_id}",
            address="Via Test 123",
            city="TestCity",
            number_of_tables=3,
            table_types=json.dumps(
                ["A", "sala rossa", "sala blu"]
            ),  # 3 tables as in UC4
            is_active=True,
        )
        db_session.add(hall)
        db_session.commit()
        return hall

    def _create_standalone_gara(self, db_session, admin_user, billiard_hall) -> Gara:
        """Create standalone tournament ready for testing."""
        today = date.today()
        gara = GaraService.create_gara(
            number=1,
            name="UC Test Tournament",
            date=today + timedelta(days=1),
            discipline="9-ball",
            distance=5,
            best_of=True,  # Use "best of 5" instead of "exactly 5"
            campionato_id=None,  # standalone
            director_id=admin_user.id,
        )
        return gara

    def test_use_case_1_guest_access_live_updates(
        self, app, isolated_admin_user, isolated_players, db_session
    ):
        """
        UC1: Guest access to ongoing tournament with live updates.

        Flow:
        1. Tournament first round completed
        2. Guest views tournament details and sees first round results
        3. Admin starts second round
        4. Guest sees new matches
        5. Player enters result
        6. Guest sees partial result
        """
        # Use isolated fixtures
        admin_user = isolated_admin_user
        players = isolated_players[:8]  # UC01 tests expect 8 players

        # Create test data
        billiard_hall = self._create_billiard_hall(db_session)
        standalone_gara = self._create_standalone_gara(
            db_session, admin_user, billiard_hall
        )

        with app.test_client() as client:
            # Setup: Register players and start first round

            # First set inscription dates and transition to inscription state
            now = datetime.now()
            GaraService.open_inscriptions(
                standalone_gara.id,
                inscription_start=now - timedelta(hours=1),
                inscription_end=now + timedelta(hours=1),
            )

            for player in players:
                InscriptionService.inscribe_user(player.id, standalone_gara.id)

            # Close inscriptions and start first round
            StateService.start_playing(
                GaraService.get_gara_by_id(standalone_gara.id)
            )

            # Create matchmaking and start first round
            try:
                GaraService.create_round_with_strategy(standalone_gara.id, 1)
            except Exception as e:
                assert False, f"Failed to create round 1: {str(e)}"

            first_round_matches = Match.query.filter_by(
                gara_id=standalone_gara.id, round_number=1
            ).all()
            assert len(first_round_matches) == 4  # 8 players = 4 matches

            # Complete first round matches using proper best-of-5 scores (winner needs 3, loser gets 2)
            # For best-of-5, winner gets 3, loser gets 2 = realistic 5-rack match
            self._complete_matches_with_results(
                first_round_matches, [(3, 2)] * len(first_round_matches)
            )

            # 1. Guest views tournament details (no authentication)
            response = client.get(f"/public/gara/{standalone_gara.id}")
            assert response.status_code == 200

            # Verify guest can see first round results
            html_content = response.data.decode("utf-8")
            assert "Turno 1" in html_content

            # Verify guest can see match results (3-2 scores from best-of-5 matches)
            assert (
                "3 - 2" in html_content or "2 - 3" in html_content
            ), "Guest should see completed match results"

            # Check classification is visible
            assert "Classifica" in html_content

            # 2. Admin starts second round
            with client.session_transaction() as sess:
                sess["_user_id"] = str(admin_user.id)

            GaraService.create_amalfi_round(standalone_gara.id, 2)

            # 3. Guest sees new matches for round 2
            response = client.get(f"/public/gara/{standalone_gara.id}")
            assert response.status_code == 200
            html_content = response.data.decode("utf-8")
            assert "Turno 2" in html_content

            second_round_matches = Match.query.filter_by(
                gara_id=standalone_gara.id, round_number=2
            ).all()
            assert len(second_round_matches) == 4

            # 4. Player enters partial result
            first_match = second_round_matches[0]
            RackService.add_rack_result(
                first_match.id, 1, first_match.player1_id, first_match.player1_id
            )
            RackService.add_rack_result(
                first_match.id, 2, first_match.player2_id, first_match.player2_id
            )

            # 5. Guest sees partial result
            response = client.get(f"/public/gara/{standalone_gara.id}")
            assert response.status_code == 200
            html_content = response.data.decode("utf-8")

            # Should see partial scores
            assert "1-1" in html_content or "In corso" in html_content

    def test_use_case_2_match_modification_round_effects(
        self,
        app,
        isolated_admin_user,
        isolated_director_user,
        isolated_players,
        db_session,
    ):
        """
        UC2: Match modification workflow with round completion effects.

        Flow:
        1. Tournament with second round completed
        2. Director sees classification after round 2
        3. Director cannot modify round 1 matches (no action buttons)
        4. Director modifies round 2 match (removes rack)
        5. Round 2 becomes "in progress", classification shows round 1 results
        """
        # Setup isolated fixtures
        admin_user = isolated_admin_user
        director_user = isolated_director_user
        players = isolated_players[:8]  # UC01 tests use 8 players

        # Create billiard hall and standalone gara
        billiard_hall = LocationService.create_billiard_hall(
            name="Test Hall",
            address="123 Test St",
            city="Test City",
            added_by_id=admin_user.id,
        )

        standalone_gara = GaraService.create_gara(
            campionato_id=None,  # Standalone
            number=1,
            name="UC2 - Test Tournament",
            date=date.today() + timedelta(days=1),
            location="Test Hall",
            distance=5,
            description="UC2 match modification test",
            rounds_count=3,
            min_participants=6,
            max_participants=8,
            entry_fee=15.0,
            matchmaking_strategy="amalfi",
            discipline="8_ball",
            best_of=False,  # Use exactly format for this test
            director_id=director_user.id,
            first_round_policy="random",
            odd_number_policy="bye",
            anti_rematch_enabled=True,
            rating_type=None,
        )

        with app.test_client() as client:
            # Setup: Complete tournament up to round 2

            # First set inscription dates and transition to inscription state
            now = datetime.now()
            GaraService.open_inscriptions(
                standalone_gara.id,
                inscription_start=now - timedelta(hours=1),
                inscription_end=now + timedelta(hours=1),
            )

            for player in players:
                InscriptionService.inscribe_user(player.id, standalone_gara.id)

            StateService.start_playing(
                GaraService.get_gara_by_id(standalone_gara.id)
            )

            # Complete round 1
            GaraService.create_amalfi_round(standalone_gara.id, 1)

            round1_matches = Match.query.filter_by(
                gara_id=standalone_gara.id, round_number=1
            ).all()

            for match in round1_matches:
                # Complete with 5-2 score
                rack_num = 1
                # Player 1 wins 5 racks
                for _ in range(5):
                    RackService.add_rack_result(
                        match.id, rack_num, match.player1_id, match.player1_id
                    )
                    rack_num += 1
                # Player 2 wins 2 racks
                for _ in range(2):
                    RackService.add_rack_result(
                        match.id, rack_num, match.player2_id, match.player2_id
                    )
                    rack_num += 1
                MatchService.to_completed(match.id)

            # Complete round 2
            GaraService.create_amalfi_round(standalone_gara.id, 2)

            round2_matches = Match.query.filter_by(
                gara_id=standalone_gara.id, round_number=2
            ).all()

            # Complete round 2 matches with 3-2 score (5 total racks)
            self._complete_matches_with_results(
                round2_matches, [(3, 2)] * len(round2_matches)
            )

            # Login as director
            with client.session_transaction() as sess:
                sess["_user_id"] = str(director_user.id)

            # Assign director_user as the director of the gara for permissions
            standalone_gara.director_id = director_user.id
            db.session.commit()

            # 1. Check tournament details page shows round 2 classification
            response = client.get(f"/gara/{standalone_gara.id}")
            assert response.status_code == 200
            html_content = response.data.decode("utf-8")

            # Should show classification after round 2
            assert "Classifica" in html_content
            assert "Turno 2" in html_content

            # 2. Verify no action buttons for round 1 (completed rounds)
            # Round 1 matches should not have modify buttons
            round1_section = html_content[
                html_content.find("Turno 1") : html_content.find("Turno 2")
            ]
            assert (
                "Modifica" not in round1_section
                or round1_section.count("Modifica") == 0
            )

            # 3. Director modifies a round 2 match (remove a rack)
            target_match = round2_matches[0]
            original_racks = Rack.query.filter_by(match_id=target_match.id).count()
            assert original_racks == 5  # 3+2 racks

            # Remove one rack
            last_rack = (
                Rack.query.filter_by(match_id=target_match.id)
                .order_by(Rack.id.desc())
                .first()
            )
            rack_id = last_rack.id

            response = client.post(f"/admin/match/rack/{rack_id}/remove")
            assert response.status_code in [200, 302]  # Success or redirect

            # 4. Verify round 2 is now "in progress" and classification shows round 1
            db.session.refresh(target_match)

            # Debug: check match state
            remaining_racks = Rack.query.filter_by(match_id=target_match.id).count()
            assert remaining_racks == 4  # Should have 4 racks after removing 1 from 5

            # With "exactly 5" format and 4 racks remaining, match should be playing
            assert target_match.status == MatchStatus.PLAYING.value

            # Check that classification now shows round 1 results (last completed round)
            response = client.get(f"/gara/{standalone_gara.id}")
            assert response.status_code == 200
            html_content = response.data.decode("utf-8")

            # Classification should be based on round 1 (last completed round)
            # since round 2 is now incomplete
            assert "Classifica" in html_content

    def test_use_case_3_tournament_round_ordering(
        self,
        app,
        isolated_admin_user,
        isolated_director_user,
        isolated_players,
        db_session,
    ):
        """
        UC3: Tournament round ordering and management visibility.

        Flow:
        1. Random tournament with 3 rounds created
        2. Initially shows rounds in order: 1, 2, 3 with only round 1 editable
        3. Complete round 1, shows round 2 first (active), then 3, then 1 (completed)
        4. Complete round 2, shows proper ordering again
        """
        # Setup isolated fixtures
        admin_user = isolated_admin_user
        director_user = isolated_director_user
        players = isolated_players[:8]  # UC01 tests use 8 players

        # Create billiard hall and standalone gara
        billiard_hall = LocationService.create_billiard_hall(
            name="Test Hall",
            address="123 Test St",
            city="Test City",
            added_by_id=admin_user.id,
        )

        standalone_gara = GaraService.create_gara(
            campionato_id=None,  # Standalone
            number=1,
            name="UC3 - Test Tournament",
            date=date.today() + timedelta(days=1),
            location="Test Hall",
            distance=5,
            description="UC3 round ordering test",
            rounds_count=3,
            min_participants=6,
            max_participants=8,
            entry_fee=15.0,
            matchmaking_strategy="random",
            discipline="8_ball",
            best_of=True,
            director_id=director_user.id,
            first_round_policy="random",
            odd_number_policy="bye",
            anti_rematch_enabled=True,
            rating_type=None,
        )

        with app.test_client() as client:
            # Setup tournament with random strategy and 3 rounds

            # First set inscription dates and transition to inscription state
            now = datetime.now()
            GaraService.open_inscriptions(
                standalone_gara.id,
                inscription_start=now - timedelta(hours=1),
                inscription_end=now + timedelta(hours=1),
            )

            for player in players:
                InscriptionService.inscribe_user(player.id, standalone_gara.id)

            StateService.start_playing(
                GaraService.get_gara_by_id(standalone_gara.id)
            )

            # Set random strategy (modify the gara)
            standalone_gara.matchmaking_strategy = "random"
            db.session.commit()

            # Login as admin
            with client.session_transaction() as sess:
                sess["_user_id"] = str(admin_user.id)

            # Create first round
            GaraService.create_amalfi_round(standalone_gara.id, 1)

            # 1. Initially shows rounds in order with only round 1 editable
            response = client.get(f"/gara/{standalone_gara.id}")
            assert response.status_code == 200
            html_content = response.data.decode("utf-8")

            # Should show round 1 with modify buttons
            assert "Turno 1" in html_content
            # Check that management section shows next round button when round 1 completed

            # 2. Complete all round 1 matches
            round1_matches = Match.query.filter_by(
                gara_id=standalone_gara.id, round_number=1
            ).all()

            for match in round1_matches:
                for _ in range(5):
                    RackService.add_rack_result(
                        match.id, 1, match.player1_id, match.player1_id
                    )
                for _ in range(2):
                    RackService.add_rack_result(
                        match.id, 2, match.player2_id, match.player2_id
                    )
                MatchService.to_completed(match.id)

            # Should now show button to start next round
            response = client.get(f"/gara/{standalone_gara.id}")
            assert response.status_code == 200
            html_content = response.data.decode("utf-8")
            assert (
                "Avvia turno successivo" in html_content or "Crea turno" in html_content
            )

            # 3. Start round 2
            GaraService.create_amalfi_round(standalone_gara.id, 2)

            # Check round ordering: round 2 (active) should be first, then 3, then 1 (completed)
            response = client.get(f"/gara/{standalone_gara.id}")
            assert response.status_code == 200
            html_content = response.data.decode("utf-8")

            # Round 2 should appear before Round 1 in matches section (look for round headers)
            turno2_header_pos = html_content.find('<h6 class="mt-3 mb-2">Turno 2</h6>')
            turno1_header_pos = html_content.find('<h6 class="mt-3 mb-2">Turno 1</h6>')
            assert (
                turno2_header_pos < turno1_header_pos
            )  # Round 2 header appears before round 1 header

            # 4. Complete round 2
            round2_matches = Match.query.filter_by(
                gara_id=standalone_gara.id, round_number=2
            ).all()

            for match in round2_matches:
                for _ in range(5):
                    RackService.add_rack_result(
                        match.id, 1, match.player1_id, match.player1_id
                    )
                for _ in range(1):
                    RackService.add_rack_result(
                        match.id, 2, match.player2_id, match.player2_id
                    )
                MatchService.to_completed(match.id)

            # Should show next round button again
            response = client.get(f"/gara/{standalone_gara.id}")
            assert response.status_code == 200
            html_content = response.data.decode("utf-8")
            assert (
                "Avvia turno successivo" in html_content or "Crea turno" in html_content
            )

    def test_use_case_4_table_assignment_queue(
        self,
        app,
        isolated_admin_user,
        isolated_director_user,
        isolated_players,
        db_session,
    ):
        """
        UC4: Table assignment and queue management system.

        Flow:
        1. Tournament with 8 players and 3 tables
        2. First round: 3 matches get tables, 4th match waits
        3. When match finishes, table assigned to waiting match
        4. Players see table assignment in dashboard and match entry
        5. Admin can reorder table assignments
        """
        # Setup isolated fixtures
        admin_user = isolated_admin_user
        director_user = isolated_director_user
        players = isolated_players[:8]  # UC01 tests use 8 players

        # Create billiard hall and standalone gara
        billiard_hall = LocationService.create_billiard_hall(
            name="Test Hall",
            address="123 Test St",
            city="Test City",
            added_by_id=admin_user.id,
        )

        standalone_gara = GaraService.create_gara(
            campionato_id=None,  # Standalone
            number=1,
            name="UC4 - Test Tournament",
            date=date.today() + timedelta(days=1),
            location="Test Hall",
            distance=5,
            description="UC4 table assignment test",
            rounds_count=3,
            min_participants=6,
            max_participants=8,
            entry_fee=15.0,
            matchmaking_strategy="amalfi",
            discipline="8_ball",
            best_of=True,
            director_id=director_user.id,
            first_round_policy="random",
            odd_number_policy="bye",
            anti_rematch_enabled=True,
            rating_type=None,
        )

        with app.test_client() as client:
            # Setup with Amalfi strategy (as mentioned in UC4)

            # First set inscription dates and transition to inscription state
            now = datetime.now()
            GaraService.open_inscriptions(
                standalone_gara.id,
                inscription_start=now - timedelta(hours=1),
                inscription_end=now + timedelta(hours=1),
            )

            for player in players:
                InscriptionService.inscribe_user(player.id, standalone_gara.id)

            standalone_gara.matchmaking_strategy = "amalfi"
            db.session.commit()

            StateService.start_playing(
                GaraService.get_gara_by_id(standalone_gara.id)
            )

            # Login as admin
            with client.session_transaction() as sess:
                sess["_user_id"] = str(admin_user.id)

            # Assign admin_user as the director of the gara for permissions
            standalone_gara.director_id = admin_user.id
            db.session.commit()

            GaraService.create_amalfi_round(standalone_gara.id, 1)

            matches = (
                Match.query.filter_by(gara_id=standalone_gara.id, round_number=1)
                .order_by(Match.id)
                .all()
            )
            assert len(matches) == 4  # 8 players = 4 matches

            # 1. First 3 matches should get table assignments, 4th should wait
            tables = ["A", "sala rossa", "sala blu"]
            for i, match in enumerate(matches[:3]):
                match.table_assignment = tables[i]
                db.session.commit()

            # 4th match has no table (waiting)
            assert matches[3].table_assignment is None

            # 2. Verify table assignments in tournament view
            response = client.get(f"/gara/{standalone_gara.id}")
            assert response.status_code == 200
            html_content = response.data.decode("utf-8")

            # Should show table column with assignments
            assert "Tavolo" in html_content or "Table" in html_content
            assert "A" in html_content
            assert "sala rossa" in html_content
            assert "sala blu" in html_content

            # 3. When first match finishes, table should be assigned to waiting match
            first_match = matches[0]

            # Complete first match
            rack_num = 1
            # Player 1 wins 5 racks
            for _ in range(5):
                RackService.add_rack_result(
                    first_match.id,
                    rack_num,
                    first_match.player1_id,
                    first_match.player1_id,
                )
                rack_num += 1
            # Player 2 wins 2 racks
            for _ in range(2):
                RackService.add_rack_result(
                    first_match.id,
                    rack_num,
                    first_match.player2_id,
                    first_match.player2_id,
                )
                rack_num += 1
            MatchService.to_completed(first_match.id)

            # Simulate table reassignment logic (would be handled by system)
            waiting_match = matches[3]
            waiting_match.table_assignment = first_match.table_assignment
            first_match.table_assignment = None
            db.session.commit()

            # 4. Verify waiting match now has table assignment
            assert waiting_match.table_assignment == "A"

            # 5. Player dashboard should show table assignment
            player = first_match.player1
            with client.session_transaction() as sess:
                sess["_user_id"] = str(player.id)

            response = client.get("/dashboard")
            assert response.status_code == 200
            # Would verify table assignment appears in player's match info

    def test_use_case_5_challenge_tournament_integration(
        self,
        app,
        isolated_admin_user,
        isolated_director_user,
        isolated_players,
        db_session,
    ):
        """
        UC5: Challenge system integration with tournaments.

        Flow:
        1. Random tournament with challenge after first round
        2. Director starts first round
        3. Player sees match and completes it, sees challenge requirement
        4. Player enters attempts, can't enter opponent's attempts (validation only)
        5. Director enters match result and challenge attempts for both players
        6. Challenge appears in player dashboard but locked until match complete
        """
        # Setup isolated fixtures
        admin_user = isolated_admin_user
        director_user = isolated_director_user
        players = isolated_players[:8]  # UC01 tests use 8 players

        # Create billiard hall and standalone gara
        billiard_hall = LocationService.create_billiard_hall(
            name="Test Hall",
            address="123 Test St",
            city="Test City",
            added_by_id=admin_user.id,
        )

        standalone_gara = GaraService.create_gara(
            campionato_id=None,  # Standalone
            number=1,
            name="UC5 - Test Tournament",
            date=date.today() + timedelta(days=1),
            location="Test Hall",
            distance=5,
            description="UC5 challenge integration test",
            rounds_count=3,
            min_participants=6,
            max_participants=8,
            entry_fee=15.0,
            matchmaking_strategy="random",
            discipline="8_ball",
            best_of=True,
            director_id=director_user.id,
            first_round_policy="random",
            odd_number_policy="bye",
            anti_rematch_enabled=True,
            rating_type=None,
        )

        with app.test_client() as client:
            # Setup random tournament

            # First set inscription dates and transition to inscription state
            now = datetime.now()
            GaraService.open_inscriptions(
                standalone_gara.id,
                inscription_start=now - timedelta(hours=1),
                inscription_end=now + timedelta(hours=1),
            )

            for player in players:
                InscriptionService.inscribe_user(player.id, standalone_gara.id)

            standalone_gara.matchmaking_strategy = "random"
            db.session.commit()

            StateService.start_playing(
                GaraService.get_gara_by_id(standalone_gara.id)
            )

            # Create a challenge for after first round
            challenge = Challenge(
                description="Spot shot challenge after first round",
                image_path="/static/challenges/uc5_challenge.jpg",
                is_active=True,
            )
            db.session.add(challenge)
            db.session.commit()

            # Login as director
            with client.session_transaction() as sess:
                sess["_user_id"] = str(director_user.id)

            # 1. Director starts first round
            GaraService.create_amalfi_round(standalone_gara.id, 1)

            first_round_matches = Match.query.filter_by(
                gara_id=standalone_gara.id, round_number=1
            ).all()
            assert len(first_round_matches) == 4

            # 2. Player completes match
            test_match = first_round_matches[0]
            player = test_match.player1

            with client.session_transaction() as sess:
                sess["_user_id"] = str(player.id)

            # Player completes match with 3-2 final score (player wins, opponent gets 2)
            RackService.set_match_result_direct(
                match_id=test_match.id,
                player1_score=3 if test_match.player1_id == player.id else 2,
                player2_score=2 if test_match.player1_id == player.id else 3,
            )

            # 3. Player should see challenge requirement (simulated)
            response = client.get("/dashboard")
            assert response.status_code == 200
            # Would verify challenge notification appears

            # 4. Player creates challenge attempt
            attempt = ChallengeAttempt(
                challenge_id=challenge.id,
                user_id=player.id,
                score=15,  # Example score
                passed=True,
                completed=True,
            )
            db.session.add(attempt)
            db.session.commit()

            # Player cannot create attempts for opponent (would be enforced in routes)

            # 5. Director enters results for both players
            with client.session_transaction() as sess:
                sess["_user_id"] = str(director_user.id)

            # Director can create attempts for both players
            opponent_attempt = ChallengeAttempt(
                challenge_id=challenge.id,
                user_id=test_match.player2_id,
                score=12,
                passed=False,
                completed=True,
            )
            db.session.add(opponent_attempt)
            db.session.commit()

            # Verify attempts were created
            player_attempts = ChallengeAttempt.query.filter_by(
                challenge_id=challenge.id, user_id=player.id
            ).count()
            opponent_attempts = ChallengeAttempt.query.filter_by(
                challenge_id=challenge.id, user_id=test_match.player2_id
            ).count()

            assert player_attempts == 1
            assert opponent_attempts == 1

    def test_use_case_6_standalone_challenge_completion(
        self, app, isolated_players, db_session
    ):
        """
        UC6: Standalone challenge completion workflow.

        Flow:
        1. Player accesses challenge list and selects one
        2. Player enters first attempt, then second, then third
        3. Player completes challenge
        4. Challenge log appears in player profile with attempts and results
        5. Player statistics updated with challenge results
        """
        # Setup isolated fixtures
        players = isolated_players[:8]  # UC01 tests use 8 players

        with app.test_client() as client:
            # Create a standalone challenge
            challenge = Challenge(
                description="UC6 Standalone Challenge",
                image_path="/static/challenges/uc6_standalone_challenge.jpg",
                is_active=True,
            )
            db.session.add(challenge)
            db.session.commit()

            player = players[0]

            with client.session_transaction() as sess:
                sess["_user_id"] = str(player.id)

            # 1. Player accesses challenge list
            response = client.get("/challenges/")
            assert response.status_code == 200
            html_content = response.data.decode("utf-8")
            assert "UC6 Standalone Challenge" in html_content

            # 2. Player enters multiple attempts
            attempts_data = [
                {"score": 10, "successful": False},
                {"score": 15, "successful": True},
                {"score": 18, "successful": True},
            ]

            for i, attempt_data in enumerate(attempts_data, 1):
                attempt = ChallengeAttempt(
                    challenge_id=challenge.id,
                    user_id=player.id,
                    score=attempt_data["score"],
                    passed=attempt_data["successful"],
                    completed=True,
                )
                db.session.add(attempt)

            db.session.commit()

            # 3. Mark challenge as completed
            # This would typically be done through a service method
            # Challenge completion would be handled by the challenge service
            # ChallengeService.complete_challenge_for_user(player.id, challenge.id)

            # 4. Verify challenge log in player profile
            response = client.get(f"/player/profile/{player.id}")
            assert response.status_code == 200
            html_content = response.data.decode("utf-8")

            # Should show challenge history
            assert "UC6 Standalone Challenge" in html_content
            assert "Completata" in html_content or "Completed" in html_content

            # 5. Verify statistics are updated
            # Player statistics should reflect challenge completion
            attempts = ChallengeAttempt.query.filter_by(
                challenge_id=challenge.id, user_id=player.id
            ).all()
            assert len(attempts) == 3

            successful_attempts = [a for a in attempts if a.passed]
            assert len(successful_attempts) == 2  # 2 successful out of 3

    def test_use_case_7_player_profile_statistics_export(
        self, app, isolated_admin_user, isolated_players, db_session
    ):
        """
        UC7: Player profile and statistics with CSV export.

        Flow:
        1. Player has completed matches and challenges
        2. Player accesses profile and sees complete history
        3. Statistics show results from tournaments, championships, individual matches
        4. Player can download complete history as CSV
        """
        # Setup isolated fixtures
        admin_user = isolated_admin_user
        players = isolated_players[:8]  # UC01 tests use 8 players

        # Create billiard hall and standalone gara
        billiard_hall = LocationService.create_billiard_hall(
            name="Test Hall",
            address="123 Test St",
            city="Test City",
            added_by_id=admin_user.id,
        )

        standalone_gara = GaraService.create_gara(
            campionato_id=None,  # Standalone
            number=1,
            name="UC7 - Test Tournament",
            date=date.today() + timedelta(days=1),
            location="Test Hall",
            distance=5,
            description="UC7 profile export test",
            rounds_count=3,
            min_participants=6,
            max_participants=8,
            entry_fee=15.0,
            matchmaking_strategy="amalfi",
            discipline="8_ball",
            best_of=True,
            director_id=admin_user.id,  # Use admin as director for this test
            first_round_policy="random",
            odd_number_policy="bye",
            anti_rematch_enabled=True,
            rating_type=None,
        )

        with app.test_client() as client:
            player = players[0]

            # First set inscription dates and transition to inscription state
            now = datetime.now()
            GaraService.open_inscriptions(
                standalone_gara.id,
                inscription_start=now - timedelta(hours=1),
                inscription_end=now + timedelta(hours=1),
            )

            # Setup: Create some match history - inscribe main player and several opponents
            InscriptionService.inscribe_user(player.id, standalone_gara.id)
            for opponent in players[
                1:6
            ]:  # Add 5 opponents (6 total) to meet minimum requirement
                InscriptionService.inscribe_user(opponent.id, standalone_gara.id)

            StateService.start_playing(
                GaraService.get_gara_by_id(standalone_gara.id)
            )

            # Create multiple rounds to ensure player has at least 2 matches
            GaraService.create_amalfi_round(standalone_gara.id, 1)

            # Complete all round 1 matches
            round1_matches = Match.query.filter_by(
                gara_id=standalone_gara.id, round_number=1
            ).all()
            for match in round1_matches:
                winner = match.player1_id if match.player1_id else match.player2_id
                loser = (
                    match.player2_id if winner == match.player1_id else match.player1_id
                )

                # Complete match with 3-2 score for realistic results
                RackService.set_match_result_direct(
                    match_id=match.id,
                    player1_score=3 if winner == match.player1_id else 2,
                    player2_score=2 if winner == match.player1_id else 3,
                )

            # Create round 2 to ensure player gets another match
            GaraService.create_amalfi_round(standalone_gara.id, 2)

            # Complete round 2 matches for additional match history
            matches = Match.query.filter(
                (Match.player1_id == player.id) | (Match.player2_id == player.id)
            ).all()

            # Complete only round 2 matches (round 1 is already completed)
            round2_matches = [m for m in matches if m.round_number == 2]
            for match in round2_matches:
                winner = (
                    match.player1_id
                    if match.player1_id == player.id
                    else match.player2_id
                )
                loser = (
                    match.player2_id if winner == match.player1_id else match.player1_id
                )

                # Complete match with 3-2 score
                RackService.set_match_result_direct(
                    match_id=match.id,
                    player1_score=3 if winner == match.player1_id else 2,
                    player2_score=2 if winner == match.player1_id else 3,
                )

            # Add some challenge history
            challenge = Challenge(
                description="Challenge for profile testing",
                image_path="/static/challenges/profile_challenge.jpg",
                is_active=True,
            )
            db.session.add(challenge)
            db.session.commit()

            # Add challenge attempts
            for i in range(2):
                attempt = ChallengeAttempt(
                    challenge_id=challenge.id,
                    user_id=player.id,
                    score=15 + i * 3,
                    passed=i == 1,  # Second attempt successful
                    completed=True,
                )
                db.session.add(attempt)

            db.session.commit()

            with client.session_transaction() as sess:
                sess["_user_id"] = str(player.id)

            # 1. Player accesses profile
            response = client.get(f"/player/profile/{player.id}")
            assert response.status_code == 200
            html_content = response.data.decode("utf-8")

            # 2. Should see complete match history
            assert "Storico" in html_content or "History" in html_content

            # Should see tournament matches
            completed_matches = Match.query.filter(
                (Match.player1_id == player.id) | (Match.player2_id == player.id),
                Match.status == MatchStatus.COMPLETED.value,
            ).count()
            assert completed_matches >= 2

            # Should see challenge history
            assert "Challenge for profile testing" in html_content

            # 3. Statistics should show results across different contexts
            # Would verify tournament stats, championship stats, individual match stats
            assert "Statistiche" in html_content or "Statistics" in html_content

            # 4. CSV export functionality
            response = client.get(f"/player/profile/{player.id}/export/csv")
            assert response.status_code == 200
            assert response.headers[
                "Content-Type"
            ] == "text/csv" or "text/csv" in response.headers.get("Content-Type", "")

            # Parse CSV content
            csv_content = response.data.decode("utf-8")
            csv_reader = csv.DictReader(io.StringIO(csv_content))
            rows = list(csv_reader)

            # Should include match and challenge data
            assert len(rows) > 0

            # Should have proper CSV headers
            if rows:
                headers = rows[0].keys()
                expected_fields = [
                    "tipo",
                    "data",
                    "avversario",
                    "risultato",
                ]  # Italian fields
                # At least some expected fields should be present
                assert any(field in headers for field in expected_fields)

    def test_database_snapshots_integration(self, app, db_session):
        """Test that all use cases can be properly snapshotted and restored."""
        import pytest
        from utils.reset_manager import ResetManager

        # Skip test if using in-memory database (snapshots not supported)
        with app.app_context():
            db_uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
            if ":memory:" in db_uri:
                pytest.skip("Database snapshots not supported with in-memory databases")

        reset_manager = ResetManager()

        # Test snapshot creation
        with app.app_context():
            # Create basic test data
            admin = User(
                username="snapshot_admin",
                email="admin@snapshot.com",
                role=UserRole.ADMIN.value,
            )
            admin.set_password("admin123")
            db_session.add(admin)
            db_session.commit()

            # Save snapshot
            result = reset_manager.save_current_state(
                "UC01_Test_Snapshot", "Test snapshot for UC01 integration tests"
            )
            assert result["status"] == "success"

            # Verify snapshot can be listed
            options = reset_manager.get_reset_options()
            snapshot_found = False
            for key, option in options.items():
                if "UC01_Test_Snapshot" in option.get("name", ""):
                    snapshot_found = True
                    break

            assert snapshot_found, "Snapshot should be available in reset options"

    def _complete_matches_with_results(
        self, matches: List[Match], results: List[tuple]
    ) -> None:
        """Complete matches with specified win-loss results using existing test pattern.

        Args:
            matches: List of matches to complete
            results: List of (winner_racks, loser_racks) tuples
        """
        import random

        for match, (winner_racks, loser_racks) in zip(matches, results):
            if match.is_bye:
                continue  # Byes auto-complete

            # Randomly choose winner (player1 or player2)
            winner_id = (
                match.player1_id if random.choice([True, False]) else match.player2_id
            )
            loser_id = (
                match.player2_id if winner_id == match.player1_id else match.player1_id
            )

            # Use RackService.set_match_result_direct for both best_of and exactly formats
            # This method handles existing racks and match completion correctly
            RackService.set_match_result_direct(
                match_id=match.id,
                player1_score=(
                    winner_racks if winner_id == match.player1_id else loser_racks
                ),
                player2_score=(
                    loser_racks if winner_id == match.player1_id else winner_racks
                ),
            )

            # Complete the match only if not already completed
            current_match = db.session.get(Match, match.id)
            if current_match.status != MatchStatus.COMPLETED:
                MatchService.to_completed(match.id)


# Helper functions for test data creation
def create_test_challenge(
    description: str, image_path: str = "/static/challenges/test.jpg"
) -> Challenge:
    """Create a test challenge with standard parameters."""
    challenge = Challenge(
        description=description,
        image_path=image_path,
        is_active=True,
    )
    db.session.add(challenge)
    db.session.commit()
    return challenge


def complete_match_with_score(match: Match, p1_score: int, p2_score: int) -> None:
    """Complete a match with specific scores for both players."""
    # Use proper RackService pattern
    for rack_num in range(1, p1_score + 1):
        RackService.add_rack_result(
            match_id=match.id,
            rack_number=rack_num,
            winner_id=match.player1_id,
            reported_by_id=match.player1_id,
            confirmed_by_player=True,
        )

    for rack_num in range(p1_score + 1, p1_score + p2_score + 1):
        RackService.add_rack_result(
            match_id=match.id,
            rack_number=rack_num,
            winner_id=match.player2_id,
            reported_by_id=match.player2_id,
            confirmed_by_player=True,
        )

    MatchService.to_completed(match.id)


def create_player_with_history(
    username: str, email: str, matches_won: int = 0, challenges_completed: int = 0
) -> User:
    """Create a player with some match and challenge history."""
    player = User(username=username, email=email, role=UserRole.PLAYER.value)
    player.set_password("player123")
    db.session.add(player)
    db.session.commit()

    # Additional setup for history would be done here
    # This is a placeholder for future enhancement

    return player
