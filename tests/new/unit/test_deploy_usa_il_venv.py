"""Il deploy installa dove la web app importa, e si ferma se non ci riesce.

Due difetti gemelli in `scripts/auto_deploy.py`, scoperti il 2026-08-17 con
`/aiuto` che rispondeva 500 da due giorni:

1. **pip girava con `sys.executable`**, cioe' con l'interprete che esegue lo
   script — che e' quello del virtualenv solo se il task e' configurato per
   usarlo. Il docstring dello script documentava `python
   scripts/auto_deploy.py`, e un `python` nudo su PythonAnywhere e'
   l'interprete di sistema: le dipendenze finivano fuori da `venv/`, dove la
   web app non guarda. `deps_in_sync()`, interrogando lo stesso interprete, le
   trovava e dichiarava che era tutto a posto.

   Nessuno se n'era accorto per sei mesi perche' fra febbraio e agosto 2026 non
   e' stata aggiunta nessuna dipendenza: ogni installazione era un no-op. Il
   primo pacchetto nuovo — PyYAML, per il mini-sito di aiuto — non e' mai
   arrivato in produzione, e `ModuleNotFoundError: No module named 'yaml'` e'
   sopravvissuto a due deploy consecutivi.

2. **un `pip install` fallito era solo un WARNING**, e il deploy proseguiva
   fino al reload. La web app ripartiva col codice nuovo e le dipendenze
   vecchie: peggio che restare ferma, perche' senza reload il codice
   precedente continua a funzionare.

Il presidio e' statico perche' non c'e' modo di provare un deploy nei test:
gira su PythonAnywhere, una volta al giorno, e il guasto si vede solo aprendo
la pagina.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "auto_deploy.py"
SORGENTE = SCRIPT.read_text(encoding="utf-8")
ALBERO = ast.parse(SORGENTE)

#: Le funzioni che lanciano un sottoprocesso il cui interprete conta: pip deve
#: installare nel virtualenv della web app, e il runner delle migrations deve
#: importare i modelli con le dipendenze di quel virtualenv.
FUNZIONI_CON_INTERPRETE = (
    "deps_in_sync",
    "install_dependencies",
    "run_migrations",
    "count_pending_migrations",
)


def _funzione(nome: str) -> ast.FunctionDef:
    for nodo in ast.walk(ALBERO):
        if isinstance(nodo, ast.FunctionDef) and nodo.name == nome:
            return nodo
    pytest.fail(f"`{nome}` non esiste piu' in auto_deploy.py: aggiorna il presidio.")


@pytest.mark.parametrize("nome", FUNZIONI_CON_INTERPRETE)
def test_il_sottoprocesso_non_usa_l_interprete_corrente(nome: str):
    """`sys.executable` e' chi esegue lo script, non chi serve la web app."""
    corpo = ast.dump(_funzione(nome))
    assert "attr='executable'" not in corpo, (
        f"`{nome}` lancia un sottoprocesso con `sys.executable`. Se il task e' "
        "configurato con un `python` nudo quello e' l'interprete di sistema, e "
        "pip installa fuori dal virtualenv da cui la web app importa — senza "
        "errori, perche' l'installazione riesce: solo altrove. Usa "
        "`venv_python()`."
    )
    assert (
        "venv_python" in corpo
    ), f"`{nome}` non risolve piu' l'interprete con `venv_python()`."


def _e_uscita(nodo: ast.AST) -> bool:
    """`sys.exit(...)` o `exit(...)`, comunque scritto."""
    for interno in ast.walk(nodo):
        if not isinstance(interno, ast.Call):
            continue
        funzione = interno.func
        if isinstance(funzione, ast.Attribute) and funzione.attr == "exit":
            return True
        if isinstance(funzione, ast.Name) and funzione.id == "exit":
            return True
    return False


def test_un_installazione_fallita_ferma_il_deploy():
    """Ricaricare con le dipendenze vecchie e' peggio che non ricaricare."""
    main = _funzione("main")

    righe_installazione = [
        nodo.lineno
        for nodo in ast.walk(main)
        if isinstance(nodo, ast.Call)
        and isinstance(nodo.func, ast.Name)
        and nodo.func.id == "install_dependencies"
    ]
    assert righe_installazione, "main() non installa piu' le dipendenze."
    riga = righe_installazione[0]

    # Il primo `if` dopo l'installazione e' quello che ne esamina l'esito:
    # deve uscire, non stampare e proseguire fino al reload.
    successivi = sorted(
        (
            nodo
            for nodo in ast.walk(main)
            if isinstance(nodo, ast.If) and nodo.lineno > riga
        ),
        key=lambda nodo: nodo.lineno,
    )
    assert successivi, "Dopo l'installazione non si controlla piu' l'esito."
    assert _e_uscita(successivi[0]), (
        "Un `pip install` fallito non interrompe piu' il deploy. Era un "
        "semplice WARNING fino al 2026-08-17: la web app ripartiva col codice "
        "nuovo e le dipendenze vecchie, e l'unica traccia era una riga in un "
        "log che nessuno legge."
    )


def test_il_docstring_documenta_il_comando_giusto():
    """Chi configura il task legge questo file, non la guida per sviluppatori.

    Le due fonti erano in disaccordo: `DEVELOPMENT_GUIDE.md` diceva
    `venv/bin/python`, il docstring dello script diceva `python`. Ha vinto il
    docstring, che e' quello che si ha davanti quando si apre lo script.
    """
    docstring = ast.get_docstring(ALBERO) or ""
    comandi = re.findall(
        r"^\s*(?:\d\.\s*Command:\s*)?(.*auto_deploy\.py)\s*$", docstring, re.M
    )
    assert comandi, "Il docstring non mostra piu' come si lancia lo script."
    for comando in comandi:
        assert "venv/bin/python" in comando, (
            f"Il docstring documenta «{comando.strip()}»: un `python` nudo su "
            "PythonAnywhere e' l'interprete di sistema, non quello del "
            "virtualenv della web app."
        )


def test_la_guida_e_il_docstring_dicono_la_stessa_cosa():
    """Due fonti che si contraddicono valgono meno di una sola."""
    guida = (
        Path(__file__).resolve().parents[3]
        / "docs"
        / "reference"
        / "DEVELOPMENT_GUIDE.md"
    ).read_text(encoding="utf-8")
    righe = [r for r in guida.splitlines() if "auto_deploy.py" in r and "python" in r]
    assert righe, "La guida non documenta piu' il comando dello scheduled task."
    for riga in righe:
        assert "venv/bin/python" in riga, (
            f"La guida documenta «{riga.strip()}», in disaccordo col docstring "
            "dello script."
        )
