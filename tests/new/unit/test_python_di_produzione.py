"""La CI e pyright verificano il Python su cui gira la produzione.

Il 27 settembre 2026 si è scoperto che il progetto girava su quattro Python
diversi: produzione 3.10 (PythonAnywhere, lo dicevano i percorsi dei
traceback), CI 3.11, sviluppo 3.12, e `pyrightconfig.json` controllava i
tipi come se fosse 3.9. Nessuno l'aveva deciso: ognuno era il default del
momento in cui era stato configurato.

La conseguenza si è vista subito. SQLAlchemy 2.1 richiede Python 3.11: in
CI i test sarebbero passati tutti, e di notte `auto_deploy` in produzione
avrebbe fallito, una notte dopo l'altra, perché pip non trova versioni
installabili. Una CI che prova un altro Python non protegge la produzione.

**La fonte è `.python-version`**, e dice la versione di **produzione**. La
CI la legge direttamente (`python-version-file`), quindi non può divergere.
pyright non sa leggerla, e per questo il suo `pythonVersion` si confronta
qui. Quando la produzione cambia Python — dopo aver creato il venv nuovo su
PythonAnywhere, non prima — si cambia quel file, e questo test chiede di
allineare anche pyright.

Il Python dello sviluppo può essere più nuovo: il codice che gira su 3.10
gira anche su 3.12. Il contrario no, ed è proprio quello che la CI
deve fermare.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _versione_di_produzione() -> str:
    return (PROJECT_ROOT / ".python-version").read_text(encoding="utf-8").strip()


def test_la_versione_di_produzione_e_major_minor():
    """`3.10`, non `3.10.19`: la patch la sceglie chi installa."""
    assert re.fullmatch(r"3\.\d+", _versione_di_produzione())


def test_la_ci_legge_la_versione_dal_file():
    ci = (PROJECT_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "python-version-file: .python-version" in ci
    letterali = re.findall(r"^\s*python-version:\s*\S+", ci, flags=re.MULTILINE)
    assert not letterali, (
        "Una versione di Python scritta a mano nella CI può divergere dalla "
        f"produzione: usa `python-version-file: .python-version`. Trovato: {letterali}"
    )


def test_pyright_controlla_la_versione_di_produzione():
    config = json.loads(
        (PROJECT_ROOT / "pyrightconfig.json").read_text(encoding="utf-8")
    )
    assert config["pythonVersion"] == _versione_di_produzione()
