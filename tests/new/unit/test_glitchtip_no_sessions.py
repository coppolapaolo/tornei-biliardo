"""Regression: GlitchTip non riceve le sessioni, che non sa gestire.

Di default `sentry_sdk` conta le richieste servite e le spedisce come busta
`sessions` (release health). GlitchTip non le implementa — issue #206 del
backend, dove il consiglio è proprio `auto_session_tracking=False` — quindi
ogni invio è traffico verso `/envelope/` che non porta niente. Nell'error log
di produzione del 2026-09-14 i `Retrying ... SSLEOFError ... /envelope/`
compaiono tutto il giorno: le sessioni ne sono la probabile origine, non
provata busta per busta.

Il test non guarda solo il parametro: arma l'SDK con le opzioni vere di
`create_app`, fa passare una richiesta riuscita da un'app Flask e controlla
cosa arriva al trasporto.
"""

from unittest.mock import patch

import sentry_sdk
from flask import Flask
from sentry_sdk.transport import Transport

from app import create_app
from config import config as config_map


class _Registratore(Transport):
    """Trasporto che tiene le buste invece di spedirle."""

    def __init__(self, options=None):
        super().__init__(options)
        self.buste = []

    def capture_envelope(self, envelope):
        self.buste.append(envelope)


def _init_kwargs_with_dsn():
    """I kwargs con cui `create_app` chiama `sentry_sdk.init`, con DSN finto.

    Stesso schema di `test_sentry_no_integration_discovery.py`: il DSN passa da
    `environment_settings()`, che ha l'ultima parola dopo `from_object`.
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


def test_una_richiesta_riuscita_non_spedisce_sessioni():
    kwargs = _init_kwargs_with_dsn()
    registratore = _Registratore()

    web = Flask("prova_sessioni")

    @web.route("/")
    def home():
        return "ok"

    scope_globale = sentry_sdk.get_global_scope()
    client_prima = scope_globale.client
    sentry_sdk.init(**dict(kwargs, transport=registratore))
    try:
        assert web.test_client().get("/").status_code == 200
        # Le sessioni si accumulano e partono a ogni flush: senza, il test
        # passerebbe anche con il tracciamento acceso.
        sentry_sdk.get_client().close()
    finally:
        # Il client è globale per processo: va rimesso quello di prima,
        # altrimenti gli altri test del worker girerebbero con questo.
        scope_globale.set_client(client_prima)

    tipi = {item.type for busta in registratore.buste for item in busta.items}
    assert not tipi & {"session", "sessions"}, tipi
