"""L'errore di un handler arriva a GlitchTip con il suo contesto, SDK vero.

I test di `test_event_system.py` sostituiscono `sentry_sdk` con un
`MagicMock`: passano con qualunque nome di funzione, anche con uno che l'SDK
non ha più. `push_scope` è deprecato in sentry-sdk 2 e sparisce con la 3:
il giorno dell'aggiornamento `_capture_handler_exception` lo chiamerebbe, lo
`except` lo trasformerebbe in un warning nel log e GlitchTip non vedrebbe più
nessun errore degli handler — senza che un test diventi rosso.

Qui l'SDK è quello installato, con un trasporto che tiene le buste invece di
spedirle, e ogni `DeprecationWarning` è un errore.
"""

import warnings

import sentry_sdk
from sentry_sdk.transport import Transport

from models.events.base import EventHandler, _capture_handler_exception
from models.events.user_events import DirectorRequestCreatedEvent


class _Registratore(Transport):
    """Trasporto che tiene le buste invece di spedirle."""

    def __init__(self, options=None):
        super().__init__(options)
        self.buste = []

    def capture_envelope(self, envelope):
        self.buste.append(envelope)


def _handler_che_fallisce(event):
    raise RuntimeError("boom")


def test_l_errore_dell_handler_arriva_con_il_contesto():
    registratore = _Registratore()
    evento = DirectorRequestCreatedEvent(
        request_id=1, user_id=123, username="testuser", admin_user_ids=[1]
    )

    scope_globale = sentry_sdk.get_global_scope()
    client_prima = scope_globale.client
    sentry_sdk.init(
        dsn="https://fake@glitchtip.example/1",
        transport=registratore,
        default_integrations=False,
        auto_session_tracking=False,
    )
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", DeprecationWarning)
            _capture_handler_exception(
                RuntimeError("boom"), evento, EventHandler(_handler_che_fallisce)
            )
        sentry_sdk.get_client().flush()
    finally:
        # Il client è globale per processo: va rimesso quello di prima.
        scope_globale.set_client(client_prima)

    eventi = [
        item.payload.json
        for busta in registratore.buste
        for item in busta.items
        if item.type == "event"
    ]
    assert len(eventi) == 1
    extra = eventi[0]["extra"]
    assert extra["event_type"] == "user.director_request_created"
    assert extra["event_id"] == evento.event_id
    assert extra["handler_name"].endswith("_handler_che_fallisce")
    assert extra["event_domain"] == "user"
