"""
Test-Driven Development per InscriptionService extraction.

Estrazione semplice dei metodi di gestione date iscrizioni da GaraService
per centralizzare tutta la logica iscrizioni in un unico service.
"""

import pytest
from datetime import datetime, date, timedelta
from models.base import db
from models.status_enum import GaraStatus
from models.competition.models import Gara
from models.user.models import User
from models.user.role_enum import UserRole


class TestInscriptionServiceTDD:
    """TDD tests per guidare l'estrazione dei metodi di gestione date."""

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

    def test_inscription_service_can_open_inscriptions(self):
        """InscriptionService deve poter aprire le iscrizioni."""
        tomorrow = date.today() + timedelta(days=1)

        gara = Gara(
            number=1,
            name="Test Gara",
            date=tomorrow,
            discipline="palla 8",
            distance=5,
            director_id=self.director_user.id,
            status=GaraStatus.SETUP.value,
        )
        db.session.add(gara)
        db.session.commit()

        from models.competition.services import InscriptionService

        # Metodo deve essere spostato da GaraService
        start_time = datetime.now() + timedelta(minutes=10)
        end_time = datetime.now() + timedelta(days=1)

        result_gara = InscriptionService.open_inscriptions(
            gara.id, start_time, end_time
        )

        assert result_gara.status == GaraStatus.INSCRIPTION.value
        assert result_gara.inscription_start == start_time
        assert result_gara.inscription_end == end_time

    def test_inscription_service_can_modify_inscription_dates(self):
        """InscriptionService deve poter modificare le date iscrizioni."""
        tomorrow = date.today() + timedelta(days=1)

        gara = Gara(
            number=1,
            name="Test Gara",
            date=tomorrow,
            discipline="palla 8",
            distance=5,
            director_id=self.director_user.id,
            status=GaraStatus.SETUP.value,
        )
        db.session.add(gara)
        db.session.commit()

        from models.competition.services import InscriptionService

        # Metodo deve essere spostato da GaraService
        new_start = datetime.now() + timedelta(minutes=30)
        new_end = datetime.now() + timedelta(hours=12)  # Prima della gara

        result_gara = InscriptionService.modify_inscription_dates(
            gara.id, new_start, new_end
        )

        assert result_gara.inscription_start == new_start
        assert result_gara.inscription_end == new_end

    def test_inscription_service_validates_date_order(self):
        """InscriptionService deve validare ordine delle date."""
        tomorrow = date.today() + timedelta(days=1)

        gara = Gara(
            number=1,
            name="Test Gara",
            date=tomorrow,
            discipline="palla 8",
            distance=5,
            director_id=self.director_user.id,
            status=GaraStatus.SETUP.value,
        )
        db.session.add(gara)
        db.session.commit()

        from models.competition.services import InscriptionService

        # Date sbagliate: fine prima di inizio
        wrong_start = datetime.now() + timedelta(days=2)
        wrong_end = datetime.now() + timedelta(days=1)

        with pytest.raises(ValueError, match="precedente"):
            InscriptionService.open_inscriptions(gara.id, wrong_start, wrong_end)
