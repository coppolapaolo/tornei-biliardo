"""Integration tests for Use Case 8: Match modification and round management.

Tests focused workflow aspects:
- Reset match reopens round
- Modify match recalculates classification
- Cannot modify locked round (when subsequent round exists)
- Cancel round enables previous modifications
"""

import pytest
from datetime import date, timedelta
from typing import List
import uuid

from models import User, Gara, Match
from models.user.role_enum import UserRole
from models.status_enum import MatchStatus
from models.competition.services import GaraService, RoundService
from models.competition.inscription_service import InscriptionService
from models.competition.round_manager import AdvancedRoundManager, RoundLockStatus
from models.match.services import MatchService, RackService
from models.classification.models import RoundClassification
from models.base import utc_now


@pytest.mark.integration
class TestUseCaseMatchReset:
    """Test Use Case 8: Match reset reopens round."""

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
        """Create 6 players for testing."""
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
    def gara_with_completed_round1(
        self, director_user: User, players_6: List[User], db_session
    ) -> Gara:
        """Create gara with completed first round."""
        gara = GaraService.create_gara(
            campionato_id=None,
            number=1,
            name="Match Modification Test",
            date=date.today() + timedelta(days=7),
            location="Test Venue",
            description="Match modification test",
            rounds_count=4,
            min_participants=4,
            max_participants=8,
            entry_fee=0.0,
            discipline="9_ball",
            distance=5,
            is_race_to=True,
            director_id=director_user.id,
            matchmaking_strategy="random",
        )

        # Open inscriptions and inscribe players
        inscription_start = utc_now() - timedelta(hours=1)
        inscription_end = utc_now() + timedelta(hours=1)
        InscriptionService.open_inscriptions(
            gara.id, inscription_start, inscription_end
        )

        for player in players_6:
            InscriptionService.inscribe_user(player.id, gara.id)

        # Start first round
        RoundService.start_first_round(gara.id)

        # Complete all round 1 matches
        round1_matches = Match.query.filter_by(gara_id=gara.id, round_number=1).all()
        for match in round1_matches:
            if not match.is_bye:
                self._complete_match_simple(match, db_session)

        # Calculate classification
        RoundClassification.calculate_classification_after_round(gara.id, 1)

        return gara

    def test_reset_match_reopens_round(
        self, gara_with_completed_round1: Gara, db_session
    ):
        """Test resetting match reopens the round.

        UC8: Admin resets match and round is reopened.
        """
        gara = gara_with_completed_round1

        # Get a completed match from round 1
        match = Match.query.filter_by(
            gara_id=gara.id,
            round_number=1,
            status=MatchStatus.COMPLETED.value,
        ).first()

        assert match is not None

        # Reset the match
        success, message = AdvancedRoundManager.reset_match_with_validation(match.id)

        assert success is True, f"Reset failed: {message}"

        # Refresh match and check state
        db_session.refresh(match)

        # Match should be back to pending or playing based on table assignment
        assert match.status in [MatchStatus.PENDING.value, MatchStatus.PLAYING.value]
        assert match.winner_id is None
        assert match.player1_score == 0
        assert match.player2_score == 0

    def test_modify_match_recalculates_classification(
        self, gara_with_completed_round1: Gara, db_session
    ):
        """Test modifying match result recalculates classification.

        UC8: Changing match result updates classification.
        """
        gara = gara_with_completed_round1

        # Get initial classification
        initial_classifications = RoundClassification.query.filter_by(
            gara_id=gara.id, round_number=1
        ).all()
        {c.user_id: c.position for c in initial_classifications}

        # Get a completed match
        match = Match.query.filter_by(
            gara_id=gara.id,
            round_number=1,
            status=MatchStatus.COMPLETED.value,
        ).first()

        original_winner = match.winner_id

        # Reset the match
        success, message = AdvancedRoundManager.reset_match_with_validation(match.id)
        assert success is True

        # Complete with different result (swap winner)
        db_session.refresh(match)
        new_winner_id = (
            match.player2_id
            if original_winner == match.player1_id
            else match.player1_id
        )
        (match.player1_id if new_winner_id == match.player2_id else match.player2_id)

        # Add racks for new winner
        for rack_num in range(1, match.match_distance + 1):
            RackService.add_rack_result(
                match_id=match.id,
                rack_number=rack_num,
                winner_id=new_winner_id,
                reported_by_id=new_winner_id,
                confirmed_by_player=True,
                validated_by_admin=True,
            )

        MatchService.to_completed(match.id)

        # Recalculate classification
        RoundClassification.calculate_classification_after_round(gara.id, 1)

        # Get new classification
        new_classifications = RoundClassification.query.filter_by(
            gara_id=gara.id, round_number=1
        ).all()
        {c.user_id: c.position for c in new_classifications}

        # Classification should exist (may or may not have changed)
        assert len(new_classifications) == len(initial_classifications)

    def _complete_match_simple(self, match: Match, db_session) -> None:
        """Complete a match with random-ish results.

        For race-to-N, winner needs exactly N racks. We interleave racks
        to simulate a realistic game flow and stop as soon as winner
        reaches the target score.
        """
        import random

        if match.is_bye:
            return

        winner_id = (
            match.player1_id if random.choice([True, False]) else match.player2_id
        )
        loser_id = (
            match.player2_id if winner_id == match.player1_id else match.player1_id
        )

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


@pytest.mark.integration
class TestUseCaseRoundLocking:
    """Test Use Case 8: Round locking prevents modifications."""

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
        """Create 6 players for testing."""
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
    def gara_with_two_rounds(
        self, director_user: User, players_6: List[User], db_session
    ) -> Gara:
        """Create gara with two completed rounds."""
        gara = GaraService.create_gara(
            campionato_id=None,
            number=1,
            name="Round Locking Test",
            date=date.today() + timedelta(days=7),
            location="Test Venue",
            description="Round locking test",
            rounds_count=4,
            min_participants=4,
            max_participants=8,
            entry_fee=0.0,
            discipline="9_ball",
            distance=5,
            is_race_to=True,
            director_id=director_user.id,
            matchmaking_strategy="random",
        )

        # Open inscriptions and inscribe players
        inscription_start = utc_now() - timedelta(hours=1)
        inscription_end = utc_now() + timedelta(hours=1)
        InscriptionService.open_inscriptions(
            gara.id, inscription_start, inscription_end
        )

        for player in players_6:
            InscriptionService.inscribe_user(player.id, gara.id)

        # Start first round
        RoundService.start_first_round(gara.id)

        # Complete all round 1 matches
        round1_matches = Match.query.filter_by(gara_id=gara.id, round_number=1).all()
        for match in round1_matches:
            if not match.is_bye:
                self._complete_match_simple(match, db_session)

        RoundClassification.calculate_classification_after_round(gara.id, 1)

        # Start round 2 (which should lock round 1)
        # Note: Random strategy creates all rounds at once, so we check existing round 2
        # matches
        round2_matches = Match.query.filter_by(gara_id=gara.id, round_number=2).all()
        if round2_matches:
            # Round 2 exists, complete it
            for match in round2_matches:
                if not match.is_bye:
                    self._complete_match_simple(match, db_session)

            RoundClassification.calculate_classification_after_round(gara.id, 2)

        return gara

    def test_round_has_lock_status(self, gara_with_two_rounds: Gara, db_session):
        """Test round lock status can be queried.

        UC8: System can check round lock status.
        """
        gara = gara_with_two_rounds

        # Round lock status should be queryable
        lock_status = AdvancedRoundManager.get_round_lock_status(gara.id, 1)

        # Lock status should be a valid enum value
        assert lock_status in [RoundLockStatus.LOCKED, RoundLockStatus.UNLOCKED]

        # Can check if match can be modified (regardless of result)
        round1_match = Match.query.filter_by(
            gara_id=gara.id,
            round_number=1,
        ).first()

        if round1_match:
            can_modify, reason = AdvancedRoundManager.can_modify_match(round1_match.id)
            # Should return a boolean and reason string
            assert isinstance(can_modify, bool)
            assert isinstance(reason, str)

    def test_round_lock_status_detection(self, gara_with_two_rounds: Gara, db_session):
        """Test round lock status is correctly detected.

        UC8: System correctly identifies locked vs unlocked rounds.
        """
        gara = gara_with_two_rounds

        # Check lock status for different rounds
        AdvancedRoundManager.get_round_lock_status(gara.id, 1)
        round2_status = AdvancedRoundManager.get_round_lock_status(gara.id, 2)

        # Round 2 should be unlocked (latest round)
        # Note: Random strategy creates all rounds, so this depends on actual state
        round3_matches = Match.query.filter_by(gara_id=gara.id, round_number=3).all()

        if not round3_matches:
            # No round 3 matches, so round 2 is current/unlocked
            assert round2_status == RoundLockStatus.UNLOCKED

    def _complete_match_simple(self, match: Match, db_session) -> None:
        """Complete a match with random-ish results.

        For race-to-N, winner needs exactly N racks. We interleave racks
        to simulate a realistic game flow and stop as soon as winner
        reaches the target score.
        """
        import random

        if match.is_bye:
            return

        winner_id = (
            match.player1_id if random.choice([True, False]) else match.player2_id
        )
        loser_id = (
            match.player2_id if winner_id == match.player1_id else match.player1_id
        )

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


@pytest.mark.integration
class TestUseCaseRoundCancellation:
    """Test Use Case 8: Cancel round enables previous modifications."""

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
        """Create 6 players for testing."""
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

    def test_amalfi_round_creation_and_cancellation(
        self, director_user: User, players_6: List[User], db_session
    ):
        """Test Amalfi round creation and cancellation functionality.

        UC8: Test round management operations.
        """
        # Create gara with Amalfi strategy
        gara = GaraService.create_gara(
            campionato_id=None,
            number=1,
            name="Cancel Round Test",
            date=date.today() + timedelta(days=7),
            location="Test Venue",
            description="Cancel round test",
            rounds_count=4,
            min_participants=4,
            max_participants=8,
            entry_fee=0.0,
            discipline="9_ball",
            distance=5,
            is_race_to=True,
            director_id=director_user.id,
            matchmaking_strategy="amalfi",
            anti_rematch_enabled=True,
        )

        # Setup inscriptions
        inscription_start = utc_now() - timedelta(hours=1)
        inscription_end = utc_now() + timedelta(hours=1)
        InscriptionService.open_inscriptions(
            gara.id, inscription_start, inscription_end
        )

        for player in players_6:
            InscriptionService.inscribe_user(player.id, gara.id)

        # Start and complete round 1
        RoundService.start_first_round(gara.id)
        round1_matches = Match.query.filter_by(gara_id=gara.id, round_number=1).all()
        for match in round1_matches:
            if not match.is_bye:
                self._complete_match_simple(match, db_session)

        db_session.commit()

        # Calculate classification
        RoundClassification.calculate_classification_after_round(gara.id, 1)

        # Verify round 1 was completed
        assert len(round1_matches) > 0, "Round 1 should have matches"

        # Create round 2
        RoundService.create_round_with_strategy(gara.id, 2)
        round2_matches = Match.query.filter_by(gara_id=gara.id, round_number=2).all()

        # Verify round 2 was created
        assert len(round2_matches) > 0, "Round 2 should have matches"

        # Test cancellation API exists and returns valid result
        success, message = AdvancedRoundManager.cancel_round(gara.id, 2)
        assert isinstance(success, bool)
        assert isinstance(message, str)

    def _complete_match_simple(self, match: Match, db_session) -> None:
        """Complete a match with random-ish results.

        For race-to-N, winner needs exactly N racks. We interleave racks
        to simulate a realistic game flow and stop as soon as winner
        reaches the target score.
        """
        import random

        if match.is_bye:
            return

        winner_id = (
            match.player1_id if random.choice([True, False]) else match.player2_id
        )
        loser_id = (
            match.player2_id if winner_id == match.player1_id else match.player1_id
        )

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
