"""La nuova gara del campionato a piazzamenti: formato e sistema (ADR-080).

Due regole, presidiate qui perché la CI esegue solo gli unit test:

* **Amalfi impone l'anti-reincontro.** Una serata Amalfi in un campionato
  che non lo propone (un girone all'italiana, dove non serve) veniva
  rifiutata dalla validazione della strategia: il modale non mandava il
  campo, e il parser ripiegava sulla proposta del campionato. Ora la
  proposta, applicata a una gara Amalfi, è accesa.
* **Il modale sceglie formato e sistema solo a piazzamenti.** Il menu del
  formato e quello del sistema compaiono solo lì; sommando i totali il
  modale resta quello di prima. Lo si legge nel template, perché è lì che si
  decide.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from models.matchmaking.configuration import anti_rematch_for_strategy

MODALE = (
    Path(__file__).resolve().parents[3]
    / "templates"
    / "components"
    / "_new_gara_modal.html"
)


class _Camp:
    """Un campionato finto, con i soli valori che il parser legge."""

    def __init__(self, tipo, sistema, anti=None, sistema_gare=None):
        self.campionato_type = tipo
        self.default_classification_system = sistema
        self.default_gara_classification_system = sistema_gare
        self.default_anti_rematch = anti

    def __getattr__(self, nome):
        return None


BASE = {
    "date": "2026-12-01",
    "time": "20:00",
    "discipline": "8_ball",
    "distance": "3",
    "rounds_count": "3",
    "min_participants": "2",
    "first_round_policy": "random",
    "odd_number_policy": "bye",
}


def _parse(app, camp, **extra):
    from routes.admin.competition.form_parser import GaraFormParser

    with app.test_request_context(method="POST", data={**BASE, **extra}):
        return GaraFormParser(campionato=camp).parse()


@pytest.mark.unit
class TestAmalfiImponeLAntiReincontro:
    def test_la_regola(self):
        assert anti_rematch_for_strategy("amalfi", False) is True
        assert anti_rematch_for_strategy("amalfi", True) is True
        # Le altre strategie tengono la scelta.
        assert anti_rematch_for_strategy("random", False) is False
        assert anti_rematch_for_strategy("random", True) is True
        assert anti_rematch_for_strategy("round_robin", False) is False

    def test_amalfi_in_un_campionato_girone_che_non_lo_propone(self, app):
        camp = _Camp("round_robin", "POSITION", anti=False)
        dati = _parse(app, camp, matchmaking_strategy="amalfi")
        assert dati["matchmaking_strategy"] == "amalfi"
        assert dati["anti_rematch_enabled"] is True

    def test_nella_gara_singola_la_casella_spenta_resta_una_scelta(self, app):
        """Fuori dal campionato non c'è proposta: la casella spenta è voluta,
        e la validazione la rifiuta col suo messaggio (e2e Amalfi)."""
        from routes.admin.competition.form_parser import GaraFormParser

        with app.test_request_context(
            method="POST", data={**BASE, "matchmaking_strategy": "amalfi"}
        ):
            dati = GaraFormParser().parse()
        assert dati["anti_rematch_enabled"] is False

    def test_il_casuale_tiene_la_proposta_del_campionato(self, app):
        camp = _Camp("round_robin", "POSITION", anti=False)
        dati = _parse(app, camp, matchmaking_strategy="random")
        assert dati["anti_rematch_enabled"] is False


@pytest.mark.unit
class TestIlModaleSceglieSoloAPiazzamenti:
    def test_i_menu_di_formato_e_sistema_dipendono_dai_piazzamenti(self):
        testo = MODALE.read_text(encoding="utf-8")
        # Un solo interruttore decide se il modale sceglie: i piazzamenti.
        assert "{% set scelta_libera = campionato_a_piazzamenti(campionato) %}" in testo
        inizio = testo.index("{% if scelta_libera %}")
        # Il blocco si chiude col primo `{% endif %}` su una riga sua.
        fine = re.compile(r"^\s*\{% endif %\}\s*$", re.M).search(testo, inizio)
        assert fine
        blocco = testo[inizio : fine.start()]
        assert 'id="create_matchmaking_strategy"' in blocco
        assert 'name="matchmaking_strategy"' in blocco
        assert 'id="create_classification_system"' in blocco
        assert 'name="classification_system"' in blocco

    def test_riusa_i_blocchi_della_modifica_della_gara(self):
        testo = MODALE.read_text(encoding="utf-8")
        assert '{% include "components/_bracket_options.html" %}' in testo
        assert '{% include "components/_campo_gironi.html" %}' in testo
        assert "js/bracket_options.js" in testo
        assert "js/strategia_gara.js" in testo
