"""Il limite di tempo nei moduli di gara e campionato (ADR-077).

Un numero di minuti, vuoto = nessun limite. Tre regole del parser:

* vuoto si salva come 0, «senza limite» per scelta;
* assente dal modulo non tocca la gara (in creazione: come il campionato);
* un valore fuori da 1–600 si rifiuta, non si corregge in silenzio.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from routes.admin.campionato_form_parser import CampionatoFormParser
from routes.admin.competition.form_parser import GaraFormParser

BASE = {
    "date": "2026-12-01",
    "time": "20:00",
    "discipline": "8_ball",
    "distance": "3",
    "rounds_count": "3",
    "min_participants": "2",
    "matchmaking_strategy": "round_robin",
    "first_round_policy": "random",
    "odd_number_policy": "bye",
}


def _parse(app, gara=None, **extra):
    with app.test_request_context(method="POST", data={**BASE, **extra}):
        return GaraFormParser(campionato=None, gara=gara).parse()


@pytest.mark.unit
class TestModuloGara:
    def test_trenta_minuti(self, app):
        assert _parse(app, time_limit_minutes="30")["time_limit_minutes"] == 30

    def test_vuoto_e_senza_limite(self, app):
        assert _parse(app, time_limit_minutes="")["time_limit_minutes"] == 0

    def test_assente_non_si_tocca(self, app):
        assert "time_limit_minutes" not in _parse(app)

    @pytest.mark.parametrize("grezzo", ["-5", "601", "mezz'ora"])
    def test_valori_fuori_scala_si_rifiutano(self, app, grezzo):
        with pytest.raises(ValueError):
            _parse(app, time_limit_minutes=grezzo)

    def test_una_gara_nata_senza_valore_resta_senza(self, app):
        """Salvare una gara nata prima del limite di tempo, senza toccare il
        campo, non le scrive uno zero nella storia."""
        vecchia = SimpleNamespace(
            time_limit_minutes=None,
            effective_time_limit_minutes=None,
            is_playoff=False,
        )
        dati = _parse(app, gara=vecchia, time_limit_minutes="")
        assert dati["time_limit_minutes"] is None

    def test_e_un_campo_del_modulo_di_modifica(self):
        assert "time_limit_minutes" in GaraFormParser.CAMPI_DEL_MODULO


@pytest.mark.unit
class TestModuloCampionato:
    def _settings(self, app, **dati):
        with app.test_request_context(method="POST", data=dati):
            from flask import request

            return CampionatoFormParser.parse_default_settings(request.form)

    def test_vuoto_e_nessun_limite(self, app):
        assert self._settings(app)["default_time_limit_minutes"] == 0

    def test_trenta_minuti(self, app):
        valori = self._settings(app, default_time_limit_minutes="30")
        assert valori["default_time_limit_minutes"] == 30

    def test_fuori_scala_si_rifiuta(self, app):
        with pytest.raises(ValueError):
            self._settings(app, default_time_limit_minutes="9999")
