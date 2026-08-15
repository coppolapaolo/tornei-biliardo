"""Configurazione dei formati a tabellone dal form gara (Step 10).

Il parser era il punto in cui i due formati diventavano irraggiungibili:
forzava il sistema di classifica a WINS/RACK, e la combinazione
"eliminazione diretta + WINS" veniva poi rifiutata dai validatori. Selezionare
un tabellone faceva quindi fallire il salvataggio, sempre.

Ora il sistema di classifica non si chiede più quando è determinato: sul
tabellone è POSITION e basta.
"""

import pytest

from routes.admin.competition.form_parser import (
    BRACKET_STRATEGIES,
    GaraFormParser,
    _resolve_classification_system,
)

pytestmark = pytest.mark.unit


class TestSistemaDiClassifica:
    def test_il_tabellone_impone_position(self):
        for strategy in BRACKET_STRATEGIES:
            assert _resolve_classification_system(strategy, "WINS") == "POSITION"
            assert _resolve_classification_system(strategy, "RACK") == "POSITION"
            assert _resolve_classification_system(strategy, "POSITION") == "POSITION"

    def test_fuori_dal_tabellone_position_non_ha_senso(self):
        """POSITION su un girone non è una scelta valida: si ricade su WINS."""
        assert _resolve_classification_system("amalfi", "POSITION") == "WINS"
        assert _resolve_classification_system("round_robin", "POSITION") == "WINS"

    def test_le_altre_strategie_conservano_la_scelta(self):
        assert _resolve_classification_system("amalfi", "RACK") == "RACK"
        assert _resolve_classification_system("random", "WINS") == "WINS"

    def test_valore_inatteso_ricade_su_wins(self):
        assert _resolve_classification_system("amalfi", "SPAZZATURA") == "WINS"


class TestOpzioniDiTabellone:
    """`_parse_bracket_options` legge il form: serve un contesto di richiesta."""

    def _parse(self, app, strategy, form=None):
        with app.test_request_context(method="POST", data=form or {}):
            return GaraFormParser._parse_bracket_options(strategy)

    def test_fuori_dal_tabellone_le_opzioni_si_azzerano(self, app):
        """Cambiando formato non ci si porta dietro una configurazione morta."""
        options = self._parse(
            app,
            "amalfi",
            {"separate_teammates": "on", "third_place_match": "on"},
        )
        assert options["separate_teammates"] is False
        assert options["third_place_match"] is False
        assert options["double_ko_rounds"] is None

    def test_separazione_compagni_letta_dal_form(self, app):
        assert (
            self._parse(app, "direct_elimination", {"separate_teammates": "on"})[
                "separate_teammates"
            ]
            is True
        )
        assert self._parse(app, "direct_elimination", {})["separate_teammates"] is False

    def test_finalina_solo_a_eliminazione_diretta(self, app):
        """Nel doppio KO il terzo posto lo decide già il tabellone."""
        de = self._parse(app, "direct_elimination", {"third_place_match": "on"})
        dk = self._parse(app, "double_knockout", {"third_place_match": "on"})
        assert de["third_place_match"] is True
        assert dk["third_place_match"] is False

    def test_gironi_solo_nel_doppio_ko(self, app):
        de = self._parse(app, "direct_elimination", {"double_ko_rounds": "2"})
        dk = self._parse(app, "double_knockout", {"double_ko_rounds": "2"})
        assert de["double_ko_rounds"] is None
        assert dk["double_ko_rounds"] == 2

    @pytest.mark.parametrize("raw", ["", "0", "abc", "-1"])
    def test_valori_non_utili_valgono_doppio_ko_pieno(self, app, raw):
        """Assente, zero o illeggibile = nessuna fase a gironi, che è il default."""
        options = self._parse(app, "double_knockout", {"double_ko_rounds": raw})
        assert options["double_ko_rounds"] is None


class TestParseCompleto:
    def test_una_gara_a_tabellone_esce_configurata(self, app):
        """Il caso che prima falliva sempre: formato a tabellone salvabile."""
        form = {
            "name": "Regionale",
            "date": "2026-09-01",
            "discipline": "palla_9",
            "distance": "5",
            "is_race_to": "on",
            "rounds_count": "4",
            "max_participants": "16",
            "matchmaking_strategy": "direct_elimination",
            "classification_system": "WINS",  # il form può mandare qualsiasi cosa
            "separate_teammates": "on",
            "third_place_match": "on",
        }
        with app.test_request_context(method="POST", data=form):
            data = GaraFormParser().parse()

        assert data["matchmaking_strategy"] == "direct_elimination"
        assert data["classification_system"] == "POSITION"
        assert data["separate_teammates"] is True
        assert data["third_place_match"] is True

    def test_le_gare_a_girone_non_cambiano(self, app):
        """Non-regressione: chi non usa i tabelloni non vede differenze."""
        form = {
            "name": "Serale",
            "date": "2026-09-01",
            "discipline": "palla_8",
            "distance": "5",
            "is_race_to": "on",
            "rounds_count": "3",
            "matchmaking_strategy": "amalfi",
            "classification_system": "RACK",
        }
        with app.test_request_context(method="POST", data=form):
            data = GaraFormParser().parse()

        assert data["matchmaking_strategy"] == "amalfi"
        assert data["classification_system"] == "RACK"
        assert data["separate_teammates"] is False
        assert data["double_ko_rounds"] is None
