"""Il mini-sito di aiuto risponde e mostra quello che deve.

I test unitari verificano la coerenza dei contenuti; questi verificano che le
pagine si aprano davvero, che siano raggiungibili **senza account** (chi deve
ancora capire come funziona l'app è il primo destinatario della guida) e che i
blocchi finiscano in pagina invece di svanire in silenzio.
"""

from __future__ import annotations

import pytest

from utils.help_content import FALLBACK_LOCALE, get_content


@pytest.mark.integration
def test_copertina_accessibile_senza_account(client):
    response = client.get("/aiuto/")
    assert response.status_code == 200
    assert "Guida" in response.get_data(as_text=True)


@pytest.mark.integration
def test_tutte_le_pagine_si_aprono(app, client):
    """Ogni pagina dichiarata nell'indice risponde 200.

    Copre anche gli errori di impaginazione: un blocco con un campo mancante
    fa fallire il template, e senza questo test se ne accorgerebbe un utente.
    """
    with app.app_context():
        content = get_content(FALLBACK_LOCALE)
        pagine = [(p.section, p.slug) for p in content.pages.values()]

    for section_id, slug in pagine:
        response = client.get(f"/aiuto/{section_id}/{slug}")
        assert (
            response.status_code == 200
        ), f"/aiuto/{section_id}/{slug} → {response.status_code}"


@pytest.mark.integration
def test_tutte_le_sezioni_si_aprono(app, client):
    with app.app_context():
        sezioni = [s.id for s in get_content(FALLBACK_LOCALE).sections]
    for section_id in sezioni:
        assert client.get(f"/aiuto/{section_id}/").status_code == 200


@pytest.mark.integration
def test_i_blocchi_finiscono_in_pagina(app, client):
    """Una pagina ricca deve mostrare titoli, passaggi, figure e note.

    Senza questa verifica un blocco scritto con il tipo sbagliato sparirebbe
    dal rendering senza errori: la pagina resterebbe valida, solo incompleta.
    """
    html = client.get("/aiuto/giocare/giocare_una_partita").get_data(as_text=True)
    assert 'class="help-h2"' in html  # titoli interni
    assert "help-step__num" in html  # passaggi numerati
    assert "/static/img/help/" in html  # figure
    assert "help-faq" in html  # domande frequenti
    assert "c7-card--" in html  # note


@pytest.mark.integration
def test_nessuna_chiave_letta_come_metodo(app, client):
    """`item.values` su un dizionario Jinja restituisce il metodo `values()`.

    E' successo: la pagina mostrava «built-in method values of dict object» al
    posto dei valori ammessi di un'opzione. Il test copre tutte le pagine
    perche' l'errore e' invisibile finche' non si guarda quella giusta.
    """
    with app.app_context():
        pagine = [
            (p.section, p.slug) for p in get_content(FALLBACK_LOCALE).pages.values()
        ]
    for section_id, slug in pagine:
        html = client.get(f"/aiuto/{section_id}/{slug}").get_data(as_text=True)
        assert "built-in method" not in html, f"/aiuto/{section_id}/{slug}"


@pytest.mark.integration
def test_pagina_inesistente(client):
    assert client.get("/aiuto/introduzione/non_esiste").status_code == 404
    assert client.get("/aiuto/sezione_inesistente/").status_code == 404


@pytest.mark.integration
def test_sezione_sbagliata_reindirizza(app, client):
    """Un collegamento vecchio, dopo un riordino dell'indice, non deve morire."""
    with app.app_context():
        page = next(iter(get_content(FALLBACK_LOCALE).pages.values()))
    response = client.get(f"/aiuto/sezione_qualsiasi/{page.slug}")
    assert response.status_code in (301, 302)
    assert page.slug in response.headers["Location"]


@pytest.mark.integration
def test_ricerca(client):
    assert client.get("/aiuto/cerca?q=iscrizione").status_code == 200
    # Senza termine la pagina propone comunque le sezioni.
    assert client.get("/aiuto/cerca").status_code == 200
    vuoto = client.get("/aiuto/cerca?q=zzzzzz").get_data(as_text=True)
    assert "Nessun risultato" in vuoto


@pytest.mark.integration
def test_api_schermata(client):
    """Predisposizione per l'interfaccia adattiva: forma stabile del JSON."""
    response = client.get("/aiuto/api/schermata/admin.match.match_detail")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["screen"] == "admin.match.match_detail"
    assert payload["hints"] and payload["tour"]


@pytest.mark.integration
def test_api_schermata_sconosciuta(client):
    """Meglio un 404 di un oggetto vuoto: chi integra deve accorgersi subito
    di aver scritto il nome dell'endpoint sbagliato."""
    assert client.get("/aiuto/api/schermata/non.esiste").status_code == 404


@pytest.mark.integration
def test_catalogo_microaiuto(client):
    response = client.get("/aiuto/microaiuto")
    assert response.status_code == 200
    assert "data-help=" in response.get_data(as_text=True)


@pytest.mark.integration
def test_la_guida_segue_la_lingua_scelta(client):
    """Cambiando lingua si resta sulla stessa pagina, tradotta.

    Gli slug sono identici fra le lingue apposta: `set_language` riporta
    all'indirizzo di partenza, e se la pagina esistesse solo in italiano chi
    passa all'inglese finirebbe su un 404.
    """
    client.get("/set_language/en")
    html = client.get("/aiuto/giocare/giocare_una_partita").get_data(as_text=True)
    assert "Scoreboard" in html or "scoreboard" in html
    # Le figure sono per lingua: la guida inglese non puo' mostrare i pulsanti
    # italiani, sarebbe l'esatto contrario del suo scopo.
    assert "img/help/en/" in html

    client.get("/set_language/it")
    html = client.get("/aiuto/giocare/giocare_una_partita").get_data(as_text=True)
    assert "Segnapunti" in html
    assert "img/help/it/" in html


@pytest.mark.integration
def test_collegamento_dal_guscio(client):
    """La guida deve essere raggiungibile da qualunque pagina, anche da chi non
    ha un account: se non si trova, tanto vale non averla scritta."""
    html = client.get("/").get_data(as_text=True)
    assert "/aiuto/" in html
