"""Unit tests for gara (competition) management."""

import pytest
import uuid
from datetime import date, timedelta

from models import User, Gara, Inscription
from models.user.models import DirectorAssignment
from models.user.role_enum import UserRole
from models.competition.models import WithdrawPolicy
from models.status_enum import GaraStatus
from models.campionato.services import TournamentService
from models.competition.services import GaraService


@pytest.mark.unit
class TestGaraModel:
    """Test Gara model functionality."""

    def test_create_gara(self, db_session):
        """Test creating a gara."""
        tomorrow = date.today() + timedelta(days=1)

        gara = Gara(
            campionato_id=None,  # Standalone
            number=1,
            name="Test Competition",
            date=tomorrow,
            location="Test Location",
            description="Test description",
            rounds_count=3,
            min_participants=4,
            max_participants=16,
            entry_fee=15.0,
            discipline="palla 9",
            distance=7,
            is_race_to=True,
            withdraw_policy=WithdrawPolicy.EXCLUDE.value,
            status=GaraStatus.SETUP.value,
        )
        db_session.add(gara)
        db_session.commit()

        assert gara.id is not None
        assert gara.name == "Test Competition"
        assert gara.date == tomorrow
        assert gara.location == "Test Location"
        assert gara.description == "Test description"
        assert gara.rounds_count == 3
        assert gara.min_participants == 4
        assert gara.max_participants == 16
        assert gara.entry_fee == 15.0
        assert gara.discipline == "palla 9"
        assert gara.distance == 7
        assert gara.is_race_to is True
        assert gara.withdraw_policy == WithdrawPolicy.EXCLUDE.value
        assert gara.status == GaraStatus.SETUP.value

    def test_gara_disciplines(self, db_session):
        """Test different gara disciplines."""
        disciplines = ["palla 9", "palla 8", "palla 10", "snooker"]
        tomorrow = date.today() + timedelta(days=1)

        for discipline in disciplines:
            gara = Gara(
                campionato_id=None,
                number=1,
                name=f"Test {discipline}",
                date=tomorrow,
                discipline=discipline,
                distance=7,
                is_race_to=True,
            )
            db_session.add(gara)

        db_session.commit()

        saved_gare = Gara.query.all()
        assert len(saved_gare) == 4

        for gara, expected_discipline in zip(saved_gare, disciplines):
            assert gara.discipline == expected_discipline

    def test_gara_race_to_vs_exact(self, db_session):
        """Test race-to vs exact number scoring."""
        tomorrow = date.today() + timedelta(days=1)

        # Race to 7 (first to 7 wins)
        race_to_gara = Gara(
            campionato_id=None,
            number=1,
            name="Race to 7",
            date=tomorrow,
            discipline="palla 9",
            distance=7,
            is_race_to=True,
        )

        # Exactly 7 racks
        exact_gara = Gara(
            campionato_id=None,
            number=1,
            name="Exactly 7",
            date=tomorrow,
            discipline="palla 9",
            distance=7,
            is_race_to=False,
        )

        db_session.add_all([race_to_gara, exact_gara])
        db_session.commit()

        # Test winning score calculation via distance_config value object
        assert (
            race_to_gara.distance_config.get_winning_racks() == 7
        )  # Race-to-7 (first to 7)
        assert exact_gara.distance_config.get_winning_racks() == 7  # Exactly 7

    def test_gara_withdraw_policies(self, db_session):
        """Test different withdraw policies."""
        tomorrow = date.today() + timedelta(days=1)
        policies = [
            WithdrawPolicy.EXCLUDE,
            WithdrawPolicy.FORFEIT,
        ]

        # Create a director for the gara tests
        unique_id = str(uuid.uuid4())[:8]
        director = User(
            username=f"director_{unique_id}",
            email=f"director_{unique_id}@test.com",
            role=UserRole.DIRECTOR.value,
        )
        director.set_password("testpass123")
        db_session.add(director)
        db_session.commit()

        for policy in policies:
            gara = Gara(
                campionato_id=None,
                number=1,
                name=f"Test {policy.value}",
                date=tomorrow,
                discipline="palla 9",
                distance=7,
                is_race_to=True,
                withdraw_policy=policy.value,
                director_id=director.id,  # Add director_id to fix validation
            )
            db_session.add(gara)

        db_session.commit()

        saved_gare = Gara.query.all()
        assert len(saved_gare) == 2

    def test_gara_can_be_modified(self, db_session):
        """Test gara modification rules."""
        tomorrow = date.today() + timedelta(days=1)

        # Create a director for the gara test
        unique_id = str(uuid.uuid4())[:8]
        director = User(
            username=f"director_{unique_id}",
            email=f"director_{unique_id}@test.com",
            role=UserRole.DIRECTOR.value,
        )
        director.set_password("testpass123")
        db_session.add(director)
        db_session.commit()

        gara = Gara(
            campionato_id=None,
            number=1,
            name="Modifiable Competition",
            date=tomorrow,
            discipline="palla 9",
            distance=7,
            is_race_to=True,
            status=GaraStatus.SETUP.value,
            director_id=director.id,  # Add director_id to fix validation
        )
        db_session.add(gara)
        db_session.commit()

        # Initially should be modifiable
        assert gara.can_be_modified() is True

        # Add inscription
        unique_id = str(uuid.uuid4())[:8]
        player = User(
            username=f"player_{unique_id}",
            email=f"player_{unique_id}@test.com",
            role=UserRole.PLAYER.value,
        )
        player.set_password("testpass123")
        db_session.add(player)
        db_session.commit()

        inscription = Inscription(user_id=player.id, gara_id=gara.id)
        db_session.add(inscription)
        db_session.commit()

        # Now should not be modifiable
        assert gara.can_be_modified() is False

    def test_gara_can_be_deleted(self, db_session):
        """Test gara deletion rules."""
        tomorrow = date.today() + timedelta(days=1)

        # Create a director for the gara test
        unique_id = str(uuid.uuid4())[:8]
        director = User(
            username=f"director_{unique_id}",
            email=f"director_{unique_id}@test.com",
            role=UserRole.DIRECTOR.value,
        )
        director.set_password("testpass123")
        db_session.add(director)
        db_session.commit()

        gara = Gara(
            campionato_id=None,
            number=1,
            name="Deletable Competition",
            date=tomorrow,
            discipline="palla 9",
            distance=7,
            is_race_to=True,
            status=GaraStatus.SETUP.value,
            director_id=director.id,  # Add director_id to fix validation
        )
        db_session.add(gara)
        db_session.commit()

        # Initially should be deletable
        assert gara.can_be_deleted() is True

        # Add inscription
        unique_id = str(uuid.uuid4())[:8]
        player = User(
            username=f"player_{unique_id}",
            email=f"player_{unique_id}@test.com",
            role=UserRole.PLAYER.value,
        )
        player.set_password("testpass123")
        db_session.add(player)
        db_session.commit()

        inscription = Inscription(user_id=player.id, gara_id=gara.id)
        db_session.add(inscription)
        db_session.commit()

        # Now should not be deletable
        assert gara.can_be_deleted() is False

    def test_gara_status_transitions(self, db_session):
        """Test gara status transitions."""
        tomorrow = date.today() + timedelta(days=1)

        gara = Gara(
            campionato_id=None,
            number=1,
            name="Status Test Competition",
            date=tomorrow,
            discipline="palla 9",
            distance=7,
            is_race_to=True,
            status=GaraStatus.SETUP.value,
        )
        db_session.add(gara)
        db_session.commit()

        # Test status transitions
        valid_statuses = [
            GaraStatus.INSCRIPTION.value,
            GaraStatus.PLAYING.value,
            GaraStatus.COMPLETED.value,
        ]

        for status in valid_statuses:
            gara.status = status
            db_session.commit()
            assert gara.status == status


@pytest.mark.unit
class TestGaraService:
    """Test GaraService functionality."""

    def test_create_standalone_gara(self, db_session):
        """Test creating standalone gara."""
        unique_id = str(uuid.uuid4())[:8]
        director = User(
            username=f"director_{unique_id}",
            email=f"director_{unique_id}@test.com",
            role=UserRole.DIRECTOR.value,
        )
        director.set_password("testpass123")
        db_session.add(director)
        db_session.commit()

        tomorrow = date.today() + timedelta(days=1)

        gara = GaraService.create_gara(
            campionato_id=None,  # Standalone
            number=1,
            name="Standalone Competition",
            date=tomorrow,
            location="Test Location",
            description="Test standalone gara",
            rounds_count=3,
            min_participants=4,
            max_participants=16,
            entry_fee=15.0,
            discipline="palla 9",
            distance=7,
            is_race_to=True,
            withdraw_policy=WithdrawPolicy.EXCLUDE.value,
            director_id=director.id,
        )

        assert gara is not None
        assert gara.campionato_id is None
        assert gara.name == "Standalone Competition"
        assert gara.date == tomorrow
        assert gara.director_id == director.id
        assert gara.status == GaraStatus.SETUP.value

    def test_create_campionato_gara(self, db_session):
        """Test creating gara within campionato."""
        # Create director and campionato
        unique_id = str(uuid.uuid4())[:8]
        director = User(
            username=f"director_{unique_id}",
            email=f"director_{unique_id}@test.com",
            role=UserRole.DIRECTOR.value,
        )
        director.set_password("testpass123")
        db_session.add(director)
        db_session.commit()

        tournament_service = TournamentService()
        campionato = tournament_service.create_campionato_with_director(
            name="Test Tournament",
            creator_user_id=director.id,
            campionato_type="Amalfi",
        )

        tomorrow = date.today() + timedelta(days=1)

        gara = GaraService.create_gara(
            campionato_id=campionato.id,
            number=1,
            name="Tournament Competition",
            date=tomorrow,
            location="Test Location",
            description="Test tournament gara",
            rounds_count=3,
            min_participants=4,
            max_participants=16,
            entry_fee=15.0,
            discipline="palla 9",
            distance=7,
            is_race_to=True,
            withdraw_policy=WithdrawPolicy.EXCLUDE.value,
        )

        assert gara is not None
        assert gara.campionato_id == campionato.id
        assert gara.name == "Tournament Competition"
        assert gara.date == tomorrow
        assert gara.director_id is None  # Not set for campionato gare

    def test_update_gara(self, db_session):
        """Test updating gara."""
        unique_id = str(uuid.uuid4())[:8]
        director = User(
            username=f"director_{unique_id}",
            email=f"director_{unique_id}@test.com",
            role=UserRole.DIRECTOR.value,
        )
        director.set_password("testpass123")
        db_session.add(director)
        db_session.commit()

        tomorrow = date.today() + timedelta(days=1)

        gara = GaraService.create_gara(
            campionato_id=None,
            number=1,
            name="Original Name",
            date=tomorrow,
            location="Original Location",
            description="Original description",
            rounds_count=3,
            min_participants=4,
            max_participants=16,
            entry_fee=15.0,
            discipline="palla 9",
            distance=7,
            is_race_to=True,
            withdraw_policy=WithdrawPolicy.EXCLUDE.value,
            director_id=director.id,
        )

        next_week = date.today() + timedelta(days=7)

        # Update gara
        updated_gara = GaraService.update_gara(
            gara_id=gara.id,
            name="Updated Name",
            date=next_week,
            location="Updated Location",
            description="Updated description",
            rounds_count=4,
            min_participants=6,
            max_participants=20,
            entry_fee=20.0,
            discipline="palla 8",
            distance=5,
            is_race_to=False,
            withdraw_policy=WithdrawPolicy.FORFEIT.value,
        )

        assert updated_gara.name == "Updated Name"
        assert updated_gara.date == next_week
        assert updated_gara.location == "Updated Location"
        assert updated_gara.description == "Updated description"
        assert updated_gara.rounds_count == 4
        assert updated_gara.min_participants == 6
        assert updated_gara.max_participants == 20
        assert updated_gara.entry_fee == 20.0
        assert updated_gara.discipline == "palla 8"
        assert updated_gara.distance == 5
        assert updated_gara.is_race_to is False
        assert updated_gara.withdraw_policy == WithdrawPolicy.FORFEIT.value

    def test_update_gara_with_inscriptions(self, db_session):
        """Test updating gara that has inscriptions (should fail)."""
        unique_id = str(uuid.uuid4())[:8]
        director = User(
            username=f"director_{unique_id}",
            email=f"director_{unique_id}@test.com",
            role=UserRole.DIRECTOR.value,
        )
        director.set_password("testpass123")
        unique_id = str(uuid.uuid4())[:8]
        player = User(
            username=f"player_{unique_id}",
            email=f"player_{unique_id}@test.com",
            role=UserRole.PLAYER.value,
        )
        player.set_password("testpass123")
        db_session.add_all([director, player])
        db_session.commit()

        tomorrow = date.today() + timedelta(days=1)

        gara = GaraService.create_gara(
            campionato_id=None,
            number=1,
            name="Gara with Inscriptions",
            date=tomorrow,
            location="Test Location",
            description="Test description",
            rounds_count=3,
            min_participants=4,
            max_participants=16,
            entry_fee=15.0,
            discipline="palla 9",
            distance=7,
            is_race_to=True,
            withdraw_policy=WithdrawPolicy.EXCLUDE.value,
            director_id=director.id,
        )

        # Add inscription
        inscription = Inscription(user_id=player.id, gara_id=gara.id)
        db_session.add(inscription)
        db_session.commit()

        # Try to update - should raise ValueError
        with pytest.raises(ValueError):
            GaraService.update_gara(
                gara_id=gara.id,
                name="New Name",
                date=date.today() + timedelta(days=7),
                location="New Location",
            )

    def test_delete_gara(self, db_session):
        """Test deleting gara."""
        unique_id = str(uuid.uuid4())[:8]
        director = User(
            username=f"director_{unique_id}",
            email=f"director_{unique_id}@test.com",
            role=UserRole.DIRECTOR.value,
        )
        director.set_password("testpass123")
        db_session.add(director)
        db_session.commit()

        tomorrow = date.today() + timedelta(days=1)

        gara = GaraService.create_gara(
            campionato_id=None,
            number=1,
            name="Gara to Delete",
            date=tomorrow,
            location="Test Location",
            description="Test description",
            rounds_count=3,
            min_participants=4,
            max_participants=16,
            entry_fee=15.0,
            discipline="palla 9",
            distance=7,
            is_race_to=True,
            withdraw_policy=WithdrawPolicy.EXCLUDE.value,
            director_id=director.id,
        )
        gara_id = gara.id

        # Delete gara
        GaraService.delete_gara(gara_id)

        # Check it's deleted
        deleted_gara = db_session.get(Gara, gara_id)
        assert deleted_gara is None

    def test_delete_gara_with_inscriptions(self, db_session):
        """Test deleting gara that has inscriptions (should fail)."""
        unique_id = str(uuid.uuid4())[:8]
        director = User(
            username=f"director_{unique_id}",
            email=f"director_{unique_id}@test.com",
            role=UserRole.DIRECTOR.value,
        )
        director.set_password("testpass123")
        unique_id = str(uuid.uuid4())[:8]
        player = User(
            username=f"player_{unique_id}",
            email=f"player_{unique_id}@test.com",
            role=UserRole.PLAYER.value,
        )
        player.set_password("testpass123")
        db_session.add_all([director, player])
        db_session.commit()

        tomorrow = date.today() + timedelta(days=1)

        gara = GaraService.create_gara(
            campionato_id=None,
            number=1,
            name="Gara with Inscriptions",
            date=tomorrow,
            location="Test Location",
            description="Test description",
            rounds_count=3,
            min_participants=4,
            max_participants=16,
            entry_fee=15.0,
            discipline="palla 9",
            distance=7,
            is_race_to=True,
            withdraw_policy=WithdrawPolicy.EXCLUDE.value,
            director_id=director.id,
        )

        # Add inscription
        inscription = Inscription(user_id=player.id, gara_id=gara.id)
        db_session.add(inscription)
        db_session.commit()

        # Try to delete - should raise ValueError
        with pytest.raises(ValueError):
            GaraService.delete_gara(gara.id)

    def test_get_gara_by_id(self, db_session):
        """Test getting gara by ID."""
        unique_id = str(uuid.uuid4())[:8]
        director = User(
            username=f"director_{unique_id}",
            email=f"director_{unique_id}@test.com",
            role=UserRole.DIRECTOR.value,
        )
        director.set_password("testpass123")
        db_session.add(director)
        db_session.commit()

        tomorrow = date.today() + timedelta(days=1)

        gara = GaraService.create_gara(
            campionato_id=None,
            number=1,
            name="Test Competition",
            date=tomorrow,
            location="Test Location",
            description="Test description",
            rounds_count=3,
            min_participants=4,
            max_participants=16,
            entry_fee=15.0,
            discipline="palla 9",
            distance=7,
            is_race_to=True,
            withdraw_policy=WithdrawPolicy.EXCLUDE.value,
            director_id=director.id,
        )

        # Get gara by ID
        retrieved_gara = GaraService.get_gara_by_id(gara.id)

        assert retrieved_gara is not None
        assert retrieved_gara.id == gara.id
        assert retrieved_gara.name == "Test Competition"

    def test_get_gara_by_id_not_found(self, db_session):
        """Test getting non-existent gara."""
        retrieved_gara = GaraService.get_gara_by_id(99999)
        assert retrieved_gara is None

    def test_add_director_to_standalone_gara(self, db_session):
        """Test adding co-director to standalone gara."""
        # Create directors
        unique_id = str(uuid.uuid4())[:8]
        main_director = User(
            username=f"main_director_{unique_id}",
            email=f"main_{unique_id}@test.com",
            role=UserRole.DIRECTOR.value,
        )
        main_director.set_password("testpass123")
        co_director = User(
            username=f"co_director_{unique_id}",
            email=f"co_{unique_id}@test.com",
            role=UserRole.DIRECTOR.value,
        )
        co_director.set_password("testpass123")
        db_session.add_all([main_director, co_director])
        db_session.commit()

        tomorrow = date.today() + timedelta(days=1)

        gara = GaraService.create_gara(
            campionato_id=None,
            number=1,
            name="Multi-Director Competition",
            date=tomorrow,
            location="Test Location",
            description="Test description",
            rounds_count=3,
            min_participants=4,
            max_participants=16,
            entry_fee=15.0,
            discipline="palla 9",
            distance=7,
            is_race_to=True,
            withdraw_policy=WithdrawPolicy.EXCLUDE.value,
            director_id=main_director.id,
        )

        # Add co-director
        assignment = DirectorAssignment(
            user_id=co_director.id,
            entity_type="gara",
            entity_id=gara.id,
            assigned_by_id=main_director.id,
        )
        db_session.add(assignment)
        db_session.commit()

        # Check assignment was created
        saved_assignment = (
            db_session.query(DirectorAssignment)
            .filter(
                DirectorAssignment.entity_type == "gara",
                DirectorAssignment.entity_id == gara.id,
                DirectorAssignment.user_id == co_director.id,
            )
            .first()
        )
        assert saved_assignment is not None
        assert saved_assignment.assigned_by_id == main_director.id

    def test_gara_inscription_management(self, db_session):
        """Test gara inscription management."""
        unique_id = str(uuid.uuid4())[:8]
        director = User(
            username=f"director_{unique_id}",
            email=f"director_{unique_id}@test.com",
            role=UserRole.DIRECTOR.value,
        )
        director.set_password("testpass123")
        players = []
        for i in range(5):
            player = User(
                username=f"player{i}_{unique_id}",
                email=f"player{i}_{unique_id}@test.com",
                role=UserRole.PLAYER.value,
            )
            player.set_password("testpass123")
            players.append(player)

        db_session.add(director)
        db_session.add_all(players)
        db_session.commit()

        tomorrow = date.today() + timedelta(days=1)

        gara = GaraService.create_gara(
            campionato_id=None,
            number=1,
            name="Inscription Test",
            date=tomorrow,
            location="Test Location",
            description="Test description",
            rounds_count=3,
            min_participants=4,
            max_participants=10,
            entry_fee=15.0,
            discipline="palla 9",
            distance=7,
            is_race_to=True,
            withdraw_policy=WithdrawPolicy.EXCLUDE.value,
            director_id=director.id,
        )

        # Add inscriptions
        inscriptions = []
        for player in players:
            inscription = Inscription(user_id=player.id, gara_id=gara.id)
            inscriptions.append(inscription)
            db_session.add(inscription)

        db_session.commit()

        # Check inscriptions were added using query
        inscriptions_count = (
            db_session.query(Inscription).filter_by(gara_id=gara.id).count()
        )
        assert inscriptions_count == 5

        # All players should be inscribed
        inscriptions = db_session.query(Inscription).filter_by(gara_id=gara.id).all()
        inscribed_user_ids = {insc.user_id for insc in inscriptions}
        expected_user_ids = {player.id for player in players}
        assert inscribed_user_ids == expected_user_ids

    def test_gara_status_management(self, db_session):
        """Test gara status management through service."""
        unique_id = str(uuid.uuid4())[:8]
        director = User(
            username=f"director_{unique_id}",
            email=f"director_{unique_id}@test.com",
            role=UserRole.DIRECTOR.value,
        )
        director.set_password("testpass123")
        db_session.add(director)
        db_session.commit()

        tomorrow = date.today() + timedelta(days=1)

        gara = GaraService.create_gara(
            campionato_id=None,
            number=1,
            name="Status Management Test",
            date=tomorrow,
            location="Test Location",
            description="Test description",
            rounds_count=3,
            min_participants=4,
            max_participants=16,
            entry_fee=15.0,
            discipline="palla 9",
            distance=7,
            is_race_to=True,
            withdraw_policy=WithdrawPolicy.EXCLUDE.value,
            director_id=director.id,
        )

        # Initially should be in SETUP status
        assert gara.status == GaraStatus.SETUP.value

        # Change to INSCRIPTION status
        gara.status = GaraStatus.INSCRIPTION.value
        db_session.commit()

        # Verify status change
        db_session.refresh(gara)
        assert gara.status == GaraStatus.INSCRIPTION.value


@pytest.mark.unit
class TestGaraStatusWithEmptyMatches:
    """Test gara status methods with edge cases involving empty match lists.

    These tests verify the fix for the bug where `all()` on an empty list
    returns True, incorrectly indicating all matches are completed when
    there are no matches at all.
    """

    def test_get_real_status_with_no_matches_returns_playing(self, db_session):
        """Test that get_real_status returns 'playing' when in playing state
        but no matches exist for the current round.

        Bug fix: Previously, all([]) returned True, incorrectly returning
        'round_completed' status.
        """
        tomorrow = date.today() + timedelta(days=1)

        gara = Gara(
            campionato_id=None,
            number=1,
            name="Empty Matches Test",
            date=tomorrow,
            discipline="palla_9",
            distance=5,
            is_race_to=True,
            status=GaraStatus.PLAYING.value,
            current_round=1,  # Round 1 but no matches
            rounds_count=3,
        )
        db_session.add(gara)
        db_session.commit()

        # With no matches, status should still be 'playing', NOT 'round_completed'
        real_status = gara.get_real_status()
        assert real_status == GaraStatus.PLAYING.value, (
            f"Expected 'playing' but got '{real_status}'. "
            "Empty match list should not be treated as all-completed."
        )

    def test_get_real_status_with_current_round_zero_returns_playing(self, db_session):
        """Test that get_real_status returns 'playing' when current_round is 0.

        This is an edge case where status is 'playing' but current_round=0,
        which is technically an inconsistent state but should be handled gracefully.
        """
        tomorrow = date.today() + timedelta(days=1)

        gara = Gara(
            campionato_id=None,
            number=1,
            name="Round Zero Test",
            date=tomorrow,
            discipline="palla_9",
            distance=5,
            is_race_to=True,
            status=GaraStatus.PLAYING.value,
            current_round=0,  # Edge case: playing but no round started
            rounds_count=3,
        )
        db_session.add(gara)
        db_session.commit()

        # With current_round=0 and no matches, should return 'playing'
        real_status = gara.get_real_status()
        assert real_status == GaraStatus.PLAYING.value, (
            f"Expected 'playing' but got '{real_status}'. "
            "current_round=0 with empty matches should not be treated as round_completed."
        )

    def test_can_start_new_round_with_no_matches_returns_false(self, db_session):
        """Test that can_start_new_round returns False when no matches exist.

        Bug fix: Previously, all([]) returned True, incorrectly indicating
        we can start a new round when there are no matches at all.
        """
        tomorrow = date.today() + timedelta(days=1)

        gara = Gara(
            campionato_id=None,
            number=1,
            name="Can Start Round Test",
            date=tomorrow,
            discipline="palla_9",
            distance=5,
            is_race_to=True,
            status=GaraStatus.PLAYING.value,
            current_round=1,
            rounds_count=3,
        )
        db_session.add(gara)
        db_session.commit()

        # Cannot start new round when no matches exist in current round
        can_start = gara.can_start_new_round()
        assert can_start is False, (
            "Expected False but got True. "
            "Cannot start new round when no matches exist in current round."
        )
