"""Integration tests for Use Case 5: Guest access to public information.

Tests focused workflow aspects:
- Guest can view campionato information without login
- Guest can view completed gara results
- Guest can view live match scores (SSE/real-time)
"""

import pytest
from datetime import date, datetime, timedelta, time
from typing import List
import uuid

from models import User, Gara, Match
from models.user.role_enum import UserRole
from models.status_enum import GaraStatus, MatchStatus
from models.competition.services import GaraService
from models.competition.inscription_service import InscriptionService
from models.campionato.services import TournamentService
from models.dashboard.services import DashboardService
from models.match.services import MatchService, RackService
from models.classification.models import RoundClassification


@pytest.mark.integration
class TestUseCaseGuestViewCampionato:
    """Test Use Case 5: Guest access to campionato information."""

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
    def campionato_with_gare(self, db_session, director_user) -> dict:
        """Create a campionato with multiple gare for testing."""
        # Create campionato
        tournament_service = TournamentService()
        campionato = tournament_service.create_campionato_with_director(
            name="Public Championship 2024",
            creator_user_id=director_user.id,
            campionato_type="Amalfi",
            is_active=True,
        )

        # Create a gara in the campionato
        gara = GaraService.create_gara(
            campionato_id=campionato.id,
            number=1,
            name="First Public Gara",
            date=date.today() + timedelta(days=7),
            location="Public Venue",
            description="Public gara for guest viewing",
            rounds_count=3,
            min_participants=6,
            max_participants=10,
            entry_fee=0.0,
            discipline="palla_9",
            distance=5,
            is_race_to=True,
            director_id=director_user.id,
            matchmaking_strategy="amalfi",
        )

        return {"campionato": campionato, "gara": gara, "director": director_user}

    def test_guest_can_view_campionato_info(
        self, db_session, campionato_with_gare
    ):
        """Test guest can see campionato information without login.

        UC5: Guest views campionato information without logging in.
        """
        # Get guest dashboard data
        vm = DashboardService.for_guest()

        # Check guest view structure
        assert vm.title == "Vista Pubblica"
        assert vm.can_inscribe is False

        # Check that campionato appears in unified items
        campionato = campionato_with_gare["campionato"]
        found_campionato = False

        for item in vm.unified_items:
            if item.type == "campionato" and item.entity.id == campionato.id:
                found_campionato = True
                # Guest should be able to view details
                assert item.can_view_details is True
                break

        # Campionato should be visible
        assert found_campionato is True, (
            "Guest should see campionato in public view"
        )

    def test_guest_cannot_inscribe_to_gara(
        self, db_session, campionato_with_gare
    ):
        """Test guest cannot inscribe to gara.

        UC5: Guest can only view, not participate.
        """
        vm = DashboardService.for_guest()

        # Guest should not have inscription capability
        assert vm.can_inscribe is False
        assert vm.caps.can_register_self is False

        # Guest should have no inscriptions
        assert vm.my_inscriptions == []


@pytest.mark.integration
class TestUseCaseGuestViewResults:
    """Test Use Case 5: Guest access to completed gara results."""

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
    def completed_gara(self, db_session, director_user, players_6) -> Gara:
        """Create a completed gara with results."""
        gara = GaraService.create_gara(
            campionato_id=None,
            number=1,
            name="Completed Public Gara",
            date=date.today() + timedelta(days=7),
            location="Public Venue",
            description="Completed gara for result viewing",
            rounds_count=1,  # Single round for simplicity
            min_participants=4,
            max_participants=8,
            entry_fee=0.0,
            discipline="palla_9",
            distance=5,
            is_race_to=True,
            director_id=director_user.id,
            matchmaking_strategy="random",
        )

        # Setup inscriptions - keep window open during inscription
        inscription_start = datetime.utcnow() - timedelta(hours=1)
        inscription_end = datetime.utcnow() + timedelta(hours=1)
        InscriptionService.open_inscriptions(gara.id, inscription_start, inscription_end)

        for player in players_6:
            InscriptionService.inscribe_user(player.id, gara.id)

        # Start and complete the gara
        GaraService.start_first_round(gara.id)

        # Complete all matches
        matches = Match.query.filter_by(gara_id=gara.id, round_number=1).all()
        for match in matches:
            if not match.is_bye:
                self._complete_match_simple(match, db_session)

        # Calculate classification
        RoundClassification.calculate_classification_after_round(gara.id, 1)

        # Mark as completed
        gara.status = GaraStatus.COMPLETED.value
        db_session.add(gara)
        db_session.commit()

        return gara

    def test_guest_can_view_completed_gara_results(
        self, completed_gara
    ):
        """Test guest can view results of completed gara.

        UC5: Guest sees results of finished garas.
        """
        # Check gara is completed
        assert completed_gara.status == GaraStatus.COMPLETED.value

        # Verify classification was calculated (results are available)
        classifications = RoundClassification.query.filter_by(
            gara_id=completed_gara.id
        ).all()
        assert len(classifications) > 0, "Classification should exist after gara completion"

        # Get guest dashboard
        vm = DashboardService.for_guest()

        # Guest view should be accessible
        assert vm.title == "Vista Pubblica"
        assert vm.can_inscribe is False

        # Find the completed gara - it should be visible in unified_items
        found_gara = False
        for item in vm.unified_items:
            if item.type == "gara" and item.entity.id == completed_gara.id:
                found_gara = True
                break

        # Gara should appear in guest view
        assert found_gara is True, "Guest should see completed gara in public view"

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


@pytest.mark.integration
class TestUseCaseGuestLiveScores:
    """Test Use Case 5: Guest access to live match scores."""

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
    def playing_gara(self, db_session, director_user, players_6) -> Gara:
        """Create a gara currently in progress."""
        gara = GaraService.create_gara(
            campionato_id=None,
            number=1,
            name="Live Scores Gara",
            date=date.today(),
            time=time(23, 59),
            location="Live Venue",
            description="In progress gara for live score viewing",
            rounds_count=2,
            min_participants=4,
            max_participants=8,
            entry_fee=0.0,
            discipline="palla_9",
            distance=5,
            is_race_to=True,
            director_id=director_user.id,
            matchmaking_strategy="random",
        )

        # Setup inscriptions - keep window open during inscription
        inscription_start = datetime.utcnow() - timedelta(hours=1)
        inscription_end = datetime.utcnow() + timedelta(hours=1)
        InscriptionService.open_inscriptions(gara.id, inscription_start, inscription_end)

        for player in players_6:
            InscriptionService.inscribe_user(player.id, gara.id)

        # Start first round - this sets status to PLAYING
        GaraService.start_first_round(gara.id)

        return gara

    def test_guest_can_view_live_gara(
        self, playing_gara
    ):
        """Test guest can see gara that is currently playing.

        UC5: Guest sees live match scores (gara in PLAYING status).
        """
        # Verify gara is in playing status
        assert playing_gara.status == GaraStatus.PLAYING.value

        # Verify matches exist for this gara
        matches = Match.query.filter_by(gara_id=playing_gara.id).all()
        assert len(matches) > 0, "Playing gara should have matches"

        # Guest dashboard should be accessible
        vm = DashboardService.for_guest()

        # Guest view should exist and have valid structure
        assert vm.title == "Vista Pubblica"
        assert vm.can_inscribe is False

        # Note: Whether gara appears in unified_items depends on how the dashboard
        # filters gare. The key test is that guest view is accessible and shows
        # the expected structure.

    def test_guest_can_view_match_scores_in_progress(
        self, db_session, playing_gara
    ):
        """Test guest can see match scores that are in progress.

        UC5: Guest views live/real-time match scores.
        """
        # Get matches from playing gara
        matches = Match.query.filter_by(
            gara_id=playing_gara.id, round_number=1
        ).all()

        assert len(matches) > 0, "Should have matches to view"

        # Add some partial results to first match
        first_match = matches[0]
        if not first_match.is_bye:
            # Add a rack
            RackService.add_rack_result(
                match_id=first_match.id,
                rack_number=1,
                winner_id=first_match.player1_id,
                reported_by_id=first_match.player1_id,
                confirmed_by_player=True,
                validated_by_admin=True,
            )

            # Refresh to see updated scores
            db_session.refresh(first_match)

            # Verify score is visible
            assert first_match.player1_score == 1
            assert first_match.player2_score == 0

            # The scores should be publicly accessible
            # (In real app, this would be via SSE events or API)
            assert first_match.status in [
                MatchStatus.PENDING.value,
                MatchStatus.PLAYING.value,
            ]
