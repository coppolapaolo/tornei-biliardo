"""
Test-Driven Development per InscriptionService extraction.

Estrazione semplice dei metodi di gestione date iscrizioni da GaraService
per centralizzare tutta la logica iscrizioni in un unico service.
"""

import pytest
from datetime import date, timedelta
from models.base import utc_now
from models.status_enum import GaraStatus
from models.competition.models import Gara


class TestInscriptionServiceTDD:
    """TDD tests per guidare l'estrazione dei metodi di gestione date."""

    def test_inscription_service_can_open_inscriptions(
        self, isolated_director_user, db_session
    ):
        """InscriptionService deve poter aprire le iscrizioni."""
        tomorrow = date.today() + timedelta(days=1)

        gara = Gara(
            number=1,
            name="Test Gara",
            date=tomorrow,
            discipline="palla 8",
            distance=5,
            director_id=isolated_director_user.id,
            status=GaraStatus.SETUP.value,
        )
        db_session.add(gara)
        db_session.commit()

        from models.competition.inscription_service import InscriptionService

        # Metodo deve essere spostato da GaraService
        start_time = utc_now() + timedelta(minutes=10)
        end_time = utc_now() + timedelta(days=1)

        result_gara = InscriptionService.open_inscriptions(
            gara.id, start_time, end_time
        )

        assert result_gara.status == GaraStatus.INSCRIPTION.value
        assert result_gara.inscription_start == start_time
        assert result_gara.inscription_end == end_time

    def test_inscription_service_can_modify_inscription_dates(
        self, isolated_director_user, db_session
    ):
        """InscriptionService deve poter modificare le date iscrizioni."""
        tomorrow = date.today() + timedelta(days=1)

        gara = Gara(
            number=1,
            name="Test Gara",
            date=tomorrow,
            discipline="palla 8",
            distance=5,
            director_id=isolated_director_user.id,
            status=GaraStatus.SETUP.value,
        )
        db_session.add(gara)
        db_session.commit()

        from models.competition.inscription_service import InscriptionService

        # Metodo deve essere spostato da GaraService
        new_start = utc_now() + timedelta(minutes=30)
        new_end = utc_now() + timedelta(hours=12)  # Prima della gara

        result_gara = InscriptionService.modify_inscription_dates(
            gara.id, new_start, new_end
        )

        assert result_gara.inscription_start == new_start
        assert result_gara.inscription_end == new_end

    def test_inscription_service_validates_date_order(
        self, isolated_director_user, db_session
    ):
        """InscriptionService deve validare ordine delle date."""
        tomorrow = date.today() + timedelta(days=1)

        gara = Gara(
            number=1,
            name="Test Gara",
            date=tomorrow,
            discipline="palla 8",
            distance=5,
            director_id=isolated_director_user.id,
            status=GaraStatus.SETUP.value,
        )
        db_session.add(gara)
        db_session.commit()

        from models.competition.inscription_service import InscriptionService

        # Date sbagliate: fine prima di inizio
        wrong_start = utc_now() + timedelta(days=2)
        wrong_end = utc_now() + timedelta(days=1)

        with pytest.raises(ValueError, match="precedente"):
            InscriptionService.open_inscriptions(gara.id, wrong_start, wrong_end)
