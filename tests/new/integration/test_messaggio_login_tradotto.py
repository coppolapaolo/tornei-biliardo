"""Il messaggio che chiede di accedere è nella lingua di chi legge.

Chi apre una pagina riservata senza sessione viene mandato al login con un
flash. Il testo lo mette Flask-Login, e senza `login_message` configurato è
il suo default inglese, «Please log in to access this page.», anche per chi
usa l'app in italiano. Da quando la sessione dell'admin scade per inattività
(ADR-063) è un messaggio che si vede davvero: se a scoprirlo è un poll, la
pagina successiva arriva da anonima e riceve proprio questo flash.

I flash si leggono dalla sessione, prima del redirect: contare testo
nell'HTML della pagina di arrivo conterebbe anche il pannello di debug.
"""

import pytest
from flask_babel import refresh

DEFAULT_INGLESE = "Please log in to access this page."


@pytest.fixture(autouse=True)
def lingua_ricalcolata_per_richiesta():
    """Flask-Babel tiene la lingua scelta in `ctx.babel_locale`.

    In questa suite il contesto non è per-richiesta — come `g._login_user` —
    quindi la lingua calcolata una volta resterebbe per tutte le richieste
    dopo: la sessione in inglese verrebbe ignorata, e al contrario un inglese
    rimasto in cache finirebbe nei test successivi dello stesso worker. Si
    ripulisce prima e dopo. In produzione ogni richiesta ha il suo contesto.
    """
    refresh()
    yield
    refresh()


def _messaggi_andando_su_pagina_riservata(client, lingua: str) -> list:
    with client.session_transaction() as sess:
        sess["language"] = lingua
    resp = client.get("/dashboard")
    assert resp.status_code == 302
    assert "/auth/login" in resp.headers["Location"]
    with client.session_transaction() as sess:
        return [str(messaggio) for _categoria, messaggio in sess.get("_flashes", [])]


@pytest.mark.parametrize(
    "lingua, atteso",
    [
        ("it", "Accedi per vedere questa pagina."),
        ("en", "Log in to see this page."),
    ],
)
def test_pagina_riservata_da_anonimo_chiede_di_accedere_nella_sua_lingua(
    client, db_session, lingua, atteso
):
    messaggi = _messaggi_andando_su_pagina_riservata(client, lingua)

    assert atteso in messaggi, messaggi
    assert DEFAULT_INGLESE not in messaggi
