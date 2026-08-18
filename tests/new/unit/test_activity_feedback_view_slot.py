"""Il turno di visualizzazione del blocco di feedback, preso una volta sola."""

from __future__ import annotations

from flask import session

from utils.activity_feedback_view import (
    SESSION_KEY,
    claim_activity_feedback_view,
    reset_activity_feedback_view,
)


def test_il_turno_si_consuma_alla_prima_chiamata(app):
    with app.test_request_context():
        assert claim_activity_feedback_view(7) is True
        assert claim_activity_feedback_view(7) is False
        assert session[SESSION_KEY] == 7


def test_un_altro_utente_ha_il_suo_turno(app):
    """Due account che si alternano sullo stesso browser sono due persone."""
    with app.test_request_context():
        assert claim_activity_feedback_view(7) is True
        assert claim_activity_feedback_view(9) is True
        assert claim_activity_feedback_view(9) is False


def test_l_azzeramento_rimette_il_blocco_in_coda(app):
    with app.test_request_context():
        claim_activity_feedback_view(7)
        reset_activity_feedback_view()
        assert claim_activity_feedback_view(7) is True


def test_fuori_da_una_richiesta_non_si_nasconde_niente(app, monkeypatch):
    """Script e test di servizio non hanno una sessione da consumare.

    Il contesto di richiesta si simula: la fixture `db_session` di questo
    progetto tiene un `test_request_context` aperto per tutta la durata di
    ogni test, quindi qui dentro una richiesta c'e' sempre.
    """
    import utils.activity_feedback_view as modulo

    monkeypatch.setattr(modulo, "has_request_context", lambda: False)

    assert claim_activity_feedback_view(7) is True
    assert claim_activity_feedback_view(7) is True
    reset_activity_feedback_view()  # non deve sollevare
