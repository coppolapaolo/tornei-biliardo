"""I messaggi delle route di gestione della gara passano da ``_()``.

Fino al 2026-10-11 la creazione della gara singola rispondeva con
``flash(f"Errore nella creazione: {e}")``: in inglese il direttore leggeva
l'italiano, e una f-string non si può nemmeno estrarre nel catalogo. Lo stesso
valeva per iscrizioni, turni, spareggio SSR ed esercizi fra i turni.

Il presidio legge il sorgente di ``routes/admin/competition/`` e rifiuta ogni
``flash(...)`` il cui testo sia un letterale o una f-string, e ogni
``"message"``/``"error"`` di una risposta JSON scritto allo stesso modo. Un
testo che arriva già composto da un servizio (``str(e)``, una variabile) non è
affar suo.
"""

import ast
from pathlib import Path

import pytest

CARTELLA = Path(__file__).resolve().parents[3] / "routes" / "admin" / "competition"


def _scritto_a_mano(nodo: ast.AST) -> bool:
    if isinstance(nodo, ast.JoinedStr):
        return True
    if isinstance(nodo, ast.Constant) and isinstance(nodo.value, str):
        return any(c.isalpha() for c in nodo.value)
    if isinstance(nodo, ast.BinOp):
        return _scritto_a_mano(nodo.left) or _scritto_a_mano(nodo.right)
    return False


def _testi_non_tradotti(percorso: Path) -> list[str]:
    albero = ast.parse(percorso.read_text(encoding="utf-8"))
    trovati = []
    for nodo in ast.walk(albero):
        if isinstance(nodo, ast.Call):
            nome = getattr(nodo.func, "id", getattr(nodo.func, "attr", ""))
            if nome == "flash" and nodo.args and _scritto_a_mano(nodo.args[0]):
                trovati.append(f"{percorso.name}:{nodo.lineno} flash")
        if isinstance(nodo, ast.Dict):
            for chiave, valore in zip(nodo.keys, nodo.values):
                if (
                    isinstance(chiave, ast.Constant)
                    and chiave.value in ("message", "error")
                    and _scritto_a_mano(valore)
                ):
                    trovati.append(f"{percorso.name}:{valore.lineno} {chiave.value}")
    return trovati


@pytest.mark.parametrize(
    "percorso", sorted(CARTELLA.glob("*.py")), ids=lambda p: p.name
)
def test_nessun_messaggio_scritto_senza_traduzione(percorso):
    assert _testi_non_tradotti(percorso) == []
