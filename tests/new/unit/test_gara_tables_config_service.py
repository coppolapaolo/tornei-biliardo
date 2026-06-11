"""Test per GaraService.update_tables_config.

La configurazione tavoli (lista in ordine di pregio + flag assegnazione per
classifica) è consentita SOLO tra apertura iscrizioni e avvio della gara.
"""

import pytest
from datetime import date

from models import Gara
from models.status_enum import GaraStatus, Discipline
from models.competition.services import GaraService
from models.exceptions import ConflictError, NotFoundError


@pytest.mark.unit
class TestUpdateTablesConfig:

    def _make_gara(self, db_session, status):
        gara = Gara(
            number=1,
            name="Gara config tavoli",
            date=date.today(),
            discipline=Discipline.NINE_BALL.value,
            distance=4,
            matchmaking_strategy="random",
            status=status,
            rounds_count=3,
            min_participants=6,
        )
        db_session.add(gara)
        db_session.commit()
        return gara

    def test_saves_tables_and_flag_during_inscription(self, db_session):
        gara = self._make_gara(db_session, GaraStatus.INSCRIPTION.value)

        GaraService.update_tables_config(
            gara_id=gara.id,
            tables=["5", "2", "7"],
            assign_tables_by_ranking=True,
        )

        refreshed = db_session.get(Gara, gara.id)
        # L'ordine della lista è significativo (ordine di pregio)
        assert refreshed.get_available_tables() == ["5", "2", "7"]
        assert refreshed.assign_tables_by_ranking is True

    def test_empty_tables_list_falls_back_to_venue(self, db_session):
        gara = self._make_gara(db_session, GaraStatus.INSCRIPTION.value)
        gara.set_available_tables(["1", "2"])
        db_session.commit()

        GaraService.update_tables_config(
            gara_id=gara.id, tables=[], assign_tables_by_ranking=False
        )

        refreshed = db_session.get(Gara, gara.id)
        assert refreshed.available_tables is None
        assert refreshed.assign_tables_by_ranking is False

    @pytest.mark.parametrize(
        "status",
        [GaraStatus.SETUP.value, GaraStatus.PLAYING.value, GaraStatus.COMPLETED.value],
    )
    def test_rejected_outside_inscription_phase(self, db_session, status):
        gara = self._make_gara(db_session, status)

        with pytest.raises(ConflictError):
            GaraService.update_tables_config(
                gara_id=gara.id,
                tables=["1"],
                assign_tables_by_ranking=True,
            )

        refreshed = db_session.get(Gara, gara.id)
        assert refreshed.available_tables is None
        assert refreshed.assign_tables_by_ranking is False

    def test_not_found(self, db_session):
        with pytest.raises(NotFoundError):
            GaraService.update_tables_config(
                gara_id=999999, tables=[], assign_tables_by_ranking=False
            )
