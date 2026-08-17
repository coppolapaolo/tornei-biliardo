"""Regression: sentry non deve andare a caccia di integrazioni all'avvio.

Di default `sentry_sdk.init` importa ~40 moduli di integrazione per scoprire
quali pacchetti siano installati. Su PythonAnywhere quel giro vede anche i
pacchetti di sistema, e `pymongo` trascina un `pyOpenSSL` incompatibile con la
`cryptography` presente: da console `create_app` moriva con

    AttributeError: module 'lib' has no attribute 'X509_V_FLAG_NOTIFY_POLICY'

La web app non se ne accorgeva (set di pacchetti diverso), ma ogni script da
console o scheduled task sì — incluso `daily_jobs.py`, che sarebbe fallito ogni
giorno. Le integrazioni che servono davvero sono due e vanno dichiarate a mano.
"""

from unittest.mock import patch

from app import create_app
from config import config as config_map


def _init_kwargs_with_dsn():
    """I kwargs con cui `create_app` chiama `sentry_sdk.init`, con DSN finto.

    Il DSN si inietta sovrascrivendo `environment_settings()`, non l'attributo
    di classe: da quando `create_app` rilegge l'ambiente dopo `from_object`
    (vedi la docstring di `Config` — serviva a far ripartire gli scheduled
    task), è quel dizionario ad avere l'ultima parola, e un attributo scritto
    a mano verrebbe semplicemente rimpiazzato.
    """
    testing = config_map["testing"]
    con_dsn = dict(
        testing.environment_settings(),
        GLITCHTIP_DSN="https://fake@glitchtip.example/1",
    )

    with patch.object(
        testing, "environment_settings", classmethod(lambda cls: dict(con_dsn))
    ):
        with patch("sentry_sdk.init") as mock_init:
            create_app("testing")

    assert mock_init.call_count == 1
    return mock_init.call_args.kwargs


def test_auto_enabling_integrations_is_disabled():
    assert _init_kwargs_with_dsn()["auto_enabling_integrations"] is False


def test_flask_and_sqlalchemy_are_declared_explicitly():
    """Erano le uniche due che si attivavano davvero: spegnendo l'auto-discovery
    senza dichiararle si perderebbe il contesto SQL negli eventi.
    """
    names = {type(i).__name__ for i in _init_kwargs_with_dsn()["integrations"]}
    assert names == {"FlaskIntegration", "SqlalchemyIntegration"}
