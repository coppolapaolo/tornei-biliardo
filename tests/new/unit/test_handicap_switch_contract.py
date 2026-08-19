"""Il contratto fra la casella «Gioco con handicap» e il parser.

Su una gara standalone l'handicap è sì/no, quindi nell'interfaccia è un
interruttore. Una casella spuntata invia **il proprio `value`**, una non
spuntata non invia nulla: perché il parser tri-stato la capisca, il `value`
deve essere esattamente `"true"`.

È un presidio, non una formalità. Con `value="on"` — il valore predefinito di
una casella HTML — il parser cadrebbe nel ramo «eredita», l'handicap non si
accenderebbe mai e **nessun errore verrebbe segnalato**: il direttore
spunterebbe la casella, salverebbe, e il rating continuerebbe ad aggiornarsi
come se niente fosse.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from routes.admin.competition.form_parser import GaraFormParser

pytestmark = pytest.mark.unit

TEMPLATES = Path(__file__).resolve().parents[3] / "templates"


def _parse(app, form: dict):
    with app.test_request_context("/", method="POST", data=form):
        return GaraFormParser(campionato=None).parse()


BASE_FORM = {
    "date": "2027-01-15",
    "time": "20:00",
    "discipline": "palla_8",
    "distance": "5",
    "rounds_count": "3",
    "matchmaking_strategy": "amalfi",
}


class TestIlParserLeggeLaCasella:
    def test_spuntata_accende_l_handicap(self, app):
        data = _parse(app, {**BASE_FORM, "has_handicap": "true"})
        assert data["has_handicap"] is True

    def test_non_spuntata_non_lo_accende(self, app):
        """Assente = eredita; su una standalone eredita vale «no»."""
        data = _parse(app, BASE_FORM)
        assert data["has_handicap"] is None

    def test_il_menu_del_campionato_conserva_i_tre_stati(self, app):
        """Dentro un campionato «eredita» è uno stato reale, non un'assenza."""
        assert (
            _parse(app, {**BASE_FORM, "has_handicap": "false"})["has_handicap"] is False
        )
        assert _parse(app, {**BASE_FORM, "has_handicap": ""})["has_handicap"] is None


class TestLeCaselleInviano_true:
    """Il valore lo si legge nei template: è lì che si romperebbe."""

    @pytest.mark.parametrize(
        "template",
        [
            "admin/gara_create_standalone.html",
            "components/_gara_edit_form.html",
        ],
    )
    def test_la_casella_handicap_dichiara_value_true(self, template):
        sorgente = (TEMPLATES / template).read_text(encoding="utf-8")
        caselle = re.findall(r'<input[^>]*name="has_handicap"[^>]*>', sorgente, re.S)
        assert caselle, f"nessun campo has_handicap in {template}"
        for casella in caselle:
            if 'type="checkbox"' not in casella:
                continue
            assert 'value="true"' in casella, (
                f'{template}: la casella has_handicap non dichiara value="true", '
                "quindi invierebbe «on» e l'handicap non si accenderebbe mai"
            )
