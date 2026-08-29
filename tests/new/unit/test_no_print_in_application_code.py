"""Un errore stampato con `print()` è un errore che non ha un destinatario.

Nel server log di produzione del 26-29 agosto 2026 comparivano righe nostre in
mezzo a quelle di uWSGI — «Calculating classification for round 1», «DEBUG:
Notification created for user 60». Erano `print()`. Il guasto vero però non è
il rumore nel log: è che **quattro** di quelle righe stavano dentro un `except`.
Lì l'eccezione viene catturata, scritta a video, e quindi **non arriva a
GlitchTip**: resta un guasto gestito che nessuno vede mai. L'unico modo di
accorgersene è leggere a mano un file di log che nessuno legge (issue #256).

`logging` non ha questo difetto: l'handler di GlitchTip è agganciato al logger
radice, quindi un `logger.error(..., exc_info=True)` diventa una issue con lo
stack, e un `logger.debug(...)` si può spegnere senza toccare il codice.

**Perché il presidio legge l'AST e non il testo.** Il `grep -rn "print("` che
ha aperto l'issue contava dieci occorrenze, ma tre erano `Blueprint(` e una
`auth_fingerprint(`; e altre tre erano `print()` scritti dentro i blocchi
``Example:`` dei docstring di `models/gamification/`, cioè codice illustrativo
che non viene eseguito e che è giusto lasciare com'è. Un criterio testuale
sbaglia in tutte e due le direzioni. Per l'AST un docstring è una costante
stringa — non contiene chiamate — e `Blueprint` è un altro nome: la distinzione
«eseguito / illustrativo» viene gratis, senza elencare eccezioni a mano.

**Cosa resta legittimo.** `utils/__init__.py` e `utils/reset_data.py` sono
strumenti da console: lì stampare a video *è* l'interfaccia, e un logger
sarebbe la scelta sbagliata. Sono le uniche due eccezioni, ed è per questo che
sono scritte qui invece che dedotte da una regola.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Iterator

PROJECT_ROOT = Path(__file__).resolve().parents[3]

# Il codice applicativo: quello che gira dentro una richiesta o uno scheduled
# task, dove non c'è nessuno davanti a un terminale a leggere.
CARTELLE_PRESIDIATE = ("models", "routes", "utils")

# Gli strumenti da console, dove la stampa a video è l'interfaccia e non un
# messaggio smarrito. Percorsi relativi alla radice del progetto.
STRUMENTI_DA_CONSOLE = frozenset(
    {
        "utils/__init__.py",
        "utils/reset_data.py",
    }
)


def _file_applicativi() -> Iterator[Path]:
    for cartella in CARTELLE_PRESIDIATE:
        yield from sorted((PROJECT_ROOT / cartella).rglob("*.py"))


def _chiamate_a_print(sorgente: str) -> list[int]:
    """Le righe in cui `print` viene *chiamato*, secondo l'AST."""
    albero = ast.parse(sorgente)
    return [
        nodo.lineno
        for nodo in ast.walk(albero)
        if isinstance(nodo, ast.Call)
        and isinstance(nodo.func, ast.Name)
        and nodo.func.id == "print"
    ]


def test_nessun_print_nel_codice_applicativo():
    """Un messaggio applicativo passa da `logging`, non da `print`."""
    colpevoli: list[str] = []

    for percorso in _file_applicativi():
        relativo = percorso.relative_to(PROJECT_ROOT).as_posix()
        if relativo in STRUMENTI_DA_CONSOLE:
            continue
        for riga in _chiamate_a_print(percorso.read_text(encoding="utf-8")):
            colpevoli.append(f"{relativo}:{riga}")

    assert not colpevoli, (
        "print() nel codice applicativo — usa logger.debug(...) o "
        "logger.error(..., exc_info=True), altrimenti l'errore non arriva a "
        "GlitchTip:\n  " + "\n  ".join(colpevoli)
    )


def test_le_eccezioni_da_console_esistono_ancora():
    """L'elenco delle eccezioni non deve sopravvivere ai file che nomina.

    Un percorso rimasto in `STRUMENTI_DA_CONSOLE` dopo che il file è stato
    rinominato o cancellato è un buco silenzioso: il presidio continuerebbe a
    passare, e nessuno saprebbe che sta esentando qualcosa che non c'è.
    """
    mancanti = [
        percorso
        for percorso in sorted(STRUMENTI_DA_CONSOLE)
        if not (PROJECT_ROOT / percorso).exists()
    ]

    assert not mancanti, (
        "Questi file sono esentati dal presidio ma non esistono più: "
        f"{mancanti}. Toglili da STRUMENTI_DA_CONSOLE."
    )
