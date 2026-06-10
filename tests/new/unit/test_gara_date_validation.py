"""
Test per la validazione delle date delle gare.

Regole:
1. La data di una gara non può essere nel passato (già implementato)
2. Per gare di campionato: la data/ora della gara N deve essere:
   - >= della gara con numero più alto < N (se esiste)
   - <= della gara con numero più basso > N (se esiste)
"""

import pytest
from datetime import date, time, timedelta
from models.competition.services import GaraService
from models.campionato.services import TournamentService


class TestGaraDateValidationPastDate:
    """Test validazione date nel passato."""

    def test_create_gara_with_past_date_raises_error(
        self, db_session, isolated_director_user
    ):
        """Creare una gara con data nel passato solleva ValueError."""
        yesterday = date.today() - timedelta(days=1)

        with pytest.raises(ValueError, match="passato"):
            GaraService.create_gara(
                number=1,
                name="Gara Test",
                date=yesterday,
                time=time(20, 0),
                discipline="palla_8",
                distance=5,
                director_id=isolated_director_user.id,
            )

    def test_create_gara_with_today_is_valid(self, db_session, isolated_director_user):
        """Creare una gara con data odierna è valido."""
        today = date.today()

        gara = GaraService.create_gara(
            number=1,
            name="Gara Oggi",
            date=today,
            time=time(20, 0),
            discipline="palla_8",
            distance=5,
            director_id=isolated_director_user.id,
        )

        assert gara is not None
        assert gara.date == today


class TestGaraSequentialDateValidation:
    """Test validazione date sequenziali per gare di campionato."""

    @pytest.fixture
    def campionato_with_gara1(self, db_session, isolated_director_user):
        """Crea un campionato con una gara esistente."""
        tournament_service = TournamentService()
        campionato = tournament_service.create_campionato_with_director(
            name="Campionato Test Date",
            creator_user_id=isolated_director_user.id,
        )
        db_session.commit()

        # Gara 1: oggi alle 18:00
        gara1 = GaraService.create_gara(
            number=1,
            name="Gara 1",
            date=date.today(),
            time=time(18, 0),
            discipline="palla_8",
            distance=5,
            campionato_id=campionato.id,
        )
        db_session.commit()

        return campionato, gara1

    def test_gara2_must_be_after_gara1(self, db_session, campionato_with_gara1):
        """Gara 2 deve avere data/ora >= gara 1."""
        campionato, _ = campionato_with_gara1

        # Gara 2 con stessa data ma ora precedente = errore
        with pytest.raises(ValueError, match="successiva"):
            GaraService.create_gara(
                number=2,
                name="Gara 2",
                date=date.today(),
                time=time(17, 0),  # prima di gara 1 (18:00)
                discipline="palla_8",
                distance=5,
                campionato_id=campionato.id,
            )

    def test_gara2_same_day_later_time_is_valid(
        self, db_session, campionato_with_gara1
    ):
        """Gara 2 stesso giorno con ora successiva è valido."""
        campionato, _ = campionato_with_gara1

        gara2 = GaraService.create_gara(
            number=2,
            name="Gara 2",
            date=date.today(),
            time=time(20, 0),  # dopo gara 1 (18:00)
            discipline="palla_8",
            distance=5,
            campionato_id=campionato.id,
        )

        assert gara2 is not None
        assert gara2.time == time(20, 0)

    def test_gara2_next_day_is_valid(self, db_session, campionato_with_gara1):
        """Gara 2 il giorno dopo è valido."""
        campionato, _ = campionato_with_gara1

        tomorrow = date.today() + timedelta(days=1)
        gara2 = GaraService.create_gara(
            number=2,
            name="Gara 2",
            date=tomorrow,
            time=time(10, 0),  # anche prima come ora, ma giorno dopo
            discipline="palla_8",
            distance=5,
            campionato_id=campionato.id,
        )

        assert gara2 is not None
        assert gara2.date == tomorrow

    @pytest.fixture
    def campionato_with_gara1_and_gara3(self, db_session, isolated_director_user):
        """Crea un campionato con gara 1 e gara 3 (gap in mezzo)."""
        tournament_service = TournamentService()
        campionato = tournament_service.create_campionato_with_director(
            name="Campionato Test Gap",
            creator_user_id=isolated_director_user.id,
        )
        db_session.commit()

        today = date.today()
        in_5_days = today + timedelta(days=5)

        GaraService.create_gara(
            number=1,
            name="Gara 1",
            date=today,
            time=time(18, 0),
            discipline="palla_8",
            distance=5,
            campionato_id=campionato.id,
        )
        db_session.commit()

        gara3 = GaraService.create_gara(
            number=3,
            name="Gara 3",
            date=in_5_days,
            time=time(20, 0),
            discipline="palla_8",
            distance=5,
            campionato_id=campionato.id,
        )
        db_session.commit()

        return campionato, gara3

    def test_gara2_must_be_between_gara1_and_gara3(
        self, db_session, campionato_with_gara1_and_gara3
    ):
        """Gara 2 deve essere >= gara 1 e <= gara 3."""
        campionato, _ = campionato_with_gara1_and_gara3

        # Gara 2 prima di gara 1 = errore (anche per data nel passato)
        yesterday = date.today() - timedelta(days=1)
        with pytest.raises(ValueError):
            GaraService.create_gara(
                number=2,
                name="Gara 2",
                date=yesterday,
                time=time(18, 0),
                discipline="palla_8",
                distance=5,
                campionato_id=campionato.id,
            )

    def test_gara2_after_gara3_raises_error(
        self, db_session, campionato_with_gara1_and_gara3
    ):
        """Gara 2 dopo gara 3 solleva errore."""
        campionato, _ = campionato_with_gara1_and_gara3

        # Gara 2 dopo gara 3 = errore
        in_10_days = date.today() + timedelta(days=10)
        with pytest.raises(ValueError, match="precedente"):
            GaraService.create_gara(
                number=2,
                name="Gara 2",
                date=in_10_days,
                time=time(18, 0),
                discipline="palla_8",
                distance=5,
                campionato_id=campionato.id,
            )

    def test_gara2_between_gara1_and_gara3_is_valid(
        self, db_session, campionato_with_gara1_and_gara3
    ):
        """Gara 2 con data tra gara 1 e gara 3 è valido."""
        campionato, _ = campionato_with_gara1_and_gara3

        in_2_days = date.today() + timedelta(days=2)
        gara2 = GaraService.create_gara(
            number=2,
            name="Gara 2",
            date=in_2_days,
            time=time(18, 0),
            discipline="palla_8",
            distance=5,
            campionato_id=campionato.id,
        )

        assert gara2 is not None
        assert gara2.date == in_2_days


class TestStandaloneGaraNoSequentialValidation:
    """Test che le gare standalone NON hanno validazione sequenziale."""

    def test_standalone_gara_ignores_sequential_validation(
        self, db_session, isolated_director_user
    ):
        """Le gare standalone non richiedono validazione sequenziale."""
        today = date.today()

        # Standalone gara - number è sempre 1, nessuna validazione sequenziale
        gara = GaraService.create_gara(
            number=1,
            name="Gara Standalone",
            date=today,
            time=time(20, 0),
            discipline="palla_8",
            distance=5,
            director_id=isolated_director_user.id,
        )

        assert gara is not None
        assert gara.campionato_id is None
