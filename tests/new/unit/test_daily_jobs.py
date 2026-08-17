"""Unit test del runner dei lavori giornalieri (`scripts/daily_jobs.py`).

Il valore del runner non è nel singolo job (testato altrove) ma nelle sue
garanzie: isolamento fra job, exit code che riflette l'esito, selezione da CLI.
Sono proprio le cose che, se si rompono, si rompono in silenzio dentro uno
scheduled task che nessuno guarda.
"""

import importlib.util
import os
import sys
from unittest.mock import patch

import pytest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_SCRIPT = os.path.join(_REPO_ROOT, "scripts", "daily_jobs.py")


def _load_runner():
    """Carica lo script come modulo (non è un package importabile)."""
    spec = importlib.util.spec_from_file_location("daily_jobs", _SCRIPT)
    assert (
        spec is not None and spec.loader is not None
    ), f"script non caricabile: {_SCRIPT}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def runner(app):
    """Runner con l'avvio dell'app sostituito da quella di test.

    `bootstrap_and_create_app` fa due cose in una — carica le env di
    produzione e *poi* importa e crea l'app — proprio perché l'ordine è la
    sostanza (vedi la sua docstring in `scripts/prod_env.py`). Qui interessa
    l'orchestrazione dei job, non quel caricamento: le env di produzione in
    test non esistono e hanno i loro test in `test_prod_env.py`.
    """
    module = _load_runner()
    with patch.object(module, "bootstrap_and_create_app", return_value=app):
        yield module


def _run(module, argv):
    with patch.object(sys, "argv", ["daily_jobs.py", *argv]):
        return module.main()


def test_all_jobs_run_and_exit_zero(runner):
    calls = []
    with patch.dict(
        runner.JOBS,
        {
            "a": ("A", lambda: calls.append("a") or "ok a"),
            "b": ("B", lambda: calls.append("b") or "ok b"),
        },
        clear=True,
    ):
        assert _run(runner, []) == 0
    assert calls == ["a", "b"]


def test_failing_job_does_not_stop_the_others(runner):
    """Il punto centrale: un job che solleva non deve azzerare il resto del
    batch. Con i job in sequenza senza isolamento, 'b' non girerebbe mai.
    """
    calls = []

    def boom():
        raise RuntimeError("job esploso")

    with patch.dict(
        runner.JOBS,
        {"a": ("A", boom), "b": ("B", lambda: calls.append("b") or "ok b")},
        clear=True,
    ):
        exit_code = _run(runner, [])

    assert calls == ["b"], "il job successivo deve girare comunque"
    assert exit_code == 1, "un fallimento deve risultare visibile nell'exit code"


def test_selection_runs_only_requested_job(runner):
    calls = []
    with patch.dict(
        runner.JOBS,
        {
            "a": ("A", lambda: calls.append("a") or "ok"),
            "b": ("B", lambda: calls.append("b") or "ok"),
        },
        clear=True,
    ):
        assert _run(runner, ["b"]) == 0
    assert calls == ["b"]


def test_unknown_job_name_is_rejected_without_running_anything(runner):
    calls = []
    with patch.dict(
        runner.JOBS,
        {"a": ("A", lambda: calls.append("a") or "ok")},
        clear=True,
    ):
        assert _run(runner, ["inesistente"]) == 2
    assert calls == []


def test_demand_job_is_registered():
    """Il job reale deve restare agganciato: se sparisce dalla mappa lo
    scheduled task gira a vuoto senza che nessuno se ne accorga.
    """
    module = _load_runner()
    assert "demand" in module.JOBS
