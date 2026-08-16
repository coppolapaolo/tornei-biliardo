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

    def test_finalina_a_eliminazione_diretta(self, app):
        de = self._parse(app, "direct_elimination", {"third_place_match": "on"})
        assert de["third_place_match"] is True

    def test_finalina_rifiutata_sul_doppio_ko_pieno(self, app):
        """Il terzo è chi perde la finale dei ripescati: non è un pari merito."""
        dk = self._parse(app, "double_knockout", {"third_place_match": "on"})
        assert dk["third_place_match"] is False

    def test_finalina_ammessa_sul_doppio_ko_a_gironi(self, app):
        """Col girone il tabellone finale è eliminazione diretta pura, quindi
        i due semifinalisti tornano a essere terzi a pari merito."""
        dk = self._parse(
            app,
            "double_knockout",
            {"third_place_match": "on", "double_ko_rounds": "2"},
        )
        assert dk["third_place_match"] is True

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


class TestCampiDerivati:
    """Sei impostazioni del form non hanno alcun effetto sul tabellone.

    Prima venivano chieste comunque, e la risposta veniva ignorata in silenzio:
    il director poteva scegliere "escludi dal turno" o accendere lo spareggio
    SSR e non succedeva nulla. Ora le impone il server, così la gara resta
    coerente anche con il JavaScript spento.
    """

    def _parse(self, app, form):
        with app.test_request_context(method="POST", data=form):
            return GaraFormParser().parse()

    def _bracket_form(self, strategy, **extra):
        form = {
            "date": "2026-09-01",
            "discipline": "palla_9",
            "distance": "5",
            "max_participants": "16",
            "matchmaking_strategy": strategy,
            # Valori che il director *potrebbe* mandare e che vanno ignorati:
            "withdraw_policy": "Exclude",
            "odd_number_policy": "trio",
            "tiebreaker_enabled": "on",
            "rounds_count": "3",
            "exact_number": "on",
        }
        form.update(extra)
        return form

    def test_il_ritiro_e_sempre_a_tavolino(self, app):
        """Dopo il sorteggio il tabellone non si tocca: l'avversario avanza."""
        data = self._parse(app, self._bracket_form("direct_elimination"))
        assert data["withdraw_policy"] == "Forfeit"

    def test_i_bye_sono_strutturali_non_una_politica(self, app):
        data = self._parse(app, self._bracket_form("double_knockout"))
        assert data["odd_number_policy"] == "bye"

    def test_la_distanza_e_sempre_a_chi_arriva_prima(self, app):
        """Sul tabellone conta solo chi passa il turno.

        Il vincitore è deciso appena uno arriva a (N+1)/2: i rack successivi
        non cambiano né il tabellone né la classifica, che è per posizione.
        Giocarli è solo una partita più lunga a parità di risultato.
        """
        de = self._parse(app, self._bracket_form("direct_elimination"))
        assert de["is_race_to"] is True
        assert de["is_race_to_sets"] is True

    def test_fuori_dal_tabellone_il_numero_esatto_resta(self, app):
        data = self._parse(app, self._bracket_form("amalfi"))
        assert data["is_race_to"] is False

    def test_l_anti_reincontro_si_spegne(self, app):
        """Nel tabellone due giocatori non possono reincontrarsi: chi perde esce.

        Nel doppio KO il reincontro fra un ripescato e chi lo aveva battuto è
        previsto dal formato, e l'incrocio del losers bracket lo allontana già
        per costruzione: non c'è niente che un flag possa aggiungere.
        """
        data = self._parse(
            app, self._bracket_form("direct_elimination", anti_rematch_enabled="on")
        )
        assert data["anti_rematch_enabled"] is False

    def test_lo_spareggio_ssr_resta_spento(self, app):
        """Le strategie POSITION dichiarano `requires_tiebreaker=False`."""
        data = self._parse(app, self._bracket_form("direct_elimination"))
        assert data["tiebreaker_enabled"] is False

    def test_i_turni_li_calcola_la_capienza(self, app):
        """Il valore digitato veniva buttato al sorteggio: non si chiede più."""
        de = self._parse(app, self._bracket_form("direct_elimination"))
        dk = self._parse(app, self._bracket_form("double_knockout"))
        assert de["rounds_count"] == 4  # log2(16)
        assert dk["rounds_count"] == 9  # 2*log2(16) + 1

    def test_il_minimo_iscritti_sale_al_pavimento_del_formato(self, app):
        """Il default del form è 6, ma il doppio KO ne richiede 8."""
        dk = self._parse(app, self._bracket_form("double_knockout"))
        assert dk["min_participants"] == 8

    def test_un_minimo_gia_alto_non_viene_abbassato(self, app):
        dk = self._parse(
            app, self._bracket_form("double_knockout", min_participants="12")
        )
        assert dk["min_participants"] == 12

    def test_fuori_dal_tabellone_le_scelte_restano_scelte(self, app):
        """Non-regressione: per chi non usa i tabelloni non cambia nulla."""
        data = self._parse(app, self._bracket_form("amalfi"))
        assert data["withdraw_policy"] == "Exclude"
        assert data["odd_number_policy"] == "trio"
        assert data["tiebreaker_enabled"] is True
        assert data["rounds_count"] == 3
        assert data["min_participants"] == 6


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
