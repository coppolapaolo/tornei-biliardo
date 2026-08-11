"""Regressione issue #56 e #57 — il titolo di una gara ha una fonte sola.

La formattazione era ripetuta nei template con tre regole divergenti:
nome con fallback, solo numero, nome senza fallback. Le gare di campionato
mostravano "Gara 2" ignorando il nome impostato dal direttore (#56), mentre
altrove un nome mancante lasciava il vuoto o un fallback diverso ("Gara
Singola", "Gara Standalone") invece di "Gara N" (#57).

Il formato è **il nome se c'è, altrimenti "Gara <numero>"**: quando il
direttore compila il campo è lui a decidere come va letto il titolo, quindi
il numero non viene anteposto — su un nome come "2ª prova" produrrebbe anche
una ripetizione.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pytest

from models.competition.models import Gara

TEMPLATES = Path(__file__).resolve().parents[3] / "templates"


def _gara(**kwargs) -> Gara:
    defaults = dict(
        number=2,
        date=date.today(),
        discipline="8_ball",
        distance=5,
        status="setup",
    )
    defaults.update(kwargs)
    return Gara(**defaults)


@pytest.mark.unit
class TestDisplayName:

    def test_uses_the_name_when_set(self, app):
        with app.test_request_context("/"):
            assert _gara(name="Trofeo di Primavera").display_name == (
                "Trofeo di Primavera"
            )

    def test_does_not_prefix_the_number(self, app):
        """Il caso dell'issue: "2ª prova" non diventa "Gara 2 - 2ª prova"."""
        with app.test_request_context("/"):
            assert _gara(number=2, name="2ª prova").display_name == "2ª prova"

    def test_falls_back_to_gara_number(self, app):
        with app.test_request_context("/"):
            assert _gara(number=2, name=None).display_name == "Gara 2"

    def test_fallback_uses_number_not_database_id(self, app):
        """Il filtro Jinja usava `gara.id`: su una gara senza nome mostrava
        "Gara 47" (chiave del DB) al posto della prova numero 2."""
        gara = _gara(number=2, name=None)
        gara.id = 47

        with app.test_request_context("/"):
            assert gara.display_name == "Gara 2"
            assert "47" not in gara.display_name

    def test_blank_name_is_treated_as_missing(self, app):
        """Un campo lasciato con spazi non deve produrre un titolo vuoto."""
        with app.test_request_context("/"):
            assert _gara(number=3, name="   ").display_name == "Gara 3"

    def test_works_outside_application_context(self):
        """Script e migration usano i modelli senza contesto Flask: il
        fallback tradotto non deve farli esplodere."""
        assert _gara(number=4, name=None).display_name == "Gara 4"


@pytest.mark.unit
class TestJinjaFilterDelegates:

    def test_filter_matches_the_property(self, app):
        from utils.jinja import gara_display_name

        gara = _gara(number=2, name=None)
        gara.id = 47

        with app.test_request_context("/"):
            assert str(gara_display_name(gara)) == gara.display_name

    def test_filter_handles_none(self, app):
        from utils.jinja import gara_display_name

        with app.test_request_context("/"):
            assert str(gara_display_name(None)) == "N/A"


@pytest.mark.unit
class TestQualifiedName:

    def test_standalone_unnamed_no_longer_renders_none(self, app):
        """`get_display_name` interpolava `self.name` grezzo: una gara senza
        nome produceva "None (Standalone)"."""
        with app.test_request_context("/"):
            assert _gara(number=2, name=None).get_display_name() == (
                "Gara 2 (Standalone)"
            )

    def test_campionato_gara_is_qualified_by_its_campionato(self, app, db_session):
        from models.campionato.models import Campionato

        campionato = Campionato(name="Campionato Invernale")
        db_session.add(campionato)
        db_session.flush()

        gara = _gara(number=2, name=None, campionato_id=campionato.id)
        db_session.add(gara)
        db_session.flush()

        with app.test_request_context("/"):
            assert gara.get_display_name() == "Gara 2 - Campionato Invernale"


@pytest.mark.unit
def test_templates_do_not_reinvent_the_fallback():
    """Anti-drift: la formattazione a mano non deve ricomparire.

    `_campionato_garas.html` è escluso di proposito — mostra il numero come
    intestazione e il nome come sottotitolo, un layout a due righe voluto,
    con una guardia che già evita la ripetizione.
    """
    allowed = {"_campionato_garas.html"}
    pattern = re.compile(
        r"""\.name\s+or\s+(?:\(?\s*['"]Gara|_\(\s*['"]Gara)""",
    )

    offenders = []
    for path in TEMPLATES.rglob("*.html"):
        if path.name in allowed:
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if pattern.search(line):
                offenders.append(f"{path.relative_to(TEMPLATES)}:{lineno}")

    assert (
        not offenders
    ), "titolo gara formattato a mano invece di `gara.display_name`: " + ", ".join(
        offenders
    )
