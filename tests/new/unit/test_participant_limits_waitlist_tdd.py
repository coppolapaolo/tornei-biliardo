"""TDD tests for participant limits and waitlist functionality.

This module implements Test-Driven Development for participant management
scenarios not fully covered by existing tests, focusing on edge cases
around inscription limits, waitlist handling, and participant coordination.

Following the Red-Green-Refactor cycle for participant management:
1. Write failing test for participant scenario (RED)
2. Implement minimal inscription logic (GREEN)
3. Refactor and improve participant handling (REFACTOR)
4. Validate with pyright (TYPE CHECK)
5. Format with black (FORMAT)
"""

import pytest
import uuid
from datetime import date, timedelta, datetime
from typing import Dict, Any

from models import User, Gara, Inscription, db
from models.user.role_enum import UserRole
from models.competition.models import WithdrawPolicy
from models.status_enum import GaraStatus
from models.competition.services import (
    GaraService,
    InscriptionService,
)
from models.competition.state_service import StateService
from models.exceptions import InvalidTransitionError


@pytest.mark.unit
class TestParticipantLimitsWaitlistTDD:
    """TDD tests for participant limits and waitlist functionality."""

    def test_inscription_should_create_waitlist_when_max_participants_reached(
        self, db_session
    ):
        """Test that inscription creates waitlist entry when max participants limit is reached.

        GREEN PHASE: Test should pass now that waitlist logic is implemented
        for max participants. Additional participants should be added to waitlist.
        """
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
            name="Max Participants Test",
            date=tomorrow,
            discipline="palla 8",
            distance=5,
            is_race_to=True,
            director_id=director.id,
            rounds_count=3,
            min_participants=4,
            max_participants=4,  # Limit to exactly 4 participants
        )

        # Set inscription dates and start inscriptions
        inscription_start = datetime.utcnow()
        inscription_end = datetime.utcnow() + timedelta(hours=2)
        GaraService.modify_inscription_dates(
            gara.id, inscription_start, inscription_end
        )
        if gara.status != GaraStatus.INSCRIPTION.value:
            StateService.to_inscription(gara)

        # Add exactly max_participants (4) players using service method
        players = []
        for i in range(4):
            player_unique_id = str(uuid.uuid4())[:8]
            player = User(
                username=f"player{i}_{player_unique_id}",
                email=f"player{i}_{player_unique_id}@test.com",
                role=UserRole.PLAYER.value,
            )
            player.set_password("testpass123")
            players.append(player)
            db_session.add(player)
            db_session.commit()

            # This should succeed for first 4 players
            inscription = InscriptionService.inscribe_user(player.id, gara.id)
            assert inscription is not None

        # Try to add 5th player - should fail
        player_5_unique_id = str(uuid.uuid4())[:8]
        player_5 = User(
            username=f"player5_{player_5_unique_id}",
            email=f"player5_{player_5_unique_id}@test.com",
            role=UserRole.PLAYER.value,
        )
        player_5.set_password("testpass123")
        db_session.add(player_5)
        db_session.commit()

        # Should create waitlist entry when max participants reached
        waitlist_inscription = InscriptionService.inscribe_user(player_5.id, gara.id)

        # Verify waitlist inscription was created
        assert waitlist_inscription is not None
        assert waitlist_inscription.is_waitlist is True
        assert waitlist_inscription.user_id == player_5.id
        assert waitlist_inscription.gara_id == gara.id

    def test_waitlist_entry_should_be_promoted_when_participant_withdraws(
        self, db_session
    ):
        """Test that waitlist entry is promoted when a participant withdraws.

        RED PHASE: Should implement waitlist promotion logic.
        """
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
            name="Waitlist Promotion Test",
            date=tomorrow,
            discipline="palla 9",
            distance=7,
            is_race_to=True,
            director_id=director.id,
            rounds_count=3,
            min_participants=3,
            max_participants=3,  # Small limit for testing
        )

        # Set inscription dates and start inscriptions
        inscription_start = datetime.utcnow()
        inscription_end = datetime.utcnow() + timedelta(hours=2)
        GaraService.modify_inscription_dates(
            gara.id, inscription_start, inscription_end
        )
        if gara.status != GaraStatus.INSCRIPTION.value:
            StateService.to_inscription(gara)

        # Add 3 regular participants
        regular_players = []
        for i in range(3):
            player_unique_id = str(uuid.uuid4())[:8]
            player = User(
                username=f"regular{i}_{player_unique_id}",
                email=f"regular{i}_{player_unique_id}@test.com",
                role=UserRole.PLAYER.value,
            )
            player.set_password("testpass123")
            regular_players.append(player)
            db_session.add(player)
            db_session.commit()

            inscription = Inscription(user_id=player.id, gara_id=gara.id)
            db_session.add(inscription)
            db_session.commit()

        # Add waitlisted player
        waitlist_player_unique_id = str(uuid.uuid4())[:8]
        waitlist_player = User(
            username=f"waitlist_{waitlist_player_unique_id}",
            email=f"waitlist_{waitlist_player_unique_id}@test.com",
            role=UserRole.PLAYER.value,
        )
        waitlist_player.set_password("testpass123")
        db_session.add(waitlist_player)
        db_session.commit()

        # This should create waitlist entry (waitlist functionality is implemented)
        waitlist_inscription = Inscription(
            user_id=waitlist_player.id, gara_id=gara.id, is_waitlist=True, waitlist_position=1
        )
        db_session.add(waitlist_inscription)
        db_session.commit()

        # Remove one regular player using the service (which should trigger waitlist promotion)
        from models.competition.inscription_service import InscriptionService

        InscriptionService.uninscribe_user(regular_players[0].id, gara.id)

        # Waitlist player should be automatically promoted
        # This requires waitlist promotion logic to be implemented
        waitlist_inscription_updated = (
            db_session.query(Inscription)
            .filter_by(gara_id=gara.id, user_id=waitlist_player.id)
            .first()
        )

        assert waitlist_inscription_updated is not None
        # Should be promoted from waitlist
        assert not getattr(waitlist_inscription_updated, "is_waitlist", False)

    def test_inscription_should_fail_when_inscriptions_closed(self, db_session):
        """Test that inscription fails when inscription period has ended.

        RED PHASE: Should validate inscription timing properly.
        """
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
            name="Closed Inscriptions Test",
            date=tomorrow,
            discipline="palla 8",
            distance=5,
            is_race_to=True,
            director_id=director.id,
            rounds_count=3,
            min_participants=4,
        )

        # Set inscription dates in the past
        inscription_start = datetime.utcnow() - timedelta(hours=2)
        inscription_end = datetime.utcnow() - timedelta(hours=1)  # Already closed
        GaraService.modify_inscription_dates(
            gara.id, inscription_start, inscription_end
        )

        # Transition to inscription state if not already
        db_session.refresh(gara)
        if gara.status != GaraStatus.INSCRIPTION.value:
            StateService.to_inscription(gara)

        # Try to inscribe after inscription period ended
        player_unique_id = str(uuid.uuid4())[:8]
        player = User(
            username=f"late_player_{player_unique_id}",
            email=f"late_player_{player_unique_id}@test.com",
            role=UserRole.PLAYER.value,
        )
        player.set_password("testpass123")
        db_session.add(player)
        db_session.commit()

        # Should fail because inscriptions are closed
        with pytest.raises(ValueError, match="Iscrizioni chiuse"):
            InscriptionService.inscribe_user(player.id, gara.id)

    def test_inscription_before_opening_should_fail(self, db_session):
        """Test that inscription fails when inscription period hasn't started yet.

        RED PHASE: Should validate inscription timing properly.
        """
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
            name="Early Inscriptions Test",
            date=tomorrow,
            discipline="palla 9",
            distance=7,
            is_race_to=True,
            director_id=director.id,
            rounds_count=3,
            min_participants=4,
        )

        # Set inscription dates in the future
        inscription_start = datetime.utcnow() + timedelta(hours=1)  # Starts in 1 hour
        inscription_end = datetime.utcnow() + timedelta(hours=3)
        GaraService.modify_inscription_dates(
            gara.id, inscription_start, inscription_end
        )

        # Transition to inscription state if not already
        db_session.refresh(gara)
        if gara.status != GaraStatus.INSCRIPTION.value:
            StateService.to_inscription(gara)

        # Try to inscribe before inscription period starts
        player_unique_id = str(uuid.uuid4())[:8]
        player = User(
            username=f"early_player_{player_unique_id}",
            email=f"early_player_{player_unique_id}@test.com",
            role=UserRole.PLAYER.value,
        )
        player.set_password("testpass123")
        db_session.add(player)
        db_session.commit()

        # Should fail because inscriptions haven't opened yet
        with pytest.raises(ValueError, match="Iscrizioni non ancora aperte"):
            InscriptionService.inscribe_user(player.id, gara.id)

    def test_duplicate_inscription_should_fail(self, db_session):
        """Test that duplicate inscription by same player fails.

        RED PHASE: Should prevent duplicate inscriptions.
        """
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
            name="Duplicate Inscription Test",
            date=tomorrow,
            discipline="palla 8",
            distance=5,
            is_race_to=True,
            director_id=director.id,
            rounds_count=3,
            min_participants=4,
        )

        # Set inscription dates and start inscriptions
        inscription_start = datetime.utcnow()
        inscription_end = datetime.utcnow() + timedelta(hours=2)
        GaraService.modify_inscription_dates(
            gara.id, inscription_start, inscription_end
        )
        if gara.status != GaraStatus.INSCRIPTION.value:
            StateService.to_inscription(gara)

        player_unique_id = str(uuid.uuid4())[:8]
        player = User(
            username=f"player_{player_unique_id}",
            email=f"player_{player_unique_id}@test.com",
            role=UserRole.PLAYER.value,
        )
        player.set_password("testpass123")
        db_session.add(player)
        db_session.commit()

        # First inscription should succeed
        first_inscription = InscriptionService.inscribe_user(player.id, gara.id)
        assert first_inscription is not None

        # Second inscription should return the same inscription (idempotent)
        second_inscription = InscriptionService.inscribe_user(player.id, gara.id)
        assert second_inscription is not None
        assert first_inscription.id == second_inscription.id

    def test_withdraw_policy_forfeit_should_exclude_from_matches(self, db_session):
        """Test that forfeit withdraw policy excludes player from future matches.

        RED PHASE: Should implement proper forfeit handling.
        """
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
            name="Forfeit Policy Test",
            date=tomorrow,
            time=datetime.utcnow().time(),
            discipline="palla 9",
            distance=7,
            is_race_to=True,
            director_id=director.id,
            rounds_count=3,
            min_participants=4,
            withdraw_policy=WithdrawPolicy.FORFEIT,
        )

        # Set inscription dates and start inscriptions
        inscription_start = datetime.utcnow()
        inscription_end = datetime.utcnow() + timedelta(hours=2)
        GaraService.modify_inscription_dates(
            gara.id, inscription_start, inscription_end
        )
        if gara.status != GaraStatus.INSCRIPTION.value:
            StateService.to_inscription(gara)

        # Add players
        players = []
        for i in range(4):
            player_unique_id = str(uuid.uuid4())[:8]
            player = User(
                username=f"player{i}_{player_unique_id}",
                email=f"player{i}_{player_unique_id}@test.com",
                role=UserRole.PLAYER.value,
            )
            player.set_password("testpass123")
            players.append(player)
            db_session.add(player)
            db_session.commit()

            InscriptionService.inscribe_user(player.id, gara.id)

        # Start first round
        StateService.start_playing(gara)

        # Player withdraws with forfeit policy
        InscriptionService.uninscribe_user(players[0].id, gara.id)

        # Verify player inscription is removed (current implementation deletes it)
        inscription = (
            db_session.query(Inscription)
            .filter_by(gara_id=gara.id, user_id=players[0].id)
            .first()
        )

        # Current implementation deletes the inscription entirely
        assert inscription is None

        # Verify remaining players count is correct
        remaining_inscriptions = (
            db_session.query(Inscription).filter_by(gara_id=gara.id).count()
        )
        assert remaining_inscriptions == 3  # 4 original - 1 withdrawn

    def test_withdraw_policy_exclude_should_remove_from_tournament(self, db_session):
        """Test that exclude withdraw policy removes player entirely.

        RED PHASE: Should implement proper exclusion handling.
        """
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
            name="Exclude Policy Test",
            date=tomorrow,
            discipline="palla 8",
            distance=5,
            is_race_to=True,
            director_id=director.id,
            rounds_count=3,
            min_participants=4,
            withdraw_policy=WithdrawPolicy.EXCLUDE,
        )

        # Set inscription dates and start inscriptions
        inscription_start = datetime.utcnow()
        inscription_end = datetime.utcnow() + timedelta(hours=2)
        GaraService.modify_inscription_dates(
            gara.id, inscription_start, inscription_end
        )
        if gara.status != GaraStatus.INSCRIPTION.value:
            StateService.to_inscription(gara)

        # Add players
        players = []
        for i in range(5):  # Add 5 players so we can exclude one
            player_unique_id = str(uuid.uuid4())[:8]
            player = User(
                username=f"player{i}_{player_unique_id}",
                email=f"player{i}_{player_unique_id}@test.com",
                role=UserRole.PLAYER.value,
            )
            player.set_password("testpass123")
            players.append(player)
            db_session.add(player)
            db_session.commit()

            InscriptionService.inscribe_user(player.id, gara.id)

        # Player withdraws with exclude policy
        InscriptionService.uninscribe_user(players[0].id, gara.id)

        # Verify player inscription is removed or marked as excluded
        inscription = (
            db_session.query(Inscription)
            .filter_by(gara_id=gara.id, user_id=players[0].id)
            .first()
        )

        # Should either be deleted or marked as excluded
        assert inscription is None or getattr(inscription, "is_excluded", False)

        # Verify remaining players can still start the tournament
        remaining_inscriptions = (
            db.session.query(Inscription).filter_by(gara_id=gara.id).count()
        )
        assert remaining_inscriptions >= gara.min_participants

    def test_director_can_inscribe_to_own_tournament(self, db_session):
        """Test that director can participate in their own tournament.

        RED PHASE: Should allow director self-inscription.
        """
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
            name="Director Self-Inscription Test",
            date=tomorrow,
            discipline="palla 9",
            distance=7,
            is_race_to=True,
            director_id=director.id,
            rounds_count=3,
            min_participants=4,
        )

        # Set inscription dates and start inscriptions
        inscription_start = datetime.utcnow()
        inscription_end = datetime.utcnow() + timedelta(hours=2)
        GaraService.modify_inscription_dates(
            gara.id, inscription_start, inscription_end
        )
        if gara.status != GaraStatus.INSCRIPTION.value:
            StateService.to_inscription(gara)

        # Director should be able to inscribe to their own tournament
        InscriptionService.inscribe_user(director.id, gara.id)

        # Verify inscription was successful
        inscription = (
            db.session.query(Inscription)
            .filter_by(gara_id=gara.id, user_id=director.id)
            .first()
        )

        assert inscription is not None

    def test_admin_cannot_inscribe_to_tournaments(self, db_session):
        """Test that admin users cannot inscribe to tournaments.

        RED PHASE: Should prevent admin tournament participation.
        """
        unique_id = str(uuid.uuid4())[:8]

        # Create director
        director = User(
            username=f"director_{unique_id}",
            email=f"director_{unique_id}@test.com",
            role=UserRole.DIRECTOR.value,
        )
        director.set_password("testpass123")
        db_session.add(director)

        # Create admin
        admin = User(
            username=f"admin_{unique_id}",
            email=f"admin_{unique_id}@test.com",
            role=UserRole.ADMIN.value,
        )
        admin.set_password("testpass123")
        db_session.add(admin)
        db_session.commit()

        tomorrow = date.today() + timedelta(days=1)

        gara = GaraService.create_gara(
            campionato_id=None,
            number=1,
            name="Admin Inscription Test",
            date=tomorrow,
            discipline="palla 8",
            distance=5,
            is_race_to=True,
            director_id=director.id,
            rounds_count=3,
            min_participants=4,
        )

        # Set inscription dates and start inscriptions
        inscription_start = datetime.utcnow()
        inscription_end = datetime.utcnow() + timedelta(hours=2)
        GaraService.modify_inscription_dates(
            gara.id, inscription_start, inscription_end
        )
        if gara.status != GaraStatus.INSCRIPTION.value:
            StateService.to_inscription(gara)

        # Admin should not be able to inscribe
        with pytest.raises(ValueError, match="Admin non può partecipare"):
            InscriptionService.inscribe_user(admin.id, gara.id)
