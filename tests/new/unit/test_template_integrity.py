"""Integrità statica di tutti i template Jinja.

Due guasti reali hanno motivato questo file, entrambi invisibili fino
all'apertura della pagina giusta nella condizione giusta:

1. `components/_pagination.html` non compilava: l'esempio d'uso nel
   commento in cima era racchiuso in `<!-- -->`, che nasconde il testo al
   browser ma non a Jinja. Il motore interpretava quel `{% set %}` e
   l'`...` dell'esempio non è sintassi valida. Le tre pagine admin di
   gamification che lo includono rispondevano 500.

2. Alcuni `url_for` puntavano a endpoint inesistenti — nomi plausibili
   (`player.create_match_proposal`, `challenge.attempt_challenge`) ma mai
   registrati. Flask solleva BuildError solo quando quel ramo del template
   viene renderizzato, quindi il 500 aspetta l'utente nella condizione
   giusta invece di presentarsi all'avvio.

I controlli sono statici: compilano ogni file e verificano i riferimenti
simbolici, senza renderizzare nulla. Girano in meno di un secondo e
coprono tutti i template, non solo quelli che qualcuno si ricorda di
aprire.
"""

import re
from pathlib import Path

import pytest

TEMPLATES = Path(__file__).resolve().parents[3] / "templates"

RE_INCLUDE = re.compile(r"{%-?\s*(?:include|extends)\s+['\"]([^'\"]+)['\"]")
# Solo endpoint letterali: url_for(variabile) non è verificabile staticamente.
RE_URL_FOR = re.compile(r"url_for\(\s*['\"]([a-zA-Z0-9_.]+)['\"]")


def _tutti_i_template():
    return sorted(
        p.relative_to(TEMPLATES).as_posix() for p in TEMPLATES.rglob("*.html")
    )


@pytest.fixture(scope="module")
def nomi_template():
    return _tutti_i_template()


def test_ci_sono_template_da_controllare(nomi_template):
    """Guardia contro un glob che smette di trovare i file e passa a vuoto."""
    assert len(nomi_template) > 100


def test_ogni_template_compila(app, nomi_template):
    """Nessun template deve avere errori di sintassi Jinja.

    `{% include %}` è risolto a runtime: un partial rotto non impedisce
    alla pagina che lo include di compilare, quindi ogni file va compilato
    per conto suo.
    """
    rotti = []
    for nome in nomi_template:
        try:
            app.jinja_env.get_template(nome)
        except Exception as exc:  # noqa: BLE001 - il messaggio grezzo è il valore
            rotti.append(f"{nome}: {type(exc).__name__}: {exc}")

    assert not rotti, "template che non compilano:\n" + "\n".join(rotti)


def test_ogni_include_esiste(nomi_template):
    """`include`/`extends` con percorso letterale devono puntare a un file."""
    mancanti = []
    for nome in nomi_template:
        testo = (TEMPLATES / nome).read_text(encoding="utf-8")
        for riferimento in RE_INCLUDE.findall(testo):
            if not (TEMPLATES / riferimento).exists():
                mancanti.append(f"{nome} -> {riferimento}")

    assert not mancanti, "include/extends non risolvibili:\n" + "\n".join(mancanti)


def test_ogni_url_for_punta_a_un_endpoint_reale(app, nomi_template):
    """Un endpoint inventato esplode solo quando quel ramo viene reso."""
    registrati = {regola.endpoint for regola in app.url_map.iter_rules()}

    fantasma = []
    for nome in nomi_template:
        testo = (TEMPLATES / nome).read_text(encoding="utf-8")
        for endpoint in RE_URL_FOR.findall(testo):
            if endpoint not in registrati:
                fantasma.append(f"{nome} -> {endpoint}")

    assert not fantasma, "url_for verso endpoint inesistenti:\n" + "\n".join(fantasma)
