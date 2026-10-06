"""Il limite di tempo su una gara singola, dalle route (ADR-077).

Le regole stanno nei test di unità (`tests/new/unit/test_limite_di_tempo.py`).
Qui si verifica il giunto interfaccia↔server: il modulo della gara singola
salva il limite, la partita nasce col suo, «Avvia partita» lo fa partire per
chi gioca e per chi dirige e lo rifiuta a chi non c'entra, le pagine mostrano
il timer — e una gara senza limite resta quella di sempre.
"""

from __future__ import annotations

import pytest

from gara_driver import GaraDriver
from models import db
from models.match.models import Match
from models.user.role_enum import UserRole


def _gara(driver: GaraDriver, **opzioni):
    direttore = driver.crea_utente(UserRole.DIRECTOR.value)
    giocatori = driver.crea_giocatori(4)
    driver.entra(direttore)
    gara_id = driver.crea_gara(min_participants=4, start_rule="first_player", **opzioni)
    driver.apri_iscrizioni(gara_id)
    driver.iscrivi_tutti(gara_id, giocatori)
    driver.entra(direttore)
    driver.avvia_primo_turno(gara_id)
    return gara_id, direttore, {g.id: g for g in giocatori}


@pytest.mark.e2e
class TestLimiteDiTempoSullaGaraSingola:
    def test_il_modulo_salva_il_limite_e_la_partita_nasce_col_suo(
        self, driver: GaraDriver
    ):
        gara_id, _, _ = _gara(driver, time_limit_minutes=30)
        assert driver.gara(gara_id).time_limit_minutes == 30
        partite = driver.partite(gara_id, turno=1)
        assert partite and all(p.time_limit_minutes == 30 for p in partite)
        assert all(p.timer_started_at is None for p in partite)

    def test_un_giocatore_avvia_e_il_timer_compare(self, driver: GaraDriver):
        gara_id, _, per_id = _gara(driver, time_limit_minutes=30)
        partita = driver.partite(gara_id, turno=1)[0]
        uno = per_id[partita.player1_id]

        driver.entra(uno)
        pagina = driver.client.get(f"/admin/match/{partita.id}").get_data(as_text=True)
        assert "Avvia partita" in pagina

        risposta = driver.client.post(f"/player/match/{partita.id}/avvia")
        assert risposta.status_code == 200, risposta.get_data(as_text=True)
        assert risposta.get_json()["time_limit_minutes"] == 30
        assert db.session.get(Match, partita.id).timer_started_at is not None

        pagina = driver.client.get(f"/admin/match/{partita.id}").get_data(as_text=True)
        assert "data-timer-inizio" in pagina
        assert "Avvia partita" not in pagina

    def test_chi_non_gioca_quella_partita_non_la_avvia(self, driver: GaraDriver):
        gara_id, _, per_id = _gara(driver, time_limit_minutes=30)
        prima, seconda = driver.partite(gara_id, turno=1)[:2]
        estraneo = per_id[seconda.player1_id]

        driver.entra(estraneo)
        risposta = driver.client.post(f"/player/match/{prima.id}/avvia")
        # `match_player_required` rimanda indietro chi non gioca: il servizio,
        # dietro, risponderebbe 403 (test di unità).
        assert risposta.status_code in (302, 403)
        assert db.session.get(Match, prima.id).timer_started_at is None

    def test_il_direttore_avvia_dalla_card(self, driver: GaraDriver):
        gara_id, direttore, _ = _gara(driver, time_limit_minutes=30)
        partita = driver.partite(gara_id, turno=1)[0]

        driver.entra(direttore)
        pagina = driver.pagina_gara(gara_id)
        assert "avviaDallaCard" in pagina
        risposta = driver.client.post(f"/admin/match/{partita.id}/avvia")
        assert risposta.status_code == 200, risposta.get_data(as_text=True)
        assert db.session.get(Match, partita.id).timer_started_at is not None
        assert "data-timer-inizio" in driver.pagina_gara(gara_id)

    def test_senza_limite_la_gara_e_quella_di_sempre(self, driver: GaraDriver):
        gara_id, direttore, per_id = _gara(driver)
        partita = driver.partite(gara_id, turno=1)[0]
        assert partita.time_limit_minutes is None

        assert "c7-timer" not in driver.pagina_gara(gara_id)
        driver.entra(per_id[partita.player1_id])
        pagina = driver.client.get(f"/admin/match/{partita.id}").get_data(as_text=True)
        assert "Avvia partita" not in pagina
        assert "c7-timer" not in pagina
        risposta = driver.client.post(f"/player/match/{partita.id}/avvia")
        assert risposta.status_code == 422
