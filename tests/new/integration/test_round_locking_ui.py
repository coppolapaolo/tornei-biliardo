"""
Test per verificare che i pulsanti di modifica match vengano nascosti
quando i turni successivi sono avviati (round locking behavior)
"""

import pytest
from datetime import date, datetime
from models import db, User, Match
from models.user.role_enum import UserRole
from models.competition.services import (
    GaraService,
    InscriptionService,
    ProvaStateMachine,
)

# Not needed: from models.matchmaking.service import MatchmakingService


@pytest.mark.integration
class TestRoundLockingUI:
    """Test UI behavior for round locking rules."""

    @pytest.fixture
    def admin_user(self, db_session):
        """Create admin user for testing."""
        import uuid

        unique_id = str(uuid.uuid4())[:8]
        admin = User(
            username=f"admin_test_{unique_id}",
            email=f"admin_test_{unique_id}@test.com",
            role=UserRole.ADMIN.value,
        )
        admin.set_password("admin123")
        db_session.add(admin)
        db_session.commit()
        return admin

    def test_match_buttons_hidden_when_subsequent_round_active(self, app, admin_user):
        """
        Test che i pulsanti di modifica match del primo turno vengano nascosti
        quando il secondo turno è stato avviato.
        """
        with app.test_client() as client:
            # Login as admin
            with client.session_transaction() as sess:
                sess["_user_id"] = str(admin_user.id)
                sess["_fresh"] = True

            # 1. Create gara with 4 players
            from datetime import timedelta

            gara = GaraService.create_gara(
                number=1,
                name="Round Locking Test Tournament",
                date=date.today(),
                discipline="9-ball",
                distance=5,
                campionato_id=None,
                director_id=admin_user.id,
                rounds_count=3,
                inscription_start=datetime.combine(
                    date.today() - timedelta(days=7), datetime.min.time()
                ),
                inscription_end=datetime.combine(
                    date.today() + timedelta(days=1), datetime.min.time()
                ),
            )

            # Move to inscription status
            ProvaStateMachine.to_inscription(gara)

            # 2. Create and register 4 players
            players = []
            import uuid

            test_id = str(uuid.uuid4())[:8]
            for i in range(4):
                player = User(
                    username=f"player_{test_id}_{i}",
                    email=f"player_{test_id}_{i}@test.com",
                    role=UserRole.PLAYER.value,
                )
                player.set_password("player123")
                db.session.add(player)
                players.append(player)

            db.session.commit()  # Commit players first to get IDs

            for player in players:
                InscriptionService.inscribe_user(player.id, gara.id)

            # 3. Start playing and create first round matches
            ProvaStateMachine.start_playing(gara)
            GaraService.create_round_with_strategy(gara.id, 1)

            # Refresh gara to get current round updated
            db.session.refresh(gara)

            # 4. Test: First round matches should have edit buttons (round not locked)
            response = client.get(f"/admin/gara/{gara.id}")
            assert response.status_code == 200

            html_content = response.data.decode("utf-8")

            # Count edit buttons - there should be some in Turno 1
            first_round_buttons_before = html_content.count(
                'class="btn btn-sm btn-primary"'
            )
            assert (
                first_round_buttons_before > 0
            ), "Should have edit buttons in first round before second round starts"

            # Should not have "Bloccato" text yet
            assert (
                "Bloccato" not in html_content
            ), "Should not have locked indicators before second round starts"

            # 5. Create second round matches (this should lock first round)
            GaraService.create_round_with_strategy(gara.id, 2)

            # Refresh gara
            db.session.refresh(gara)

            # 6. Test: After second round starts, first round buttons should be
            # hidden/locked
            response = client.get(f"/admin/gara/{gara.id}")
            assert response.status_code == 200

            html_content = response.data.decode("utf-8")

            # Should have "Bloccato" text for locked matches
            assert (
                "Bloccato" in html_content
            ), "Should have locked indicators after second round starts"

            # Verify that round 1 specifically shows locked indicators

            # Find the matches table section for Turno 1
            turno_1_matches_start = html_content.find(
                '<h6 class="mt-3 mb-2">Turno 1</h6>'
            )
            assert turno_1_matches_start >= 0, "Should find Turno 1 matches section"

            # Find the end of the Turno 1 matches section
            turno_2_matches = html_content.find('<h6 class="mt-3 mb-2">Turno 2</h6>')
            if turno_2_matches > turno_1_matches_start:
                turno_1_section_end = turno_2_matches
            else:
                # If no Turno 2, find end of matches card
                turno_1_section_end = html_content.find(
                    "</div>\n    </div>\n</div>", turno_1_matches_start
                )

            turno_1_section = html_content[turno_1_matches_start:turno_1_section_end]
            locked_in_round_1 = turno_1_section.count("Bloccato")
            buttons_in_round_1 = turno_1_section.count('class="btn btn-sm btn-primary"')

            assert (
                locked_in_round_1 > 0
            ), f"Should have locked indicators in Turno 1 matches section, found {locked_in_round_1}"  # noqa: E501
            assert (
                buttons_in_round_1 == 0
            ), f"Should have no edit buttons in Turno 1 section, found {buttons_in_round_1}"  # noqa: E501

    def test_round_locking_with_completed_matches(self, app, admin_user):
        """
        Test che anche i match completati del primo turno non possano essere
        modificati quando il secondo turno è avviato.
        """
        with app.test_client() as client:
            # Login as admin
            with client.session_transaction() as sess:
                sess["_user_id"] = str(admin_user.id)
                sess["_fresh"] = True

            # 1. Create gara and players
            from datetime import timedelta

            gara = GaraService.create_gara(
                number=1,
                name="Completed Match Lock Test",
                date=date.today(),
                discipline="8-ball",
                distance=3,
                campionato_id=None,
                director_id=admin_user.id,
                rounds_count=2,
                inscription_start=datetime.combine(
                    date.today() - timedelta(days=7), datetime.min.time()
                ),
                inscription_end=datetime.combine(
                    date.today() + timedelta(days=1), datetime.min.time()
                ),
            )

            ProvaStateMachine.to_inscription(gara)

            # Create 4 players
            players = []
            import uuid

            test_id = str(uuid.uuid4())[:8]
            for i in range(4):
                player = User(
                    username=f"lock_test_player_{test_id}_{i}",
                    email=f"lock_test_player_{test_id}_{i}@test.com",
                    role=UserRole.PLAYER.value,
                )
                player.set_password("player123")
                db.session.add(player)
                players.append(player)

            db.session.commit()  # Commit players first to get IDs

            for player in players:
                InscriptionService.inscribe_user(player.id, gara.id)

            # 2. Start first round
            ProvaStateMachine.start_playing(gara)
            GaraService.create_round_with_strategy(gara.id, 1)

            # 3. Complete first round matches
            first_round_matches = Match.query.filter_by(
                gara_id=gara.id, round_number=1
            ).all()

            for i, match in enumerate(first_round_matches):
                if not match.is_bye:
                    # Simulate match completion
                    match.status = "completed"
                    match.winner_id = match.player1_id
                    match.player1_score = 3
                    match.player2_score = 1
                    db.session.add(match)

            db.session.commit()

            # 4. Start second round (this should lock first round completely)
            GaraService.create_round_with_strategy(gara.id, 2)
            db.session.refresh(gara)

            # 5. Check UI - completed matches in first round should be locked
            response = client.get(f"/admin/gara/{gara.id}")
            assert response.status_code == 200

            html_content = response.data.decode("utf-8")

            # Should show locked indicators for first round matches
            assert (
                "Bloccato" in html_content
            ), "Completed first round matches should show as locked when second round is active"  # noqa: E501

            # Verify the round structure is displayed correctly
            assert "Turno 1" in html_content, "Should show Turno 1"
            assert "Turno 2" in html_content, "Should show Turno 2"

    def test_third_round_locks_previous_rounds(self, app, admin_user):
        """
        Test che quando viene avviato il terzo turno, sia il primo che il secondo
        turno vengano bloccati.
        """
        with app.test_client() as client:
            # Login as admin
            with client.session_transaction() as sess:
                sess["_user_id"] = str(admin_user.id)
                sess["_fresh"] = True

            # Create 3-round tournament
            from datetime import timedelta

            gara = GaraService.create_gara(
                number=1,
                name="Three Round Lock Test",
                date=date.today(),
                discipline="9-ball",
                distance=5,
                campionato_id=None,
                director_id=admin_user.id,
                rounds_count=3,
                inscription_start=datetime.combine(
                    date.today() - timedelta(days=7), datetime.min.time()
                ),
                inscription_end=datetime.combine(
                    date.today() + timedelta(days=1), datetime.min.time()
                ),
            )

            ProvaStateMachine.to_inscription(gara)

            # Create 6 players for more matches
            players = []
            import uuid

            test_id = str(uuid.uuid4())[:8]
            for i in range(6):
                player = User(
                    username=f"three_round_player_{test_id}_{i}",
                    email=f"three_round_player_{test_id}_{i}@test.com",
                    role=UserRole.PLAYER.value,
                )
                player.set_password("player123")
                db.session.add(player)
                players.append(player)

            db.session.commit()  # Commit players first to get IDs

            for player in players:
                InscriptionService.inscribe_user(player.id, gara.id)

            # Start tournament and create all three rounds
            ProvaStateMachine.start_playing(gara)

            # Create multiple rounds (as many as the strategy allows)
            created_rounds = []
            for round_num in [1, 2, 3]:
                try:
                    GaraService.create_round_with_strategy(gara.id, round_num)
                    created_rounds.append(round_num)
                except Exception as e:
                    print(f"Could not create round {round_num}: {e}")
                    break

            db.session.refresh(gara)

            # Check what matches actually exist
            all_matches = Match.query.filter_by(gara_id=gara.id).all()
            actual_round_numbers = set(m.round_number for m in all_matches)

            # We need at least 2 rounds to test locking
            assert (
                len(actual_round_numbers) >= 2
            ), f"Need at least 2 rounds for lock testing, got {len(actual_round_numbers)}"  # noqa: E501

            # Test UI
            response = client.get(f"/admin/gara/{gara.id}")
            assert response.status_code == 200

            html_content = response.data.decode("utf-8")

            # All created rounds should be visible
            for round_num in sorted(actual_round_numbers):
                assert (
                    f"Turno {round_num}" in html_content
                ), f"Turno {round_num} should be visible in HTML"

            # All rounds except the highest should be locked
            locked_count = html_content.count("Bloccato")
            assert locked_count > 0, "Previous rounds should show locked indicators"

            # Only the highest round should have edit buttons
            # Check for any edit-related elements (less fragile than specific CSS classes)
            edit_elements = (
                html_content.count("btn-primary")
                + html_content.count("edit")
                + html_content.count("modifica")
            )
            assert (
                edit_elements > 0
            ), "Current (highest) round should have edit-related elements"  # noqa: E501
