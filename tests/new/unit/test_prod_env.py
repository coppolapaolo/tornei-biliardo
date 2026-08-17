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
    names = ("SECRET_KEY", "ENCRYPTION_KEY", "ADMIN_PASSWORD", "FLASK_ENV")
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


def test_admin_password_is_required_by_default():
    """Regressione: `create_app` in produzione chiama `create_admin_if_not_exists`,
    che senza ADMIN_PASSWORD solleva un RuntimeError opaco (config.py non le dà
    fallback in produzione). Se non è fra i required, il bootstrap la lascia
    passare e l'utente vede di nuovo un traceback invece del messaggio utile.
    """
    assert "ADMIN_PASSWORD" in prod_env.PRODUCTION_REQUIRED

    os.environ["SECRET_KEY"] = "presente"
    with patch.object(prod_env, "read_wsgi_env", return_value={}):
        with pytest.raises(SystemExit) as exc:
            prod_env.bootstrap_or_exit()
    assert "ADMIN_PASSWORD" in str(exc.value)


def test_bootstrap_does_not_block_outside_production():
    """Con FLASK_ENV=development le variabili hanno dei default in config.py:
    fermare lo script sarebbe un falso negativo.
    """
    os.environ["FLASK_ENV"] = "development"
    with patch.object(prod_env, "read_wsgi_env", return_value={}):
        prod_env.bootstrap_or_exit(("SECRET_KEY",))  # non solleva


def test_flask_env_from_wsgi_decides_whether_to_block():
    """FLASK_ENV è essa stessa una variabile del file WSGI: il controllo va
    fatto dopo il caricamento, altrimenti si deciderebbe su un ambiente
    incompleto e in produzione non si bloccherebbe mai.
    """
    with patch.object(
        prod_env, "read_wsgi_env", return_value={"FLASK_ENV": "production"}
    ):
        with pytest.raises(SystemExit):
            prod_env.bootstrap_or_exit(("SECRET_KEY",))


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


# ── bootstrap_and_create_app: l'ordine è la sostanza ────────────────────────


def test_bootstrap_and_create_app_carica_le_env_prima_di_creare_l_app():
    """Il guasto che ha fermato due scheduled task, in una riga.

    `daily_jobs.py` e `send_match_reminders.py` chiamavano `bootstrap_or_exit()`
    nel punto giusto, ma avevano `from app import create_app` in cima al file:
    `config` era quindi già importato — e SECRET_KEY già congelata a stringa
    vuota — quando l'ambiente veniva popolato. Nel log le due righe si
    contraddicevano ("Env di produzione lette da ...: SECRET_KEY" seguito da
    "SECRET_KEY env var must be set in production") perché raccontavano
    momenti diversi.

    Qui si verifica la cosa esatta che allora non era vera: quando `create_app`
    viene invocata, la variabile è già nell'ambiente.
    """
    visto = {}

    def registra_ambiente(config_name=None):
        visto["SECRET_KEY"] = os.environ.get("SECRET_KEY")
        visto["config_name"] = config_name
        return "app-finta"

    import app as app_module

    with patch.object(
        prod_env,
        "read_wsgi_env",
        return_value={
            "SECRET_KEY": "dal-wsgi",
            "ADMIN_PASSWORD": "pw",
            "FLASK_ENV": "production",
        },
    ), patch.object(app_module, "create_app", side_effect=registra_ambiente):
        risultato = prod_env.bootstrap_and_create_app()

    assert risultato == "app-finta"
    assert visto["SECRET_KEY"] == "dal-wsgi"
    assert visto["config_name"] == "production"


def test_bootstrap_and_create_app_si_ferma_senza_le_variabili_richieste():
    """Se il bootstrap non ce la fa, l'app non si crea affatto: meglio un
    messaggio che dice da dove dovrebbe arrivare la variabile che un
    traceback su SECRET_KEY dieci righe più in là.
    """
    import app as app_module

    with patch.object(prod_env, "read_wsgi_env", return_value={}), patch.object(
        app_module, "create_app"
    ) as create_app:
        with pytest.raises(SystemExit):
            prod_env.bootstrap_and_create_app()

    create_app.assert_not_called()


def test_bootstrap_and_create_app_accetta_requisiti_aggiuntivi():
    """`reconcile_achievements.py` tocca i PII e pretende anche
    ENCRYPTION_KEY: senza, la decifratura degraderebbe in silenzio sulla
    chiave di sviluppo (incidente 2026-06-25)."""
    import app as app_module

    with patch.object(
        prod_env,
        "read_wsgi_env",
        return_value={
            "SECRET_KEY": "s",
            "ADMIN_PASSWORD": "pw",
            "FLASK_ENV": "production",
        },
    ), patch.object(app_module, "create_app"):
        with pytest.raises(SystemExit) as exc:
            prod_env.bootstrap_and_create_app(
                required=prod_env.PRODUCTION_REQUIRED + ("ENCRYPTION_KEY",)
            )

    assert "ENCRYPTION_KEY" in str(exc.value)
