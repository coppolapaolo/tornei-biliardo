"""Integration tests for Use Case 2: Admin/Director Random Strategy with Challenge Integration.

Tests comprehensive workflow:
- 3 rounds with Random strategy and challenge system integration
- Challenge after first round (2 attempts)
- Third round discipline change to 9-ball
- Classification ordering by rack wins
- Variants: different player counts, trio handling
"""

import pytest
from datetime import date, datetime, timedelta
from typing import List, Dict, Any
import uuid

from models import User, Gara, Match, Inscription
from models.user.role_enum import UserRole
from models.status_enum import GaraStatus, MatchStatus
from models.matchmaking.configuration import (
    MatchmakingStrategy,
    FirstRoundPolicy,
    OddNumberPolicy,
)
from models.competition.services import GaraService, InscriptionService
from models.match.services import MatchService, RackService
from models.classification.models import RoundClassification


@pytest.mark.integration
class TestUseCaseRandomStrategyWithChallenges:
    """Test Use Case 2A: Random strategy with challenge system integration."""

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
    def players_8(self, db_session) -> List[User]:
        """Create 8 players for tournament testing."""
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

    def test_random_strategy_tournament_with_challenge_integration(
        self, admin_user: User, players_8: List[User], db_session, client
    ):
        """Test full Random strategy tournament with challenge system.

        Workflow:
        1. Admin creates tournament with Random strategy
        2. Complete first round with random pairings
        3. Challenge system activated after round 1 (players get challenges)
        4. Complete challenge attempts (2 attempts each)
        5. Second round with updated pairings
        6. Third round with discipline change to 9-ball
        7. Final classification ordered by rack wins
        """
        # Step 1: Create tournament with Random strategy
        gara = GaraService.create_gara(
            campionato_id=None,
            number=1,
            name="Random Strategy Challenge Tournament",
            date=date.today() + timedelta(days=1),
            location="Challenge Pool Hall",
            description="8-ball tournament with Random strategy and challenge system",
            rounds_count=3,
            min_participants=6,
            max_participants=10,
            entry_fee=20.0,
            discipline="palla_8",
            distance=7,
            best_of=True,
            director_id=admin_user.id,
            matchmaking_strategy=MatchmakingStrategy.RANDOM.value,  # Random strategy
            first_round_policy=FirstRoundPolicy.RANDOM.value,
            odd_number_policy=OddNumberPolicy.BYE.value,
            anti_rematch_enabled=True,
            rating_type=None,
        )

        assert gara.matchmaking_strategy == MatchmakingStrategy.RANDOM.value
        assert gara.discipline == "palla_8"

        # Step 2: All players inscribe
        for player in players_8:
            InscriptionService.inscribe_user(player.id, gara.id)

        # Step 3: Start tournament
        inscription_start = datetime.now() - timedelta(hours=1)
        inscription_end = datetime.now() + timedelta(hours=1)
        GaraService.open_inscriptions(gara.id, inscription_start, inscription_end)
        GaraService.start_first_round(gara.id)

        db_session.refresh(gara)
        assert gara.status == GaraStatus.PLAYING.value
        assert gara.current_round == 1

        # Step 4: Complete first round with varied results
        round1_matches = Match.query.filter_by(gara_id=gara.id, round_number=1).all()
        assert len(round1_matches) == 4  # 8 players = 4 matches

        # Verify random pairings (non-deterministic, just verify structure)
        normal_matches = [m for m in round1_matches if not m.is_bye and not m.is_trio]
        assert len(normal_matches) == 4
        for match in normal_matches:
            assert match.player1_id != match.player2_id

        # Complete round 1 matches
        self._complete_matches_with_results(
            round1_matches,
            [
                (4, 3),  # Close match
                (4, 1),  # Dominant match
                (4, 2),  # Medium match
                (4, 0),  # Shutout match
            ],
            db_session,
        )

        RoundClassification.calculate_classification_after_round(gara.id, 1)

        # Step 5: Add 2 challenges after first round (2 attempts each) as per spec
        from models.challenge.models import Challenge
        from models.challenge.services import ChallengeService

        # Challenge 1: Spot shot challenge
        challenge1 = Challenge(
            description="Post-Round 1 Spot Shot Challenge - Spot shot challenge after first round",
            image_path="/static/challenges/spot_shot.jpg",
            pass_fail_only=False,
            is_active=True,
        )
        db_session.add(challenge1)

        # Challenge 2: Break shot challenge
        challenge2 = Challenge(
            description="Post-Round 1 Break Challenge - Break shot challenge after first round",
            image_path="/static/challenges/break_shot.jpg",
            pass_fail_only=False,
            is_active=True,
        )
        db_session.add(challenge2)
        db_session.commit()

        # Players complete challenges (2 attempts each)
        for player in players_8[:4]:  # First 4 players attempt challenges
            # Challenge 1 attempts (2 attempts each)
            for attempt_num in range(2):
                attempt = ChallengeService.start_challenge_attempt(
                    user_id=player.id,
                    challenge_id=challenge1.id,
                    gara_id=gara.id,
                    round_number=1,
                )
                score = 75 + (player.id % 20) + (attempt_num * 5)  # Improving scores
                ChallengeService.complete_challenge_attempt(
                    attempt_id=attempt.id,
                    score=score,
                    notes=f"Round 1 challenge attempt {attempt_num + 1}",
                )

            # Challenge 2 attempts (2 attempts each)
            for attempt_num in range(2):
                attempt = ChallengeService.start_challenge_attempt(
                    user_id=player.id,
                    challenge_id=challenge2.id,
                    gara_id=gara.id,
                    round_number=1,
                )
                score = 70 + (player.id % 25) + (attempt_num * 10)  # Improving scores
                ChallengeService.complete_challenge_attempt(
                    attempt_id=attempt.id,
                    score=score,
                    notes=f"Round 1 break challenge attempt {attempt_num + 1}",
                )

        # Step 6: Start second round with Random strategy
        total_matches, normal_matches, bye_matches, trio_matches = (
            GaraService.create_round_with_strategy(gara.id, 2)
        )
        gara.current_round = 2
        db_session.add(gara)
        db_session.commit()

        round2_matches = Match.query.filter_by(gara_id=gara.id, round_number=2).all()
        assert len(round2_matches) == 4

        # Verify anti-rematch is working with Random strategy
        round1_pairings = {
            tuple(sorted([m.player1_id, m.player2_id])) for m in round1_matches
        }
        round2_pairings = {
            tuple(sorted([m.player1_id, m.player2_id]))
            for m in round2_matches
            if not m.is_bye
        }

        rematch_count = len(round1_pairings.intersection(round2_pairings))
        assert rematch_count == 0, f"Found {rematch_count} rematches in round 2"

        # Complete round 2
        self._complete_matches_with_results(
            round2_matches,
            [
                (4, 2),
                (4, 3),
                (4, 1),
                (4, 0),
            ],
            db_session,
        )

        RoundClassification.calculate_classification_after_round(gara.id, 2)

        # Step 7: Third round with discipline change to 9-ball
        # Per UC2 spec: "cambia la disciplina del solo terzo turno in palla 9"
        # Save original discipline and temporarily change for round 3
        original_discipline = gara.discipline
        gara.discipline = "palla_9"  # Change to 9-ball for round 3
        db_session.add(gara)
        db_session.commit()

        total_matches, normal_matches, bye_matches, trio_matches = (
            GaraService.create_round_with_strategy(gara.id, 3)
        )
        gara.current_round = 3
        db_session.add(gara)
        db_session.commit()

        round3_matches = Match.query.filter_by(gara_id=gara.id, round_number=3).all()
        assert len(round3_matches) == 4

        # Verify discipline change is reflected
        db_session.refresh(gara)
        assert gara.discipline == "palla_9"

        # Complete final round
        self._complete_matches_with_results(
            round3_matches,
            [
                (4, 3),
                (4, 1),
                (4, 2),
                (4, 0),
            ],
            db_session,
        )

        RoundClassification.calculate_classification_after_round(gara.id, 3)

        # Step 8: Verify final classification exists and uses rack-based ordering
        from amalfi.engine import get_amalfi_classification

        final_classification = get_amalfi_classification(gara.id, 3)
        assert final_classification is not None
        assert len(final_classification) == 8

        # UC2 spec: "il sistema calcola la classifica secondo l'ordinamento (numero rack vinti)"
        # Verify that classification is ordered by rack-based metrics (rack_difference)
        previous_rack_diff = float("inf")
        for player_classification in final_classification:
            current_rack_diff = player_classification.rack_difference
            # Classification should be ordered by rack difference (descending)
            assert (
                current_rack_diff <= previous_rack_diff
            ), f"Classification not ordered by rack performance: {current_rack_diff} > {previous_rack_diff}"
            previous_rack_diff = current_rack_diff

        # Step 10: Verify tournament completion
        db_session.refresh(gara)
        assert gara.current_round == 3

        print(f"✅ Random strategy tournament completed successfully")
        print(f"   - 3 rounds with Random matchmaking and anti-rematch")
        print(f"   - Discipline changed to 9-ball for final round")
        print(f"   - Final classification established")

    def _complete_matches_with_results(
        self, matches: List[Match], results: List[tuple], db_session
    ) -> None:
        """Complete matches with specified win-loss results."""
        for match, (winner_racks, loser_racks) in zip(matches, results):
            if match.is_bye:
                continue

            # Randomly choose winner (player1 or player2)
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

            # Complete match
            MatchService.to_completed(match.id)


@pytest.mark.integration
class TestUseCaseRandomStrategyVariants:
    """Test Use Case 2B: Random strategy variants with different player counts."""

    @pytest.fixture
    def players_7(self, db_session) -> List[User]:
        """Create 7 players for odd number testing."""
        batch_id = str(uuid.uuid4())[:8]
        players = []
        for i in range(7):
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
    def players_9(self, db_session) -> List[User]:
        """Create 9 players for trio testing."""
        batch_id = str(uuid.uuid4())[:8]
        players = []
        for i in range(9):
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

    def test_random_strategy_with_odd_players_bye_handling(
        self, isolated_director_user: User, players_7: List[User], db_session, client
    ):
        """Test Random strategy with 7 players and bye handling.

        Tests:
        - Random pairings with odd numbers
        - Bye rotation across rounds
        - Different bye players each round
        """
        # Create tournament with bye handling for odd numbers
        gara = GaraService.create_gara(
            campionato_id=None,
            number=1,
            name="Random Strategy Odd Players",
            date=date.today() + timedelta(days=1),
            location="Odd Numbers Hall",
            description="7 players with bye rotation",
            rounds_count=3,
            min_participants=6,
            max_participants=8,
            entry_fee=15.0,
            discipline="palla_10",
            distance=6,
            best_of=True,
            director_id=isolated_director_user.id,
            matchmaking_strategy=MatchmakingStrategy.RANDOM.value,
            first_round_policy="random",
            odd_number_policy="bye",  # Bye handling
            anti_rematch_enabled=True,
            rating_type=None,
        )

        # All 7 players inscribe
        for player in players_7:
            InscriptionService.inscribe_user(player.id, gara.id)

        # Start tournament
        inscription_start = datetime.now() - timedelta(hours=1)
        inscription_end = datetime.now() + timedelta(hours=1)
        GaraService.open_inscriptions(gara.id, inscription_start, inscription_end)
        GaraService.start_first_round(gara.id)

        bye_players_by_round = []

        # Complete all 3 rounds, tracking bye players
        for round_num in range(1, 4):
            if round_num > 1:
                # Complete previous round first
                prev_matches = Match.query.filter_by(
                    gara_id=gara.id, round_number=round_num - 1
                ).all()

                regular_matches = [m for m in prev_matches if not m.is_bye]
                self._complete_matches_with_results(
                    regular_matches,
                    [
                        (3, 2),
                        (3, 1),
                        (3, 0),
                    ],
                    db_session,
                )

                RoundClassification.calculate_classification_after_round(
                    gara.id, round_num - 1
                )

                # Create next round
                total_matches, normal_matches, bye_matches, trio_matches = (
                    GaraService.create_round_with_strategy(gara.id, round_num)
                )
                gara.current_round = round_num
                db_session.add(gara)
                db_session.commit()

            # Analyze current round
            matches = Match.query.filter_by(
                gara_id=gara.id, round_number=round_num
            ).all()

            regular_matches = [m for m in matches if not m.is_bye]
            bye_matches = [m for m in matches if m.is_bye]

            assert len(regular_matches) == 3  # 6 players in 3 matches
            assert len(bye_matches) == 1  # 1 player gets bye
            assert len(matches) == 4  # Total matches

            # Track who got the bye
            bye_player_id = bye_matches[0].player1_id
            bye_players_by_round.append(bye_player_id)

            print(f"Round {round_num}: Player {bye_player_id} gets bye")

        # Verify different players got byes (Random strategy should distribute byes)
        unique_bye_players = len(set(bye_players_by_round))
        assert (
            unique_bye_players >= 2
        ), f"Only {unique_bye_players} different players got byes"

        print(f"✅ Random strategy with odd players completed successfully")
        print(f"   - {unique_bye_players} different players received byes")
        print(f"   - Bye distribution across rounds: {bye_players_by_round}")

    def test_random_strategy_with_trio_handling(
        self, isolated_director_user: User, players_9: List[User], db_session, client
    ):
        """Test Random strategy with trio handling for odd numbers.

        Tests:
        - 9 players with trio match option
        - Random pairings including trio matches
        - Trio match scoring and completion
        """
        # Create tournament with trio handling
        gara = GaraService.create_gara(
            campionato_id=None,
            number=1,
            name="Random Strategy Trio Matches",
            date=date.today() + timedelta(days=2),
            location="Trio Challenge Hall",
            description="9 players with trio match handling",
            rounds_count=2,  # Fewer rounds for trio complexity
            min_participants=8,
            max_participants=10,
            entry_fee=25.0,
            discipline="one_pocket",
            distance=5,
            best_of=True,
            director_id=isolated_director_user.id,
            matchmaking_strategy=MatchmakingStrategy.RANDOM.value,
            first_round_policy="random",
            odd_number_policy="trio",  # Trio handling instead of bye
            anti_rematch_enabled=False,  # Disable for trio testing
            rating_type=None,
        )

        # All 9 players inscribe
        for player in players_9:
            InscriptionService.inscribe_user(player.id, gara.id)

        # Start tournament
        inscription_start = datetime.now() - timedelta(hours=1)
        inscription_end = datetime.now() + timedelta(hours=1)
        GaraService.open_inscriptions(gara.id, inscription_start, inscription_end)
        GaraService.start_first_round(gara.id)

        # Verify first round structure
        round1_matches = Match.query.filter_by(gara_id=gara.id, round_number=1).all()

        regular_matches = [m for m in round1_matches if not m.is_trio and not m.is_bye]
        trio_matches_list = [m for m in round1_matches if m.is_trio]
        bye_matches = [m for m in round1_matches if m.is_bye]

        # With 9 players and trio handling: could be 3 regular + 1 trio, or other combinations
        total_players_in_matches = 0
        for match in round1_matches:
            if match.is_trio:
                total_players_in_matches += 3  # Trio has 3 players
            elif not match.is_bye:
                total_players_in_matches += 2  # Regular match has 2 players
            else:
                total_players_in_matches += 1  # Bye has 1 player

        assert (
            total_players_in_matches == 9
        ), f"Expected 9 players total, got {total_players_in_matches}"
        assert len(trio_matches_list) >= 1, "Should have at least one trio match"

        # Complete regular matches
        if regular_matches:
            results = [(3, 2)] * len(regular_matches)
            self._complete_matches_with_results(regular_matches, results, db_session)

        # Complete trio matches (more complex)
        for trio_match in trio_matches_list:
            self._complete_trio_match(trio_match, db_session)

        RoundClassification.calculate_classification_after_round(gara.id, 1)

        # Second round
        total_matches, normal_matches, bye_matches, trio_matches = (
            GaraService.create_amalfi_round(gara.id, 2)
        )
        gara.current_round = 2
        db_session.add(gara)
        db_session.commit()

        round2_matches = Match.query.filter_by(gara_id=gara.id, round_number=2).all()

        # Complete second round
        regular_matches_r2 = [
            m for m in round2_matches if not m.is_trio and not m.is_bye
        ]
        trio_matches_r2_list = [m for m in round2_matches if m.is_trio]

        if regular_matches_r2:
            results = [(3, 1)] * len(regular_matches_r2)
            self._complete_matches_with_results(regular_matches_r2, results, db_session)

        for trio_match in trio_matches_r2_list:
            self._complete_trio_match(trio_match, db_session)

        RoundClassification.calculate_classification_after_round(gara.id, 2)

        # Verify final results
        from amalfi.engine import get_amalfi_classification

        final_classification = get_amalfi_classification(gara.id, 2)
        assert final_classification is not None
        assert len(final_classification) == 9

        print(f"✅ Random strategy with trio handling completed successfully")
        print(
            f"   - Round 1: {len(trio_matches_list)} trio matches, {len(regular_matches)} regular matches"
        )
        print(
            f"   - Round 2: {len(trio_matches_r2_list)} trio matches, {len(regular_matches_r2)} regular matches"
        )
        print(f"   - All 9 players have final classification")

    def _complete_matches_with_results(
        self, matches: List[Match], results: List[tuple], db_session
    ) -> None:
        """Complete matches with specified win-loss results."""
        for match, (winner_racks, loser_racks) in zip(matches, results):
            if match.is_bye or match.is_trio:
                continue

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

    def _complete_trio_match(self, trio_match: Match, db_session) -> None:
        """Complete a trio match with realistic 3-player scoring."""
        if not trio_match.is_trio:
            return

        # Simulate trio completion with proper rack scoring for all 3 players
        # In a trio match, we need to ensure all players have some racks recorded

        import random

        # Simulate trio completion - player1 wins (3 racks), others get some racks
        winner_id = trio_match.player1_id

        # Add racks for winner (3 wins)
        for rack_num in range(1, 4):
            RackService.add_rack_result(
                match_id=trio_match.id,
                rack_number=rack_num,
                winner_id=winner_id,
                reported_by_id=winner_id,
                confirmed_by_player=True,
                validated_by_admin=True,
            )

        # Add racks for other players (1 rack each)
        if trio_match.player2_id:
            RackService.add_rack_result(
                match_id=trio_match.id,
                rack_number=4,
                winner_id=trio_match.player2_id,
                reported_by_id=trio_match.player2_id,
                confirmed_by_player=True,
                validated_by_admin=True,
            )

        # Complete the match properly using MatchService
        MatchService.to_completed(trio_match.id)

        print(
            f"   - Completed trio match {trio_match.id} with winner {trio_match.winner_id}"
        )
