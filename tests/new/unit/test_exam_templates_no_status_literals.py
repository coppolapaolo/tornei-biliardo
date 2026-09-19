"""Nei template degli esami lo stato si confronta con l'enum, non con una stringa.

``r.status == 'accepted'`` funziona finché il letterale coincide col valore
dell'enum, e smette di funzionare **in silenzio**: un refuso, o un valore
rinominato, manda la riga nel ramo ``else`` — in `requests.html` voleva dire
mostrare «Scaduta» su un appuntamento confermato. Con l'enum passato al
template il refuso diventa un errore alla prima apertura della pagina.

`session.html` entra in elenco con la fase 3d, che la riscrive.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

TEMPLATES = Path(__file__).resolve().parents[3] / "templates" / "exam"

GUARDED = ["requests.html", "request_detail.html", "request_form.html"]

LITERAL = re.compile(r"\b(?:status|mode)\s*(?:==|!=|in)\s*[\[(]?\s*['\"]")


@pytest.mark.parametrize("name", GUARDED)
def test_nessuno_stato_confrontato_con_un_letterale(name):
    source = (TEMPLATES / name).read_text(encoding="utf-8")

    found = [
        f"{name}:{number}: {line.strip()}"
        for number, line in enumerate(source.splitlines(), start=1)
        if LITERAL.search(line)
    ]

    assert not found, "Stato confrontato con un letterale:\n" + "\n".join(found)
