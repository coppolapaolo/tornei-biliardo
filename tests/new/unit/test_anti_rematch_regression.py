"""
Regression test for anti-rematch bug.

Bug: In una gara Amalfi con anti_rematch_enabled=True, alcuni match tra gli stessi
giocatori venivano generati nonostante l'opzione anti-rematch fosse attiva.

Scenari testati:
- 8 giocatori, 3 round: con 4 match per round, ogni giocatore gioca 3 match
  e non dovrebbe mai incontrare lo stesso avversario due volte.
- 6 giocatori, 3 round: scenario più piccolo per debug.

Vedi: docs/adr/NNNN-fix-anti-rematch-enforcement.md (se applicabile)
"""

from datetime import date, timedelta

from models.competition.services import GaraService, RoundService
from models.competition.inscription_service import InscriptionService
from models.match.models import Match
from models.classification.models import RoundClassification, PlayerEncounter
from models.classification.encounter_service import PlayerEncounterService
from models.matchmaking.policies import anti_rematch_allowed
from models import db
from models.base import utc_now


class TestAntiRematchRegression:
    """Regression tests for anti-rematch logic in Amalfi strategy.

    These tests verify that anti-rematch prevents ALL rematches,
    not just minimizes them.
    """

    def test_anti_rematch_prevents_all_rematches_8_players_3_rounds(
        self, isolated_director_user, db_session
    ):
        """
        Regression test: Anti-rematch must prevent ALL rematches.

        Scenario: 8 players, 3 rounds, anti_rematch_enabled=True
        - Each round has 4 matches (no bye needed with even players)
        - Each player plays 3 matches total
        - NO player pair should meet more than once

        Bug: Rematches were observed despite anti-rematch being enabled.
        Fix: [TBD - test first to confirm bug]
        """
        from models.user.models import User

        # Create 8 test players
        players = []
        for i in range(8):
            user = User(
                username=f"antirematch_player_{i}",
                email=f"antirematch{i}@test.com",
                password_hash="test123",
            )
            db.session.add(user)
            players.append(user)
        db.session.flush()

        # Create gara with anti-rematch enabled
        tomorrow = date.today() + timedelta(days=1)
        gara = GaraService.create_gara(
            campionato_id=None,
            number=1,
            name="Anti-Rematch Test 8p3r",
            date=tomorrow,
            location="Test Location",
            description="Regression test for anti-rematch bug",
            rounds_count=3,
            min_participants=4,
            max_participants=8,
            entry_fee=10.0,
            discipline="palla_9",
            distance=5,
            is_race_to=True,
            director_id=isolated_director_user.id,
            matchmaking_strategy="amalfi",
            first_round_policy="random",
            odd_number_policy="bye",
            anti_rematch_enabled=True,  # CRITICAL: must prevent rematches
        )

        # Register all 8 players
        for player in players:
            InscriptionService.inscribe_user(player.id, gara.id)

        # Open inscriptions and start tournament
        inscription_start = utc_now()
        inscription_end = utc_now() + timedelta(hours=1)
        InscriptionService.open_inscriptions(
            gara.id, inscription_start, inscription_end
        )
        RoundService.start_first_round(gara.id)

        # Track all pairings across ALL rounds
        all_encounters = set()  # set of (min_id, max_id) tuples
        rematches_found = []

        for round_num in range(1, 4):
            if round_num == 1:
                matches = Match.query.filter_by(
                    gara_id=gara.id, round_number=round_num
                ).all()
            else:
                # Complete previous round matches first
                prev_matches = Match.query.filter_by(
                    gara_id=gara.id, round_number=round_num - 1
                ).all()
                for match in prev_matches:
                    if not match.is_bye:
                        # Simulate completion with player1 winning
                        match.status = "completed"
                        match.player1_score = 5
                        match.player2_score = 2
                        match.winner_id = match.player1_id
                        # Usa il service come in produzione (invalida la cache)
                        PlayerEncounterService.record_match_encounters(match)
                db.session.flush()

                # Calculate classification for completed round
                RoundClassification.calculate_classification_after_round(
                    gara.id, round_num - 1
                )

                # Create next round
                RoundService.create_round_with_strategy(gara.id, round_num)
                matches = Match.query.filter_by(
                    gara_id=gara.id, round_number=round_num
                ).all()

            # Check for rematches in this round
            for match in matches:
                if not match.is_bye and match.player2_id:
                    # Normalize pairing (smaller id first)
                    pairing = (
                        min(match.player1_id, match.player2_id),
                        max(match.player1_id, match.player2_id),
                    )

                    if pairing in all_encounters:
                        rematches_found.append(
                            {
                                "round": round_num,
                                "player1_id": match.player1_id,
                                "player2_id": match.player2_id,
                                "pairing": pairing,
                            }
                        )
                    else:
                        all_encounters.add(pairing)

        # CRITICAL ASSERTION: No rematches should occur
        assert len(rematches_found) == 0, (
            f"Anti-rematch FAILED: Found {len(rematches_found)} rematch(es)! "
            f"Details: {rematches_found}"
        )

    def test_anti_rematch_prevents_rematches_6_players_3_rounds(
        self, isolated_director_user, db_session
    ):
        """
        Regression test: Smaller scenario for easier debugging.

        Scenario: 6 players, 3 rounds
        - Each round has 3 matches (no bye with even players)
        - Each player plays 3 matches total
        - With 6 players, each can play 5 unique opponents
        - 3 rounds = 3 matches per player, so no rematches needed
        """
        from models.user.models import User

        # Create 6 test players
        players = []
        for i in range(6):
            user = User(
                username=f"antirematch6_player_{i}",
                email=f"antirematch6_{i}@test.com",
                password_hash="test123",
            )
            db.session.add(user)
            players.append(user)
        db.session.flush()

        # Create gara
        tomorrow = date.today() + timedelta(days=1)
        gara = GaraService.create_gara(
            campionato_id=None,
            number=1,
            name="Anti-Rematch Test 6p3r",
            date=tomorrow,
            location="Test Location",
            description="Regression test - 6 players",
            rounds_count=3,
            min_participants=4,
            max_participants=8,
            entry_fee=10.0,
            discipline="palla_9",
            distance=5,
            is_race_to=True,
            director_id=isolated_director_user.id,
            matchmaking_strategy="amalfi",
            first_round_policy="random",
            odd_number_policy="bye",
            anti_rematch_enabled=True,
        )

        # Register players
        for player in players:
            InscriptionService.inscribe_user(player.id, gara.id)

        # Start tournament
        inscription_start = utc_now()
        inscription_end = utc_now() + timedelta(hours=1)
        InscriptionService.open_inscriptions(
            gara.id, inscription_start, inscription_end
        )
        RoundService.start_first_round(gara.id)

        # Track encounters
        all_encounters = set()
        rematches_found = []

        for round_num in range(1, 4):
            if round_num > 1:
                # Complete previous round
                prev_matches = Match.query.filter_by(
                    gara_id=gara.id, round_number=round_num - 1
                ).all()
                for match in prev_matches:
                    if not match.is_bye and match.player2_id:
                        match.status = "completed"
                        match.player1_score = 5
                        match.player2_score = 2
                        match.winner_id = match.player1_id
                        PlayerEncounterService.record_match_encounters(match)
                db.session.flush()

                RoundClassification.calculate_classification_after_round(
                    gara.id, round_num - 1
                )
                RoundService.create_round_with_strategy(gara.id, round_num)

            matches = Match.query.filter_by(
                gara_id=gara.id, round_number=round_num
            ).all()

            for match in matches:
                if not match.is_bye and match.player2_id:
                    pairing = (
                        min(match.player1_id, match.player2_id),
                        max(match.player1_id, match.player2_id),
                    )

                    if pairing in all_encounters:
                        rematches_found.append({"round": round_num, "pairing": pairing})
                    else:
                        all_encounters.add(pairing)

        assert len(rematches_found) == 0, (
            f"Anti-rematch FAILED: {len(rematches_found)} rematch(es) found! "
            f"Details: {rematches_found}"
        )

    def test_player_encounter_have_played_returns_true_after_match(
        self, isolated_director_user, db_session
    ):
        """
        Unit test: Verify PlayerEncounter.have_played() works correctly.

        This tests the underlying mechanism used by anti-rematch logic.
        """
        from models.user.models import User

        # Create 2 test players
        player1 = User(
            username="encounter_test_p1",
            email="encounter_p1@test.com",
            password_hash="test123",
        )
        player2 = User(
            username="encounter_test_p2",
            email="encounter_p2@test.com",
            password_hash="test123",
        )
        db.session.add_all([player1, player2])
        db.session.flush()

        # Create gara
        tomorrow = date.today() + timedelta(days=1)
        gara = GaraService.create_gara(
            campionato_id=None,
            number=1,
            name="Encounter Test",
            date=tomorrow,
            location="Test Location",
            description="Test PlayerEncounter",
            rounds_count=1,
            min_participants=2,
            max_participants=8,
            entry_fee=10.0,
            discipline="palla_9",
            distance=5,
            is_race_to=True,
            director_id=isolated_director_user.id,
            matchmaking_strategy="amalfi",
            first_round_policy="random",
            odd_number_policy="bye",
            anti_rematch_enabled=True,
        )

        # Initially, players should NOT have played
        assert not PlayerEncounter.have_played(gara.id, player1.id, player2.id)
        assert anti_rematch_allowed(gara.id, player1.id, player2.id)

        # Record encounter
        PlayerEncounter.record_encounter(
            gara_id=gara.id,
            player1_id=player1.id,
            player2_id=player2.id,
            round_number=1,
        )
        db.session.flush()

        # Now they SHOULD have played
        assert PlayerEncounter.have_played(gara.id, player1.id, player2.id)
        # And anti-rematch should NOT allow pairing
        assert not anti_rematch_allowed(gara.id, player1.id, player2.id)

        # Test symmetry (order shouldn't matter)
        assert PlayerEncounter.have_played(gara.id, player2.id, player1.id)
        assert not anti_rematch_allowed(gara.id, player2.id, player1.id)

    def test_amalfi_strategy_respects_encounter_history(
        self, isolated_director_user, db_session
    ):
        """
        Integration test: Verify AmalfiStrategy applies anti-rematch in round 2+.

        This tests that the strategy actually uses the encounter data
        when generating pairings.
        """
        from models.user.models import User

        # Create 4 players for minimal scenario
        players = []
        for i in range(4):
            user = User(
                username=f"amalfi_hap_test_{i}",
                email=f"amalfi_hap_{i}@test.com",
                password_hash="test123",
            )
            db.session.add(user)
            players.append(user)
        db.session.flush()

        # Create gara
        tomorrow = date.today() + timedelta(days=1)
        gara = GaraService.create_gara(
            campionato_id=None,
            number=1,
            name="Amalfi HAP Test",
            date=tomorrow,
            location="Test Location",
            description="Test encounter history integration",
            rounds_count=2,
            min_participants=4,
            max_participants=8,
            entry_fee=10.0,
            discipline="palla_9",
            distance=5,
            is_race_to=True,
            director_id=isolated_director_user.id,
            matchmaking_strategy="amalfi",
            first_round_policy="random",
            odd_number_policy="bye",
            anti_rematch_enabled=True,
        )

        for player in players:
            InscriptionService.inscribe_user(player.id, gara.id)

        # Start tournament
        inscription_start = utc_now()
        inscription_end = utc_now() + timedelta(hours=1)
        InscriptionService.open_inscriptions(
            gara.id, inscription_start, inscription_end
        )
        RoundService.start_first_round(gara.id)

        # Get round 1 pairings
        round1_matches = Match.query.filter_by(gara_id=gara.id, round_number=1).all()
        round1_pairings = set()
        for match in round1_matches:
            if not match.is_bye and match.player2_id:
                pairing = (
                    min(match.player1_id, match.player2_id),
                    max(match.player1_id, match.player2_id),
                )
                round1_pairings.add(pairing)

        # Complete round 1 and record encounters
        for match in round1_matches:
            if not match.is_bye and match.player2_id:
                match.status = "completed"
                match.player1_score = 5
                match.player2_score = 2
                match.winner_id = match.player1_id
                PlayerEncounterService.record_match_encounters(match)
        db.session.flush()

        # Calculate classification
        RoundClassification.calculate_classification_after_round(gara.id, 1)

        # Create round 2
        RoundService.create_round_with_strategy(gara.id, 2)

        # Get round 2 pairings
        round2_matches = Match.query.filter_by(gara_id=gara.id, round_number=2).all()
        round2_pairings = set()
        for match in round2_matches:
            if not match.is_bye and match.player2_id:
                pairing = (
                    min(match.player1_id, match.player2_id),
                    max(match.player1_id, match.player2_id),
                )
                round2_pairings.add(pairing)

        # Round 2 pairings should NOT contain any round 1 pairings
        rematches = round1_pairings & round2_pairings
        assert len(rematches) == 0, (
            f"Strategy created rematch in round 2! "
            f"Round 1 pairings: {round1_pairings}, "
            f"Round 2 pairings: {round2_pairings}, "
            f"Rematches: {rematches}"
        )

    def test_anti_rematch_validation_rounds_vs_players(
        self, isolated_director_user, db_session
    ):
        """
        Validation test: Anti-rematch requires enough players for rounds.

        Mathematical constraint:
        - With k players, each can play at most k-1 unique opponents
        - So max rounds with anti-rematch = k-1
        - If rounds_count > k-1, anti-rematch is mathematically impossible

        Examples:
        - 8 players, 3 rounds: OK (3 < 8-1=7)
        - 6 players, 3 rounds: OK (3 < 6-1=5)
        - 4 players, 5 rounds: INVALID (5 > 4-1=3)

        This is validated by validate_gara_data() in GaraService.
        """
        # Test the validation function directly
        # Invalid case: 4 max players, 5 rounds, anti-rematch enabled
        invalid_data = {
            "name": "Invalid Config",
            "discipline": "palla_9",
            "distance": 5,
            "rounds_count": 5,
            "max_participants": 4,
            "anti_rematch_enabled": True,
        }
        errors = GaraService.validate_gara_data(invalid_data)

        # Should have an error for rounds_count
        assert "rounds_count" in errors, (
            f"Expected validation error for rounds_count with 4 players "
            f"and 5 rounds (max is 3), but got errors: {errors}"
        )
        assert (
            "anti-rematch" in errors["rounds_count"].lower()
            or "turni" in errors["rounds_count"].lower()
        ), (
            "Expected error message to mention anti-rematch constraint, "
            f"got: {errors['rounds_count']}"
        )

    def test_anti_rematch_validation_valid_configuration(
        self, isolated_director_user, db_session
    ):
        """
        Validation test: Valid anti-rematch configuration should pass.

        8 players, 3 rounds: OK (3 < 8-1=7)
        """
        valid_data = {
            "name": "Valid Config",
            "discipline": "palla_9",
            "distance": 5,
            "rounds_count": 3,
            "max_participants": 8,
            "anti_rematch_enabled": True,
        }
        errors = GaraService.validate_gara_data(valid_data)

        # Should NOT have an error for rounds_count
        assert "rounds_count" not in errors, (
            "Unexpected validation error for valid config "
            f"(8 players, 3 rounds): {errors}"
        )

    def test_anti_rematch_validation_no_max_participants(
        self, isolated_director_user, db_session
    ):
        """
        Validation test: Without max_participants, no constraint applies.

        If max_participants is not set, we can't validate the constraint
        because we don't know how many players will join.
        """
        data_without_max = {
            "name": "No Max Config",
            "discipline": "palla_9",
            "distance": 5,
            "rounds_count": 10,  # High number but no max_participants
            "anti_rematch_enabled": True,
            # max_participants not set
        }
        errors = GaraService.validate_gara_data(data_without_max)

        # Should NOT have an anti-rematch error (can't validate without max)
        if "rounds_count" in errors:
            assert (
                "anti-rematch" not in errors["rounds_count"].lower()
            ), f"Should not validate anti-rematch without max_participants: {errors}"

    def test_anti_rematch_validation_disabled(self, isolated_director_user, db_session):
        """
        Validation test: With anti-rematch disabled, no constraint applies.
        """
        data_no_anti_rematch = {
            "name": "No Anti-Rematch Config",
            "discipline": "palla_9",
            "distance": 5,
            "rounds_count": 10,  # More than max_participants - 1
            "max_participants": 4,
            "anti_rematch_enabled": False,  # Disabled
        }
        errors = GaraService.validate_gara_data(data_no_anti_rematch)

        # Should NOT have an anti-rematch error
        if "rounds_count" in errors:
            assert (
                "anti-rematch" not in errors["rounds_count"].lower()
            ), f"Should not validate anti-rematch when disabled: {errors}"

    def test_contract_reset_preserves_encounter(
        self, isolated_director_user, db_session
    ):
        """
        Contract test: reset_match_complete PRESERVES the PlayerEncounter.

        Semantics (see docs/adr/ADR-026-reset-match-preserves-pair-semantics.md):
        Reset = score correction, pair preserved. The same two players will
        replay the same match, so the encounter between them must remain as
        "already happened" for the anti-rematch logic.

        To release a pair (e.g. regenerate the round with different pairings),
        the director must cancel the round via
        `AdvancedRoundManager.cancel_round`, which has its own cleanup via
        `PlayerEncounter.delete_round_encounters`.

        This test supersedes the previous `test_encounter_cleanup_on_match_reset`
        (named after the assumption codified in ADR-002) which enforced the
        opposite semantics. ADR-026 documents why ADR-002 was partly wrong.
        """
        from models.user.models import User
        from models.match.services import RackService

        # Create 4 test players
        players = []
        for i in range(4):
            user = User(
                username=f"reset_encounter_test_{i}",
                email=f"reset_enc_{i}@test.com",
                password_hash="test123",
            )
            db.session.add(user)
            players.append(user)
        db.session.flush()

        # Create gara
        tomorrow = date.today() + timedelta(days=1)
        gara = GaraService.create_gara(
            campionato_id=None,
            number=1,
            name="Encounter Preserved on Reset",
            date=tomorrow,
            location="Test Location",
            description="Contract: reset preserves encounter (ADR-026)",
            rounds_count=2,
            min_participants=4,
            max_participants=8,
            entry_fee=10.0,
            discipline="palla_9",
            distance=5,
            is_race_to=True,
            director_id=isolated_director_user.id,
            matchmaking_strategy="amalfi",
            first_round_policy="random",
            odd_number_policy="bye",
            anti_rematch_enabled=True,
        )

        for player in players:
            InscriptionService.inscribe_user(player.id, gara.id)

        # Start tournament
        inscription_start = utc_now()
        inscription_end = utc_now() + timedelta(hours=1)
        InscriptionService.open_inscriptions(
            gara.id, inscription_start, inscription_end
        )
        RoundService.start_first_round(gara.id)

        # Complete round 1 matches using MatchService.to_completed()
        # which records encounters
        from models.match.services import MatchService

        round1_matches = Match.query.filter_by(gara_id=gara.id, round_number=1).all()
        for match in round1_matches:
            if not match.is_bye and match.player2_id:
                # Set scores and complete via service (triggers encounter recording)
                match.player1_score = 5
                match.player2_score = 2
                match.winner_id = match.player1_id
                match.status = "playing"  # Must be in playing first
                db.session.flush()
                MatchService.to_completed(match.id)
        db.session.flush()

        # Reload matches
        round1_matches = Match.query.filter_by(gara_id=gara.id, round_number=1).all()

        # Verify encounters were recorded
        for match in round1_matches:
            if not match.is_bye and match.player2_id:
                p1 = min(match.player1_id, match.player2_id)
                p2 = max(match.player1_id, match.player2_id)
                assert PlayerEncounter.have_played(
                    gara.id, p1, p2
                ), f"Encounter should exist after match completion: {p1} vs {p2}"

        # Now reset the first match
        first_match = round1_matches[0]
        if not first_match.is_bye and first_match.player2_id:
            # Reset match (score correction scenario)
            RackService.reset_match_complete(first_match.id)
            db.session.flush()

            # CONTRACT: Encounter must be PRESERVED after reset.
            # The same two players will replay the same match; the pair
            # remains "already faced" from the anti-rematch perspective.
            p1 = min(first_match.player1_id, first_match.player2_id)
            p2 = max(first_match.player1_id, first_match.player2_id)

            assert PlayerEncounter.have_played(gara.id, p1, p2), (
                f"Encounter MUST exist after match reset (ADR-026). "
                f"Players {p1} vs {p2}: reset is score correction, "
                f"the pair is preserved by design. To release a pair, "
                f"use cancel_round instead."
            )
            # Symmetry: (p2, p1) must also report the encounter
            assert PlayerEncounter.have_played(gara.id, p2, p1), (
                "have_played must be symmetric: reset preservation holds "
                "regardless of argument order (ADR-026)."
            )

    def test_encounter_cleanup_on_round_cancel(
        self, isolated_director_user, db_session
    ):
        """
        Regression test: Encounters must be deleted when round is cancelled.

        Bug scenario:
        1. Round 1 completed → encounters recorded
        2. Director cancels round 1 entirely
        3. Encounters NOT deleted (bug!)
        4. New round 1 generated with stale anti-rematch data

        Fix: All PlayerEncounter records for cancelled round must be deleted.
        """
        from models.user.models import User
        from models.competition.round_manager import AdvancedRoundManager

        # Create 4 test players
        players = []
        for i in range(4):
            user = User(
                username=f"cancel_encounter_test_{i}",
                email=f"cancel_enc_{i}@test.com",
                password_hash="test123",
            )
            db.session.add(user)
            players.append(user)
        db.session.flush()

        # Create gara
        tomorrow = date.today() + timedelta(days=1)
        gara = GaraService.create_gara(
            campionato_id=None,
            number=1,
            name="Round Cancel Encounter Test",
            date=tomorrow,
            location="Test Location",
            description="Test encounter cleanup on round cancel",
            rounds_count=2,
            min_participants=4,
            max_participants=8,
            entry_fee=10.0,
            discipline="palla_9",
            distance=5,
            is_race_to=True,
            director_id=isolated_director_user.id,
            matchmaking_strategy="amalfi",
            first_round_policy="random",
            odd_number_policy="bye",
            anti_rematch_enabled=True,
        )

        for player in players:
            InscriptionService.inscribe_user(player.id, gara.id)

        # Start tournament
        inscription_start = utc_now()
        inscription_end = utc_now() + timedelta(hours=1)
        InscriptionService.open_inscriptions(
            gara.id, inscription_start, inscription_end
        )
        RoundService.start_first_round(gara.id)

        # Complete round 1 matches to record encounters
        from models.match.services import MatchService

        round1_matches = Match.query.filter_by(gara_id=gara.id, round_number=1).all()
        for match in round1_matches:
            if not match.is_bye and match.player2_id:
                # Set scores and complete via service (triggers encounter recording)
                match.player1_score = 5
                match.player2_score = 2
                match.winner_id = match.player1_id
                match.status = "playing"
                db.session.flush()
                MatchService.to_completed(match.id)
        db.session.flush()

        # Reload matches
        round1_matches = Match.query.filter_by(gara_id=gara.id, round_number=1).all()

        # Store pairings to verify later
        round1_pairings = []
        for match in round1_matches:
            if not match.is_bye and match.player2_id:
                p1, p2 = min(match.player1_id, match.player2_id), max(
                    match.player1_id, match.player2_id
                )
                round1_pairings.append((p1, p2))
                assert PlayerEncounter.have_played(gara.id, p1, p2)

        # First, reset all matches (required before cancelling round)
        for match in round1_matches:
            if not match.is_bye and match.winner_id:
                from models.match.services import RackService

                RackService.reset_match_complete(match.id)
        db.session.flush()

        # Cancel round 1 — MUST succeed. Previously this test would pass
        # even if cancel_round returned (False, ...) silently, because the
        # cleanup inside reset_match_complete (removed by ADR-026) would
        # have done the work. Now we assert success explicitly so a
        # regression where cancel_round's precondition blocks reset
        # matches again would fail loudly.
        success, message = AdvancedRoundManager.cancel_round(gara.id, 1)
        db.session.flush()
        assert success, (
            f"cancel_round must succeed on a round where all matches have "
            f"been reset (score=0, status=PENDING/PLAYING). Got: {message}"
        )

        # CRITICAL: All encounters for round 1 should be deleted
        # by cancel_round's own cleanup (delete_round_encounters).
        for p1, p2 in round1_pairings:
            assert not PlayerEncounter.have_played(gara.id, p1, p2), (
                f"Encounter should NOT exist after round cancel! "
                f"Players {p1} vs {p2} encounter still present."
            )
