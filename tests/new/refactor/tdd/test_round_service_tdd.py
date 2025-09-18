"""
Test-Driven Development per RoundService extraction.

Estrazione semplice dei metodi di gestione turni da GaraService
per centralizzare tutta la logica round management in un unico service.
"""

import pytest
from datetime import datetime, date, timedelta
from models.base import db
from models.status_enum import GaraStatus
from models.competition.models import Gara, Inscription
from models.user.models import User
from models.user.role_enum import UserRole


class TestRoundServiceTDD:
    """TDD tests per guidare l'estrazione dei metodi di gestione turni."""

    def setup_method(self, method):
        """Setup per ogni test."""
        self.director_user = User(
            username="director_test",
            email="director@test.com",
            role=UserRole.DIRECTOR.value
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

    def test_round_service_can_start_first_round(self):
        """RoundService deve poter avviare il primo turno."""
        tomorrow = date.today() + timedelta(days=1)

        gara = Gara(
            number=1,
            name="Test Gara",
            date=tomorrow,
            discipline="palla 8",
            distance=5,
            director_id=self.director_user.id,
            status=GaraStatus.INSCRIPTION.value
        )
        db.session.add(gara)
        db.session.commit()

        # Aggiungi iscrizioni sufficienti
        inscription1 = Inscription(user_id=self.director_user.id, gara_id=gara.id)

        # Secondo giocatore
        player2 = User(username="player2_test", email="player2@test.com", role=UserRole.PLAYER.value)
        player2.set_password("password123")
        db.session.add(player2)
        db.session.commit()
        inscription2 = Inscription(user_id=player2.id, gara_id=gara.id)

        db.session.add(inscription1)
        db.session.add(inscription2)
        db.session.commit()

        from models.competition.services import RoundService

        # Metodo deve essere spostato da GaraService
        result_gara = RoundService.start_first_round(gara.id)

        assert result_gara.status == GaraStatus.PLAYING.value
        assert result_gara.current_round == 1

    def test_round_service_can_cancel_first_round_startup(self):
        """RoundService deve avere il metodo cancel_first_round_startup."""
        from models.competition.services import RoundService

        # Test che il metodo esista ed è chiamabile
        assert hasattr(RoundService, 'cancel_first_round_startup')
        assert callable(getattr(RoundService, 'cancel_first_round_startup'))

    def test_round_service_can_create_round_with_strategy(self):
        """RoundService deve gestire creazione turno con strategia."""
        tomorrow = date.today() + timedelta(days=1)

        gara = Gara(
            number=1,
            name="Test Gara",
            date=tomorrow,
            discipline="palla 8",
            distance=5,
            director_id=self.director_user.id,
            status=GaraStatus.PLAYING.value,
            current_round=1
        )
        db.session.add(gara)
        db.session.commit()

        from models.competition.services import RoundService

        # Dovrebbe creare un turno usando la strategia
        result = RoundService.create_round_with_strategy(gara.id, round_number=2)

        # Il risultato dipende dalla strategia ma dovrebbe restituire informazioni sui match
        assert result is not None

    def test_round_service_can_preview_round(self):
        """RoundService deve avere il metodo preview_round_with_strategy."""
        from models.competition.services import RoundService

        # Test che il metodo esista ed è chiamabile
        assert hasattr(RoundService, 'preview_round_with_strategy')
        assert callable(getattr(RoundService, 'preview_round_with_strategy'))