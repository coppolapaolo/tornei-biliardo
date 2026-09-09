"""Aiuto contestuale (ADR-058, tappa 4): il contratto fra `hints.yaml` e i template.

`hints.yaml` dichiara per ogni micro-aiuto un `anchor`, e promette che un
elemento dell'interfaccia lo esporrà come `data-help="<anchor>"`. Finché il
componente client non esisteva la promessa era solo dichiarata; da quando
`static/js/help-hints.js` la consuma, un'ancora senza elemento è una «?» che
non compare mai, e un `data-help` senza suggerimento è un elemento che chiede
un testo che nessuno ha scritto. In entrambi i casi non c'è errore a
runtime — il componente salta ciò che non trova — quindi il presidio è
statico, sui sorgenti (AC15 della specifica in
`docs/usecases/competizione-di-prova.md`).

Il file guarda anche le tre condizioni senza cui il componente resta muto:
l'API aperta in produzione ai ruoli che la guida serve, la configurazione
iniettata dal guscio, e l'interruttore nel banner della prova.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from utils.feature_flags import ENDPOINT_ROLES

ROOT = Path(__file__).resolve().parents[3]
TEMPLATES = ROOT / "templates"
HELP_CONTENT = ROOT / "help_content"

# Solo valori letterali: un `data-help="{{ ... }}"` sfuggirebbe al confronto
# e riaprirebbe esattamente il buco che questo test chiude.
DATA_HELP = re.compile(r"""\bdata-help=["']([^"'{}]+)["']""")
DATA_HELP_ANY = re.compile(r"""\bdata-help=["']([^"']*)["']""")


def _anchors(locale: str) -> dict[str, str]:
    data = yaml.safe_load((HELP_CONTENT / locale / "hints.yaml").read_text())
    return {hint["anchor"]: hint["id"] for hint in data["hints"]}


def _app_templates() -> list[Path]:
    """I template dell'app: il mini-sito (`templates/help/`) resta fuori.

    Il catalogo dei micro-aiuti (`help/hints.html`) rende `data-help` con il
    valore di ogni ancora per mostrarle: e' documentazione, non una schermata
    su cui il componente attacca una «?».
    """
    return [
        path
        for path in sorted(TEMPLATES.rglob("*.html"))
        if "help" not in path.relative_to(TEMPLATES).parts[:1]
    ]


def _data_help_in_templates() -> dict[str, set[str]]:
    """anchor → template che la espongono."""
    found: dict[str, set[str]] = {}
    for path in _app_templates():
        source = path.read_text(encoding="utf-8", errors="ignore")
        for anchor in DATA_HELP.findall(source):
            found.setdefault(anchor, set()).add(str(path.relative_to(ROOT)))
    return found


@pytest.mark.unit
def test_ogni_ancora_dichiarata_ha_un_elemento_nei_template():
    """Da `hints.yaml` ai template: nessuna «?» promessa e mai mostrata."""
    exposed = _data_help_in_templates()
    missing = sorted(a for a in _anchors("it") if a not in exposed)
    assert (
        not missing
    ), "Ancore di hints.yaml senza `data-help` in nessun template: " + ", ".join(
        missing
    )


@pytest.mark.unit
def test_ogni_data_help_nei_template_ha_un_suggerimento():
    """Dai template a `hints.yaml`: nessun elemento che chiede un testo assente."""
    anchors = _anchors("it")
    exposed = _data_help_in_templates()
    unknown = {a: files for a, files in exposed.items() if a not in anchors}
    assert not unknown, "`data-help` senza suggerimento in hints.yaml: " + "; ".join(
        f"{a} ({', '.join(sorted(files))})" for a, files in sorted(unknown.items())
    )


@pytest.mark.unit
def test_nessun_data_help_dinamico():
    """Il valore è un letterale, altrimenti i due test sopra non vedono niente."""
    dynamic = []
    for path in _app_templates():
        source = path.read_text(encoding="utf-8", errors="ignore")
        for value in DATA_HELP_ANY.findall(source):
            if "{" in value or not re.fullmatch(r"[a-z0-9-]+", value):
                dynamic.append(f"{path.relative_to(ROOT)}: data-help={value!r}")
    assert not dynamic, "\n".join(dynamic)


@pytest.mark.unit
def test_le_ancore_sono_le_stesse_in_ogni_lingua():
    """`anchor` non si traduce: è il contratto con i template, uguale ovunque."""
    reference = _anchors("it")
    for locale_dir in sorted(HELP_CONTENT.iterdir()):
        if not (locale_dir / "hints.yaml").exists():
            continue
        assert _anchors(locale_dir.name) == reference, locale_dir.name


@pytest.mark.unit
def test_l_api_della_schermata_e_aperta_a_chi_legge_la_guida():
    """In produzione il componente chiama `/aiuto/api/schermata/<endpoint>`.

    Fuori matrice l'endpoint è admin-only (ADR-028): il direttore nella sua
    prova riceverebbe 404 e nessuna «?». Il mini-sito è aperto anche agli
    ospiti, e l'API che serve i suoi testi segue la stessa regola.
    """
    assert {"anonimo", "player", "director"} <= ENDPOINT_ROLES["help.screen_api"]


@pytest.mark.unit
def test_il_guscio_inietta_la_configurazione_e_carica_il_componente():
    base = (TEMPLATES / "base.html").read_text(encoding="utf-8")
    assert 'id="help-hints-config"' in base
    assert "help-hints.js" in base
    # L'endpoint corrente è ciò che il componente chiede all'API.
    assert "request.endpoint" in base.split('id="help-hints-config"', 1)[1][:1500]


@pytest.mark.unit
def test_il_banner_della_prova_ha_l_interruttore():
    banner = (TEMPLATES / "components" / "_prova_banner.html").read_text(
        encoding="utf-8"
    )
    assert "data-help-toggle" in banner
    # Il banner puo' essere incluso due volte nella stessa pagina: niente id.
    assert ' id="' not in banner
