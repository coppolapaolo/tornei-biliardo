"""Le regole della fase finale e della finale nei moduli, nelle proposte e
nelle parole (ADR-081, emendamento del 2026-10-12).

La precedenza e la nascita delle partite stanno in
`test_gironi_tabellone_finale.py::TestRegoleDellaFinale`; qui il passaggio
interfaccia↔server: il modulo della gara (e della gara avviata, e del
campionato) legge distanza della fase finale, limite e distanza della sola
finale; il campionato li propone; storia e regolamento li dicono.
"""

from __future__ import annotations

import pytest

from models.campionato.proposte import CAMPI_PROPOSTI
from models.competition.campi_modificabili import REGOLE
from routes.admin.competition.form_parser import GaraFormParser
from tests.new.unit import test_fase_finale_moduli as moduli
from tests.new.unit.test_fase_finale_moduli import TABELLONE, _campionato, _gara, _parse

pytestmark = pytest.mark.unit

NUOVI = ("final_phase_distance", "final_time_limit_minutes", "final_distance")

FINALE = {
    "final_phase_distance_mode": "altra",
    "final_phase_distance": "4",
    "final_time_limit": "nessuno",
    "final_distance_mode": "altra",
    "final_distance": "7",
}


class TestModuloGara:
    def test_legge_le_regole_della_finale(self, app):
        dati = _parse(app, **TABELLONE, **FINALE)
        assert dati["final_phase_distance"] == 4
        assert dati["final_time_limit_minutes"] == 0
        assert dati["final_distance"] == 7

    def test_come_prima_e_none(self, app):
        dati = _parse(
            app,
            **TABELLONE,
            final_phase_distance_mode="come",
            final_time_limit="gironi",
            final_distance_mode="come",
        )
        assert [dati[c] for c in NUOVI] == [None, None, None]

    def test_senza_tabellone_non_si_toccano(self, app):
        dati = _parse(app, final_phase_mode="nessuna", **FINALE)
        assert not set(NUOVI) & set(dati)

    def test_distanza_fuori_misura(self, app):
        with pytest.raises(ValueError):
            _parse(app, **TABELLONE, final_distance_mode="altra", final_distance="0")

    def test_sono_campi_del_modulo_e_regole(self):
        for campo in NUOVI:
            assert campo in GaraFormParser.CAMPI_DEL_MODULO
            # Valgono per le partite che nasceranno (ADR-075).
            assert campo in REGOLE

    def test_a_gara_avviata(self, app):
        with app.test_request_context(method="POST", data=FINALE):
            dati = GaraFormParser(gara=None).parse_a_gara_avviata(set(NUOVI))
        assert dati == {
            "final_phase_distance": 4,
            "final_time_limit_minutes": 0,
            "final_distance": 7,
        }


class TestCampionato:
    def test_il_modulo_del_campionato(self, app):
        valori = moduli.TestModuloCampionato()._gironi(
            app,
            default_max_groups="2",
            default_final_phase_mode="tabellone",
            default_final_phase_time_limit="gironi",
            default_final_phase_distance_mode="altra",
            default_final_phase_distance="5",
            default_final_time_limit="minuti",
            default_final_time_limit_minutes="60",
            default_final_distance_mode="come",
        )
        assert valori["default_final_phase_distance"] == 5
        assert valori["default_final_time_limit_minutes"] == 60
        assert valori["default_final_distance"] is None

    def test_li_propone_e_la_gara_li_riceve(self, app, db_session):
        for campo in NUOVI:
            assert CAMPI_PROPOSTI[f"default_{campo}"] == campo
        camp = _campionato(
            default_final_phase_mode="tabellone",
            default_final_phase_distance=4,
            default_final_time_limit_minutes=0,
            default_final_distance=7,
        )
        gara = _gara(camp)
        assert (
            gara.final_phase_distance,
            gara.final_time_limit_minutes,
            gara.final_distance,
        ) == (4, 0, 7)


class TestParole:
    def test_la_frase(self, app):
        from models.competition.gironi_service import descrivi_fase_finale

        with app.test_request_context():
            frase = descrivi_fase_finale(
                2, True, 45, distanza=4, minuti_finale=0, distanza_finale=7
            )
            vuota = descrivi_fase_finale(2, False)
        assert "nel tabellone al 4, 45 minuti a partita" in frase
        assert "la finale al 7, senza limite di tempo" in frase
        assert "finale al" not in vuota and "nel tabellone" not in vuota

    def test_la_storia(self, app):
        from models.storia.etichette import etichetta, valore

        with app.test_request_context():
            assert valore("final_time_limit_minutes", "") == "come la fase finale"
            assert valore("final_time_limit_minutes", "0") == "senza limite"
            assert valore("final_distance", "") == "come la fase finale"
            assert valore("final_phase_distance", "") == "come i gironi"
            assert valore("final_distance", "7") == "al 7"
            assert valore("default_final_distance", "7") == "al 7"
            assert etichetta("final_distance") == "Distanza della finale"
