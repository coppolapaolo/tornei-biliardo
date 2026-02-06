"""Integration tests for Use Case 3: Round-robin strategy workflow.

Tests focused workflow aspects:
- Round-robin all vs all pairing
- Multi-set match scoring
- Live classification update after each match
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
from models.classification.models import RoundClassification
from models.base import utc_now


@pytest.mark.integration
class TestUseCaseRoundRobin:
    """Test Use Case 3: Round-robin strategy workflow."""

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

    @pytest.fixture
    def players_8(self, db_session) -> List[User]:
        """Create 8 players for larger round-robin testing."""
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

    def test_round_robin_gara_creation(
        self, director_user: User, db_session
    ):
        """Test creating Round-robin gara with correct parameters.

        UC3: Round-robin strategy, min 6, max 12 players, multi-set scoring.
        """
        gara = GaraService.create_gara(
            campionato_id=None,
            number=1,
            name="Round Robin Tournament",
            date=date.today() + timedelta(days=7),
            location="Test Venue",
            description="Round-robin strategy test",
            rounds_count=5,  # For 6 players: each plays 5 opponents
            min_participants=6,
            max_participants=12,
            entry_fee=0.0,
            discipline="palla_8",
            distance=5,  # Sets are race to 5 racks
            is_race_to=True,
            director_id=director_user.id,
            matchmaking_strategy="round_robin",
            first_round_policy="random",
            odd_number_policy="bye",
            anti_rematch_enabled=False,  # Not applicable for round-robin
        )

        assert gara is not None
        assert gara.matchmaking_strategy == "round_robin"
        assert gara.min_participants == 6
        assert gara.max_participants == 12
        assert gara.discipline == "palla_8"
        assert gara.status == GaraStatus.SETUP.value

    def test_round_robin_first_round_pairing(
        self, director_user: User, players_6: List[User], db_session
    ):
        """Test round-robin creates first round with unique pairings.

        UC3: First round of round-robin creates valid pairings.
        """
        gara = GaraService.create_gara(
            campionato_id=None,
            number=1,
            name="Round Robin Test",
            date=date.today() + timedelta(days=7),
            location="Test Venue",
            description="Round-robin pairing",
            rounds_count=5,  # 6 players need 5 rounds
            min_participants=4,
            max_participants=8,
            entry_fee=0.0,
            discipline="palla_8",
            distance=5,
            is_race_to=True,
            director_id=director_user.id,
            matchmaking_strategy="round_robin",
            first_round_policy="random",
            odd_number_policy="bye",
            anti_rematch_enabled=False,
        )

        # Open inscriptions and inscribe players
        inscription_start = utc_now() - timedelta(hours=1)
        inscription_end = utc_now() + timedelta(hours=1)
        InscriptionService.open_inscriptions(gara.id, inscription_start, inscription_end)

        for player in players_6:
            InscriptionService.inscribe_user(player.id, gara.id)

        # Start first round
        GaraService.start_first_round(gara.id)

        # Check round 1 matches
        round1_matches = Match.query.filter_by(gara_id=gara.id, round_number=1).all()

        # With 6 players: should have 3 matches
        non_bye_matches = [m for m in round1_matches if not m.is_bye]
        assert len(non_bye_matches) == 3, f"Expected 3 matches, got {len(non_bye_matches)}"

        # Verify each player plays exactly once in round 1
        player_ids = {p.id for p in players_6}
        players_in_round = set()
        for match in non_bye_matches:
            players_in_round.add(match.player1_id)
            players_in_round.add(match.player2_id)

        assert players_in_round == player_ids, "Not all players are in round 1"

        # Verify no duplicate pairings
        pairings = [frozenset([m.player1_id, m.player2_id]) for m in non_bye_matches]
        assert len(set(pairings)) == len(pairings), "Found duplicate pairings"

    def test_round_robin_classification_update_after_match(
        self, director_user: User, players_6: List[User], db_session
    ):
        """Test classification updates after each completed match.

        UC3: Classification updated after every match completion.
        """
        gara = GaraService.create_gara(
            campionato_id=None,
            number=1,
            name="Live Classification Test",
            date=date.today() + timedelta(days=7),
            location="Test Venue",
            description="Live classification update",
            rounds_count=5,
            min_participants=4,
            max_participants=8,
            entry_fee=0.0,
            discipline="palla_8",
            distance=5,
            is_race_to=True,
            director_id=director_user.id,
            matchmaking_strategy="round_robin",
            first_round_policy="random",
            odd_number_policy="bye",
            anti_rematch_enabled=False,
        )

        # Setup
        inscription_start = utc_now() - timedelta(hours=1)
        inscription_end = utc_now() + timedelta(hours=1)
        InscriptionService.open_inscriptions(gara.id, inscription_start, inscription_end)

        for player in players_6:
            InscriptionService.inscribe_user(player.id, gara.id)

        GaraService.start_first_round(gara.id)

        # Complete first round matches one by one
        round1_matches = Match.query.filter_by(gara_id=gara.id, round_number=1).all()

        for match in round1_matches:
            if not match.is_bye:
                self._complete_match_simple(match, db_session)

        # Calculate classification after round 1
        RoundClassification.calculate_classification_after_round(gara.id, 1)

        # Check classification exists and is ordered
        classifications = RoundClassification.query.filter_by(
            gara_id=gara.id, round_number=1
        ).order_by(RoundClassification.position).all()

        assert len(classifications) == 6

        # Verify ordering by matches won, then rack difference
        for i in range(len(classifications) - 1):
            current = classifications[i]
            next_cls = classifications[i + 1]

            # Check ordering is valid (matches_won desc, then rack_diff desc)
            if current.matches_won > next_cls.matches_won:
                continue  # Valid: more wins
            elif current.matches_won == next_cls.matches_won:
                assert current.rack_difference >= next_cls.rack_difference, (
                    f"Position {current.position} should have better or equal rack diff"
                )
            else:
                pytest.fail(
                    f"Position {current.position} has fewer wins than {next_cls.position}"
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
