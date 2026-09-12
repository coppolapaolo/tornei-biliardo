"""Integration test per la route admin.competition.update_tables_config.

Sezione "Tavoli della gara" in «Impostazioni gara» (dal 2026-09-12 la pagina
del direttore e' a fasi e i tavoli stanno li'): salvataggio della lista
tavoli (in ordine di pregio) e del flag "assegna tavoli in base alla
classifica", consentito solo tra apertura iscrizioni e avvio gara.
"""

import pytest
from datetime import date

from models import Gara
from models.status_enum import GaraStatus, Discipline


@pytest.mark.integration
class TestTablesConfigRoute:

    def _make_gara(self, db_session, status=GaraStatus.INSCRIPTION.value):
        gara = Gara(
            number=1,
            name="Gara route tavoli",
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

    def test_section_visible_in_impostazioni_during_inscription(
        self, logged_in_client, db_session
    ):
        client, _ = logged_in_client(role="admin")
        gara = self._make_gara(db_session)

        response = client.get(f"/admin/gara/{gara.id}/impostazioni")

        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert 'id="sezioneTavoli"' in html
        assert "assign_tables_by_ranking" in html  # checkbox (strategia random)
        assert f"/admin/gara/{gara.id}/tables-config" in html

    def test_form_not_prefilled_with_venue_fallback(self, logged_in_client, db_session):
        """Se available_tables è vuoto il campo NON va precompilato con i
        tavoli della sala: un submit senza modifiche congelerebbe la lista
        perdendo il fallback dinamico (rilievo Copilot PR #37)."""
        from models import BilliardHall

        client, _ = logged_in_client(role="admin")
        venue = BilliardHall(
            name="Sala Prefill Test",
            number_of_tables=2,
            is_active=True,
            verified=True,
        )
        venue.set_table_names(["Alpha", "Beta"])
        db_session.add(venue)
        db_session.commit()

        gara = self._make_gara(db_session)
        gara.billiard_hall_id = venue.id
        db_session.commit()
        assert gara.get_available_tables() == ["Alpha", "Beta"]  # fallback attivo

        response = client.get(f"/admin/gara/{gara.id}/impostazioni")

        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert 'id="sezioneTavoli"' in html
        assert 'value="Alpha, Beta"' not in html

    def test_admin_saves_tables_and_flag(self, logged_in_client, db_session):
        client, _ = logged_in_client(role="admin")
        gara = self._make_gara(db_session)

        response = client.post(
            f"/admin/gara/{gara.id}/tables-config",
            data={
                "available_tables": " 5 , 2, 7 ",
                "assign_tables_by_ranking": "on",
            },
        )

        assert response.status_code == 302
        refreshed = db_session.get(Gara, gara.id)
        assert refreshed.get_available_tables() == ["5", "2", "7"]
        assert refreshed.assign_tables_by_ranking is True

    def test_checkbox_absent_disables_flag(self, logged_in_client, db_session):
        client, _ = logged_in_client(role="admin")
        gara = self._make_gara(db_session)
        gara.assign_tables_by_ranking = True
        db_session.commit()

        response = client.post(
            f"/admin/gara/{gara.id}/tables-config",
            data={"available_tables": "1, 2"},
        )

        assert response.status_code == 302
        refreshed = db_session.get(Gara, gara.id)
        assert refreshed.assign_tables_by_ranking is False

    def test_rejected_when_gara_is_playing(self, logged_in_client, db_session):
        client, _ = logged_in_client(role="admin")
        gara = self._make_gara(db_session, status=GaraStatus.PLAYING.value)

        response = client.post(
            f"/admin/gara/{gara.id}/tables-config",
            data={"available_tables": "1"},
            follow_redirects=False,
        )

        # La route fa flash dell'errore e redirige al dettaglio gara
        assert response.status_code == 302
        refreshed = db_session.get(Gara, gara.id)
        assert refreshed.available_tables is None

    def test_player_cannot_save(self, logged_in_client, db_session):
        client, _ = logged_in_client(role="player")
        gara = self._make_gara(db_session)

        response = client.post(
            f"/admin/gara/{gara.id}/tables-config",
            data={"available_tables": "1"},
        )

        # gara_manager_required blocca i non gestori (redirect o 403)
        assert response.status_code in (302, 403)
        refreshed = db_session.get(Gara, gara.id)
        assert refreshed.available_tables is None
