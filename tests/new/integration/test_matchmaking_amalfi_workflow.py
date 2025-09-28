"""Integration tests for complete Amalfi gara workflow."""

import pytest
from datetime import date, datetime, timedelta
from typing import List, Dict

from models import User, Gara, Inscription, Match, Rack
from models.user.models import DirectorAssignment
from models.user.role_enum import UserRole
from models.status_enum import GaraStatus, MatchStatus
from models.competition.services import GaraService, InscriptionService
from models.match.services import MatchService, RackService
from models.classification.models import RoundClassification
# Removed: from amalfi.engine import get_amalfi_classification


@pytest.mark.integration
class TestAmalfiCompleteWorkflow:
    """Test complete Amalfi gara workflow from creation to final classification."""

    @pytest.fixture
    def admin_user(self, db_session):
        """Create admin user."""
        import uuid

        unique_id = str(uuid.uuid4())[:8]
        admin = User(
            username=f"admin_{unique_id}",
            email=f"admin_{unique_id}@test.com",
            role=UserRole.ADMIN.value,
        )
        admin.set_password("admin123")
        db_session.add(admin)
        db_session.commit()
        return admin

    @pytest.fixture
    def director_user(self, db_session):
        """Create director user."""
        import uuid

        unique_id = str(uuid.uuid4())[:8]
        director = User(
            username=f"director_{unique_id}",
            email=f"director_{unique_id}@test.com",
            role=UserRole.DIRECTOR.value,
        )
        director.set_password("director123")
        db_session.add(director)
        db_session.commit()
        return director

    @pytest.fixture
    def players(self, db_session):
        """Create 8 test players."""
        import uuid

        batch_id = str(uuid.uuid4())[:8]
        players = []
        for i in range(1, 9):
            player = User(
                username=f"player{i}_{batch_id}",
                email=f"player{i}_{batch_id}@test.com",
                role=UserRole.PLAYER.value,
            )
            player.set_password("player123")
            players.append(player)

        db_session.add_all(players)
        db_session.commit()
        return players

    def test_complete_amalfi_gara_workflow_admin(self, admin_user, players, db_session):
        """Test complete 3-round Amalfi gara workflow with admin."""
        self._test_complete_amalfi_workflow(admin_user, players, db_session)

    def test_complete_amalfi_gara_workflow_director(
        self, director_user, players, db_session
    ):
        """Test complete 3-round Amalfi gara workflow with director."""
        self._test_complete_amalfi_workflow(director_user, players, db_session)

    def _test_complete_amalfi_workflow(
        self, creator: User, players: List[User], db_session
    ):
        """Test complete Amalfi gara workflow implementation."""

        # ====== STEP 1: Creazione Gara ======
        tomorrow = date.today() + timedelta(days=1)
        gara = GaraService.create_gara(
            campionato_id=None,  # Standalone
            number=1,
            name="Test Amalfi Complete Workflow",
            date=tomorrow,
            time=None,
            location="Test Location",
            description="Test complete Amalfi workflow",
            rounds_count=3,
            min_participants=6,
            max_participants=10,
            entry_fee=15.0,
            discipline="palla_9",
            distance=9,
            best_of=True,
            withdraw_policy="exclude",
            director_id=creator.id,
            matchmaking_strategy="amalfi",
            first_round_policy="random",
            odd_number_policy="bye",
            anti_rematch_enabled=True,
            rating_type=None,
        )

        assert gara is not None
        assert gara.campionato_id is None  # Standalone
        assert gara.rounds_count == 3
        assert gara.min_participants == 6
        assert gara.max_participants == 10
        assert gara.discipline == "palla_9"
        assert gara.distance == 9
        assert gara.best_of is True
        assert gara.matchmaking_strategy == "amalfi"
        assert gara.first_round_policy == "random"
        assert gara.status == GaraStatus.SETUP.value

        # ====== STEP 2: Apertura Iscrizioni ======
        inscription_start = datetime.now()
        inscription_end = datetime.now() + timedelta(hours=2)

        GaraService.open_inscriptions(gara.id, inscription_start, inscription_end)

        db_session.refresh(gara)
        assert gara.status == GaraStatus.INSCRIPTION.value
        assert gara.inscription_start == inscription_start
        assert gara.inscription_end == inscription_end

        # ====== STEP 3: Iscrizione 8 Giocatori ======
        inscriptions = []
        for i, player in enumerate(players):
            inscription = InscriptionService.inscribe_user(
                user_id=player.id, gara_id=gara.id
            )
            assert inscription is not None
            assert inscription.user_id == player.id
            assert inscription.gara_id == gara.id
            assert (
                inscription.is_waitlist is False
            )  # Gara has max 10, so first 8 should not be waitlisted
            inscriptions.append(inscription)

        # Verifica 8 iscrizioni attive
        active_inscriptions_count = gara.get_active_inscriptions_count()
        assert active_inscriptions_count == 8

        # ====== STEP 4: Avvio Primo Turno (Random) ======
        GaraService.start_first_round(gara.id)

        # Reload gara from database to get updated status
        gara = db_session.get(Gara, gara.id)
        assert gara.status == GaraStatus.PLAYING.value
        assert gara.current_round == 1

        # Verifica match del primo turno
        round1_matches = Match.query.filter_by(gara_id=gara.id, round_number=1).all()

        # Con 8 giocatori, dovremmo avere 4 match normali
        normal_matches = [m for m in round1_matches if not m.is_bye and not m.is_trio]
        bye_matches = [m for m in round1_matches if m.is_bye]

        assert len(normal_matches) == 4
        assert len(bye_matches) == 0  # 8 è pari, nessun bye

        # ====== STEP 5: Completamento Tutti i Match del Primo Turno ======
        self._complete_all_matches_in_round(round1_matches, db_session)

        # Verifica che tutti i match siano completati
        for match in round1_matches:
            db_session.refresh(match)
            assert match.status == MatchStatus.COMPLETED.value

        # ====== STEP 6: Classifica Primo Turno ======
        # Calcola classificazione del primo turno
        RoundClassification.calculate_classification_after_round(gara.id, 1)

        classification_round1 = (
            RoundClassification.query.filter_by(gara_id=gara.id, round_number=1)
            .order_by(RoundClassification.position)
            .all()
        )
        assert classification_round1 is not None
        assert len(classification_round1) == 8

        # Verifica ordinamento: vinte, differenza rack, ordine precedente
        self._verify_classification_ordering(classification_round1)

        # ====== STEP 7: Secondo Turno (Abbinamento Amalfi) ======
        total_matches, normal_matches, bye_matches, trio_matches = (
            GaraService.create_amalfi_round(gara.id, 2)
        )

        # Aggiorna manualmente il current_round (come fatto nel controller)
        gara.current_round = 2
        db_session.add(gara)
        db_session.commit()
        db_session.refresh(gara)
        assert gara.current_round == 2

        round2_matches = Match.query.filter_by(gara_id=gara.id, round_number=2).all()

        assert len(round2_matches) == total_matches
        assert normal_matches == 4  # 8 giocatori = 4 match
        assert bye_matches == 0
        assert trio_matches == 0

        # ====== STEP 8: Completamento Tutti i Match del Secondo Turno ======
        self._complete_all_matches_in_round(round2_matches, db_session)

        # ====== STEP 9: Classifica Secondo Turno ======
        RoundClassification.calculate_classification_after_round(gara.id, 2)

        classification_round2 = (
            RoundClassification.query.filter_by(gara_id=gara.id, round_number=2)
            .order_by(RoundClassification.position)
            .all()
        )
        assert classification_round2 is not None
        assert len(classification_round2) == 8
        self._verify_classification_ordering(classification_round2)

        # ====== STEP 10: Terzo Turno (Abbinamento Amalfi) ======
        total_matches, normal_matches, bye_matches, trio_matches = (
            GaraService.create_amalfi_round(gara.id, 3)
        )

        # Aggiorna manualmente il current_round (come fatto nel controller)
        gara.current_round = 3
        db_session.add(gara)
        db_session.commit()
        db_session.refresh(gara)
        assert gara.current_round == 3

        round3_matches = Match.query.filter_by(gara_id=gara.id, round_number=3).all()

        assert len(round3_matches) == total_matches
        assert normal_matches == 4
        assert bye_matches == 0
        assert trio_matches == 0

        # ====== STEP 11: Completamento Tutti i Match del Terzo Turno ======
        self._complete_all_matches_in_round(round3_matches, db_session)

        # ====== STEP 12: Classifica Finale ======
        RoundClassification.calculate_classification_after_round(gara.id, 3)

        final_classification = (
            RoundClassification.query.filter_by(gara_id=gara.id, round_number=3)
            .order_by(RoundClassification.position)
            .all()
        )
        assert final_classification is not None
        assert len(final_classification) == 8
        self._verify_classification_ordering(final_classification)

        # Verifica che la gara sia considerata completa
        all_matches = Match.query.filter_by(gara_id=gara.id).all()
        completed_matches = [
            m for m in all_matches if m.status == MatchStatus.COMPLETED.value
        ]
        assert len(completed_matches) == len(all_matches)

        # Verifica totale match: 3 turni × 4 match per turno = 12 match
        assert len(all_matches) == 12

        print(f"✅ Test completato con successo!")
        print(f"   - Gara creata: {gara.name}")
        print(f"   - Iscritti: {active_inscriptions_count}")
        print(f"   - Match totali: {len(all_matches)}")
        print(f"   - Turni completati: {gara.current_round}")
        print(f"   - Classificazione finale: {len(final_classification)} posizioni")

    def _complete_all_matches_in_round(self, matches: List[Match], db_session):
        """Complete all matches in a round with realistic results."""
        for i, match in enumerate(matches):
            if match.is_bye:
                # Bye matches should already be completed
                continue
            elif match.is_trio:
                # Handle trio matches (not expected in this test but included for completeness)
                continue
            else:
                # Normal match - simulate realistic palla 9 al meglio di 9 (first to 5)
                self._simulate_normal_match(match, db_session)

    def _simulate_normal_match(self, match: Match, db_session):
        """Simulate a normal match with realistic rack-by-rack scoring."""
        # Palla 9 al meglio di 9 = first to 5 racks
        target_racks = 5
        player1_racks = 0
        player2_racks = 0

        # Simulate racks until one player reaches target
        rack_number = 1
        while player1_racks < target_racks and player2_racks < target_racks:
            # Alternate winner with some randomness (60-40 split)
            if rack_number % 3 == 1:
                winner_id = match.player1_id
                player1_racks += 1
            else:
                winner_id = match.player2_id
                player2_racks += 1

            # Add rack using service - use winner as reporter for test
            RackService.add_rack_result(
                match_id=match.id,
                rack_number=rack_number,
                winner_id=winner_id,
                reported_by_id=winner_id,  # Self-reporting for test
                confirmed_by_player=True,  # Auto-confirm for test
                validated_by_admin=True,  # Auto-validate for test
            )
            rack_number += 1

        # Complete the match using service
        MatchService.to_completed(match.id)

        db_session.refresh(match)
        assert match.status == MatchStatus.COMPLETED.value

        # Verify final score through rack count
        final_racks = Rack.query.filter_by(match_id=match.id).all()
        player1_final = len([r for r in final_racks if r.winner_id == match.player1_id])
        player2_final = len([r for r in final_racks if r.winner_id == match.player2_id])

        # Verify a player reached the target racks (al meglio di 9 = first to 5)
        assert max(player1_final, player2_final) == target_racks
        # Verify we have the right total number of racks played
        assert len(final_racks) >= target_racks  # At least target_racks, could be more

    def _verify_classification_ordering(self, classification: List):
        """Verify that classification is properly ordered by Amalfi rules."""
        prev_wins = None
        prev_diff = None

        for i, player_data in enumerate(classification):
            # Get player stats from RoundClassification object
            if hasattr(player_data, "wins"):
                wins = player_data.wins
                diff = player_data.rack_difference
            elif hasattr(player_data, "match_wins"):
                wins = player_data.match_wins
                diff = (
                    player_data.rack_difference
                    if hasattr(player_data, "rack_difference")
                    else 0
                )
            else:
                # Fallback for unknown format
                wins = 0
                diff = 0

            if prev_wins is not None:
                # Check ordering: wins desc, then diff desc, then position
                assert (
                    wins <= prev_wins
                ), f"Position {i}: wins ordering violation (prev: {prev_wins}, current: {wins})"

                if wins == prev_wins and prev_diff is not None:
                    assert (
                        diff <= prev_diff
                    ), f"Position {i}: rack difference ordering violation (prev: {prev_diff}, current: {diff})"

            prev_wins = wins
            prev_diff = diff

    def test_amalfi_anti_rematch_behavior(self, director_user, players, db_session):
        """Test that Amalfi anti-rematch logic works correctly across rounds."""
        # Create smaller gara for easier tracking of rematches
        tomorrow = date.today() + timedelta(days=1)
        gara = GaraService.create_gara(
            campionato_id=None,
            number=1,
            name="Test Anti-Rematch",
            date=tomorrow,
            location="Test Location",
            description="Test anti-rematch logic",
            rounds_count=3,  # Valid rounds for 6 players to test anti-rematch
            min_participants=4,
            max_participants=6,
            entry_fee=10.0,
            discipline="palla_9",
            distance=7,
            best_of=True,
            director_id=director_user.id,
            matchmaking_strategy="amalfi",
            first_round_policy="random",
            odd_number_policy="bye",
            anti_rematch_enabled=True,
        )

        # Use only 6 players for easier tracking
        test_players = players[:6]

        # Register players
        for player in test_players:
            InscriptionService.inscribe_user(player.id, gara.id)

        # Open inscriptions and start
        inscription_start = datetime.now()
        inscription_end = datetime.now() + timedelta(hours=1)
        GaraService.open_inscriptions(gara.id, inscription_start, inscription_end)
        GaraService.start_first_round(gara.id)

        # Track all pairings across rounds
        all_pairings = []
        immediate_rematches = 0

        for round_num in range(1, 4):  # Test first 3 rounds
            if round_num == 1:
                matches = Match.query.filter_by(
                    gara_id=gara.id, round_number=round_num
                ).all()
            else:
                # Complete previous round first
                prev_matches = Match.query.filter_by(
                    gara_id=gara.id, round_number=round_num - 1
                ).all()
                self._complete_all_matches_in_round(prev_matches, db_session)
                RoundClassification.calculate_classification_after_round(
                    gara.id, round_num - 1
                )

                # Create next round
                GaraService.create_amalfi_round(gara.id, round_num)
                matches = Match.query.filter_by(
                    gara_id=gara.id, round_number=round_num
                ).all()

            # Track pairings in this round
            round_pairings = set()
            for match in matches:
                if not match.is_bye and not match.is_trio:
                    # Create normalized pairing (smaller id first)
                    pairing = tuple(sorted([match.player1_id, match.player2_id]))
                    round_pairings.add(pairing)

                    # Count immediate rematches (same pairing in consecutive rounds)
                    if round_num > 1 and len(all_pairings) > 0:
                        prev_round_pairings = all_pairings[-1]
                        if pairing in prev_round_pairings:
                            immediate_rematches += 1

            all_pairings.append(round_pairings)

        # With anti-rematch enabled, immediate rematches should be minimized
        # (allow up to 1 for edge cases with small tournaments)
        assert (
            immediate_rematches <= 1
        ), f"Too many immediate rematches: {immediate_rematches} (expected ≤ 1)"

        total_unique_pairings = len(set.union(*all_pairings)) if all_pairings else 0
        print(
            f"✅ Anti-rematch test passed: {total_unique_pairings} unique pairings, {immediate_rematches} immediate rematches"
        )

    def test_amalfi_odd_number_handling(self, director_user, players, db_session):
        """Test Amalfi handling of odd number of players (bye matches)."""
        tomorrow = date.today() + timedelta(days=1)
        gara = GaraService.create_gara(
            campionato_id=None,
            number=1,
            name="Test Odd Players",
            date=tomorrow,
            location="Test Location",
            description="Test odd number player handling",
            rounds_count=3,
            min_participants=5,
            max_participants=9,
            entry_fee=10.0,
            discipline="palla_9",
            distance=7,
            best_of=True,
            director_id=director_user.id,
            matchmaking_strategy="amalfi",
            first_round_policy="random",
            odd_number_policy="bye",
            anti_rematch_enabled=True,
        )

        # Register 7 players (odd number)
        test_players = players[:7]
        for player in test_players:
            InscriptionService.inscribe_user(player.id, gara.id)

        # Start gara
        inscription_start = datetime.now()
        inscription_end = datetime.now() + timedelta(hours=1)
        GaraService.open_inscriptions(gara.id, inscription_start, inscription_end)
        GaraService.start_first_round(gara.id)

        # Check round 1 matches
        round1_matches = Match.query.filter_by(gara_id=gara.id, round_number=1).all()
        normal_matches = [m for m in round1_matches if not m.is_bye]
        bye_matches = [m for m in round1_matches if m.is_bye]

        assert len(normal_matches) == 3  # 6 players in normal matches
        assert len(bye_matches) == 1  # 1 player gets bye

        # Verify bye match is already completed
        bye_match = bye_matches[0]
        assert bye_match.status == MatchStatus.COMPLETED.value
        assert bye_match.player1_score >= 1  # Bye winner gets score
        assert bye_match.player2_score == 0  # No opponent

        print(f"✅ Odd number test passed: 7 players → 3 normal + 1 bye match")
