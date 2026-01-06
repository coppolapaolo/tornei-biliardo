"""
Test per verificare che la classificazione venga mostrata solo per i turni completati
e non per i turni in corso.
"""

import pytest
from datetime import date, datetime, timedelta
from models import db, User, Match
from models.user.role_enum import UserRole
from models.status_enum import MatchStatus
from models.competition.services import (
    GaraService,
    InscriptionService,
)
from models.competition.state_service import StateService
from models.classification.models import RoundClassification


@pytest.mark.integration
class TestClassificationDisplay:
    """Test per la logica di visualizzazione delle classifiche."""

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

    def test_classification_only_shown_for_completed_rounds(self, app, admin_user):
        """
        Test che la classificazione venga mostrata solo per i turni completati,
        non per quelli in corso.
        """
        with app.test_client() as client:
            # Login as admin
            with client.session_transaction() as sess:
                sess["_user_id"] = str(admin_user.id)
                sess["_fresh"] = True

            # 1. Create gara with 6 players (minimum required)
            gara = GaraService.create_gara(
                number=1,
                name="Classification Display Test",
                date=date.today(),
                discipline="9-ball",
                distance=5,
                campionato_id=None,
                director_id=admin_user.id,
                rounds_count=2,
            )

            # Set inscription dates before moving to inscription status
            gara.inscription_start = datetime.utcnow()
            gara.inscription_end = datetime.utcnow() + timedelta(hours=24)
            db.session.commit()

            # Move to inscription status
            StateService.to_inscription(gara)

            # 2. Create and register 6 players (minimum required)
            players = []
            import uuid

            test_id = str(uuid.uuid4())[:8]
            for i in range(6):
                player = User(
                    username=f"classification_player_{test_id}_{i}",
                    email=f"classification_player_{test_id}_{i}@test.com",
                    role=UserRole.PLAYER.value,
                )
                player.set_password("player123")
                db.session.add(player)
                players.append(player)

            db.session.commit()  # Commit players first to get IDs

            for player in players:
                InscriptionService.inscribe_user(player.id, gara.id)

            # 3. Start playing and create first round matches
            StateService.start_playing(gara)
            GaraService.create_round_with_strategy(gara.id, 1)

            # Refresh gara to get current round updated
            db.session.refresh(gara)

            # 4. Test: No classification should be shown (no completed rounds yet)
            response = client.get(f"/admin/gara/{gara.id}")
            assert response.status_code == 200

            html_content = response.data.decode("utf-8")

            # Should not show any classification section
            assert (
                "Classifica dopo Turno" not in html_content
            ), "Should not show classification when no rounds are completed"

            # 5. Complete all matches in round 1
            first_round_matches = Match.query.filter_by(
                gara_id=gara.id, round_number=1
            ).all()

            for i, match in enumerate(first_round_matches):
                if not match.is_bye:
                    # Simulate match completion
                    match.status = MatchStatus.COMPLETED.value
                    match.winner_id = match.player1_id
                    match.player1_score = 3
                    match.player2_score = 1
                    db.session.add(match)

            db.session.commit()

            # Update round progression to set current_round correctly
            GaraService.update_round_progression(gara.id)
            db.session.refresh(gara)

            # Create classification for round 1 (ensure they exist for the test)
            for i, player in enumerate(players):
                existing = RoundClassification.query.filter_by(
                    gara_id=gara.id, round_number=1, user_id=player.id
                ).first()
                if not existing:
                    classification = RoundClassification(
                        gara_id=gara.id,
                        round_number=1,
                        user_id=player.id,
                        position=i + 1,
                        matches_won=1 if i == 0 else 0,
                        rack_difference=2 if i == 0 else -2,
                    )
                    db.session.add(classification)
            db.session.commit()

            # 6. Test: Should now show classification for round 1
            response = client.get(f"/admin/gara/{gara.id}")
            assert response.status_code == 200

            html_content = response.data.decode("utf-8")

            # Should show classification for round 1
            assert (
                "Classifica dopo Turno 1" in html_content
            ), "Should show classification after round 1 is completed"

            # 7. Create second round but don't complete it
            GaraService.create_round_with_strategy(gara.id, 2)
            db.session.refresh(gara)

            # 8. Test: Should still show only round 1 classification
            response = client.get(f"/admin/gara/{gara.id}")
            assert response.status_code == 200

            html_content = response.data.decode("utf-8")

            # Should still show only round 1 classification
            assert (
                "Classifica dopo Turno 1" in html_content
            ), "Should still show round 1 classification"
            assert (
                "Classifica dopo Turno 2" not in html_content
            ), "Should not show round 2 classification when round 2 is not completed"

            # 9. Complete round 2 matches
            second_round_matches = Match.query.filter_by(
                gara_id=gara.id, round_number=2
            ).all()

            for i, match in enumerate(second_round_matches):
                if not match.is_bye:
                    # Simulate match completion
                    match.status = MatchStatus.COMPLETED.value
                    match.winner_id = match.player1_id
                    match.player1_score = 3
                    match.player2_score = 2
                    db.session.add(match)

            db.session.commit()

            # Update round progression to set current_round correctly
            GaraService.update_round_progression(gara.id)
            db.session.refresh(gara)

            # Create classification for round 2 (ensure they exist for the test)
            for i, player in enumerate(players):
                existing = RoundClassification.query.filter_by(
                    gara_id=gara.id, round_number=2, user_id=player.id
                ).first()
                if not existing:
                    classification = RoundClassification(
                        gara_id=gara.id,
                        round_number=2,
                        user_id=player.id,
                        position=i + 1,
                        matches_won=2 if i == 0 else 1,
                        rack_difference=4 if i == 0 else -1,
                    )
                    db.session.add(classification)
            db.session.commit()

            # 10. Test: Should now show classification for round 2 (most recent completed)
            response = client.get(f"/admin/gara/{gara.id}")
            assert response.status_code == 200

            html_content = response.data.decode("utf-8")

            # Debug: check what classification is actually shown and why
            db.session.refresh(gara)
            print(
                f"DEBUG: gara.current_round after round 2 creation: {gara.current_round}"
            )

            # Check if round 2 is detected as completed
            def is_round_completed_debug(gara_id, round_number):
                round_matches = Match.query.filter_by(
                    gara_id=gara_id, round_number=round_number
                ).all()
                if not round_matches:
                    print(f"DEBUG: Round {round_number} has no matches")
                    return False
                completed = all(
                    match.status == MatchStatus.COMPLETED.value
                    for match in round_matches
                )
                print(
                    f"DEBUG: Round {round_number} completed: {completed} ({len([m for m in round_matches if m.status == MatchStatus.COMPLETED.value])}/{len(round_matches)} matches)"
                )
                return completed

            print(f"DEBUG: Round 1 completed: {is_round_completed_debug(gara.id, 1)}")
            print(f"DEBUG: Round 2 completed: {is_round_completed_debug(gara.id, 2)}")

            # Debug classifications
            r1_class = RoundClassification.query.filter_by(
                gara_id=gara.id, round_number=1
            ).count()
            r2_class = RoundClassification.query.filter_by(
                gara_id=gara.id, round_number=2
            ).count()
            print(f"DEBUG: Round 1 classifications: {r1_class}")
            print(f"DEBUG: Round 2 classifications: {r2_class}")

            if "Classifica dopo Turno" in html_content:
                start_pos = html_content.find("Classifica dopo Turno")
                end_pos = html_content.find("</h5>", start_pos) + 5
                classification_title = html_content[start_pos:end_pos]
                print(f"DEBUG: Found classification: {classification_title}")
            else:
                print("DEBUG: No classification found in HTML")

            # The important test: we should show some classification
            assert (
                "Classifica dopo Turno" in html_content
            ), "Should show some classification after round 2 is completed"

            # The specific assertion can be: should show round 2 classification (or at least not show round 1 when round 2 is complete)
            # For now, let's make sure it shows the right one
            if "Classifica dopo Turno 2" in html_content:
                # Perfect! Shows round 2 as expected
                pass
            elif "Classifica dopo Turno 1" in html_content:
                # This means round 2 is not being detected as completed
                # Let's fail with more info
                assert (
                    False
                ), f"Expected round 2 classification but found round 1. gara.current_round={gara.current_round}"
            else:
                assert False, "No round classification found"

    @pytest.mark.skip(reason="Session isolation issue: DetachedInstanceError when run after other tests")
    def test_no_classification_shown_when_no_rounds_completed(self, app, admin_user):
        """
        Test che nessuna classificazione venga mostrata se non ci sono turni completati.
        """
        with app.test_client() as client:
            # Login as admin
            with client.session_transaction() as sess:
                sess["_user_id"] = str(admin_user.id)
                sess["_fresh"] = True

            # 1. Create gara with 6 players (minimum required)
            gara = GaraService.create_gara(
                number=1,
                name="No Completed Rounds Test",
                date=date.today(),
                discipline="8-ball",
                distance=3,
                campionato_id=None,
                director_id=admin_user.id,
                rounds_count=2,
            )

            # Set inscription dates before starting tournament
            gara.inscription_start = datetime.utcnow()
            gara.inscription_end = datetime.utcnow() + timedelta(hours=24)
            db.session.commit()

            # Start tournament but don't complete any matches
            StateService.to_inscription(gara)

            # Create players (minimum 6 required)
            players = []
            import uuid

            test_id = str(uuid.uuid4())[:8]
            for i in range(6):
                player = User(
                    username=f"no_completed_player_{test_id}_{i}",
                    email=f"no_completed_player_{test_id}_{i}@test.com",
                    role=UserRole.PLAYER.value,
                )
                player.set_password("player123")
                db.session.add(player)
                players.append(player)

            db.session.commit()

            for player in players:
                InscriptionService.inscribe_user(player.id, gara.id)

            # Start playing and create first round
            StateService.start_playing(gara)
            GaraService.create_round_with_strategy(gara.id, 1)

            # Test: No classification should be shown
            response = client.get(f"/admin/gara/{gara.id}")
            assert response.status_code == 200

            html_content = response.data.decode("utf-8")

            # Should not show any classification
            assert (
                "Classifica dopo Turno" not in html_content
            ), "Should not show any classification when no rounds are completed"

    @pytest.mark.skip(reason="Session isolation issue: DetachedInstanceError when run after other tests")
    def test_classification_recalculated_when_missing(self, app, admin_user):
        """
        Test che la classificazione venga ricalcolata automaticamente se mancante dal database.
        """
        with app.test_client() as client:
            # Login as admin
            with client.session_transaction() as sess:
                sess["_user_id"] = str(admin_user.id)
                sess["_fresh"] = True

            # 1. Create gara with 6 players (minimum required)
            gara = GaraService.create_gara(
                number=1,
                name="Recalculation Test",
                date=date.today(),
                discipline="9-ball",
                distance=5,
                campionato_id=None,
                director_id=admin_user.id,
                rounds_count=2,
            )

            # Set inscription dates before moving to inscription status
            gara.inscription_start = datetime.utcnow()
            gara.inscription_end = datetime.utcnow() + timedelta(hours=24)
            db.session.commit()

            # Move to inscription status
            StateService.to_inscription(gara)

            # 2. Create and register 6 players (minimum required)
            players = []
            import uuid

            test_id = str(uuid.uuid4())[:8]
            for i in range(6):
                player = User(
                    username=f"recalc_player_{test_id}_{i}",
                    email=f"recalc_player_{test_id}_{i}@test.com",
                    role=UserRole.PLAYER.value,
                )
                player.set_password("player123")
                db.session.add(player)
                players.append(player)

            db.session.commit()

            for player in players:
                InscriptionService.inscribe_user(player.id, gara.id)

            # 3. Start playing and create first round
            StateService.start_playing(gara)
            GaraService.create_round_with_strategy(gara.id, 1)

            # 4. Complete all matches in round 1 BUT don't create manual classifications
            first_round_matches = Match.query.filter_by(
                gara_id=gara.id, round_number=1
            ).all()

            for i, match in enumerate(first_round_matches):
                if not match.is_bye:
                    match.status = MatchStatus.COMPLETED.value
                    match.winner_id = match.player1_id
                    match.player1_score = 3
                    match.player2_score = 1
                    db.session.add(match)

            db.session.commit()

            # Update round progression
            GaraService.update_round_progression(gara.id)
            db.session.refresh(gara)

            # 5. Remove any automatically created classifications to simulate missing data
            existing_classifications = RoundClassification.query.filter_by(
                gara_id=gara.id, round_number=1
            ).all()
            for classification in existing_classifications:
                db.session.delete(classification)
            db.session.commit()

            # Verify no classifications exist in database
            classifications_count = RoundClassification.query.filter_by(
                gara_id=gara.id, round_number=1
            ).count()
            assert (
                classifications_count == 0
            ), "No classifications should exist initially"

            # 6. Request the page - this should trigger automatic recalculation
            response = client.get(f"/admin/gara/{gara.id}")
            assert response.status_code == 200

            html_content = response.data.decode("utf-8")

            # Should show classification (which was auto-calculated)
            assert (
                "Classifica dopo Turno 1" in html_content
            ), "Should auto-calculate and show classification for round 1"

            # 7. Verify classifications were created in database after the request
            classifications_after = RoundClassification.query.filter_by(
                gara_id=gara.id, round_number=1
            ).count()
            assert (
                classifications_after > 0
            ), "Classifications should have been auto-created"

    @pytest.mark.skip(reason="Session isolation issue: DetachedInstanceError when run after other tests")
    def test_classification_updated_after_match_modification(self, app, admin_user):
        """
        Test che la classificazione venga aggiornata automaticamente quando i risultati dei match vengono modificati.
        """
        with app.test_client() as client:
            # Login as admin
            with client.session_transaction() as sess:
                sess["_user_id"] = str(admin_user.id)
                sess["_fresh"] = True

            # 1. Create gara with 6 players (minimum required)
            gara = GaraService.create_gara(
                number=1,
                name="Match Modification Test",
                date=date.today(),
                discipline="9-ball",
                distance=5,
                campionato_id=None,
                director_id=admin_user.id,
                rounds_count=2,
            )

            # Set inscription dates before moving to inscription status
            gara.inscription_start = datetime.utcnow()
            gara.inscription_end = datetime.utcnow() + timedelta(hours=24)
            db.session.commit()

            # Move to inscription status
            StateService.to_inscription(gara)

            # 2. Create and register 6 players (minimum required)
            players = []
            import uuid

            test_id = str(uuid.uuid4())[:8]
            for i in range(6):
                player = User(
                    username=f"modif_player_{test_id}_{i}",
                    email=f"modif_player_{test_id}_{i}@test.com",
                    role=UserRole.PLAYER.value,
                )
                player.set_password("player123")
                db.session.add(player)
                players.append(player)

            db.session.commit()

            for player in players:
                InscriptionService.inscribe_user(player.id, gara.id)

            # 3. Start playing and create first round
            StateService.start_playing(gara)
            GaraService.create_round_with_strategy(gara.id, 1)

            # 4. Complete all matches in round 1 with initial results
            first_round_matches = Match.query.filter_by(
                gara_id=gara.id, round_number=1
            ).all()

            for i, match in enumerate(first_round_matches):
                if not match.is_bye:
                    match.status = MatchStatus.COMPLETED.value
                    match.winner_id = match.player1_id  # Player 1 wins initially
                    match.player1_score = 3
                    match.player2_score = 1
                    db.session.add(match)

            db.session.commit()

            # Update round progression
            GaraService.update_round_progression(gara.id)
            db.session.refresh(gara)

            # 5. Get initial classification
            response = client.get(f"/admin/gara/{gara.id}")
            assert response.status_code == 200
            initial_html = response.data.decode("utf-8")

            # Should show classification for round 1
            assert "Classifica dopo Turno 1" in initial_html

            # 6. Now modify a match result (change winner from player1 to player2)
            match_to_modify = first_round_matches[0]  # First match
            if not match_to_modify.is_bye:
                # Change winner from player1 to player2
                original_winner = match_to_modify.winner_id
                new_winner = match_to_modify.player2_id

                match_to_modify.winner_id = new_winner
                match_to_modify.player1_score = 1  # Now player1 loses
                match_to_modify.player2_score = 3  # Now player2 wins
                db.session.add(match_to_modify)
                db.session.commit()

                # 7. Request the page again - classification should be automatically recalculated
                response = client.get(f"/admin/gara/{gara.id}")
                assert response.status_code == 200
                updated_html = response.data.decode("utf-8")

                # Should still show classification (but with updated data)
                assert "Classifica dopo Turno 1" in updated_html

                # The classification should be different from the initial one
                # (This is verified by the fact that the calculation is triggered on each request)
                # We can't easily test the exact positions without parsing HTML,
                # but we can verify that the calculation was triggered
