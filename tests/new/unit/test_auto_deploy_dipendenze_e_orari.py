"""`auto_deploy`: il controllo delle dipendenze e l'orario su ogni riga.

Il controllo gira in un sottoprocesso lanciato con l'interprete del venv
(`scripts/requirements_check.py`): i pacchetti che contano sono quelli da cui
importa la web app, non quelli di chi esegue lo script. Se il controllo non
riesce a rispondere, la risposta e' «fuori sync» — si installa — e il motivo
si stampa: un controllo che fallisce in silenzio e' esattamente il difetto che
si e' corretto (vedi `test_requirements_check.py`).

L'orario serve a misurare quello che il log non diceva: nelle notti con
migration i worker vengono fermati da uno a quattro secondi dopo la fine del
task, segno che il `disable` dell'API e' asincrono. Senza un orario per riga il
ritardo non si vede.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

import scripts.auto_deploy as auto_deploy

SORGENTE = (
    Path(__file__).resolve().parents[3] / "scripts" / "auto_deploy.py"
).read_text(encoding="utf-8")


@pytest.mark.unit
def test_in_sync_quando_il_controllo_riesce(monkeypatch):
    comandi = []
    monkeypatch.setattr(
        auto_deploy,
        "run_command",
        lambda cmd, cwd=None: (comandi.append(cmd), (True, ""))[1],
    )

    assert auto_deploy.deps_in_sync() is True
    assert comandi and comandi[0][0] == auto_deploy.venv_python()
    assert comandi[0][1].endswith("requirements_check.py")
    assert "pip" not in comandi[0], "Il controllo non deve piu' chiedere a pip."


@pytest.mark.unit
def test_fuori_sync_stampa_cosa_manca(monkeypatch, capsys):
    monkeypatch.setattr(
        auto_deploy,
        "run_command",
        lambda cmd, cwd=None: (False, "PyYAML>=6.0,<7.0: non installato"),
    )

    assert auto_deploy.deps_in_sync() is False
    assert "PyYAML>=6.0,<7.0: non installato" in capsys.readouterr().out


@pytest.mark.unit
def test_controllo_fallito_e_fuori_sync_e_lo_dice(monkeypatch, capsys):
    """Nessun output dal sottoprocesso: la riga stampata non puo' restare vuota."""
    monkeypatch.setattr(auto_deploy, "run_command", lambda cmd, cwd=None: (False, ""))

    assert auto_deploy.deps_in_sync() is False
    assert "Dipendenze" in capsys.readouterr().out


@pytest.mark.unit
def test_log_prefissa_l_orario_utc(capsys):
    auto_deploy.log("Disable web app: HTTP 200")
    riga = capsys.readouterr().out
    assert re.match(
        r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} UTC  Disable web app: HTTP 200\n$", riga
    ), riga


@pytest.mark.unit
def test_log_su_piu_righe_prefissa_ogni_riga(capsys):
    auto_deploy.log("Git pull: Updating a..b\n 2 files changed")
    righe = capsys.readouterr().out.splitlines()
    assert len(righe) == 2
    assert all(
        re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} UTC  ", r) for r in righe
    )


@pytest.mark.unit
def test_nessuna_print_fuori_da_log():
    """Una `print` nuda e' una riga senza orario: tutto passa da `log`."""
    albero = ast.parse(SORGENTE)
    fuori = []
    for funzione in ast.walk(albero):
        if not isinstance(funzione, ast.FunctionDef) or funzione.name == "log":
            continue
        for nodo in ast.walk(funzione):
            if (
                isinstance(nodo, ast.Call)
                and isinstance(nodo.func, ast.Name)
                and nodo.func.id == "print"
            ):
                fuori.append(f"{funzione.name}:{nodo.lineno}")
    assert not fuori, f"print senza orario in auto_deploy.py: {fuori}"
