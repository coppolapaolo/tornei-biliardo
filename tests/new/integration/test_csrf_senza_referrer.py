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


def test_un_token_vecchio_di_ore_vale_ancora(csrf_client, db_session):
    """Il modulo lasciato aperto sul telefono deve funzionare lo stesso.

    Il default di Flask-WTF invalida il token dopo un'ora dalla generazione
    della pagina: su un telefono, dove il browser non si chiude mai, una
    scheda ripresa il giorno dopo ha il cookie buono e il token scaduto, e
    l'invio finisce sulla stessa pagina 400. Qui l'ora non si aspetta: si
    stringe il limite a un secondo per **dimostrare** che il controllo
    esiste, e poi lo si toglie come in produzione.

    L'attesa è di poco più di due secondi e non di uno: itsdangerous conta
    l'età in secondi interi e rifiuta solo quando **supera** il limite, quindi
    a 1,2 secondi un token con limite 1 risulta ancora buono.
    """
    import time

    from models.user.services import UserService  # type: ignore

    UserService.create_user("utente_token_vecchio", "vecchio@test.local", "p@ssw0rd")

    def invia(token: str):
        return csrf_client.post(
            "/auth/login",
            base_url="https://localhost",
            data={
                "username": "utente_token_vecchio",
                "password": "p@ssw0rd",
                "csrf_token": token,
            },
        )

    token = _token_di_login(csrf_client)
    time.sleep(2.2)

    csrf_client.application.config["WTF_CSRF_TIME_LIMIT"] = 1
    try:
        assert invia(token).status_code == 400, "il limite di tempo non è attivo"
    finally:
        csrf_client.application.config["WTF_CSRF_TIME_LIMIT"] = None

    # Stesso token, stessa età: senza limite di tempo si entra.
    assert invia(token).status_code in (200, 302)


def test_la_configurazione_non_fa_scadere_il_token():
    """Presidio statico: il default di un'ora non deve tornare da solo."""
    from config import Config

    assert Config.WTF_CSRF_TIME_LIMIT is None


def test_le_pagine_di_auth_non_si_mettono_in_cache(client):
    """Ogni pagina di auth porta un token legato alla sessione di chi la
    chiede: una copia servita da una cache (misurato in produzione: mancava
    del tutto `Cache-Control`) porta il token di una sessione che non esiste
    più, e l'invio finisce in 400."""
    for percorso in ("/auth/login", "/auth/register", "/auth/forgot-password"):
        risposta = client.get(percorso)
        assert risposta.headers.get("Cache-Control") == "no-store", percorso


def test_senza_cookie_la_pagina_400_parla_di_cookie(csrf_client, db_session):
    """Cookie bloccati: ogni invio fallirà identico, e «ricarica e riprova»
    è un consiglio che non può funzionare. La pagina deve dirlo."""
    risposta = csrf_client.post(
        "/auth/login",
        base_url="https://localhost",
        data={"username": "x", "password": "y", "csrf_token": "z"},
    )
    assert risposta.status_code == 400
    assert 'data-causa="cookie-assenti"' in risposta.get_data(as_text=True)


def test_con_cookie_e_token_guasto_la_pagina_400_dice_di_riaprire(
    csrf_client, db_session
):
    csrf_client.get("/auth/login", base_url="https://localhost")  # crea la sessione
    risposta = csrf_client.post(
        "/auth/login",
        base_url="https://localhost",
        data={"username": "x", "password": "y", "csrf_token": "token-guasto"},
    )
    assert risposta.status_code == 400
    assert 'data-causa="modulo-non-valido"' in risposta.get_data(as_text=True)


def test_la_diagnosi_cookie_e_aperta_e_misura_il_giro_completo(app):
    """La pagina del test dei cookie serve a chi non riesce a entrare:
    deve aprirsi da anonimi, e l'eco deve dire la verità nei due casi.

    Contesto applicativo annidato per la stessa ragione del fixture
    `csrf_client`: quello di sessione fa sopravvivere `g.csrf_token` fra i
    test, e `generate_csrf()` smette di toccare la sessione — la pagina
    uscirebbe senza Set-Cookie solo nei test, mai in produzione.
    """
    with app.app_context():
        client = app.test_client()
        pagina = client.get("/auth/diagnosi")
        assert pagina.status_code == 200
        assert 'id="diagnosi"' in pagina.get_data(as_text=True)
        assert pagina.headers.get("Cache-Control") == "no-store"

        # Il client ha appena ricevuto il cookie di sessione: il giro è vero.
        eco = client.get("/auth/diagnosi/eco").get_json()
        assert eco == {"cookie_arrivato": True, "sessione_valida": True}

        # Un client nuovo, senza cookie: il giro deve dire di no, non fingere.
        eco_nudo = app.test_client().get("/auth/diagnosi/eco").get_json()
        assert eco_nudo["cookie_arrivato"] is False

        # Gli esiti locali riferiti dalla pagina non devono rompere l'eco,
        # né presenti né assenti né malformati.
        for query in ("", "?dichiara=1&salva=0", "?salva=banana"):
            risposta = client.get("/auth/diagnosi/eco" + query)
            assert risposta.status_code == 200


def test_la_pagina_400_senza_cookie_porta_alla_diagnosi(csrf_client, db_session):
    risposta = csrf_client.post(
        "/auth/login",
        base_url="https://localhost",
        data={"username": "x", "password": "y", "csrf_token": "z"},
    )
    assert risposta.status_code == 400
    assert "/auth/diagnosi" in risposta.get_data(as_text=True)
