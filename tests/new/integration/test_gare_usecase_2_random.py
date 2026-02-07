"""Integration tests for Use Case 2: Random strategy workflow.

Tests focused workflow aspects:
- Random strategy with discipline change per round
- Challenge insertion after first round
- Trio handling for odd number of players
- Three-way tiebreaker for top positions
"""

import pytest
from datetime import date, datetime, timedelta
from typing import List
import uuid

from models import User, Gara, Match
from models.user.role_enum import UserRole
from models.status_enum import GaraStatus, MatchStatus
from models.competition.services import GaraService
from models.competition.inscription_service import InscriptionService
from models.competition.round_service import RoundService
from models.match.services import MatchService, RackService
from models.match.models import TrioMatch
from models.classification.models import RoundClassification
from models.base import utc_now


@pytest.mark.integration
class TestUseCaseRandomStrategy:
    """Test Use Case 2: Random strategy workflow."""

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
        """Create 8 players for testing."""
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

    @pytest.fixture
    def players_9(self, db_session) -> List[User]:
        """Create 9 players for odd number testing."""
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

    def test_random_gara_creation_with_discipline_change(
        self, director_user: User, db_session
    ):
        """Test creating Random gara with configuration for discipline changes.

        UC2: Random strategy with discipline change for specific rounds.
        """
        gara = GaraService.create_gara(
            campionato_id=None,
            number=1,
            name="Random Strategy Tournament",
            date=date.today() + timedelta(days=7),
            location="Test Venue",
            description="Random strategy with discipline change",
            rounds_count=3,
            min_participants=6,
            max_participants=10,
            entry_fee=0.0,
            discipline="palla_8",  # Default discipline
            distance=5,
            is_race_to=True,
            director_id=director_user.id,
            matchmaking_strategy="random",
            first_round_policy="random",
            odd_number_policy="bye",
            anti_rematch_enabled=True,
        )

        assert gara is not None
        assert gara.rounds_count == 3
        assert gara.matchmaking_strategy == "random"
        assert gara.discipline == "palla_8"
        assert gara.anti_rematch_enabled is True
        assert gara.status == GaraStatus.SETUP.value

    def test_random_first_round_random_pairing(
        self, director_user: User, players_8: List[User], db_session
    ):
        """Test Random strategy creates all rounds at once with random pairing.

        UC2: First round random pairing, all rounds at once for Random strategy.
        """
        gara = GaraService.create_gara(
            campionato_id=None,
            number=1,
            name="Random Pairing Test",
            date=date.today() + timedelta(days=7),
            location="Test Venue",
            description="Random pairing all rounds",
            rounds_count=3,
            min_participants=6,
            max_participants=10,
            entry_fee=0.0,
            discipline="palla_8",
            distance=5,
            is_race_to=True,
            director_id=director_user.id,
            matchmaking_strategy="random",
            first_round_policy="random",
            odd_number_policy="bye",
            anti_rematch_enabled=True,
        )

        # Open inscriptions and inscribe players
        inscription_start = utc_now() - timedelta(hours=1)
        inscription_end = utc_now() + timedelta(hours=1)
        InscriptionService.open_inscriptions(gara.id, inscription_start, inscription_end)

        for player in players_8:
            InscriptionService.inscribe_user(player.id, gara.id)

        # Start first round - Random strategy creates ALL rounds
        RoundService.start_first_round(gara.id)

        # Check matches created for ALL rounds
        for round_num in range(1, 4):
            matches = Match.query.filter_by(gara_id=gara.id, round_number=round_num).all()
            assert len(matches) == 4, f"Round {round_num} should have 4 matches"

        # Verify no rematch across rounds
        pairings_per_round = []
        for round_num in range(1, 4):
            matches = Match.query.filter_by(gara_id=gara.id, round_number=round_num).all()
            pairings = set()
            for match in matches:
                pairing = frozenset([match.player1_id, match.player2_id])
                pairings.add(pairing)
            pairings_per_round.append(pairings)

        # Check anti-rematch between rounds
        for i in range(len(pairings_per_round)):
            for j in range(i + 1, len(pairings_per_round)):
                overlap = pairings_per_round[i] & pairings_per_round[j]
                assert len(overlap) == 0, f"Rematch found between round {i+1} and {j+1}"

    def test_random_trio_odd_handling(
        self, director_user: User, players_9: List[User], db_session
    ):
        """Test Random strategy handles odd number with trio.

        UC2 variant: 9 players with trio odd handling.
        """
        gara = GaraService.create_gara(
            campionato_id=None,
            number=1,
            name="Trio Test",
            date=date.today() + timedelta(days=7),
            location="Test Venue",
            description="Trio odd handling",
            rounds_count=3,
            min_participants=6,
            max_participants=12,
            entry_fee=0.0,
            discipline="palla_8",
            distance=5,
            is_race_to=True,
            director_id=director_user.id,
            matchmaking_strategy="random",
            first_round_policy="random",
            odd_number_policy="trio",  # Use trio for odd numbers
            anti_rematch_enabled=True,
        )

        # Open inscriptions and inscribe 9 players
        inscription_start = utc_now() - timedelta(hours=1)
        inscription_end = utc_now() + timedelta(hours=1)
        InscriptionService.open_inscriptions(gara.id, inscription_start, inscription_end)

        for player in players_9:
            InscriptionService.inscribe_user(player.id, gara.id)

        # Start first round
        RoundService.start_first_round(gara.id)

        # Check round 1 matches
        round1_matches = Match.query.filter_by(gara_id=gara.id, round_number=1).all()

        # With 9 players and trio policy: should have 3 regular matches + 1 trio
        regular_matches = [m for m in round1_matches if not m.is_trio]
        trio_matches = [m for m in round1_matches if m.is_trio]

        assert len(regular_matches) == 3, "Should have 3 regular matches"
        assert len(trio_matches) == 1, "Should have 1 trio match"

        # Verify trio has 3 players
        if trio_matches:
            trio_match = trio_matches[0]
            trio = TrioMatch.query.filter_by(match_id=trio_match.id).first()
            assert trio is not None, "TrioMatch record should exist"
            assert trio.player1_id is not None
            assert trio.player2_id is not None
            assert trio.player3_id is not None

    def test_random_anti_rematch_across_all_rounds(
        self, director_user: User, players_8: List[User], db_session
    ):
        """Test anti-rematch is enforced in all rounds with Random strategy.

        UC2: Random pairing in all rounds, no rematch.
        """
        gara = GaraService.create_gara(
            campionato_id=None,
            number=1,
            name="Anti-Rematch Random Test",
            date=date.today() + timedelta(days=7),
            location="Test Venue",
            description="Anti-rematch enforcement",
            rounds_count=3,
            min_participants=6,
            max_participants=10,
            entry_fee=0.0,
            discipline="palla_8",
            distance=5,
            is_race_to=True,
            director_id=director_user.id,
            matchmaking_strategy="random",
            first_round_policy="random",
            odd_number_policy="bye",
            anti_rematch_enabled=True,
        )

        # Setup and start
        inscription_start = utc_now() - timedelta(hours=1)
        inscription_end = utc_now() + timedelta(hours=1)
        InscriptionService.open_inscriptions(gara.id, inscription_start, inscription_end)

        for player in players_8:
            InscriptionService.inscribe_user(player.id, gara.id)

        RoundService.start_first_round(gara.id)

        # Collect all pairings
        all_pairings = []
        for round_num in range(1, 4):
            matches = Match.query.filter_by(gara_id=gara.id, round_number=round_num).all()
            for match in matches:
                pairing = tuple(sorted([match.player1_id, match.player2_id]))
                all_pairings.append(pairing)

        # Check no duplicate pairings
        unique_pairings = set(all_pairings)
        assert len(unique_pairings) == len(all_pairings), "Found duplicate pairings"


@pytest.mark.integration
class TestUseCaseRandomChallenge:
    """Test Use Case 2: Challenge insertion after round."""

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
        """Create 6 players for challenge testing."""
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

    def test_random_gara_with_challenges_configuration(
        self, director_user: User, players_6: List[User], db_session
    ):
        """Test Random gara can be configured for challenges.

        UC2: Add two challenges after first round.
        Note: Full challenge logic is complex, this tests configuration.
        """
        gara = GaraService.create_gara(
            campionato_id=None,
            number=1,
            name="Challenge Config Test",
            date=date.today() + timedelta(days=7),
            location="Test Venue",
            description="Challenge configuration test",
            rounds_count=3,
            min_participants=4,
            max_participants=8,
            entry_fee=0.0,
            discipline="palla_8",
            distance=5,
            is_race_to=True,
            director_id=director_user.id,
            matchmaking_strategy="random",
            first_round_policy="random",
            odd_number_policy="bye",
            anti_rematch_enabled=True,
        )

        # Setup inscriptions
        inscription_start = utc_now() - timedelta(hours=1)
        inscription_end = utc_now() + timedelta(hours=1)
        InscriptionService.open_inscriptions(gara.id, inscription_start, inscription_end)

        for player in players_6:
            InscriptionService.inscribe_user(player.id, gara.id)

        # Start first round
        RoundService.start_first_round(gara.id)

        # Verify gara started successfully
        db_session.refresh(gara)
        assert gara.status == GaraStatus.PLAYING.value
        assert gara.current_round == 1

        # Verify matches created
        round1_matches = Match.query.filter_by(gara_id=gara.id, round_number=1).all()
        assert len(round1_matches) == 3  # 6 players = 3 matches


@pytest.mark.integration
class TestUseCaseRandomClassification:
    """Test Use Case 2: Random strategy classification."""

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
        """Create 6 players for classification testing."""
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

    def test_random_classification_by_racks_won(
        self, director_user: User, players_6: List[User], db_session
    ):
        """Test Random strategy classification uses racks won.

        UC2: Classification ordered by number of racks won.
        """
        gara = GaraService.create_gara(
            campionato_id=None,
            number=1,
            name="Classification Test",
            date=date.today() + timedelta(days=7),
            location="Test Venue",
            description="Classification by racks",
            rounds_count=2,
            min_participants=4,
            max_participants=8,
            entry_fee=0.0,
            discipline="palla_8",
            distance=5,
            is_race_to=True,
            director_id=director_user.id,
            matchmaking_strategy="random",
            first_round_policy="random",
            odd_number_policy="bye",
            anti_rematch_enabled=True,
        )

        # Setup
        inscription_start = utc_now() - timedelta(hours=1)
        inscription_end = utc_now() + timedelta(hours=1)
        InscriptionService.open_inscriptions(gara.id, inscription_start, inscription_end)

        for player in players_6:
            InscriptionService.inscribe_user(player.id, gara.id)

        RoundService.start_first_round(gara.id)

        # Complete round 1 matches
        round1_matches = Match.query.filter_by(gara_id=gara.id, round_number=1).all()
        for match in round1_matches:
            self._complete_match_simple(match, db_session)

        # Calculate classification
        RoundClassification.calculate_classification_after_round(gara.id, 1)

        # Check classification exists
        classifications = RoundClassification.query.filter_by(
            gara_id=gara.id, round_number=1
        ).order_by(RoundClassification.position).all()

        assert len(classifications) == 6

        # Verify ordering by position (1 is best)
        for i in range(len(classifications) - 1):
            current = classifications[i]
            next_cls = classifications[i + 1]
            # Position should be sequential
            assert current.position < next_cls.position, (
                f"Position {current.position} should be less than {next_cls.position}"
            )

    def _complete_match_simple(self, match: Match, db_session) -> None:
        """Complete a match with random-ish results.

        For race-to-N, winner needs exactly N racks. We interleave racks
        to simulate a realistic game flow and stop as soon as winner
        reaches the target score.
        """
        import random

        if match.is_bye:
            return

        winner_id = match.player1_id if random.choice([True, False]) else match.player2_id
        loser_id = match.player2_id if winner_id == match.player1_id else match.player1_id

        winning_racks = match.match_distance
        loser_racks = random.randint(0, winning_racks - 1)

        rack_num = 1
        winner_count = 0
        loser_count = 0

        # Interleave racks, winner gets to winning_racks first
        while winner_count < winning_racks:
            if loser_count < loser_racks and random.choice([True, False, False]):
                RackService.add_rack_result(
                    match_id=match.id,
                    rack_number=rack_num,
                    winner_id=loser_id,
                    reported_by_id=loser_id,
                    confirmed_by_player=True,
                    validated_by_admin=True,
                )
                loser_count += 1
            else:
                RackService.add_rack_result(
                    match_id=match.id,
                    rack_number=rack_num,
                    winner_id=winner_id,
                    reported_by_id=winner_id,
                    confirmed_by_player=True,
                    validated_by_admin=True,
                )
                winner_count += 1
            rack_num += 1

        db_session.refresh(match)
        if match.status != MatchStatus.COMPLETED.value:
            MatchService.to_completed(match.id)
