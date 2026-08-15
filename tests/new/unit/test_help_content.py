"""Coerenza dei contenuti del mini-sito di aiuto (`help_content/`).

La documentazione con le schermate non si rompe: **invecchia**. Continua a
rispondere, con parole ragionevoli e immagini nitide, descrivendo un'app che
non esiste piu'. Questi test sono l'unico modo per accorgersene senza rileggere
tutta la guida a ogni rilascio: verificano i legami che, quando si spezzano,
non danno alcun errore visibile — la pagina tolta dall'indice ma ancora
collegata, la figura citata e mai catturata, il rimando a una schermata che nel
frattempo ha cambiato nome.

Chi aggiorna la guida trova il procedimento nella skill `help-docs`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from utils.help_content import (
    AUDIENCES,
    FALLBACK_LOCALE,
    available_locales,
    get_content,
    hints_for_screen,
    render_text,
    screen_payload,
    search,
    validate,
)

ROOT = Path(__file__).resolve().parents[3]
STATIC = ROOT / "static"


def _locales() -> list[str]:
    return available_locales()


@pytest.mark.unit
def test_contenuto_coerente(app):
    """Nessun legame rotto fra indice, pagine, figure, ancore ed endpoint.

    E' il test che conta davvero: `validate` raccoglie in un colpo solo tutte
    le incoerenze che renderebbero la guida silenziosamente falsa. Gira su
    **ogni lingua**: una traduzione che cita una figura mai catturata o un
    endpoint rinominato sbaglia esattamente come farebbe l'originale.
    """
    with app.app_context():
        endpoints = {rule.endpoint for rule in app.url_map.iter_rules()}
        for locale in _locales():
            problems = validate(
                locale, known_endpoints=endpoints, static_dir=str(STATIC)
            )
            assert (
                not problems
            ), f"Contenuti dell'aiuto incoerenti ({locale}):\n  - " + "\n  - ".join(
                problems
            )


@pytest.mark.unit
def test_la_lingua_di_riferimento_esiste(app):
    with app.app_context():
        assert FALLBACK_LOCALE in available_locales()


@pytest.mark.unit
def test_le_lingue_hanno_la_stessa_struttura(app):
    """Sezioni e pagine devono coincidere fra le lingue.

    Il cambio lingua tiene l'indirizzo corrente: se una pagina esiste solo in
    italiano, chi passa all'inglese da quella pagina finisce su un 404. Ed e'
    l'errore che si introduce da soli aggiungendo una pagina e traducendola
    "dopo".
    """
    with app.app_context():
        strutture = {}
        for locale in _locales():
            content = get_content(locale)
            strutture[locale] = (
                {section.id for section in content.sections},
                set(content.pages),
            )

    riferimento = strutture[FALLBACK_LOCALE]
    for locale, struttura in strutture.items():
        assert struttura[0] == riferimento[0], (
            f"Sezioni diverse in «{locale}»: "
            f"mancano {riferimento[0] - struttura[0]}, "
            f"in piu' {struttura[0] - riferimento[0]}"
        )
        assert struttura[1] == riferimento[1], (
            f"Pagine diverse in «{locale}»: "
            f"mancano {riferimento[1] - struttura[1]}, "
            f"in piu' {struttura[1] - riferimento[1]}"
        )


@pytest.mark.unit
def test_le_ancore_del_microaiuto_non_si_traducono(app):
    """`anchor` e' il contratto con i template dell'app.

    E' il valore che l'elemento dell'interfaccia esporra' in `data-help`:
    tradurlo significherebbe due ancore diverse per lo stesso comando, e
    l'interfaccia adattiva ne troverebbe una sola.
    """
    with app.app_context():
        ancore = {
            locale: {
                hint_id: hint.anchor
                for hint_id, hint in get_content(locale).hints.items()
            }
            for locale in _locales()
        }
    riferimento = ancore[FALLBACK_LOCALE]
    for locale, mappa in ancore.items():
        assert mappa == riferimento, f"Ancore divergenti in «{locale}»"


@pytest.mark.unit
def test_ogni_sezione_ha_almeno_una_pagina(app):
    with app.app_context():
        for locale in _locales():
            content = get_content(locale)
            vuote = [s.id for s in content.sections if not content.pages_of(s)]
            assert not vuote, f"Sezioni senza pagine in «{locale}»: {vuote}"


@pytest.mark.unit
def test_esiste_un_percorso_di_partenza(app):
    """La copertina propone i tutorial: senza, chi apre la guida non sa da dove
    cominciare e si trova davanti un elenco di argomenti."""
    with app.app_context():
        content = get_content(FALLBACK_LOCALE)
        tutorial = [p for p in content.pages.values() if p.kind == "tutorial"]
    assert len(tutorial) >= 3, "Servono almeno tre guide passo passo"


@pytest.mark.unit
def test_ogni_ruolo_ha_contenuti_dedicati(app):
    """Giocatore e direttore devono trovare pagine scritte per loro."""
    with app.app_context():
        content = get_content(FALLBACK_LOCALE)
        coperti = {who for page in content.pages.values() for who in page.audience}
    for ruolo in ("giocatore", "direttore"):
        assert ruolo in coperti, f"Nessuna pagina rivolta a «{ruolo}»"
    assert coperti <= AUDIENCES


@pytest.mark.unit
def test_le_figure_dichiarate_sono_tutte_usate(app):
    """Una cattura mai citata è peso morto: viene rigenerata a ogni giro e
    nessuno la guarda. Segnalarla tiene onesto il manifest."""
    with app.app_context():
        content = get_content(FALLBACK_LOCALE)
        usate: set[str] = set()
        for page in content.pages.values():
            for block in page.blocks:
                if block.get("shot"):
                    usate.add(block["shot"])
                for item in block.get("items") or []:
                    if isinstance(item, dict) and item.get("shot"):
                        usate.add(item["shot"])
        orfane = set(content.shots) - usate
    assert (
        not orfane
    ), f"Schermate catturate ma non usate da nessuna pagina: {sorted(orfane)}"


@pytest.mark.unit
def test_i_suggerimenti_stanno_in_un_fumetto(app):
    """Un micro-aiuto è una o due frasi accanto a un comando. Oltre, è un
    paragrafo nel posto sbagliato e va spostato nella pagina."""
    with app.app_context():
        for locale in _locales():
            hints = get_content(locale).hints.values()
            lunghi = [(h.id, len(h.short)) for h in hints if len(h.short) > 220]
            assert not lunghi, f"Suggerimenti troppo lunghi in «{locale}»: {lunghi}"


@pytest.mark.unit
def test_le_presentazioni_coprono_le_schermate_principali(app):
    """Le schermate su cui si passa più tempo devono avere una presentazione
    pronta per la futura interfaccia adattiva."""
    with app.app_context():
        tours = get_content(FALLBACK_LOCALE).tours
    for screen in (
        "dashboard.dashboard",
        "admin.competition.gara_detail",
        "admin.match.match_detail",
    ):
        assert screen in tours, f"Manca la presentazione per «{screen}»"


@pytest.mark.unit
def test_ricerca(app):
    with app.app_context():
        assert search("iscrizione"), "La ricerca non trova «iscrizione»"
        assert search("qwertyuiop") == []
        assert search("") == []
        # Il titolo pesa piu' del corpo: chi cerca «classifiche» vuole la
        # pagina sulle classifiche, non le altre che le nominano.
        primo = search("classifiche")[0]
        assert primo.slug == "classifiche"


@pytest.mark.unit
def test_api_per_schermata(app):
    """La forma del JSON è il contratto con la futura interfaccia adattiva."""
    with app.app_context():
        payload = screen_payload("admin.match.match_detail")
    assert payload["screen"] == "admin.match.match_detail"
    assert payload["tour"] and payload["tour"]["steps"]
    assert payload["hints"]
    primo = payload["hints"][0]
    assert set(primo) == {"id", "label", "short", "anchor", "url"}
    # Un passo che rimanda a un suggerimento ne eredita il testo: se qui
    # fosse vuoto, i due testi sarebbero da scrivere due volte.
    con_hint = [s for s in payload["tour"]["steps"] if s["hint"]]
    assert con_hint and all(s["text"] for s in con_hint)


@pytest.mark.unit
def test_suggerimenti_per_schermata(app):
    with app.app_context():
        assert hints_for_screen("admin.match.match_detail")
        assert hints_for_screen("endpoint.inesistente") == []


@pytest.mark.unit
@pytest.mark.parametrize(
    "sorgente, atteso",
    [
        ("**forte**", "<strong>forte</strong>"),
        ("`codice`", "<code>codice</code>"),
        ("[qui](/aiuto/)", '<a href="/aiuto/">qui</a>'),
        # Il testo viene messo in sicurezza prima del markup: i contenuti
        # stanno nel repository, ma una guida che sa produrre HTML arbitrario
        # e' un'arma puntata al piede.
        ("<script>alert(1)</script>", "&lt;script&gt;"),
        # Uno schema pericoloso non diventa un collegamento.
        ("[x](javascript:alert(1))", "x"),
    ],
)
def test_markup_minimo(sorgente, atteso):
    assert atteso in str(render_text(sorgente))


@pytest.mark.unit
def test_markup_non_produce_collegamenti_pericolosi():
    assert "javascript:" not in str(render_text("[x](javascript:alert(1))"))
