"""Presidio statico sull'ordine degli import negli script di produzione.

Un `from app import create_app` in cima a uno script tira dentro `config` e
mezzo dominio **prima** che `bootstrap_or_exit()` abbia messo le variabili del
file WSGI in `os.environ`. Chi legge l'ambiente durante l'import si porta a
casa un ambiente vuoto e non lo rilegge mai più.

È costato due scheduled task fermi — `daily_jobs.py` ogni notte,
`send_match_reminders.py` ogni ora — più `reconcile_achievements.py`, che
sarebbe morto allo stesso modo alla prima esecuzione da console.

`config` e `utils.encryption` sono stati resi indifferenti all'ordine, quindi
questo presidio non è più l'unica difesa. Resta perché è l'unico controllo
*statico*: nessun test funzionale si accorge di un import spostato in cima, e
il guasto si manifesta solo in produzione, dove le env arrivano dal WSGI e non
dalla shell.

La regola è volutamente stretta: vale per gli script che hanno **dichiarato**
di voler girare in produzione, cioè quelli che importano `prod_env`. Gli
script di analisi che si lanciano a mano in sviluppo (`recalc_elo.py`,
`diagnose_elo.py`, …) restano fuori: non caricano env di produzione, quindi
per loro l'ordine non significa niente.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[3] / "scripts"

#: I moduli che leggono `os.environ` durante il proprio import.
MODULI_SENSIBILI = {"app", "config"}


def _import_di_modulo(tree: ast.Module) -> set[str]:
    """I moduli importati a livello di modulo (non dentro funzioni)."""
    nomi: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            nomi.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.level == 0:
                nomi.add(node.module.split(".")[0])
    return nomi


def _script_di_produzione() -> list[Path]:
    """Gli script che caricano le env di produzione, cioè usano `prod_env`."""
    trovati = []
    for path in sorted(SCRIPTS_DIR.rglob("*.py")):
        if path.name == "prod_env.py":
            continue
        if "prod_env" in path.read_text(encoding="utf-8"):
            trovati.append(path)
    return trovati


def test_ci_sono_script_di_produzione_da_controllare():
    """Se la lista si svuota (rinomino, refuso nel filtro) il presidio smette
    di presidiare senza fallire: meglio accorgersene qui."""
    assert _script_di_produzione(), "nessuno script trovato: il filtro è rotto?"


@pytest.mark.unit
@pytest.mark.parametrize("script", _script_di_produzione(), ids=lambda p: p.name)
def test_nessun_import_di_app_o_config_a_livello_di_modulo(script: Path):
    tree = ast.parse(script.read_text(encoding="utf-8"))
    colpevoli = _import_di_modulo(tree) & MODULI_SENSIBILI

    assert not colpevoli, (
        f"{script.name} importa {', '.join(sorted(colpevoli))} a livello di "
        "modulo: l'ambiente verrebbe letto prima di bootstrap_or_exit(). "
        "Usa prod_env.bootstrap_and_create_app(), che importa l'app dopo aver "
        "caricato le env dal file WSGI."
    )


@pytest.mark.unit
def test_prod_env_non_importa_l_app_a_livello_di_modulo():
    """Vale a maggior ragione per il modulo che *è* il bootstrap: se lo
    facesse, ogni script che lo importa avrebbe il problema di riflesso."""
    tree = ast.parse((SCRIPTS_DIR / "prod_env.py").read_text(encoding="utf-8"))

    assert not (_import_di_modulo(tree) & MODULI_SENSIBILI)
