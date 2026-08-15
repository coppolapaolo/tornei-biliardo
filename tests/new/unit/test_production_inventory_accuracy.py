"""L'inventario delle route deve descrivere l'app che esiste davvero.

`docs/reference/PRODUCTION_INVENTORY.md` e' la base su cui si compila la
matrice `ENDPOINT_ROLES` di ADR-028: se l'inventario cita un endpoint che non
esiste, quell'errore viene ricopiato nella matrice e da li' in produzione. E'
gia' successo due volte — `admin.competition.round_management_overview` (una
pagina il cui template non e' mai esistito, listata per mesi) e
`admin.user.users_list` promesso ai direttori mentre il decoratore lo nega.

Questo test non chiede all'inventario di essere completo: chiede che cio' che
afferma sia vero. Ogni riga di tabella che cita un endpoint Flask deve citarne
uno registrato, e sul path a cui e' davvero montato.
"""

import re
from pathlib import Path

import pytest

INVENTORY = (
    Path(__file__).resolve().parents[3] / "docs/reference/PRODUCTION_INVENTORY.md"
)

# `blueprint.endpoint` o `blueprint.sub.endpoint`, come compaiono in tabella.
ENDPOINT_RE = re.compile(r"[a-z_]+(?:\.[a-z_0-9]+)+")


def _cited_rows():
    """(numero di riga, path, endpoint) per ogni riga di tabella dell'inventario."""
    for lineno, line in enumerate(INVENTORY.read_text().splitlines(), start=1):
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.split("|")]
        # | (vuoto) | path | metodo | endpoint | decoratori | tipo | descrizione |
        if len(cells) < 5:
            continue
        path, endpoint = cells[1].strip("`"), cells[3].strip("`")
        if ENDPOINT_RE.fullmatch(endpoint):
            yield lineno, path, endpoint


def test_inventory_file_exists():
    assert INVENTORY.exists(), f"inventario mancante: {INVENTORY}"


def test_inventory_cites_only_real_endpoints(app):
    """Nessuna riga cita un endpoint che Flask non conosce."""
    real = {rule.endpoint for rule in app.url_map.iter_rules()}
    fantasmi = [
        f"riga {lineno}: `{endpoint}`"
        for lineno, _path, endpoint in _cited_rows()
        if endpoint not in real
    ]
    assert not fantasmi, (
        "endpoint inesistenti citati in PRODUCTION_INVENTORY.md — la route e'"
        " stata rinominata o rimossa e l'inventario non e' stato aggiornato:\n"
        + "\n".join(fantasmi)
    )


def test_inventory_paths_match_the_url_map(app):
    """Ogni endpoint e' documentato sul path a cui e' davvero montato.

    Un path sbagliato non e' un dettaglio estetico: chi legge l'inventario per
    decidere cosa esporre in produzione ragiona sul prefisso (il blueprint
    `admin.competition` vive sotto `/admin/gara`, non `/admin/competition`).
    """
    per_path = {}
    for rule in app.url_map.iter_rules():
        per_path.setdefault(str(rule), set()).add(rule.endpoint)

    disallineate = []
    for lineno, path, endpoint in _cited_rows():
        if path not in per_path:
            disallineate.append(
                f"riga {lineno}: path inesistente `{path}` ({endpoint})"
            )
        elif endpoint not in per_path[path]:
            disallineate.append(
                f"riga {lineno}: `{endpoint}` non e' montato su `{path}`"
                f" (li' c'e' {sorted(per_path[path])})"
            )

    assert not disallineate, "\n".join(disallineate)


@pytest.mark.parametrize("blueprint", ["admin.competition"])
def test_competition_section_is_complete(app, blueprint):
    """La sezione ADMIN/COMPETITION copre tutte le route del blueprint.

    Verificata riga per riga contro `app.url_map` (2026-08-15). Le altre
    sezioni non hanno ancora questa garanzia: restano lacunose, e il test
    sopra si limita a impedire che raccontino il falso.
    """
    documentati = {endpoint for _l, _p, endpoint in _cited_rows()}
    reali = {
        rule.endpoint
        for rule in app.url_map.iter_rules()
        if rule.endpoint.startswith(f"{blueprint}.")
    }
    mancanti = sorted(reali - documentati)
    assert not mancanti, f"route di `{blueprint}` assenti dall'inventario: {mancanti}"
