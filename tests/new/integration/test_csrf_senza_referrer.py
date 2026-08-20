"""Il login non deve dipendere dall'header `Referer` (regressione).

In produzione (HTTPS) Flask-WTF pretendeva, oltre al token, anche un `Referer`
combaciante con l'host: chi non lo manda — browser con la privacy stretta,
webview dentro altre app, estensioni e proxy che lo tolgono — prendeva 400 su
ogni POST, login compreso, e restava fuori dal sito senza alcun modo di
entrare. Riprodotto contro www.torneibiliardo.it il 2026-08-19: stesso token,
stessa sessione, 400 senza `Referer` e 200 con.

Questi test girano con il CSRF **acceso** (la suite lo spegne) e su base_url
`https://`, perché il controllo di Flask-WTF scattava solo su richiesta
sicura.
"""

import re

import pytest

TOKEN_RE = re.compile(r'name="csrf_token" value="([^"]+)"')


@pytest.fixture
def csrf_client(app):
    """Client con protezione CSRF attiva e richieste viste come HTTPS.

    Il contesto applicativo annidato non è un vezzo: la suite ne tiene uno
    aperto per tutta la sessione, e Flask lo riusa a ogni richiesta invece di
    crearne uno nuovo. Così `g.csrf_token` — dove Flask-WTF ricorda di aver
    già generato il token — sopravvive da un test all'altro, e il test
    successivo si ritrova la pagina col token ma la sessione senza. Un
    contesto per test rimette le cose come stanno in produzione, dove ogni
    richiesta ha il suo.
    """
    precedente = app.config.get("WTF_CSRF_ENABLED", True)
    app.config["WTF_CSRF_ENABLED"] = True
    try:
        with app.app_context():
            yield app.test_client()
    finally:
        app.config["WTF_CSRF_ENABLED"] = precedente


def _token_di_login(client) -> str:
    pagina = client.get("/auth/login", base_url="https://localhost")
    trovato = TOKEN_RE.search(pagina.get_data(as_text=True))
    assert trovato, "la pagina di login non contiene il campo csrf_token"
    return trovato.group(1)


def _post_login(client, token, **kwargs):
    return client.post(
        "/auth/login",
        base_url="https://localhost",
        data={
            "username": "utente_senza_referrer",
            "password": "p@ssw0rd",
            "csrf_token": token,
        },
        **kwargs,
    )


def test_login_senza_referrer_non_e_400(csrf_client, db_session):
    """Il caso del guasto: token valido, nessun `Referer`."""
    from models.user.services import UserService  # type: ignore

    UserService.create_user(
        "utente_senza_referrer", "senza.referrer@test.local", "p@ssw0rd"
    )

    risposta = _post_login(csrf_client, _token_di_login(csrf_client))

    assert risposta.status_code != 400
    assert risposta.status_code in (200, 302)


def test_login_senza_token_resta_400(csrf_client, db_session):
    """La protezione non è stata spenta: senza token si passa comunque no."""
    risposta = _post_login(csrf_client, "")

    assert risposta.status_code == 400


def test_post_da_un_altro_sito_e_400(csrf_client, db_session):
    """`Origin` estranea: è il caso che il referrer serviva davvero a fermare."""
    token = _token_di_login(csrf_client)

    risposta = _post_login(
        csrf_client, token, headers={"Origin": "https://sito-cattivo.example"}
    )

    assert risposta.status_code == 400


def test_post_con_origin_del_sito_passa(csrf_client, db_session):
    """`Origin` nostra: il controllo non deve bloccare i form del sito."""
    from models.user.services import UserService  # type: ignore

    UserService.create_user("utente_origin", "origin@test.local", "p@ssw0rd")

    token = _token_di_login(csrf_client)
    risposta = csrf_client.post(
        "/auth/login",
        base_url="https://localhost",
        data={
            "username": "utente_origin",
            "password": "p@ssw0rd",
            "csrf_token": token,
        },
        headers={"Origin": "https://localhost"},
    )

    assert risposta.status_code in (200, 302)


def test_configurazione_non_pretende_il_referrer():
    """Presidio statico: il default di Flask-WTF non deve tornare da solo."""
    from config import Config

    assert Config.WTF_CSRF_SSL_STRICT is False
