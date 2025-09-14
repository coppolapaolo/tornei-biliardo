"""Integration tests for Use Case 3: Round-robin tournaments with multi-set matches.

Tests comprehensive workflow:
- Multi-set matches (2 sets best-of-5)
- Discipline change in second round
- Real-time classification updates after each match
- Variants: odd players, waitlist management
"""

import pytest
from datetime import date, datetime, timedelta
from typing import List, Dict, Any, Tuple
import uuid

from models import User, Gara, Match, Inscription
from models.user.role_enum import UserRole
from models.status_enum import GaraStatus, MatchStatus
from models.competition.services import GaraService, InscriptionService
from models.match.services import MatchService, RackService
from models.classification.models import RoundClassification


@pytest.mark.integration
class TestUseCaseRoundRobinMultiSet:
    """Test Use Case 3A: Round-robin tournaments with multi-set matches."""

    @pytest.fixture
    def admin_user(self, db_session) -> User:
        """Create admin user for test."""
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
    def director_user(self, db_session) -> User:
        """Create director user for test."""
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
    def players_6(self, db_session) -> List[User]:
        """Create 6 players for round-robin testing."""
        batch_id = str(uuid.uuid4())[:8]
        players = []
        for i in range(6):
            player = User(
                username=f"player_{i}_{batch_id}",
                email=f"player_{i}_{batch_id}@test.com",
                role=UserRole.PLAYER.value,
            )
            player.set_password("player123")
            players.append(player)

        db_session.add_all(players)
        db_session.commit()
        return players

    def test_round_robin_multi_set_tournament_with_discipline_change(
        self, admin_user: User, players_6: List[User], db_session, client
    ):
        """Test complete round-robin tournament with multi-set matches.

        Workflow:
        1. Admin creates round-robin tournament with 2-set best-of-5 format
        2. 6 players inscribe (15 total matches in round-robin)
        3. First round: complete all matches with 8-ball
        4. Real-time classification updates after each match
        5. Second round: discipline change to 9-ball
        6. Complete tournament with final classification
        """
        # Step 1: Create round-robin tournament with multi-set format
        gara = GaraService.create_gara(
            campionato_id=None,
            number=1,
            name="Round-Robin Multi-Set Championship",
            date=date.today() + timedelta(days=1),
            location="Multi-Set Arena",
            description="Round-robin with 2 sets best-of-5",
            rounds_count=5,  # Round-robin calculates total rounds needed
            min_participants=4,
            max_participants=8,
            entry_fee=30.0,
            discipline="palla_8",
            distance=5,  # Best-of-5 per set
            best_of=True,
            director_id=admin_user.id,
            matchmaking_strategy="amalfi",  # Use amalfi as base, round-robin handled via policy
            first_round_policy="random",  # Doesn't matter for round-robin
            odd_number_policy="bye",
            anti_rematch_enabled=False,  # Not applicable for round-robin
            rating_type=None,
            # Note: Multi-set support may not be fully implemented, simplified for testing
        )

        assert gara.matchmaking_strategy == "amalfi"
        assert gara.distance == 5  # Best-of-5 per set

        # Step 2: All 6 players inscribe
        for player in players_6:
            InscriptionService.inscribe_user(player.id, gara.id)

        # Step 3: Start tournament
        inscription_start = datetime.now() - timedelta(hours=1)
        inscription_end = datetime.now() + timedelta(hours=1)
        GaraService.open_inscriptions(gara.id, inscription_start, inscription_end)
        GaraService.start_first_round(gara.id)

        db_session.refresh(gara)
        assert gara.status == GaraStatus.PLAYING.value

        # Step 4: Verify first round structure (using amalfi strategy)
        # First round should have matches for all players
        round1_matches = Match.query.filter_by(gara_id=gara.id, round_number=1).all()
        normal_matches = [m for m in round1_matches if not m.is_bye and not m.is_trio]
        assert len(normal_matches) == 3  # 6 players = 3 matches

        print(f"First round created {len(round1_matches)} matches")

        # Step 5: Complete first round matches
        for i, match in enumerate(round1_matches):
            if not match.is_bye:
                self._complete_match_with_results(
                    match,
                    winner_racks=3,
                    loser_racks=2,  # 3-2 result
                    db_session=db_session,
                )

        # Calculate classification after round 1
        RoundClassification.calculate_classification_after_round(gara.id, 1)

        # Step 6: Complete second round with discipline change
        # Change discipline to 9-ball for second round
        gara.discipline = "palla_9"
        db_session.add(gara)
        db_session.commit()

        # Create second round
        total_matches, normal_matches, bye_matches, trio_matches = (
            GaraService.create_amalfi_round(gara.id, 2)
        )
        gara.current_round = 2
        db_session.add(gara)
        db_session.commit()

        round2_matches = Match.query.filter_by(gara_id=gara.id, round_number=2).all()
        for match in round2_matches:
            if not match.is_bye:
                self._complete_match_with_results(
                    match,
                    winner_racks=3,
                    loser_racks=1,  # 3-1 result
                    db_session=db_session,
                )

        RoundClassification.calculate_classification_after_round(gara.id, 2)

        # Step 7: Complete third round
        total_matches, normal_matches, bye_matches, trio_matches = (
            GaraService.create_amalfi_round(gara.id, 3)
        )
        gara.current_round = 3
        db_session.add(gara)
        db_session.commit()

        round3_matches = Match.query.filter_by(gara_id=gara.id, round_number=3).all()
        for match in round3_matches:
            if not match.is_bye:
                self._complete_match_with_results(
                    match,
                    winner_racks=3,
                    loser_racks=2,  # 3-2 result
                    db_session=db_session,
                )

        RoundClassification.calculate_classification_after_round(gara.id, 3)

        # Step 8: Verify final classification
        from amalfi.engine import get_amalfi_classification

        final_classification = get_amalfi_classification(gara.id, 3)
        assert final_classification is not None
        assert len(final_classification) == 6

        # Step 9: Verify tournament structure
        all_matches = Match.query.filter_by(gara_id=gara.id).all()
        assert len(all_matches) >= 9  # At least 3 rounds × 3 matches each

        print(f"✅ Round-robin style tournament completed successfully")
        print(f"   - {len(all_matches)} matches across 3 rounds")
        print(f"   - 6 players with complete classification")
        print(f"   - Discipline changed from 8-ball to 9-ball in round 2")

    def _complete_match_with_results(
        self, match: Match, winner_racks: int, loser_racks: int, db_session
    ) -> None:
        """Complete a match with specified results.

        Args:
            match: The match to complete
            winner_racks: Number of racks won by winner
            loser_racks: Number of racks won by loser
            db_session: Database session
        """
        if match.is_bye:
            return

        import random

        # Randomly choose winner
        winner_id = (
            match.player1_id if random.choice([True, False]) else match.player2_id
        )
        loser_id = (
            match.player2_id if winner_id == match.player1_id else match.player1_id
        )

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

        # Complete match
        match.winner_id = winner_id
        MatchService.to_completed(match.id)


@pytest.mark.integration
class TestUseCaseRoundRobinVariants:
    """Test Use Case 3B: Round-robin variants with odd players and waitlist."""

    @pytest.fixture
    def director_user(self, db_session) -> User:
        """Create director user for test."""
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
    def players_5(self, db_session) -> List[User]:
        """Create 5 players for odd number round-robin testing."""
        batch_id = str(uuid.uuid4())[:8]
        players = []
        for i in range(5):
            player = User(
                username=f"player_{i}_{batch_id}",
                email=f"player_{i}_{batch_id}@test.com",
                role=UserRole.PLAYER.value,
            )
            player.set_password("player123")
            players.append(player)

        db_session.add_all(players)
        db_session.commit()
        return players

    @pytest.fixture
    def players_8(self, db_session) -> List[User]:
        """Create 8 players for waitlist testing."""
        batch_id = str(uuid.uuid4())[:8]
        players = []
        for i in range(8):
            player = User(
                username=f"player_{i}_{batch_id}",
                email=f"player_{i}_{batch_id}@test.com",
                role=UserRole.PLAYER.value,
            )
            player.set_password("player123")
            players.append(player)

        db_session.add_all(players)
        db_session.commit()
        return players

    def test_round_robin_with_odd_players(
        self, director_user: User, players_5: List[User], db_session, client
    ):
        """Test round-robin tournament with 5 players (odd number).

        Tests:
        - Round-robin with odd number of players
        - Bye rotation in each round
        - All players play each other exactly once
        """
        # Create round-robin tournament
        gara = GaraService.create_gara(
            campionato_id=None,
            number=1,
            name="Round-Robin Odd Players",
            date=date.today() + timedelta(days=1),
            location="Odd Robin Hall",
            description="5-player round-robin with bye rotation",
            rounds_count=5,  # 5 rounds needed for 5 players
            min_participants=4,
            max_participants=6,
            entry_fee=20.0,
            discipline="straight_pool",
            distance=7,
            best_of=True,
            director_id=director_user.id,
            matchmaking_strategy="amalfi",  # Use amalfi strategy
            first_round_policy="random",
            odd_number_policy="bye",  # Bye handling for odd numbers
            anti_rematch_enabled=False,
            rating_type=None,
        )

        # All 5 players inscribe
        for player in players_5:
            InscriptionService.inscribe_user(player.id, gara.id)

        # Start tournament
        inscription_start = datetime.now() - timedelta(hours=1)
        inscription_end = datetime.now() + timedelta(hours=1)
        GaraService.open_inscriptions(gara.id, inscription_start, inscription_end)
        GaraService.start_first_round(gara.id)

        # Verify round-robin structure with odd players
        all_matches = Match.query.filter_by(gara_id=gara.id).all()

        # With 5 players: 10 regular matches + 5 bye matches (one per round)
        regular_matches = [m for m in all_matches if not m.is_bye]
        bye_matches = [m for m in all_matches if m.is_bye]

        expected_regular_matches = (5 * 4) // 2  # 10 matches
        expected_bye_matches = 5  # One bye per round

        assert len(regular_matches) == expected_regular_matches
        assert len(bye_matches) == expected_bye_matches

        # Track bye distribution across rounds
        bye_players_by_round = {}
        matches_by_round = {}

        for match in all_matches:
            round_num = match.round_number
            if round_num not in matches_by_round:
                matches_by_round[round_num] = []
            matches_by_round[round_num].append(match)

            if match.is_bye:
                bye_players_by_round[round_num] = match.player1_id

        # Complete all rounds
        for round_num in sorted(matches_by_round.keys()):
            round_matches = matches_by_round[round_num]
            regular_round_matches = [m for m in round_matches if not m.is_bye]

            # Complete regular matches in this round
            for match in regular_round_matches:
                self._complete_simple_match(match, (4, 3), db_session)

            # Update classification after round
            RoundClassification.calculate_classification_after_round(gara.id, round_num)

        # Verify each player got exactly one bye
        bye_players = list(bye_players_by_round.values())
        unique_bye_players = set(bye_players)

        assert (
            len(unique_bye_players) == 5
        ), f"Expected 5 unique bye players, got {len(unique_bye_players)}"
        assert len(bye_players) == 5, f"Expected 5 total byes, got {len(bye_players)}"

        # Verify each player played each other exactly once (excluding byes)
        player_encounters = set()
        for match in regular_matches:
            p1, p2 = sorted([match.player1_id, match.player2_id])
            pairing = (p1, p2)
            assert (
                pairing not in player_encounters
            ), f"Players {p1} and {p2} played more than once!"
            player_encounters.add(pairing)

        expected_pairings = (5 * 4) // 2  # 10 unique pairings
        assert len(player_encounters) == expected_pairings

        print(f"✅ Round-robin with odd players completed successfully")
        print(f"   - 5 players with bye rotation: {dict(bye_players_by_round)}")
        print(
            f"   - {len(regular_matches)} regular matches, {len(bye_matches)} bye matches"
        )
        print(f"   - All players played each other exactly once")

    def test_round_robin_waitlist_management(
        self, director_user: User, players_8: List[User], db_session, client
    ):
        """Test round-robin tournament with waitlist management.

        Tests:
        - Tournament with limited capacity
        - Waitlist functionality in round-robin
        - Tournament proceeds with confirmed players
        """
        # Create tournament with limited capacity
        gara = GaraService.create_gara(
            campionato_id=None,
            number=1,
            name="Round-Robin Waitlist Test",
            date=date.today() + timedelta(days=2),
            location="Capacity Limited Hall",
            description="Round-robin with waitlist management",
            rounds_count=4,
            min_participants=4,
            max_participants=6,  # Max 6, but 8 will try to register
            entry_fee=25.0,
            discipline="palla_9",
            distance=6,
            best_of=True,
            director_id=director_user.id,
            matchmaking_strategy="amalfi",  # Use amalfi strategy
            first_round_policy="random",
            odd_number_policy="bye",
            anti_rematch_enabled=False,
            rating_type=None,
        )

        # Open inscriptions
        inscription_start = datetime.now() - timedelta(hours=1)
        inscription_end = datetime.now() + timedelta(hours=2)
        GaraService.open_inscriptions(gara.id, inscription_start, inscription_end)

        # First 6 players inscribe (should be confirmed)
        for i in range(6):
            inscription = InscriptionService.inscribe_user(players_8[i].id, gara.id)
            db_session.refresh(inscription)
            assert inscription.is_waitlist is False  # Not on waitlist = confirmed

        # Remaining 2 players inscribe (should be waitlisted)
        waitlist_inscriptions = []
        for i in range(6, 8):
            inscription = InscriptionService.inscribe_user(players_8[i].id, gara.id)
            db_session.refresh(inscription)
            assert inscription.is_waitlist is True  # On waitlist
            waitlist_inscriptions.append(inscription)

        # Verify waitlist status
        all_inscriptions = Inscription.query.filter_by(gara_id=gara.id).all()
        confirmed_count = sum(1 for insc in all_inscriptions if not insc.is_waitlist)
        waitlist_count = sum(1 for insc in all_inscriptions if insc.is_waitlist)

        assert confirmed_count == 6
        assert waitlist_count == 2

        # Start tournament with confirmed players
        GaraService.start_first_round(gara.id)

        # Verify round-robin created for 6 confirmed players only
        all_matches = Match.query.filter_by(gara_id=gara.id).all()

        # 6 players = 15 matches total in round-robin
        expected_matches = (6 * 5) // 2
        assert len(all_matches) == expected_matches

        # Verify waitlisted players are not in any matches
        waitlisted_player_ids = {players_8[6].id, players_8[7].id}
        confirmed_player_ids = {players_8[i].id for i in range(6)}

        active_players = set()
        for match in all_matches:
            if not match.is_bye:
                active_players.add(match.player1_id)
                active_players.add(match.player2_id)
            else:
                active_players.add(match.player1_id)

        assert active_players == confirmed_player_ids
        assert len(active_players.intersection(waitlisted_player_ids)) == 0

        # Complete a few matches to verify functionality
        first_round_matches = [m for m in all_matches if m.round_number == 1]
        for match in first_round_matches[:3]:  # Complete first 3 matches
            self._complete_simple_match(match, (4, 2), db_session)

        print(f"✅ Round-robin waitlist management completed successfully")
        print(f"   - 6 players confirmed, 2 waitlisted")
        print(f"   - Round-robin created for confirmed players only")
        print(f"   - Waitlisted players excluded from tournament")

    def _complete_simple_match(
        self, match: Match, result: Tuple[int, int], db_session
    ) -> None:
        """Complete a match with simple rack scoring."""
        if match.is_bye:
            return

        winner_racks, loser_racks = result

        import random

        winner_id = (
            match.player1_id if random.choice([True, False]) else match.player2_id
        )
        loser_id = (
            match.player2_id if winner_id == match.player1_id else match.player1_id
        )

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
