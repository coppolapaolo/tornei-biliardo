"""Unit test di `scripts/prod_env.py`.

Copre il caso che ha fatto fallire il primo lancio in produzione: uno script
avviato da console/scheduled task non eredita le env dal file WSGI, quindi
`create_app("production")` esplode su SECRET_KEY. Il bootstrap deve procurarsi
le variabili da solo e, se non ci riesce, dirlo in modo comprensibile invece di
lasciare un traceback.
"""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

import scripts.prod_env as prod_env


@pytest.fixture(autouse=True)
def clean_env():
    """Isola le variabili toccate dai test."""
    names = ("SECRET_KEY", "ENCRYPTION_KEY", "FLASK_ENV")
    saved = {n: os.environ.get(n) for n in names}
    for n in names:
        os.environ.pop(n, None)
    yield
    for n, v in saved.items():
        if v is None:
            os.environ.pop(n, None)
        else:
            os.environ[n] = v


def test_loads_missing_vars_from_wsgi():
    with patch.object(
        prod_env,
        "read_wsgi_env",
        return_value={"SECRET_KEY": "s", "FLASK_ENV": "production"},
    ):
        loaded, missing = prod_env.load_production_env(("SECRET_KEY",))
    assert loaded == ["FLASK_ENV", "SECRET_KEY"]
    assert missing == []
    assert os.environ["SECRET_KEY"] == "s"


def test_existing_env_wins_over_wsgi():
    """Un valore passato a mano sulla riga di comando non va sovrascritto."""
    os.environ["SECRET_KEY"] = "da-riga-di-comando"
    with patch.object(
        prod_env, "read_wsgi_env", return_value={"SECRET_KEY": "dal-wsgi"}
    ):
        loaded, missing = prod_env.load_production_env(("SECRET_KEY",))
    assert os.environ["SECRET_KEY"] == "da-riga-di-comando"
    assert loaded == []
    assert missing == []


def test_missing_required_is_reported_not_swallowed():
    """File WSGI illeggibile (read_wsgi_env torna {}) → il required resta vuoto."""
    with patch.object(prod_env, "read_wsgi_env", return_value={}):
        _loaded, missing = prod_env.load_production_env(
            ("SECRET_KEY", "ENCRYPTION_KEY")
        )
    assert missing == ["SECRET_KEY", "ENCRYPTION_KEY"]


def test_bootstrap_exits_with_actionable_message():
    """Il fallimento deve nominare le variabili e dire da dove arrivano: è il
    caso reale in cui l'utente vedeva solo `RuntimeError: SECRET_KEY ...`.
    """
    with patch.object(prod_env, "read_wsgi_env", return_value={}):
        with pytest.raises(SystemExit) as exc:
            prod_env.bootstrap_or_exit(("SECRET_KEY",))
    message = str(exc.value)
    assert "SECRET_KEY" in message
    assert str(prod_env.WSGI_FILE) in message


def test_bootstrap_succeeds_silently_when_env_complete():
    os.environ["SECRET_KEY"] = "presente"
    with patch.object(prod_env, "read_wsgi_env", return_value={}):
        prod_env.bootstrap_or_exit(("SECRET_KEY",))  # non solleva


def test_read_wsgi_env_is_shared_with_auto_deploy():
    """Una sola implementazione: se qualcuno la duplica, il test se ne accorge."""
    import scripts.auto_deploy as auto_deploy

    assert prod_env.read_wsgi_env is auto_deploy.read_wsgi_env
    assert prod_env.WSGI_FILE == auto_deploy.WSGI_FILE


def test_unreadable_wsgi_file_does_not_raise(tmp_path: Path):
    """Percorso inesistente: read_wsgi_env torna {} e il caricamento non esplode."""
    with patch.object(prod_env, "WSGI_FILE", tmp_path / "non-esiste.py"):
        loaded, missing = prod_env.load_production_env(("SECRET_KEY",))
    assert loaded == []
    assert missing == ["SECRET_KEY"]
