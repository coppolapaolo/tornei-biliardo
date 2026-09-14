"""Il poll di chi ha perso la sessione risponde 401, non la pagina di login.

Con `@login_required` un poll senza sessione riceveva un 302 verso
`/auth/login`. `fetch` segue i redirect da solo, quindi al JavaScript
arrivava il **200** della pagina di login: `response.ok` era vero,
`response.json()` falliva, e il poller ripartiva tre secondi dopo — per
sempre. Nei log di produzione di sei giorni erano 4232 poll più 4232 pagine
di login, il 17% di tutte le richieste.

Un 401 JSON è una risposta che il client riconosce e su cui si ferma.
"""

from __future__ import annotations

import pytest

POLL_RISERVATI = [
    "/sse/poll/trio/1",
    "/sse/poll/gara/1",
    "/sse/poll/user/1",
    "/sse/poll/individual_match/1",
    "/sse/poll/match/1",
]


@pytest.mark.parametrize("url", POLL_RISERVATI)
def test_poll_senza_sessione_risponde_401_json(client, url):
    risposta = client.get(url)

    assert risposta.status_code == 401
    assert "Location" not in risposta.headers
    assert risposta.is_json
    assert risposta.get_json()["error"] == "unauthenticated"


def test_poll_dello_schermo_in_sala_resta_pubblico(client):
    """Lo schermo in sala non ha login: un indirizzo ignoto è 404, non 401."""
    assert client.get("/sse/poll/sala/nessuna-gara-cosi").status_code == 404


def test_poll_con_sessione_continua_a_rispondere(logged_in_client):
    client, utente = logged_in_client(role="player")

    gara = client.get("/sse/poll/gara/1")
    proprio = client.get(f"/sse/poll/user/{utente.id}")

    assert gara.status_code == 200
    assert "cursor" in gara.get_json()
    assert proprio.status_code == 200


def test_la_pagina_passa_al_polling_i_testi_dell_avviso(logged_in_client):
    """`polling.js` legge testi e login da `#polling-config`.

    Se quel blocco non fosse JSON valido — un apostrofo senza `|tojson` —
    il poller si fermerebbe lo stesso, ma l'avviso non comparirebbe e la
    pagina resterebbe muta: nessun altro test se ne accorgerebbe.
    """
    import json
    import re

    client, _ = logged_in_client(role="player")
    html = client.get("/dashboard/").get_data(as_text=True)

    blocco = re.search(
        r'<script type="application/json" id="polling-config">(.*?)</script>',
        html,
        re.S,
    )
    assert blocco, "base.html non espone la configurazione del polling"
    config = json.loads(blocco.group(1))
    assert config["login_url"] == "/auth/login"
    assert set(config["i18n"]) == {"title", "text", "action"}
    assert all(config["i18n"].values())


def test_poll_degli_eventi_altrui_resta_403(logged_in_client):
    client, utente = logged_in_client(role="player")

    assert client.get(f"/sse/poll/user/{utente.id + 1000}").status_code == 403
