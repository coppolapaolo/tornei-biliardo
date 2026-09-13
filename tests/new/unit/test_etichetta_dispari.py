"""La formula dei dispari si mostra col suo nome tradotto, mai col valore grezzo.

Le schermate del direttore e la scheda informazioni della gara scrivevano
`odd_number_policy.replace('_', ' ').title()`: «Bye», «Bye With Challenge»
in una pagina italiana, con una parola che l'interfaccia non usa.
"""

from pathlib import Path

import pytest

from models.matchmaking.configuration import OddNumberPolicy
from utils.jinja import etichetta_dispari

pytestmark = pytest.mark.unit

TEMPLATES = Path(__file__).resolve().parents[3] / "templates"


@pytest.mark.parametrize(
    "policy, atteso",
    [
        (OddNumberPolicy.NO.value, "Lista d'attesa"),
        (OddNumberPolicy.BYE.value, "X a tavolino"),
        (OddNumberPolicy.BYE_WITH_CHALLENGE.value, "X a tavolino con esercizio"),
        (OddNumberPolicy.TRIO.value, "Trio, partita a tre"),
        (OddNumberPolicy.BYE, "X a tavolino"),
    ],
)
def test_ogni_formula_ha_il_suo_nome(app, policy, atteso):
    with app.test_request_context():
        assert etichetta_dispari(policy) == atteso


def test_un_valore_sconosciuto_torna_com_e(app):
    with app.test_request_context():
        assert etichetta_dispari("boh") == "boh"
        assert etichetta_dispari(None) == ""


def test_nessun_template_ripulisce_a_mano_il_valore_della_formula():
    colpevoli = [
        str(p.relative_to(TEMPLATES))
        for p in TEMPLATES.rglob("*.html")
        if "odd_number_policy.replace(" in p.read_text(encoding="utf-8")
    ]
    assert colpevoli == []


def test_le_righe_delle_partite_impilano_i_nomi_sotto_lg():
    """Con nome e cognome veri i due nomi affiancati si troncavano a «Andrea F…».

    Sul telefono vanno uno sopra l'altro, e il trattino fra i due sparisce;
    dal desktop tornano sulla stessa riga.
    """
    css = (
        Path(__file__).resolve().parents[3] / "static" / "css" / "theme-7c.css"
    ).read_text(encoding="utf-8")
    base = css.index(".c7-riga-partita__nomi {")
    regola = css[base : css.index("}", base)]
    assert "flex-direction: column" in regola
    sep = css.index(".c7-riga-partita__sep {")
    assert "display: none" in css[sep : css.index("}", sep)]
    media = css.index("@media (min-width: 992px)", base)
    blocco = css[media : css.index("\n}\n", media)]
    assert ".c7-riga-partita__nomi { flex-direction: row" in blocco
