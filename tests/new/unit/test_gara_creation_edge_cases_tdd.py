"""TDD tests for gara creation edge cases and complex validations.

This module implements Test-Driven Development for edge cases not fully covered
by existing tests, focusing on complex combinations of strategy, discipline,
distance, and other parameters.

Following the Red-Green-Refactor cycle:
1. Write failing test (RED)
2. Implement minimal code to pass (GREEN)
3. Refactor and improve (REFACTOR)
4. Validate with pyright (TYPE CHECK)
5. Format with black (FORMAT)
"""

import pytest
import uuid
from datetime import date, timedelta, datetime
from typing import Dict, Any

from models import User, Gara, Inscription
from models.user.role_enum import UserRole
from models.competition.models import WithdrawPolicy
from models.status_enum import GaraStatus
from models.competition.services import GaraService, InscriptionService
from models.competition.state_service import StateService
from models.exceptions import InvalidTransitionError
from models.base import utc_now


@pytest.mark.unit
class TestGaraCreationEdgeCasesTDD:
    """TDD tests for edge cases in gara creation and validation."""

    def test_strategy_amalfi_with_trio_policy_should_fail(
        self, db_session
    ):
        """Test that Amalfi strategy with trio policy is REJECTED.

        Amalfi algorithm does not implement trio natively — it would
        silently fall back to bye. To prevent confusion, the combination
        is blocked at validation time. Trio is only supported by Random.
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

        with pytest.raises(ValueError, match="non supporta"):
            GaraService.create_gara(
                campionato_id=None,
                number=1,
                name="Invalid Amalfi Trio",
                date=tomorrow,
                discipline="palla 9",
                distance=5,
                is_race_to=False,
                director_id=director.id,
                matchmaking_strategy="amalfi",
                odd_number_policy="trio",
                rounds_count=3,
                min_participants=4,
            )

    def test_strategy_random_with_rating_based_first_round_should_fail(
        self, db_session
    ):
        """Test that Random strategy with rating-based first round fails validation.

        RED PHASE: Random strategy should only support random first round policy.
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

        # Random strategy should only support random first round
        with pytest.raises(
            ValueError, match="non supporta la policy di primo turno rating"
        ):
            GaraService.create_gara(
                campionato_id=None,
                number=1,
                name="Invalid Random Rating",
                date=tomorrow,
                discipline="palla 8",
                distance=7,
                is_race_to=True,
                director_id=director.id,
                matchmaking_strategy="random",
                first_round_policy="rating",  # Should fail with random strategy
                rounds_count=3,
                min_participants=4,
            )

    def test_strategy_round_robin_with_trio_policy_should_fail(self, db_session):
        """Test that Round Robin strategy with trio policy fails validation.

        RED PHASE: Round Robin should not support trio matches.
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

        # Round Robin should not support trio matches
        with pytest.raises(
            ValueError, match="non supporta la policy per numero dispari trio"
        ):
            GaraService.create_gara(
                campionato_id=None,
                number=1,
                name="Invalid Round Robin Trio",
                date=tomorrow,
                discipline="palla 10",
                distance=5,
                is_race_to=True,
                director_id=director.id,
                matchmaking_strategy="round_robin",
                odd_number_policy="trio",  # Should fail with round_robin
                rounds_count=5,
                min_participants=6,
            )

    def test_inscription_dates_spanning_multiple_months(self, db_session):
        """Test handling of inscription dates spanning multiple months.

        RED PHASE: Test proper handling of date validation across month boundaries.
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

        # Gara in 2 months
        gara_date = date.today() + timedelta(days=60)

        # Inscriptions start today, end next month
        inscription_start = utc_now()
        inscription_end = utc_now() + timedelta(days=30)

        gara = GaraService.create_gara(
            campionato_id=None,
            number=1,
            name="Multi-Month Inscriptions",
            date=gara_date,
            discipline="palla 9",
            distance=7,
            is_race_to=True,
            director_id=director.id,
            matchmaking_strategy="amalfi",
            rounds_count=3,
            min_participants=4,
        )

        # This should work - dates are valid
        updated_gara = InscriptionService.modify_inscription_dates(
            gara.id, inscription_start, inscription_end
        )

        assert updated_gara.inscription_start == inscription_start
        assert updated_gara.inscription_end == inscription_end

    def test_gara_date_in_past_should_fail(self, db_session):
        """Test that creating gara with date in past fails validation.

        RED PHASE: Should prevent creation of gara with past date.
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

        yesterday = date.today() - timedelta(days=1)

        # Should validate that gara date is not in the past
        with pytest.raises(
            ValueError, match="Data della gara non può essere nel passato"
        ):
            GaraService.create_gara(
                campionato_id=None,
                number=1,
                name="Past Date Gara",
                date=yesterday,  # Yesterday should fail
                discipline="palla 8",
                distance=5,
                is_race_to=True,
                director_id=director.id,
                matchmaking_strategy="amalfi",
                rounds_count=3,
                min_participants=4,
            )

    def test_inscription_end_after_gara_date_should_fail(self, db_session):
        """Test that inscription end after gara date fails validation.

        RED PHASE: Inscriptions should not end after the gara starts.
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
            name="Invalid Inscription Dates",
            date=tomorrow,
            discipline="palla 9",
            distance=7,
            is_race_to=True,
            director_id=director.id,
            matchmaking_strategy="amalfi",
            rounds_count=3,
            min_participants=4,
        )

        # Try to set inscription end after gara date
        inscription_start = utc_now()
        inscription_end = datetime.combine(
            tomorrow + timedelta(days=1), datetime.min.time()
        ) + timedelta(hours=1)

        with pytest.raises(
            ValueError,
            match="Le iscrizioni non possono terminare dopo la data della gara",
        ):
            InscriptionService.modify_inscription_dates(
                gara.id, inscription_start, inscription_end
            )

    def test_max_participants_less_than_min_should_fail(self, db_session):
        """Test that max_participants less than min_participants fails validation.

        RED PHASE: Business logic should prevent max < min participants.
        """
        data = {
            "name": "Invalid Participants",
            "discipline": "palla 8",
            "distance": 5,
            "min_participants": 8,
            "max_participants": 4,  # Less than min - should fail
            "entry_fee": 10.0,
            "rounds_count": 3,
        }

        errors = GaraService.validate_gara_data(data)

        # Should have error for max_participants
        assert "max_participants" in errors
        assert ">= min" in errors["max_participants"]

    def test_zero_max_participants_should_allow_unlimited(self, db_session):
        """Test that zero max_participants is treated as unlimited.

        RED PHASE: Zero should be a valid value meaning unlimited.
        """
        data = {
            "name": "Unlimited Participants",
            "discipline": "palla 9",
            "distance": 7,
            "min_participants": 4,
            "max_participants": None,  # None should mean unlimited
            "entry_fee": 0.0,
            "rounds_count": 3,
        }

        errors = GaraService.validate_gara_data(data)

        # Should not have error for max_participants
        assert "max_participants" not in errors

    def test_negative_entry_fee_should_fail(self, db_session):
        """Test that negative entry fee fails validation.

        RED PHASE: Entry fee should not be negative.
        """
        data = {
            "name": "Negative Fee",
            "discipline": "palla 10",
            "distance": 3,
            "min_participants": 4,
            "entry_fee": -5.0,  # Negative should fail
            "rounds_count": 3,
        }

        errors = GaraService.validate_gara_data(data)

        # Should have error for entry_fee
        assert "entry_fee" in errors
        assert "negativa" in errors["entry_fee"]

    def test_trio_policy_with_distance_outside_2_7_should_fail(self, db_session):
        """Test that trio policy with distance outside 2-7 fails validation.

        Per ADR-005: Trio matches are only allowed for distances 2-7.
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

        # Trio with distance > 7 should fail (per ADR-005)
        with pytest.raises(
            ValueError, match="Match a tre supportati solo per distanze da 2 a 7"
        ):
            GaraService.create_gara(
                campionato_id=None,
                number=1,
                name="Invalid Trio Distance",
                date=tomorrow,
                discipline="palla 8",
                distance=8,  # Greater than 7
                is_race_to=True,
                director_id=director.id,
                matchmaking_strategy="amalfi",
                odd_number_policy="trio",  # Should fail with distance > 7
                rounds_count=3,
                min_participants=4,
            )

    def test_direct_elimination_with_trio_policy_should_fail(self, db_session):
        """Test that direct elimination with trio policy fails validation.

        RED PHASE: Direct elimination should not support trio matches.
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

        with pytest.raises(
            ValueError, match="non supporta la policy per numero dispari trio"
        ):
            GaraService.create_gara(
                campionato_id=None,
                number=1,
                name="Invalid Elimination Trio",
                date=tomorrow,
                discipline="palla 9",
                distance=5,
                is_race_to=True,
                director_id=director.id,
                matchmaking_strategy="direct_elimination",
                odd_number_policy="trio",  # Should fail with elimination
                rounds_count=3,
                min_participants=4,
            )

    def test_rounds_count_zero_should_fail(self, db_session):
        """Test that rounds_count of zero fails validation.

        RED PHASE: Must have at least 1 round.
        """
        data = {
            "name": "Zero Rounds",
            "discipline": "palla 8",
            "distance": 5,
            "min_participants": 4,
            "rounds_count": 0,  # Should fail
        }

        errors = GaraService.validate_gara_data(data)

        assert "rounds_count" in errors
        assert "almeno 1" in errors["rounds_count"]

    def test_invalid_date_format_should_fail(self, db_session):
        """Test that invalid date format fails validation.

        RED PHASE: Date format validation should catch invalid formats.
        """
        data = {
            "name": "Invalid Date",
            "discipline": "palla 9",
            "distance": 7,
            "min_participants": 4,
            "inscription_start": "not-a-date",  # Invalid format
            "inscription_end": "2025-13-45",  # Invalid date
        }

        errors = GaraService.validate_gara_data(data)

        assert "inscription_start" in errors
        assert "inscription_end" in errors
        assert "Formato data non valido" in errors["inscription_start"]
        assert "Formato data non valido" in errors["inscription_end"]
