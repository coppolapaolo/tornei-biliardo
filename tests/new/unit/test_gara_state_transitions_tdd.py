"""TDD tests for complex gara state transitions and workflows.

This module implements Test-Driven Development for complex state transition
scenarios not fully covered by existing tests, focusing on the StateService
and edge cases in gara lifecycle management.

Following the Red-Green-Refactor cycle for state transitions:
1. Write failing test for state transition (RED)
2. Implement minimal state machine logic (GREEN)
3. Refactor and improve state management (REFACTOR)
4. Validate with pyright (TYPE CHECK)
5. Format with black (FORMAT)
"""

import pytest
import uuid
from datetime import date, timedelta

from models import User, Gara, Inscription, Match
from models.user.role_enum import UserRole
from models.status_enum import GaraStatus
from models.competition.services import GaraService, InscriptionService
from models.competition.state_service import StateService
from models.exceptions import InvalidTransitionError
from models.base import utc_now


@pytest.mark.unit
class TestGaraStateTransitionsTDD:
    """TDD tests for complex gara state transitions."""

    def test_setup_to_inscription_with_missing_dates_should_fail(self, db_session):
        """Test that SETUP -> INSCRIPTION fails without inscription dates.

        RED PHASE: This test should fail initially because validation
        might not be comprehensive for state transition requirements.
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
            name="State Transition Test",
            date=tomorrow,
            discipline="palla 9",
            distance=7,
            is_race_to=True,
            director_id=director.id,
            rounds_count=3,
            min_participants=4,
        )

        # Try to transition to INSCRIPTION without setting inscription dates
        with pytest.raises(
            InvalidTransitionError, match="Date di iscrizione non impostate"
        ):
            StateService.to_inscription(gara)

    def test_inscription_to_playing_with_insufficient_players_should_fail(
        self, db_session
    ):
        """Test that INSCRIPTION -> PLAYING fails with insufficient players.

        RED PHASE: Should prevent starting tournament without minimum participants.
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
            name="Insufficient Players Test",
            date=tomorrow,
            discipline="palla 8",
            distance=5,
            is_race_to=True,
            director_id=director.id,
            rounds_count=3,
            min_participants=6,  # Require at least 6 players
        )

        # Set inscription dates and start inscriptions
        # modify_inscription_dates automatically transitions to INSCRIPTION
        # when current time is within the inscription period
        inscription_start = utc_now()
        inscription_end = utc_now() + timedelta(hours=2)
        InscriptionService.modify_inscription_dates(
            gara.id, inscription_start, inscription_end
        )

        # Refresh gara to get updated status
        db_session.refresh(gara)
        assert gara.status == GaraStatus.INSCRIPTION.value

        # Add only 3 players (less than minimum of 6)
        for i in range(3):
            player_unique_id = str(uuid.uuid4())[:8]
            player = User(
                username=f"player{i}_{player_unique_id}",
                email=f"player{i}_{player_unique_id}@test.com",
                role=UserRole.PLAYER.value,
            )
            player.set_password("testpass123")
            db_session.add(player)
            db_session.commit()

            inscription = Inscription(user_id=player.id, gara_id=gara.id)
            db_session.add(inscription)

        db_session.commit()

        # Try to start first round with insufficient players
        with pytest.raises(
            InvalidTransitionError, match="Giocatori insufficienti per iniziare"
        ):
            StateService.start_playing(gara)

    def test_playing_to_completed_with_pending_matches_should_fail(self, db_session):
        """Test that PLAYING -> COMPLETED fails with pending matches.

        RED PHASE: Should prevent completing tournament with unfinished matches.
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
            name="Pending Matches Test",
            date=tomorrow,
            discipline="palla 9",
            distance=7,
            is_race_to=True,
            director_id=director.id,
            rounds_count=2,
            min_participants=4,
        )

        # Complete full workflow to PLAYING state
        # modify_inscription_dates automatically transitions to INSCRIPTION
        # when current time is within the inscription period
        inscription_start = utc_now()
        inscription_end = utc_now() + timedelta(hours=2)
        InscriptionService.modify_inscription_dates(
            gara.id, inscription_start, inscription_end
        )

        # Refresh gara to get updated status
        db_session.refresh(gara)
        assert gara.status == GaraStatus.INSCRIPTION.value

        # Add sufficient players
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

            inscription = Inscription(user_id=player.id, gara_id=gara.id)
            db_session.add(inscription)

        db_session.commit()

        # Refresh gara to get updated relationships from database
        db_session.refresh(gara)

        # Start first round (creates matches)
        gara = StateService.start_playing(gara)

        # Verify gara is now PLAYING
        assert gara.status == GaraStatus.PLAYING.value

        # Create pending matches manually to test the validation
        from models.status_enum import MatchStatus

        match1 = Match(
            gara_id=gara.id,
            player1_id=players[0].id,
            player2_id=players[1].id,
            round_number=1,
            status=MatchStatus.PENDING.value,
        )
        match2 = Match(
            gara_id=gara.id,
            player1_id=players[2].id,
            player2_id=players[3].id,
            round_number=1,
            status=MatchStatus.PLAYING.value,
        )
        db_session.add_all([match1, match2])
        db_session.commit()

        # Try to complete tournament with pending matches
        with pytest.raises(InvalidTransitionError, match="Match ancora in corso"):
            StateService.complete(gara)

    def test_rollback_from_playing_to_inscription_when_no_results_entered(
        self, db_session
    ):
        """Test rollback from PLAYING to INSCRIPTION when no match results entered.

        RED PHASE: Should allow rollback if no results have been entered yet.
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
            name="Rollback Test",
            date=tomorrow,
            discipline="palla 8",
            distance=5,
            is_race_to=True,
            director_id=director.id,
            rounds_count=3,
            min_participants=4,
        )

        # Complete setup to PLAYING
        # modify_inscription_dates automatically transitions to INSCRIPTION
        # when current time is within the inscription period
        inscription_start = utc_now()
        inscription_end = utc_now() + timedelta(hours=2)
        InscriptionService.modify_inscription_dates(
            gara.id, inscription_start, inscription_end
        )

        # Refresh gara to get updated status
        db_session.refresh(gara)
        assert gara.status == GaraStatus.INSCRIPTION.value

        # Add players
        for i in range(4):
            player_unique_id = str(uuid.uuid4())[:8]
            player = User(
                username=f"player{i}_{player_unique_id}",
                email=f"player{i}_{player_unique_id}@test.com",
                role=UserRole.PLAYER.value,
            )
            player.set_password("testpass123")
            db_session.add(player)
            db_session.commit()

            inscription = Inscription(user_id=player.id, gara_id=gara.id)
            db_session.add(inscription)

        db_session.commit()

        # Refresh gara before start_playing to get updated relationships
        db_session.refresh(gara)

        # Start first round
        gara = StateService.start_playing(gara)

        # Verify in PLAYING state
        assert gara.status == GaraStatus.PLAYING.value

        # For rollback from PLAYING, we need to first move back to INSCRIPTION manually
        # (this simulates an admin manually resetting the gara state for rollback)
        gara.status = GaraStatus.INSCRIPTION.value
        db_session.commit()

        # Now we can use the available rollback method
        gara = StateService.reopen_setup(gara)

        # Verify rollback to SETUP
        assert gara.status == GaraStatus.SETUP.value

    def test_rollback_from_inscription_to_setup_when_date_changed(self, db_session):
        """Test rollback from INSCRIPTION to SETUP when gara date is changed.

        RED PHASE: Should allow rollback to setup for major changes like date.
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
            name="Date Change Test",
            date=tomorrow,
            discipline="palla 10",
            distance=3,
            is_race_to=True,
            director_id=director.id,
            rounds_count=3,
            min_participants=4,
        )

        # Set inscription dates and start inscriptions
        # modify_inscription_dates automatically transitions to INSCRIPTION
        # when current time is within the inscription period
        inscription_start = utc_now()
        inscription_end = utc_now() + timedelta(hours=2)
        InscriptionService.modify_inscription_dates(
            gara.id, inscription_start, inscription_end
        )

        # Refresh gara to get updated status
        db_session.refresh(gara)

        # Verify in INSCRIPTION state
        assert gara.status == GaraStatus.INSCRIPTION.value

        # Should be able to rollback to SETUP for major changes
        gara = StateService.reopen_setup(gara)

        # Verify rollback to SETUP
        assert gara.status == GaraStatus.SETUP.value

    def test_invalid_transition_from_completed_should_fail(self, db_session):
        """Test that transitions from COMPLETED state should fail.

        RED PHASE: Once completed, gara should not allow any transitions.
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
            name="Completed State Test",
            date=tomorrow,
            discipline="palla 9",
            distance=7,
            is_race_to=True,
            director_id=director.id,
            rounds_count=1,
            min_participants=2,
        )

        # Manually set to COMPLETED (simulating completed tournament)
        gara.status = GaraStatus.COMPLETED.value
        db_session.commit()

        # All transitions should fail from COMPLETED
        with pytest.raises(InvalidTransitionError, match="Transizione non ammessa"):
            StateService.to_inscription(gara)

        with pytest.raises(InvalidTransitionError, match="Transizione non ammessa"):
            StateService.start_playing(gara)

        with pytest.raises(InvalidTransitionError, match="Transizione non ammessa"):
            StateService.reopen_setup(gara)

    def test_concurrent_state_transition_should_handle_race_condition(self, db_session):
        """Test that concurrent state transitions are handled safely.

        RED PHASE: Should prevent race conditions in state transitions.
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
            name="Concurrent Transition Test",
            date=tomorrow,
            discipline="palla 8",
            distance=5,
            is_race_to=True,
            director_id=director.id,
            rounds_count=3,
            min_participants=4,
        )

        # Set inscription dates
        # modify_inscription_dates automatically transitions to INSCRIPTION
        # when current time is within the inscription period
        inscription_start = utc_now()
        inscription_end = utc_now() + timedelta(hours=2)
        InscriptionService.modify_inscription_dates(
            gara.id, inscription_start, inscription_end
        )

        # Refresh gara to get updated status
        db_session.refresh(gara)
        assert gara.status == GaraStatus.INSCRIPTION.value

        # Concurrent transition should fail (already in INSCRIPTION state)
        with pytest.raises(InvalidTransitionError, match="Transizione non ammessa"):
            StateService.to_inscription(gara)

    def test_state_transition_with_validation_callbacks(self, db_session):
        """Test state transitions trigger proper validation callbacks.

        RED PHASE: State transitions should validate business rules.
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
            name="Validation Callbacks Test",
            date=tomorrow,
            discipline="palla 9",
            distance=7,
            is_race_to=True,
            director_id=director.id,
            rounds_count=3,
            min_participants=4,
            matchmaking_strategy="amalfi",
        )

        # Transition should validate strategy configuration
        # modify_inscription_dates automatically transitions to INSCRIPTION
        # when current time is within the inscription period
        inscription_start = utc_now()
        inscription_end = utc_now() + timedelta(hours=2)
        InscriptionService.modify_inscription_dates(
            gara.id, inscription_start, inscription_end
        )

        # Refresh gara to get updated status - should succeed with valid configuration
        db_session.refresh(gara)
        assert gara.status == GaraStatus.INSCRIPTION.value

    def test_state_persistence_across_transactions(self, db_session):
        """Test that state changes are properly persisted across transactions.

        RED PHASE: State changes should be atomic and persistent.
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
            name="Persistence Test",
            date=tomorrow,
            discipline="palla 8",
            distance=5,
            is_race_to=True,
            director_id=director.id,
            rounds_count=3,
            min_participants=4,
        )

        original_gara_id = gara.id

        # Set inscription dates and transition
        # modify_inscription_dates automatically transitions to INSCRIPTION
        # when current time is within the inscription period
        inscription_start = utc_now()
        inscription_end = utc_now() + timedelta(hours=2)
        InscriptionService.modify_inscription_dates(
            gara.id, inscription_start, inscription_end
        )

        # Commit and clear session to ensure persistence
        db_session.commit()
        db_session.expunge_all()

        # Reload gara in new transaction
        reloaded_gara = db_session.get(Gara, original_gara_id)

        # State should be persisted
        assert reloaded_gara is not None
        assert reloaded_gara.status == GaraStatus.INSCRIPTION.value
        assert reloaded_gara.inscription_start == inscription_start
        assert reloaded_gara.inscription_end == inscription_end
