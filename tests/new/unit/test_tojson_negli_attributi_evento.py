"""`|tojson` in un attributo `on…` vuole gli apici singoli.

`tojson` produce una stringa JSON fra **doppi** apici. Dentro
`onsubmit="return confirm({{ msg|tojson }})"` il primo `"` del JSON chiude
l'attributo: il browser legge `onsubmit="return confirm("`, lo scarta come
codice non valido, e il resto diventa spazzatura fra gli attributi del tag.
Non c'è nessun errore visibile — il form semplicemente parte **senza**
chiedere niente.

La regola era scritta in `templates/CLAUDE.md` e non era presidiata. Il 27
settembre 2026 ne sono venuti fuori tre casi, tutti conferme che non sono mai
comparse: «Chiudi il corso» (`istruttore/gruppo.html`), «Non seguirla più» e
«Archivia» sulle schede (`sheet/`). Trovati solo perché si stavano
convertendo i `confirm()` del browser (ADR-074).

Il controllo è testuale, non una regex: il valore dell'attributo arriva fino
al primo `"` **fuori** da `{{ … }}`, perché dentro un'espressione Jinja i
doppi apici sono del sorgente Python e spariscono al rendering.
"""

from __future__ import annotations

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]

_INIZIO = re.compile(r'\son[a-z]+="')


def attributi_rotti(testo: str) -> list[int]:
    """Righe degli attributi `on…="…"` che contengono un `|tojson`."""
    righe = []
    for m in _INIZIO.finditer(testo):
        i, valore = m.end(), []
        while i < len(testo):
            if testo.startswith("{{", i):
                fine = testo.find("}}", i)
                fine = len(testo) if fine < 0 else fine + 2
                valore.append(testo[i:fine])
                i = fine
                continue
            if testo[i] == '"':
                break
            valore.append(testo[i])
            i += 1
        if re.search(r"\|\s*tojson", "".join(valore)):
            righe.append(testo.count("\n", 0, m.start()) + 1)
    return righe


def test_il_riconoscitore():
    assert attributi_rotti('<form onsubmit="return f({{ x|tojson }})">') == [1]
    assert attributi_rotti("<form onsubmit='return f({{ x|tojson }})'>") == []
    assert attributi_rotti('<b onclick="f({{ _("a")|tojson }})">') == [1]
    assert attributi_rotti('<b onclick="f()" title="{{ x|tojson }}">') == []


def test_nessun_tojson_in_attributi_evento_fra_doppi_apici():
    trovati = []
    for percorso in sorted((PROJECT_ROOT / "templates").rglob("*.html")):
        relativo = percorso.relative_to(PROJECT_ROOT).as_posix()
        for riga in attributi_rotti(percorso.read_text(encoding="utf-8")):
            trovati.append(f"{relativo}:{riga}")
    assert not trovati, (
        "`|tojson` in un attributo evento fra doppi apici: il JSON chiude "
        "l'attributo e il codice non gira mai. Usa gli apici singoli "
        "(templates/CLAUDE.md):\n  " + "\n  ".join(trovati)
    )
