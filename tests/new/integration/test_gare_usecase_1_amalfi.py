"""Integration tests for Use Case 1: Amalfi strategy complete workflow.

Tests focused workflow aspects:
- Gara creation with 3 rounds, Amalfi strategy
- Inscription with waitlist when max reached
- First round random pairing
- Anti-rematch enforcement in subsequent rounds
- Classification ordering (matches won, rack diff, previous order)
- Challenge tiebreaker for top 3 ties
"""

import pytest
from datetime import date, timedelta
from typing import List
import uuid

from models import User, Match
from models.user.role_enum import UserRole
from models.status_enum import GaraStatus, MatchStatus
from models.competition.services import GaraService
from models.competition.inscription_service import InscriptionService
from models.competition.round_service import RoundService
from models.match.services import MatchService, RackService
from models.classification.models import RoundClassification
from models.base import utc_now


@pytest.mark.integration
class TestUseCaseAmalfiWorkflow:
    """Test Use Case 1: Amalfi strategy workflow."""

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
    def players_11(self, db_session) -> List[User]:
        """Create 11 players for waitlist testing."""
        batch_id = str(uuid.uuid4())[:8]
        players = []
        for i in range(11):
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

    def test_amalfi_gara_creation_with_3_rounds(self, director_user: User, db_session):
        """Test creating Amalfi gara with correct parameters.

        UC1: Admin/director creates gara with 3 rounds, Amalfi strategy,
        min 6, max 10 players, discipline 9_ball, race to 5.
        """
        gara = GaraService.create_gara(
            campionato_id=None,
            number=1,
            name="Amalfi Tournament",
            date=date.today() + timedelta(days=7),
            location="Test Venue",
            description="Amalfi strategy test",
            rounds_count=3,
            min_participants=6,
            max_participants=10,
            entry_fee=0.0,
            discipline="9_ball",
            distance=5,
            is_race_to=True,
            director_id=director_user.id,
            matchmaking_strategy="amalfi",
            first_round_policy="random",
            odd_number_policy="bye",
            anti_rematch_enabled=True,
        )

        assert gara is not None
        assert gara.rounds_count == 3
        assert gara.matchmaking_strategy == "amalfi"
        assert gara.min_participants == 6
        assert gara.max_participants == 10
        assert gara.distance == 5
        assert gara.discipline == "9_ball"
        assert gara.anti_rematch_enabled is True
        assert gara.first_round_policy == "random"
        assert gara.status == GaraStatus.SETUP.value

    def test_amalfi_inscription_and_waitlist(
        self, director_user: User, players_11: List[User], db_session
    ):
        """Test inscription with waitlist when max participants reached.

        UC1 variant: 11 players inscribe to gara with max 10,
        last one goes to waitlist.
        """
        gara = GaraService.create_gara(
            campionato_id=None,
            number=1,
            name="Waitlist Test",
            date=date.today() + timedelta(days=7),
            location="Test Venue",
            description="Waitlist test",
            rounds_count=3,
            min_participants=6,
            max_participants=10,
            entry_fee=0.0,
            discipline="9_ball",
            distance=5,
            is_race_to=True,
            director_id=director_user.id,
            matchmaking_strategy="amalfi",
        )

        # Open inscriptions
        inscription_start = utc_now() - timedelta(hours=1)
        inscription_end = utc_now() + timedelta(days=5)
        InscriptionService.open_inscriptions(
            gara.id, inscription_start, inscription_end
        )

        # Inscribe all 11 players
        inscriptions = []
        for player in players_11:
            insc = InscriptionService.inscribe_user(player.id, gara.id)
            inscriptions.append(insc)

        # First 10 should be active, 11th on waitlist
        active_count = sum(1 for i in inscriptions if not i.is_waitlist)
        waitlist_count = sum(1 for i in inscriptions if i.is_waitlist)

        assert active_count == 10
        assert waitlist_count == 1
        assert inscriptions[-1].is_waitlist is True
        assert inscriptions[-1].waitlist_position == 1

    def test_amalfi_first_round_random_pairing(
        self, director_user: User, players_8: List[User], db_session
    ):
        """Test first round uses random pairing.

        UC1: First round pairing is random.
        """
        gara = GaraService.create_gara(
            campionato_id=None,
            number=1,
            name="Random Pairing Test",
            date=date.today() + timedelta(days=7),
            location="Test Venue",
            description="First round random pairing",
            rounds_count=3,
            min_participants=6,
            max_participants=10,
            entry_fee=0.0,
            discipline="9_ball",
            distance=5,
            is_race_to=True,
            director_id=director_user.id,
            matchmaking_strategy="amalfi",
            first_round_policy="random",
            odd_number_policy="bye",
            anti_rematch_enabled=True,
        )

        # Open inscriptions and inscribe players
        inscription_start = utc_now() - timedelta(hours=1)
        inscription_end = utc_now() + timedelta(hours=1)
        InscriptionService.open_inscriptions(
            gara.id, inscription_start, inscription_end
        )

        for player in players_8:
            InscriptionService.inscribe_user(player.id, gara.id)

        # Start first round
        RoundService.start_first_round(gara.id)

        # Check matches created
        matches = Match.query.filter_by(gara_id=gara.id, round_number=1).all()
        assert len(matches) == 4  # 8 players = 4 matches

        # Verify all players are paired
        player_ids_in_matches = set()
        for match in matches:
            player_ids_in_matches.add(match.player1_id)
            player_ids_in_matches.add(match.player2_id)

        player_ids = {p.id for p in players_8}
        assert player_ids_in_matches == player_ids

    def test_amalfi_anti_rematch_enforcement(
        self, director_user: User, players_8: List[User], db_session
    ):
        """Test anti-rematch is enforced in rounds 2 and 3.

        UC1: Second and third rounds use Amalfi pairing without rematch.
        """
        gara = GaraService.create_gara(
            campionato_id=None,
            number=1,
            name="Anti-Rematch Test",
            date=date.today() + timedelta(days=7),
            location="Test Venue",
            description="Anti-rematch enforcement",
            rounds_count=3,
            min_participants=6,
            max_participants=10,
            entry_fee=0.0,
            discipline="9_ball",
            distance=5,
            is_race_to=True,
            director_id=director_user.id,
            matchmaking_strategy="amalfi",
            first_round_policy="random",
            odd_number_policy="bye",
            anti_rematch_enabled=True,
        )

        # Setup and start
        inscription_start = utc_now() - timedelta(hours=1)
        inscription_end = utc_now() + timedelta(hours=1)
        InscriptionService.open_inscriptions(
            gara.id, inscription_start, inscription_end
        )

        for player in players_8:
            InscriptionService.inscribe_user(player.id, gara.id)

        RoundService.start_first_round(gara.id)

        # Complete round 1 matches
        round1_matches = Match.query.filter_by(gara_id=gara.id, round_number=1).all()
        round1_pairings = set()
        for match in round1_matches:
            self._complete_match_simple(match, db_session)
            pairing = frozenset([match.player1_id, match.player2_id])
            round1_pairings.add(pairing)

        # Calculate classification after round 1
        RoundClassification.calculate_classification_after_round(gara.id, 1)

        # Create and check round 2
        RoundService.create_round_with_strategy(gara.id, 2)
        round2_matches = Match.query.filter_by(gara_id=gara.id, round_number=2).all()

        # Verify no rematch from round 1
        for match in round2_matches:
            pairing = frozenset([match.player1_id, match.player2_id])
            assert pairing not in round1_pairings, "Round 2 has rematch from round 1"

        # Complete round 2
        round2_pairings = set()
        for match in round2_matches:
            self._complete_match_simple(match, db_session)
            pairing = frozenset([match.player1_id, match.player2_id])
            round2_pairings.add(pairing)

        RoundClassification.calculate_classification_after_round(gara.id, 2)

        # Create and check round 3
        RoundService.create_round_with_strategy(gara.id, 3)
        round3_matches = Match.query.filter_by(gara_id=gara.id, round_number=3).all()

        # Verify no rematch from rounds 1 or 2
        all_previous_pairings = round1_pairings | round2_pairings
        for match in round3_matches:
            pairing = frozenset([match.player1_id, match.player2_id])
            assert pairing not in all_previous_pairings, "Round 3 has rematch"

    def test_amalfi_classification_ordering(
        self, director_user: User, players_8: List[User], db_session
    ):
        """Test classification uses correct ordering.

        UC1: Classification ordered by (matches won, rack difference, previous order).
        """
        gara = GaraService.create_gara(
            campionato_id=None,
            number=1,
            name="Classification Test",
            date=date.today() + timedelta(days=7),
            location="Test Venue",
            description="Classification ordering",
            rounds_count=2,
            min_participants=6,
            max_participants=10,
            entry_fee=0.0,
            discipline="9_ball",
            distance=5,
            is_race_to=True,
            director_id=director_user.id,
            matchmaking_strategy="amalfi",
            first_round_policy="random",
            odd_number_policy="bye",
            anti_rematch_enabled=True,
        )

        # Setup
        inscription_start = utc_now() - timedelta(hours=1)
        inscription_end = utc_now() + timedelta(hours=1)
        InscriptionService.open_inscriptions(
            gara.id, inscription_start, inscription_end
        )

        for player in players_8:
            InscriptionService.inscribe_user(player.id, gara.id)

        RoundService.start_first_round(gara.id)

        # Complete round 1 with known results
        round1_matches = Match.query.filter_by(gara_id=gara.id, round_number=1).all()
        for match in round1_matches:
            self._complete_match_simple(match, db_session)

        # Calculate classification
        RoundClassification.calculate_classification_after_round(gara.id, 1)

        # Check classification exists and is ordered
        classifications = (
            RoundClassification.query.filter_by(gara_id=gara.id, round_number=1)
            .order_by(RoundClassification.position)
            .all()
        )

        assert len(classifications) == 8

        # Verify ordering: higher matches won = lower position
        for i in range(len(classifications) - 1):
            current = classifications[i]
            next_cls = classifications[i + 1]

            # Primary: matches won (descending)
            assert current.matches_won >= next_cls.matches_won, (
                f"Position {current.position} has fewer wins than position "
                f"{next_cls.position}"
            )

    def _complete_match_simple(self, match: Match, db_session) -> None:
        """Complete a match with random-ish results."""
        import random

        if match.is_bye:
            return

        winner_id = (
            match.player1_id if random.choice([True, False]) else match.player2_id
        )
        loser_id = (
            match.player2_id if winner_id == match.player1_id else match.player1_id
        )

        # For race-to-N, winner needs exactly N racks
        winning_racks = match.match_distance
        loser_racks = random.randint(0, winning_racks - 1)

        rack_num = 1
        winner_count = 0
        loser_count = 0

        # Interleave racks, winner gets to winning_racks first
        while winner_count < winning_racks:
            # Sometimes give loser a rack (if they haven't reached max)
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

        # Match should auto-complete when winner reaches target
        # If not, explicitly complete it
        db_session.refresh(match)
        if match.status != MatchStatus.COMPLETED.value:
            MatchService.to_completed(match.id)


@pytest.mark.integration
class TestUseCaseAmalfiChallenge:
    """Test Use Case 1: Challenge tiebreaker for top 3 ties."""

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

    def test_amalfi_challenge_tiebreaker_setup(
        self, director_user: User, players_6: List[User], db_session
    ):
        """Test challenge tiebreaker is configured correctly.

        UC1: Challenge with spot shot rally for ties in top 3.
        Note: Full challenge execution is complex, this tests setup.
        """
        gara = GaraService.create_gara(
            campionato_id=None,
            number=1,
            name="Challenge Tiebreaker Test",
            date=date.today() + timedelta(days=7),
            location="Test Venue",
            description="Challenge tiebreaker test",
            rounds_count=2,
            min_participants=4,
            max_participants=8,
            entry_fee=0.0,
            discipline="9_ball",
            distance=5,
            is_race_to=True,
            director_id=director_user.id,
            matchmaking_strategy="amalfi",
            first_round_policy="random",
            odd_number_policy="bye",
            anti_rematch_enabled=True,
        )

        # Note: Challenge configuration is typically set via challenge models
        # This test verifies gara can be created for challenge scenarios
        assert gara is not None
        assert gara.rounds_count == 2
        assert gara.matchmaking_strategy == "amalfi"

        # Setup inscriptions
        inscription_start = utc_now() - timedelta(hours=1)
        inscription_end = utc_now() + timedelta(hours=1)
        InscriptionService.open_inscriptions(
            gara.id, inscription_start, inscription_end
        )

        for player in players_6:
            InscriptionService.inscribe_user(player.id, gara.id)

        # Verify inscriptions
        assert gara.get_active_inscriptions_count() == 6
