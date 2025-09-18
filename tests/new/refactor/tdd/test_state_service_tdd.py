"""
Test-Driven Development per StateService extraction.

Estrazione semplice dei metodi di ProvaStateMachine per seguire SRP.
Mantiene la stessa interfaccia esistente (Gara → Gara) senza sovraingegnerizzare.
"""

import pytest
from datetime import datetime, date, timedelta
from models.base import db
from models.status_enum import GaraStatus
from models.exceptions import InvalidTransitionError
from models.competition.models import Gara
from models.user.models import User
from models.user.role_enum import UserRole


class TestStateServiceTDD:
    """TDD tests per guidare lo sviluppo di StateService."""

    def setup_method(self, method):
        """Setup per ogni test."""
        self.director_user = User(
            username="director_test",
            email="director@test.com",
            role=UserRole.DIRECTOR.value,
        )
        self.director_user.set_password("password123")
        db.session.add(self.director_user)
        db.session.commit()

    def teardown_method(self, method):
        """Cleanup dopo ogni test."""
        try:
            db.session.query(Gara).delete()
            db.session.commit()
            db.session.query(User).delete()
            db.session.commit()
        except Exception:
            db.session.rollback()

    # ===== RED PHASE: Test che falliscono =====

    def test_state_service_exists_and_importable(self):
        """RED: StateService deve essere importabile."""
        # Questo test fallirà fino a quando non creiamo StateService
        try:
            from models.competition.state_service import StateService

            assert StateService is not None
        except ImportError:
            pytest.fail("StateService non è ancora implementato")

    def test_state_service_can_transition_to_inscription(self):
        """StateService deve gestire transizione setup -> inscription."""
        tomorrow = date.today() + timedelta(days=1)

        gara = Gara(
            number=1,
            name="Test Gara",
            date=tomorrow,
            discipline="palla 8",
            distance=5,
            director_id=self.director_user.id,
            status=GaraStatus.SETUP.value,
            inscription_start=datetime.now() + timedelta(minutes=10),
            inscription_end=datetime.now() + timedelta(days=1),
        )
        db.session.add(gara)
        db.session.commit()

        from models.competition.state_service import StateService

        # Interface semplice: Gara → Gara
        result_gara = StateService.to_inscription(gara)

        assert result_gara.status == GaraStatus.INSCRIPTION.value

    def test_state_service_validates_transition_preconditions(self):
        """StateService deve validare le precondizioni delle transizioni."""
        tomorrow = date.today() + timedelta(days=1)

        gara = Gara(
            number=1,
            name="Test Gara",
            date=tomorrow,
            discipline="palla 8",
            distance=5,
            director_id=self.director_user.id,
            status=GaraStatus.PLAYING.value,  # Stato non valido per inscription
        )
        db.session.add(gara)
        db.session.commit()

        from models.competition.state_service import StateService

        # Deve fallire con uno stato non valido
        with pytest.raises(InvalidTransitionError):
            StateService.to_inscription(gara)

    def test_state_service_can_start_playing(self):
        """StateService deve gestire transizione inscription -> playing."""
        tomorrow = date.today() + timedelta(days=1)

        gara = Gara(
            number=1,
            name="Test Gara",
            date=tomorrow,
            discipline="palla 8",
            distance=5,
            director_id=self.director_user.id,
            status=GaraStatus.INSCRIPTION.value,
        )
        db.session.add(gara)
        db.session.commit()

        # Aggiungi iscrizioni (minimo 2)
        from models.competition.models import Inscription

        # Crea secondo giocatore
        from models.user.models import User
        from models.user.role_enum import UserRole

        player2 = User(
            username="player2_test",
            email="player2@test.com",
            role=UserRole.PLAYER.value,
        )
        player2.set_password("password123")
        db.session.add(player2)
        db.session.commit()

        inscription1 = Inscription(user_id=self.director_user.id, gara_id=gara.id)
        inscription2 = Inscription(user_id=player2.id, gara_id=gara.id)
        db.session.add(inscription1)
        db.session.add(inscription2)
        db.session.commit()

        from models.competition.state_service import StateService

        result_gara = StateService.start_playing(gara)

        assert result_gara.status == GaraStatus.PLAYING.value
        assert result_gara.current_round == 1

    def test_state_service_can_complete(self):
        """StateService deve gestire transizione playing -> completed."""
        tomorrow = date.today() + timedelta(days=1)

        gara = Gara(
            number=1,
            name="Test Gara",
            date=tomorrow,
            discipline="palla 8",
            distance=5,
            director_id=self.director_user.id,
            status=GaraStatus.PLAYING.value,
            current_round=3,
        )
        db.session.add(gara)
        db.session.commit()

        from models.competition.state_service import StateService

        result_gara = StateService.complete(gara)

        assert result_gara.status == GaraStatus.COMPLETED.value

    def test_state_service_can_reopen_setup(self):
        """StateService deve gestire transizione inscription -> setup."""
        tomorrow = date.today() + timedelta(days=1)

        gara = Gara(
            number=1,
            name="Test Gara",
            date=tomorrow,
            discipline="palla 8",
            distance=5,
            director_id=self.director_user.id,
            status=GaraStatus.INSCRIPTION.value,
        )
        db.session.add(gara)
        db.session.commit()

        from models.competition.state_service import StateService

        result_gara = StateService.reopen_setup(gara)

        assert result_gara.status == GaraStatus.SETUP.value

    def test_state_service_validates_inscription_requirements(self):
        """StateService deve validare i requisiti per iniziare il gioco."""
        tomorrow = date.today() + timedelta(days=1)

        gara = Gara(
            number=1,
            name="Test Gara",
            date=tomorrow,
            discipline="palla 8",
            distance=5,
            director_id=self.director_user.id,
            status=GaraStatus.INSCRIPTION.value,
            min_participants=2,
        )
        db.session.add(gara)
        db.session.commit()

        from models.competition.state_service import StateService

        # Deve fallire senza iscrizioni sufficienti
        with pytest.raises(InvalidTransitionError, match="insufficienti"):
            StateService.start_playing(gara)
