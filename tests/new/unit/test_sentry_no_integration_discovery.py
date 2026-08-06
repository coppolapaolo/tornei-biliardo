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
    original_dsn = config_map["testing"].GLITCHTIP_DSN
    config_map["testing"].GLITCHTIP_DSN = "https://fake@glitchtip.example/1"
    try:
        with patch("sentry_sdk.init") as mock_init:
            create_app("testing")
        assert mock_init.call_count == 1
        return mock_init.call_args.kwargs
    finally:
        config_map["testing"].GLITCHTIP_DSN = original_dsn


def test_auto_enabling_integrations_is_disabled():
    assert _init_kwargs_with_dsn()["auto_enabling_integrations"] is False


def test_flask_and_sqlalchemy_are_declared_explicitly():
    """Erano le uniche due che si attivavano davvero: spegnendo l'auto-discovery
    senza dichiararle si perderebbe il contesto SQL negli eventi.
    """
    names = {type(i).__name__ for i in _init_kwargs_with_dsn()["integrations"]}
    assert names == {"FlaskIntegration", "SqlalchemyIntegration"}
