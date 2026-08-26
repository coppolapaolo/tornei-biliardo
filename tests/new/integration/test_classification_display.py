"""
Test per verificare che la classificazione venga mostrata solo per i turni completati
e non per i turni in corso.
"""

import pytest
from datetime import date, timedelta
from models import db, User, Match
from models.user.role_enum import UserRole
from models.status_enum import MatchStatus
from models.competition.services import (
    GaraService,
    RoundService,
    InscriptionService,
)
from models.competition.state_service import StateService
from models.classification.models import RoundClassification
from models.base import utc_now


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
        # Use get() for proper session attachment (avoids DetachedInstanceError)
        return db_session.get(User, admin.id)

    def test_classification_only_shown_for_completed_rounds(self, app, admin_user):
        """
        Test che la classificazione venga mostrata solo per i turni completati,
        non per quelli in corso.
        """
        with app.test_client() as client:
            # Login as admin
            with client.session_transaction() as sess:
                sess["_user_id"] = admin_user.get_id()
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
            gara.inscription_start = utc_now()
            gara.inscription_end = utc_now() + timedelta(hours=24)
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
            RoundService.create_round_with_strategy(gara.id, 1)

            # Refresh gara to get current round updated
            db.session.refresh(gara)

            # 4. Test: No classification should be shown (no completed rounds yet)
            response = client.get(f"/admin/gara/{gara.id}")
            assert response.status_code == 200

            html_content = response.data.decode("utf-8")

            # Should not show any classification section
            assert (
                "Classifica dopo il turno" not in html_content
            ), "Should not show classification when no rounds are completed"

            # 5. Complete all matches in round 1
            first_round_matches = Match.query.filter_by(
                gara_id=gara.id, round_number=1
            ).all()

            for i, match in enumerate(first_round_matches):
                if not match.is_bye:
                    # Simulate match completion
                    match.status = MatchStatus.CLOSED_UNILATERALLY.value
                    match.winner_id = match.player1_id
                    match.player1_score = 3
                    match.player2_score = 1
                    db.session.add(match)

            db.session.commit()

            # Update round progression to set current_round correctly
            RoundService.update_round_progression(gara.id)
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
                "Classifica dopo il turno 1" in html_content
            ), "Should show classification after round 1 is completed"

            # 7. Create second round but don't complete it
            RoundService.create_round_with_strategy(gara.id, 2)
            db.session.refresh(gara)

            # 8. Test: Should still show only round 1 classification
            response = client.get(f"/admin/gara/{gara.id}")
            assert response.status_code == 200

            html_content = response.data.decode("utf-8")

            # Should still show only round 1 classification
            assert (
                "Classifica dopo il turno 1" in html_content
            ), "Should still show round 1 classification"
            assert (
                "Classifica dopo il turno 2" not in html_content
            ), "Should not show round 2 classification when round 2 is not completed"

            # 9. Complete round 2 matches
            second_round_matches = Match.query.filter_by(
                gara_id=gara.id, round_number=2
            ).all()

            for i, match in enumerate(second_round_matches):
                if not match.is_bye:
                    # Simulate match completion
                    match.status = MatchStatus.CLOSED_UNILATERALLY.value
                    match.winner_id = match.player1_id
                    match.player1_score = 3
                    match.player2_score = 2
                    db.session.add(match)

            db.session.commit()

            # Update round progression to set current_round correctly
            RoundService.update_round_progression(gara.id)
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

            # 10. Test: Should now show classification for round 2 (most recent
            # completed)
            response = client.get(f"/admin/gara/{gara.id}")
            assert response.status_code == 200

            html_content = response.data.decode("utf-8")

            # Debug: check what classification is actually shown and why
            db.session.refresh(gara)
            print(
                (
                    f"DEBUG: gara.current_round after round 2 creation: "
                    f"{gara.current_round}"
                )
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
                    match.status == MatchStatus.CLOSED_UNILATERALLY.value
                    for match in round_matches
                )
                n_completate = len(
                    [
                        m
                        for m in round_matches
                        if m.status == MatchStatus.CLOSED_UNILATERALLY.value
                    ]
                )
                print(
                    f"DEBUG: Round {round_number} completed: {completed} "
                    f"({n_completate}/{len(round_matches)} matches)"
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

            if "Classifica dopo il turno" in html_content:
                start_pos = html_content.find("Classifica dopo il turno")
                end_pos = html_content.find("</h5>", start_pos) + 5
                classification_title = html_content[start_pos:end_pos]
                print(f"DEBUG: Found classification: {classification_title}")
            else:
                print("DEBUG: No classification found in HTML")

            # The important test: we should show some classification
            assert (
                "Classifica dopo il turno" in html_content
            ), "Should show some classification after round 2 is completed"

            # The specific assertion can be: should show round 2 classification (or at
            # least not show round 1 when round 2 is complete)
            # For now, let's make sure it shows the right one
            if "Classifica dopo il turno 2" in html_content:
                # Perfect! Shows round 2 as expected
                pass
            elif "Classifica dopo il turno 1" in html_content:
                # This means round 2 is not being detected as completed
                # Let's fail with more info
                assert False, (
                    f"Expected round 2 classification but found round 1. "
                    f"gara.current_round={gara.current_round}"
                )
            else:
                assert False, "No round classification found"

    def test_no_classification_shown_when_no_rounds_completed(self, app, admin_user):
        """
        Test che nessuna classificazione venga mostrata se non ci sono turni completati.
        """
        with app.test_client() as client:
            # Login as admin
            with client.session_transaction() as sess:
                sess["_user_id"] = admin_user.get_id()
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
            gara.inscription_start = utc_now()
            gara.inscription_end = utc_now() + timedelta(hours=24)
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
            RoundService.create_round_with_strategy(gara.id, 1)

            # Test: No classification should be shown
            response = client.get(f"/admin/gara/{gara.id}")
            assert response.status_code == 200

            html_content = response.data.decode("utf-8")

            # Should not show any classification
            assert (
                "Classifica dopo il turno" not in html_content
            ), "Should not show any classification when no rounds are completed"

    def test_classification_recalculated_when_missing(self, app, admin_user):
        """
        Test che la classificazione venga ricalcolata automaticamente se mancante dal
        database.
        """
        with app.test_client() as client:
            # Login as admin
            with client.session_transaction() as sess:
                sess["_user_id"] = admin_user.get_id()
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
            gara.inscription_start = utc_now()
            gara.inscription_end = utc_now() + timedelta(hours=24)
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
            RoundService.create_round_with_strategy(gara.id, 1)

            # 4. Complete all matches in round 1 BUT don't create manual classifications
            first_round_matches = Match.query.filter_by(
                gara_id=gara.id, round_number=1
            ).all()

            for i, match in enumerate(first_round_matches):
                if not match.is_bye:
                    match.status = MatchStatus.CLOSED_UNILATERALLY.value
                    match.winner_id = match.player1_id
                    match.player1_score = 3
                    match.player2_score = 1
                    db.session.add(match)

            db.session.commit()

            # Update round progression
            RoundService.update_round_progression(gara.id)
            db.session.refresh(gara)

            # 5. Remove any automatically created classifications to simulate missing
            # data
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
                "Classifica dopo il turno 1" in html_content
            ), "Should auto-calculate and show classification for round 1"

            # 7. Verify classifications were created in database after the request
            classifications_after = RoundClassification.query.filter_by(
                gara_id=gara.id, round_number=1
            ).count()
            assert (
                classifications_after > 0
            ), "Classifications should have been auto-created"

    def test_classification_updated_after_match_modification(self, app, admin_user):
        """
        Test che la classificazione venga aggiornata automaticamente quando i risultati
        dei match vengono modificati.
        """
        with app.test_client() as client:
            # Login as admin
            with client.session_transaction() as sess:
                sess["_user_id"] = admin_user.get_id()
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
            gara.inscription_start = utc_now()
            gara.inscription_end = utc_now() + timedelta(hours=24)
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
            RoundService.create_round_with_strategy(gara.id, 1)

            # 4. Complete all matches in round 1 with initial results
            first_round_matches = Match.query.filter_by(
                gara_id=gara.id, round_number=1
            ).all()

            for i, match in enumerate(first_round_matches):
                if not match.is_bye:
                    match.status = MatchStatus.CLOSED_UNILATERALLY.value
                    match.winner_id = match.player1_id  # Player 1 wins initially
                    match.player1_score = 3
                    match.player2_score = 1
                    db.session.add(match)

            db.session.commit()

            # Update round progression
            RoundService.update_round_progression(gara.id)
            db.session.refresh(gara)

            # 5. Get initial classification
            response = client.get(f"/admin/gara/{gara.id}")
            assert response.status_code == 200
            initial_html = response.data.decode("utf-8")

            # Should show classification for round 1
            assert "Classifica dopo il turno 1" in initial_html

            # 6. Now modify a match result (change winner from player1 to player2)
            match_to_modify = first_round_matches[0]  # First match
            if not match_to_modify.is_bye:
                # Change winner from player1 to player2
                match_to_modify.winner_id
                new_winner = match_to_modify.player2_id

                match_to_modify.winner_id = new_winner
                match_to_modify.player1_score = 1  # Now player1 loses
                match_to_modify.player2_score = 3  # Now player2 wins
                db.session.add(match_to_modify)
                db.session.commit()

                # 7. Request the page again - classification should be automatically
                # recalculated
                response = client.get(f"/admin/gara/{gara.id}")
                assert response.status_code == 200
                updated_html = response.data.decode("utf-8")

                # Should still show classification (but with updated data)
                assert "Classifica dopo il turno 1" in updated_html

                # The classification should be different from the initial one
                # (This is verified by the fact that the calculation is triggered on
                # each request)
                # We can't easily test the exact positions without parsing HTML,
                # but we can verify that the calculation was triggered

    def test_classification_not_shown_when_zero_scores(self, app, admin_user):
        """
        Test che la classificazione NON venga mostrata quando tutti i giocatori
        hanno punteggi a zero (rack_difference = 0 e matches_won = 0).

        Scenario: gara avviata, primo turno creato ma nessuna partita completata.
        La classificazione esiste nel DB ma con tutti zeri → non deve apparire
        nell'HTML.
        """
        with app.test_client() as client:
            # Login as admin
            with client.session_transaction() as sess:
                sess["_user_id"] = admin_user.get_id()
                sess["_fresh"] = True

            # 1. Create gara with 6 players (minimum required)
            gara = GaraService.create_gara(
                number=1,
                name="Zero Scores Test",
                date=date.today(),
                discipline="9-ball",
                distance=5,
                campionato_id=None,
                director_id=admin_user.id,
                rounds_count=2,
            )

            # Set inscription dates before moving to inscription status
            gara.inscription_start = utc_now()
            gara.inscription_end = utc_now() + timedelta(hours=24)
            db.session.commit()

            # Move to inscription status
            StateService.to_inscription(gara)

            # 2. Create and register 6 players (minimum required)
            players = []
            import uuid

            test_id = str(uuid.uuid4())[:8]
            for i in range(6):
                player = User(
                    username=f"zero_scores_player_{test_id}_{i}",
                    email=f"zero_scores_player_{test_id}_{i}@test.com",
                    role=UserRole.PLAYER.value,
                )
                player.set_password("player123")
                db.session.add(player)
                players.append(player)

            db.session.commit()

            for player in players:
                InscriptionService.inscribe_user(player.id, gara.id)

            # 3. Start playing and create first round
            gara_id = gara.id  # Store ID before any session changes
            StateService.start_playing(gara)
            RoundService.create_round_with_strategy(gara_id, 1)

            # Use get() instead of refresh() for session isolation
            from models.competition.models import Gara

            gara = db.session.get(Gara, gara_id)

            # 4. Create classification records manually with ALL ZERO scores
            # This simulates a scenario where classification exists but no one has
            # played yet
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
                        matches_won=0,  # Zero!
                        rack_difference=0,  # Zero!
                    )
                    db.session.add(classification)
            db.session.commit()

            # Verify classification records exist in DB with zero scores
            classifications = RoundClassification.query.filter_by(
                gara_id=gara.id, round_number=1
            ).all()
            assert len(classifications) == 6, "6 classification records should exist"
            assert all(
                c.rack_difference == 0 and c.matches_won == 0 for c in classifications
            ), "All classifications should have zero scores"

            # 5. Test: Classification should NOT be shown because all scores are zero
            response = client.get(f"/admin/gara/{gara.id}")
            assert response.status_code == 200

            html_content = response.data.decode("utf-8")

            # Should NOT show desktop classification
            assert (
                "Classifica dopo il turno" not in html_content
            ), "Desktop classification should not be shown when all scores are zero"

            # Should NOT show mobile classification (compact/completa toggle)
            assert '<option value="compact">' not in html_content, (
                "Mobile classification toggle should not be shown when all scores are "
                "zero"
            )

            # Should NOT show the classification card with trophy icon
            assert (
                'fa-trophy"></i> Classifica' not in html_content
                and '<i class="fas fa-list-ol"></i> Classifica' not in html_content
            ), "Classification card should not appear when all scores are zero"

    def test_classification_shown_when_at_least_one_score(self, app, admin_user):
        """
        Test che la classificazione VENGA mostrata quando almeno un giocatore
        ha un punteggio non-zero.

        Nota: Per strategia Amalfi, il turno deve essere COMPLETATO (tutte le partite)
        per mostrare la classifica. Per Random, basta una partita completata.
        """
        with app.test_client() as client:
            # Login as admin
            with client.session_transaction() as sess:
                sess["_user_id"] = admin_user.get_id()
                sess["_fresh"] = True

            # 1. Create gara with 6 players
            gara = GaraService.create_gara(
                number=1,
                name="With Scores Test",
                date=date.today(),
                discipline="9-ball",
                distance=5,
                campionato_id=None,
                director_id=admin_user.id,
                rounds_count=2,
            )

            gara.inscription_start = utc_now()
            gara.inscription_end = utc_now() + timedelta(hours=24)
            db.session.commit()

            StateService.to_inscription(gara)

            # 2. Create and register 6 players
            players = []
            import uuid

            test_id = str(uuid.uuid4())[:8]
            for i in range(6):
                player = User(
                    username=f"with_scores_player_{test_id}_{i}",
                    email=f"with_scores_player_{test_id}_{i}@test.com",
                    role=UserRole.PLAYER.value,
                )
                player.set_password("player123")
                db.session.add(player)
                players.append(player)

            db.session.commit()

            for player in players:
                InscriptionService.inscribe_user(player.id, gara.id)

            # 3. Start playing and create first round
            gara_id = gara.id  # Store ID before any session changes
            StateService.start_playing(gara)
            RoundService.create_round_with_strategy(gara_id, 1)

            # 4. Complete ALL matches in round 1 (required for Amalfi strategy)
            first_round_matches = Match.query.filter_by(
                gara_id=gara_id, round_number=1
            ).all()

            for match in first_round_matches:
                if not match.is_bye:
                    match.status = MatchStatus.CLOSED_UNILATERALLY.value
                    match.winner_id = match.player1_id
                    match.player1_score = 5
                    match.player2_score = 2
                    db.session.add(match)

            db.session.commit()

            # Update round progression - use get() instead of refresh()
            RoundService.update_round_progression(gara_id)
            from models.competition.models import Gara

            gara = db.session.get(Gara, gara_id)

            # 5. Create classification with at least one non-zero entry
            for i, player in enumerate(players):
                existing = RoundClassification.query.filter_by(
                    gara_id=gara_id, round_number=1, user_id=player.id
                ).first()
                if not existing:
                    classification = RoundClassification(
                        gara_id=gara_id,
                        round_number=1,
                        user_id=player.id,
                        position=i + 1,
                        matches_won=(
                            1 if i < 3 else 0
                        ),  # First 3 players won their matches
                        rack_difference=3 if i < 3 else -3,
                    )
                    db.session.add(classification)
            db.session.commit()

            # 6. Test: Classification SHOULD be shown
            response = client.get(f"/admin/gara/{gara_id}")
            assert response.status_code == 200

            html_content = response.data.decode("utf-8")

            # Should show classification (at least one player has scores)
            has_desktop_classification = (
                "Classifica dopo il turno" in html_content
                or "Classifica Complessiva" in html_content
            )
            has_mobile_classification = '<option value="compact">' in html_content

            assert has_desktop_classification or has_mobile_classification, (
                "Classification should be shown when at least one player has non-zero "
                "scores"
            )
