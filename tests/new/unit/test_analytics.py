"""Test per l'integrazione Google Analytics 4.

Il rischio principale non è che il tracking non funzioni: è che funzioni
*troppo*, cioè che lo snippet finisca anche in sviluppo e nei test e inquini
le statistiche di produzione con traffico finto. Per questo il primo test
verifica l'assenza dello snippet, non la sua presenza.
"""

import json

from flask import get_flashed_messages

from utils.analytics import ANALYTICS_FLASH_CATEGORY, AnalyticsEvent, track_event
from utils.feature_flags import ENDPOINT_ROLES

GA_TEST_ID = "G-TEST12345"


class TestAnalyticsSnippetRendering:
    """Lo snippet GA deve comparire solo quando l'ID è configurato."""

    def test_snippet_assente_senza_measurement_id(self, client):
        """TestingConfig non ha GA_MEASUREMENT_ID: nessuna richiesta a Google."""
        response = client.get("/privacy")

        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert "googletagmanager.com" not in html
        assert "gtag(" not in html

    def test_snippet_presente_con_measurement_id(self, app, client, monkeypatch):
        monkeypatch.setitem(app.config, "GA_MEASUREMENT_ID", GA_TEST_ID)

        response = client.get("/privacy")

        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert "googletagmanager.com/gtag/js?id=" + GA_TEST_ID in html
        assert GA_TEST_ID in html

    def test_sezione_cookie_analitici_solo_se_ga_attivo(self, app, client, monkeypatch):
        """L'informativa non deve dichiarare cookie che il sito non usa."""
        senza_ga = client.get("/privacy").get_data(as_text=True)
        assert "Google Analytics" not in senza_ga

        monkeypatch.setitem(app.config, "GA_MEASUREMENT_ID", GA_TEST_ID)
        con_ga = client.get("/privacy").get_data(as_text=True)
        assert "Google Analytics" in con_ga


class TestTrackEvent:
    """`track_event` accoda eventi custom solo quando ha senso farlo."""

    def test_no_op_senza_measurement_id(self, app):
        with app.test_request_context():
            track_event(AnalyticsEvent.USER_REGISTERED)

            assert get_flashed_messages(with_categories=True) == []

    def test_accoda_evento_con_measurement_id(self, app, monkeypatch):
        monkeypatch.setitem(app.config, "GA_MEASUREMENT_ID", GA_TEST_ID)

        with app.test_request_context():
            track_event(AnalyticsEvent.GARA_INSCRIPTION, gara_id=42, waitlist=False)

            messages = get_flashed_messages(with_categories=True)

        assert len(messages) == 1
        category, payload = messages[0]
        assert category == ANALYTICS_FLASH_CATEGORY

        event = json.loads(payload)
        assert event["name"] == "gara_inscription"
        assert event["params"] == {"gara_id": 42, "waitlist": False}

    def test_no_op_fuori_da_request_context(self, app):
        """Chiamato da uno script o da un task non deve sollevare."""
        with app.app_context():
            track_event(AnalyticsEvent.USER_REGISTERED)  # non deve sollevare

    def test_payload_e_json_valido_per_il_template(self, app, monkeypatch):
        """Il template fa `{{ message | safe }}`: un JSON malformato romperebbe
        tutto il JavaScript della pagina, non solo il tracking."""
        monkeypatch.setitem(app.config, "GA_MEASUREMENT_ID", GA_TEST_ID)

        with app.test_request_context():
            track_event(AnalyticsEvent.GARA_CREATED, gara_id=1, standalone=True)
            messages = get_flashed_messages(with_categories=True)

        event = json.loads(messages[0][1])
        assert set(event.keys()) == {"name", "params"}


class TestPrivacyPolicyEndpoint:
    """ADR-028: senza entry nella matrice la pagina sarebbe admin-only in prod."""

    def test_privacy_policy_visibile_agli_anonimi(self):
        assert "anonimo" in ENDPOINT_ROLES["main.privacy_policy"]

    def test_privacy_policy_visibile_a_tutti_i_ruoli(self):
        assert ENDPOINT_ROLES["main.privacy_policy"] == {
            "anonimo",
            "player",
            "director",
        }
