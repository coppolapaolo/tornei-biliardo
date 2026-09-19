#!/usr/bin/env python3
"""Scrive traduzioni in un catalogo `.po` **senza riformattarlo**.

Serve al passo 3 della skill `translate`. Riscrivere il catalogo con
`babel.messages.pofile.write_po` funziona, ma riformatta ogni voce: la PR che
aggiunge dieci stringhe si porta dietro migliaia di righe cambiate, e i
cataloghi sono già il punto in cui due PR aperte insieme vanno in conflitto.
Qui si tocca solo il blocco della voce che si traduce.

Uso:

    # le traduzioni in un file JSON {"msgid italiano": "english msgstr", ...}
    python scripts/po_set.py translations/en/LC_MESSAGES/messages.po nuove.json

    # passo 3-bis: toglie `fuzzy` dalle voci a msgstr vuoto (catalogo italiano)
    python scripts/po_set.py translations/it/LC_MESSAGES/messages.po --clear-empty-fuzzy

Cosa fa a una voce tradotta: riscrive `msgstr` (a capo come li mette Babel),
toglie il flag `fuzzy` e le righe `#|` della voce a cui pybabel l'aveva
avvicinata. Le voci **plurali** non le tocca e le elenca: vanno scritte a mano.
Un `msgid` del JSON che nel catalogo non c'è è un errore, non un avviso: quasi
sempre è un refuso, e la stringa resterebbe non tradotta in silenzio.
"""

from __future__ import annotations

import ast
import json
import re
import sys
from io import BytesIO
from pathlib import Path

from babel.messages.catalog import Catalog
from babel.messages.pofile import write_po


def _msgstr_lines(msgid: str, msgstr: str) -> list[str]:
    """Le righe `msgstr` come le scriverebbe Babel: si fa scrivere a lui un
    catalogo di una voce sola e si prendono quelle. Rifare a mano i suoi a capo
    vorrebbe dire un diff al prossimo `pybabel update`."""
    catalog = Catalog()
    catalog.add(msgid, msgstr)
    buffer = BytesIO()
    write_po(buffer, catalog, omit_header=True, width=76)
    lines = buffer.getvalue().decode("utf-8").strip("\n").split("\n")
    start = next(i for i, line in enumerate(lines) if line.startswith("msgstr "))
    return lines[start:]


def _unquote(lines: list[str]) -> str:
    return "".join(ast.literal_eval(line.strip()) for line in lines if line.strip())


def _field(block: list[str], name: str) -> tuple[int, int] | None:
    """Intervallo [inizio, fine) delle righe del campo `name` nel blocco."""
    for start, line in enumerate(block):
        if line.startswith(name + " "):
            end = start + 1
            while end < len(block) and block[end].startswith('"'):
                end += 1
            return start, end
    return None


def _msgid(block: list[str]) -> str | None:
    span = _field(block, "msgid")
    if span is None:
        return None
    first = block[span[0]][len("msgid ") :]
    return _unquote([first] + block[span[0] + 1 : span[1]])


def _msgstr(block: list[str]) -> str | None:
    span = _field(block, "msgstr")
    if span is None:
        return None
    first = block[span[0]][len("msgstr ") :]
    return _unquote([first] + block[span[0] + 1 : span[1]])


def _drop_fuzzy(block: list[str]) -> list[str]:
    out = []
    for line in block:
        if line.startswith("#|"):
            continue
        if line.startswith("#,"):
            flags = [f.strip() for f in line[2:].split(",") if f.strip() != "fuzzy"]
            if not flags:
                continue
            line = "#, " + ", ".join(flags)
        out.append(line)
    return out


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__)
        return 2
    po_path = Path(argv[1])
    clear_only = argv[2] == "--clear-empty-fuzzy"
    wanted = {} if clear_only else json.loads(Path(argv[2]).read_text("utf-8"))

    blocks = [b.split("\n") for b in po_path.read_text("utf-8").split("\n\n")]
    done, plurals, cleared = set(), [], 0

    for index, block in enumerate(blocks):
        msgid = _msgid(block)
        if not msgid:
            continue
        is_fuzzy = any(
            line.startswith("#,") and re.search(r"\bfuzzy\b", line) for line in block
        )
        if clear_only:
            if is_fuzzy and _msgstr(block) == "":
                blocks[index] = _drop_fuzzy(block)
                cleared += 1
            continue
        if msgid not in wanted:
            continue
        if _field(block, "msgid_plural") is not None:
            plurals.append(msgid)
            continue
        start, end = _field(block, "msgstr")  # type: ignore[misc]
        block[start:end] = _msgstr_lines(msgid, wanted[msgid])
        blocks[index] = _drop_fuzzy(block)
        done.add(msgid)

    po_path.write_text("\n\n".join("\n".join(b) for b in blocks), "utf-8")

    if clear_only:
        print(f"{po_path}: tolto `fuzzy` da {cleared} voci a msgstr vuoto")
        return 0
    print(f"{po_path}: {len(done)} voci scritte")
    for msgid in plurals:
        print(f"  PLURALE, da scrivere a mano: {msgid!r}")
    missing = set(wanted) - done - set(plurals)
    for msgid in sorted(missing):
        print(f"  NON TROVATA nel catalogo: {msgid!r}")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
