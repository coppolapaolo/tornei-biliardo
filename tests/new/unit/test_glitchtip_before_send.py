"""Test del filtro before_send per GlitchTip (rumore uwsgi 'write error').

L'evento `OSError: write error` è generato da uwsgi quando il client chiude
la connessione prima che la risposta sia scritta (tipico della prima
richiesta dopo un reload della web app). È rumore benigno che consuma la
quota GlitchTip Free: il filtro lo scarta alla fonte.
"""

import sys

from app import glitchtip_before_send


def _hint_for(exc: BaseException) -> dict:
    try:
        raise exc
    except BaseException:
        return {"exc_info": sys.exc_info()}


def test_scarta_oserror_write_error():
    event = {"event_id": "abc"}
    hint = _hint_for(OSError("write error"))
    assert glitchtip_before_send(event, hint) is None


def test_mantiene_altri_oserror():
    event = {"event_id": "abc"}
    hint = _hint_for(OSError("disk I/O error"))
    assert glitchtip_before_send(event, hint) is event


def test_mantiene_eccezioni_diverse():
    event = {"event_id": "abc"}
    hint = _hint_for(ValueError("write error"))
    assert glitchtip_before_send(event, hint) is event


def test_mantiene_eventi_senza_exc_info():
    event = {"event_id": "abc"}
    assert glitchtip_before_send(event, {}) is event


def test_scarta_oserror_write_error_da_logging():
    # L'OSError di uwsgi arriva anche via logging integration: evento
    # message-only (logentry), hint senza exc_info (issue 5295144).
    event = {
        "event_id": "abc",
        "logentry": {"message": "OSError: write error", "params": []},
    }
    assert glitchtip_before_send(event, {"log_record": object()}) is None


def test_scarta_oserror_write_error_message_top_level():
    event = {"event_id": "abc", "message": "OSError: write error"}
    assert glitchtip_before_send(event, {}) is None


def test_mantiene_altri_messaggi_di_log():
    event = {
        "event_id": "abc",
        "logentry": {"message": "Errore inatteso nel matchmaking", "params": []},
    }
    assert glitchtip_before_send(event, {"log_record": object()}) is event
