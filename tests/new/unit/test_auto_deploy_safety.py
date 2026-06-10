"""Test per scripts/auto_deploy.py: migrations mai con la web app accesa.

Incidente 2026-06-10: scritture concorrenti console+webapp su SQLite/NFS
hanno corrotto il DB di produzione. auto_deploy deve disabilitare la web app
prima delle migrations e riabilitarla sempre (anche su errore).
"""

import pytest

import scripts.auto_deploy as auto_deploy


@pytest.mark.unit
@pytest.mark.parametrize(
    "output,expected",
    [
        ("Total: 44 | Applied: 44 | Pending: 0", 0),
        ("Total: 46 | Applied: 44 | Pending: 2", 2),
        ("output inatteso senza il conteggio", None),
        ("", None),
    ],
)
def test_parse_pending(output, expected):
    assert auto_deploy.parse_pending(output) == expected


@pytest.mark.unit
def test_migrations_run_between_disable_and_enable(monkeypatch):
    """Ordine obbligato: disable -> migrations -> enable."""
    calls = []
    monkeypatch.setattr(
        auto_deploy,
        "webapp_api",
        lambda action: (calls.append(action), (True, "ok"))[1],
    )
    monkeypatch.setattr(
        auto_deploy,
        "run_migrations",
        lambda: (calls.append("migrate"), (True, "ok"))[1],
    )

    success, _ = auto_deploy.run_migrations_safely()

    assert success is True
    assert calls == ["disable", "migrate", "enable"]


@pytest.mark.unit
def test_no_migrations_if_disable_fails(monkeypatch):
    """Senza disable (es. token API mancante) le migrations NON partono."""
    calls = []
    monkeypatch.setattr(
        auto_deploy,
        "webapp_api",
        lambda action: (calls.append(action), (False, "no token"))[1],
    )
    monkeypatch.setattr(
        auto_deploy,
        "run_migrations",
        lambda: (calls.append("migrate"), (True, "ok"))[1],
    )

    success, msg = auto_deploy.run_migrations_safely()

    assert success is False
    assert "migrate" not in calls
    assert "enable" not in calls  # mai disabilitata, niente da riabilitare


@pytest.mark.unit
def test_enable_runs_even_if_migrations_fail(monkeypatch):
    """La web app viene riabilitata anche quando le migrations falliscono."""
    calls = []
    monkeypatch.setattr(
        auto_deploy,
        "webapp_api",
        lambda action: (calls.append(action), (True, "ok"))[1],
    )

    def failing_migrations():
        calls.append("migrate")
        raise RuntimeError("boom")

    monkeypatch.setattr(auto_deploy, "run_migrations", failing_migrations)

    with pytest.raises(RuntimeError):
        auto_deploy.run_migrations_safely()

    assert calls == ["disable", "migrate", "enable"]
