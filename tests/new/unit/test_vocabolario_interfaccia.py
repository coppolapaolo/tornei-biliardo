"""Presidio statico del vocabolario dell'interfaccia.

Tre parole hanno smesso di essere sinonimi, e la confusione fra loro era il
motivo della rinomina:

- l'esercizio di abilità (nel codice ``Challenge``) si chiama **esercizio**,
  mai «challenge» e mai «drill»;
- la partita fra due giocatori fuori da una gara si chiama **sfida
  individuale**, mai «match individuale»;
- «sfida» quindi è occupata: usarla per l'esercizio rimetterebbe in piedi
  l'ambiguità appena tolta.

I nomi *tecnici* non c'entrano e restano dove sono: la classe ``Challenge``, la
tabella ``challenge``, le route ``/challenges/``, i codici ABAC
``do_challenge``/``create_challenge``, gli slug dei traguardi. Questo test
guarda **solo** ciò che finisce sotto gli occhi di chi usa l'app, cioè le
stringhe dentro ``_()`` — e le riconosce col parser di Babel, non con una
regex: un apostrofo italiano dentro una stringa (``l'esercizio``) manda fuori
strada qualunque espressione regolare, ed è esattamente il caso più frequente.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterator, Tuple

from babel.messages.extract import extract_from_dir

ROOT = Path(__file__).resolve().parents[3]

# Le stesse regole di babel.cfg: se un giorno divergono, meglio scoprirlo qui.
_METHOD_MAP = [
    ("**.py", "python"),
    ("**/templates/**.html", "jinja2"),
]
_OPTIONS = {
    "**/templates/**.html": {
        "encoding": "utf-8",
        "silent": "false",
        "extensions": "jinja2.ext.do,jinja2.ext.loopcontrols",
    }
}

# Cartelle che non producono interfaccia (o che la producono per i test).
_SKIP = (
    "venv/",
    "tests/",
    "migrations/",
    "scripts/",
    "_bmad",
    "docs/",
    "node_modules/",
)

_VIETATE = (
    (re.compile(r"\bchallenges?\b", re.IGNORECASE), "«challenge» → «esercizio»"),
    (re.compile(r"\bdrills?\b", re.IGNORECASE), "«drill» → «esercizio»"),
    (
        re.compile(r"\bmatch\s+individual", re.IGNORECASE),
        "«match individuale» → «sfida individuale»",
    ),
)


def _stringhe_interfaccia() -> Iterator[Tuple[str, int, str]]:
    """(file, riga, testo) per ogni stringa marcata come traducibile."""
    for filename, lineno, message, _comments, _ctx in extract_from_dir(
        str(ROOT), method_map=_METHOD_MAP, options_map=_OPTIONS
    ):
        rel = filename.replace("\\", "/")
        if any(part in rel for part in _SKIP):
            continue
        testi = message if isinstance(message, tuple) else (message,)
        for testo in testi:
            if isinstance(testo, str) and testo:
                yield rel, lineno, testo


def test_interfaccia_non_dice_piu_challenge_ne_drill():
    """Nessuna stringa visibile chiama l'esercizio «challenge» o «drill».

    Regressione: prima della rinomina la stessa cosa si chiamava in tre modi
    diversi — «Challenge» nel menu, «drill» nell'esame, «esercizio» nella
    schermata di creazione — e nessuno dei tre era sbagliato abbastanza da
    farsi notare.
    """
    colpevoli = [
        f"{rel}:{riga} — {motivo}: {testo!r}"
        for rel, riga, testo in _stringhe_interfaccia()
        for pattern, motivo in _VIETATE
        if pattern.search(testo)
    ]
    assert not colpevoli, "Vocabolario dell'interfaccia disallineato:\n" + "\n".join(
        sorted(colpevoli)
    )


def test_esercizio_non_si_chiama_sfida():
    """«Sfida» è la partita fra giocatori: non deve tornare a dire «esercizio».

    Le pagine dell'esercizio (catalogo, allenamento, builder, esami) sono il
    posto dove la vecchia parola aveva più presa, quindi è lì che il presidio
    guarda. Le pagine delle sfide individuali dicono «sfida» a ragione e
    restano fuori.
    """
    aree = ("templates/challenge/", "templates/exam/", "routes/challenge.py")
    sfida = re.compile(r"\bsfid[aeo]\b", re.IGNORECASE)
    colpevoli = [
        f"{rel}:{riga} — {testo!r}"
        for rel, riga, testo in _stringhe_interfaccia()
        if any(area in rel for area in aree) and sfida.search(testo)
    ]
    assert not colpevoli, (
        "Nelle pagine degli esercizi è ricomparsa la parola «sfida», "
        "che ora indica la partita fra due giocatori:\n" + "\n".join(sorted(colpevoli))
    )
