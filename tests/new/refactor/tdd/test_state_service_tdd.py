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

    # ===== RED PHASE: Test che falliscono =====

    def test_state_service_exists_and_importable(self):
        """RED: StateService deve essere importabile."""
        # Questo test fallirà fino a quando non creiamo StateService
        try:
            from models.competition.state_service import StateService

            assert StateService is not None
        except ImportError:
            pytest.fail("StateService non è ancora implementato")

    def test_state_service_can_transition_to_inscription(
        self, isolated_director_user, db_session
    ):
        """StateService deve gestire transizione setup -> inscription."""
        tomorrow = date.today() + timedelta(days=1)

        gara = Gara(
            number=1,
            name="Test Gara",
            date=tomorrow,
            discipline="palla 8",
            distance=5,
            director_id=isolated_director_user.id,
            status=GaraStatus.SETUP.value,
            inscription_start=datetime.utcnow() + timedelta(minutes=10),
            inscription_end=datetime.utcnow() + timedelta(days=1),
        )
        db_session.add(gara)
        db_session.commit()

        from models.competition.state_service import StateService

        # Interface semplice: Gara → Gara
        result_gara = StateService.to_inscription(gara)

        assert result_gara.status == GaraStatus.INSCRIPTION.value

    def test_state_service_validates_transition_preconditions(
        self, isolated_director_user, db_session
    ):
        """StateService deve validare le precondizioni delle transizioni."""
        tomorrow = date.today() + timedelta(days=1)

        gara = Gara(
            number=1,
            name="Test Gara",
            date=tomorrow,
            discipline="palla 8",
            distance=5,
            director_id=isolated_director_user.id,
            status=GaraStatus.PLAYING.value,  # Stato non valido per inscription
        )
        db_session.add(gara)
        db_session.commit()

        from models.competition.state_service import StateService

        # Deve fallire con uno stato non valido
        with pytest.raises(InvalidTransitionError):
            StateService.to_inscription(gara)

    def test_state_service_can_start_playing(self, isolated_director_user, db_session):
        """StateService deve gestire transizione inscription -> playing."""
        tomorrow = date.today() + timedelta(days=1)

        gara = Gara(
            number=1,
            name="Test Gara",
            date=tomorrow,
            discipline="palla 8",
            distance=5,
            director_id=isolated_director_user.id,
            status=GaraStatus.INSCRIPTION.value,
        )
        db_session.add(gara)
        db_session.commit()

        # Aggiungi iscrizioni (minimo 6 per min_participants default)
        from models.competition.models import Inscription

        inscription1 = Inscription(user_id=isolated_director_user.id, gara_id=gara.id)
        db.session.add(inscription1)

        # Crea 5 giocatori aggiuntivi
        for i in range(2, 7):
            player = User(
                username=f"player{i}_state_test",
                email=f"player{i}_state@test.com",
                role=UserRole.PLAYER.value,
            )
            player.set_password("password123")
            db.session.add(player)
            db.session.commit()
            inscription = Inscription(user_id=player.id, gara_id=gara.id)
            db.session.add(inscription)

        db.session.commit()

        from models.competition.state_service import StateService

        result_gara = StateService.start_playing(gara)

        assert result_gara.status == GaraStatus.PLAYING.value
        assert result_gara.current_round == 1

    def test_state_service_can_complete(self, isolated_director_user, db_session):
        """StateService deve gestire transizione playing -> completed."""
        tomorrow = date.today() + timedelta(days=1)

        gara = Gara(
            number=1,
            name="Test Gara",
            date=tomorrow,
            discipline="palla 8",
            distance=5,
            director_id=isolated_director_user.id,
            status=GaraStatus.PLAYING.value,
            current_round=3,
        )
        db_session.add(gara)
        db_session.commit()

        from models.competition.state_service import StateService

        result_gara = StateService.complete(gara)

        assert result_gara.status == GaraStatus.COMPLETED.value

    def test_state_service_can_reopen_setup(self, isolated_director_user, db_session):
        """StateService deve gestire transizione inscription -> setup."""
        tomorrow = date.today() + timedelta(days=1)

        gara = Gara(
            number=1,
            name="Test Gara",
            date=tomorrow,
            discipline="palla 8",
            distance=5,
            director_id=isolated_director_user.id,
            status=GaraStatus.INSCRIPTION.value,
        )
        db_session.add(gara)
        db_session.commit()

        from models.competition.state_service import StateService

        result_gara = StateService.reopen_setup(gara)

        assert result_gara.status == GaraStatus.SETUP.value

    def test_state_service_validates_inscription_requirements(
        self, isolated_director_user, db_session
    ):
        """StateService deve validare i requisiti per iniziare il gioco."""
        tomorrow = date.today() + timedelta(days=1)

        gara = Gara(
            number=1,
            name="Test Gara",
            date=tomorrow,
            discipline="palla 8",
            distance=5,
            director_id=isolated_director_user.id,
            status=GaraStatus.INSCRIPTION.value,
            min_participants=2,
        )
        db_session.add(gara)
        db_session.commit()

        from models.competition.state_service import StateService

        # Deve fallire senza iscrizioni sufficienti
        with pytest.raises(InvalidTransitionError, match="insufficienti"):
            StateService.start_playing(gara)
