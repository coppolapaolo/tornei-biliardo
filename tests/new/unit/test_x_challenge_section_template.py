"""La sezione «esercizio per la X» non contiene campi obbligatori nell'HTML.

Presidia il guasto visto in produzione il 2026-09-04, nato con la PR #269 e
rimasto invisibile per una settimana perché nessun test lo poteva vedere: la
validazione HTML5 è del browser, e i test di integrazione fanno POST diretti.

**Il difetto.** Il `<select>` dell'esercizio era `required` e vuoto dentro un
contenitore `display:none`. La specifica HTML5 dice che il browser deve
bloccare l'invio e *segnalare* il controllo invalido — ma non può mostrare il
messaggio accanto a un elemento che non riceve il focus, quindi blocca e basta.
Il pulsante Salva diventava inerte e muto: con qualunque politica diversa da
«X con esercizio» (cioè quasi sempre, il default è «X vinta a tavolino»)
nessuna gara si poteva creare dal modal né modificare.

**Perché il presidio è qui e non nella suite jsdom.** Quella prova che
`x_challenge_section.js` mette e toglie l'obbligo insieme alla visibilità;
questa prova che *l'HTML servito non ha già l'obbligo addosso* prima che un
solo byte di JavaScript giri. Sono due domande diverse e il difetto stava
nella seconda.

L'obbligatorietà non sparisce: la impone il server in
`GaraFormParser._parse_x_challenge`, con un messaggio scritto per il direttore,
e il JavaScript la rimette sul campo quando la sezione si vede.
"""

from html.parser import HTMLParser
from pathlib import Path

import pytest

TEMPLATES = Path(__file__).resolve().parents[3] / "templates"

#: I due moduli che chiedono l'esercizio della X: modifica e creazione.
SEZIONI = [
    ("components/_gara_edit_form.html", "x_challenge_section"),
    ("components/_new_gara_modal.html", "create_x_challenge_section"),
]


class _Sezione(HTMLParser):
    """Raccoglie i tag contenuti nell'elemento con un dato id.

    Il Jinja nel mezzo (`{% if %}`, `{{ _(...) }}`) resta testo: i tag HTML
    intorno sono ben formati, ed è tutto ciò che serve per contare i livelli.
    """

    def __init__(self, id_cercato: str) -> None:
        super().__init__(convert_charrefs=True)
        self.id_cercato = id_cercato
        self.attributi_contenitore: dict[str, str | None] | None = None
        self.campi: list[tuple[str, dict[str, str | None]]] = []
        self._profondita = 0
        self._finita = False

    def handle_starttag(self, tag, attrs):
        attributi = dict(attrs)
        if self._finita:
            return

        if not self._profondita:
            if attributi.get("id") == self.id_cercato:
                self.attributi_contenitore = attributi
                self._profondita = 1
            return

        if tag in ("select", "input", "textarea"):
            self.campi.append((tag, attributi))
        if tag == "div":
            self._profondita += 1

    def handle_endtag(self, tag):
        if self._finita or not self._profondita or tag != "div":
            return
        self._profondita -= 1
        if not self._profondita:
            # Il contenitore si è chiuso: quello che segue non lo riguarda,
            # e senza questo il parser continuerebbe a raccogliere i campi
            # del resto del modulo (che sono `required` a buon diritto).
            self._finita = True

    def handle_startendtag(self, tag, attrs):
        if self._profondita and not self._finita:
            self.handle_starttag(tag, attrs)


def _analizza(percorso: str, id_sezione: str) -> _Sezione:
    parser = _Sezione(id_sezione)
    parser.feed((TEMPLATES / percorso).read_text(encoding="utf-8"))
    assert (
        parser.attributi_contenitore is not None
    ), f"{percorso}: nessun elemento con id={id_sezione!r} — il test va aggiornato"
    return parser


@pytest.mark.parametrize("percorso,id_sezione", SEZIONI)
def test_nessun_campo_obbligatorio_nell_html(percorso, id_sezione):
    """Il difetto esatto: un `required` che il browser non può mostrare."""
    sezione = _analizza(percorso, id_sezione)
    obbligatori = [
        attributi.get("name") or attributi.get("id")
        for _, attributi in sezione.campi
        if "required" in attributi
    ]
    assert obbligatori == [], (
        f"{percorso}: {obbligatori} è `required` dentro una sezione che il "
        "template può servire nascosta. Il browser blocca il salvataggio senza "
        "poter dire dove: l'obbligo lo mette x_challenge_section.js quando la "
        "sezione si vede, e il server lo pretende comunque."
    )


@pytest.mark.parametrize("percorso,id_sezione", SEZIONI)
def test_la_sezione_ha_un_padrone_solo(percorso, id_sezione):
    """`data-bracket-hide` significa «il display lo scrive bracket_options.js».

    La sezione lo portava, e quel file rimetteva `display: ''` a ogni sync con
    una strategia a girone — cancellando il `display:none` deciso dalla
    politica. Il campo dell'esercizio riappariva anche con «X vinta a
    tavolino»: due script padroni dello stesso nodo, nessuno dei due al
    corrente dell'altro.
    """
    sezione = _analizza(percorso, id_sezione)
    attributi = sezione.attributi_contenitore or {}
    assert "data-bracket-hide" not in attributi, (
        f"{percorso}: la sezione della X non può essere anche `data-bracket-hide`. "
        "Il caso «formato a tabellone» lo gestisce x_challenge_section.js, che "
        "ascolta l'evento `gara:formato`."
    )
    assert attributi.get("data-x-challenge-section"), (
        f"{percorso}: manca `data-x-challenge-section` con l'id del select della "
        "politica — senza, x_challenge_section.js non trova la sezione."
    )


@pytest.mark.parametrize("percorso,id_sezione", SEZIONI)
def test_il_template_carica_il_file_che_governa_la_sezione(percorso, id_sezione):
    """Senza lo script la sezione resterebbe ferma allo stato iniziale."""
    sorgente = (TEMPLATES / percorso).read_text(encoding="utf-8")
    assert "js/x_challenge_section.js" in sorgente, (
        f"{percorso}: la sezione c'è ma il file che la governa non è caricato. "
        "Visibilità e obbligo resterebbero quelli del render, e cambiare la "
        "politica non cambierebbe niente."
    )


@pytest.mark.parametrize("percorso,id_sezione", SEZIONI)
def test_il_select_della_politica_esiste_davvero(percorso, id_sezione):
    """L'aggancio è un id: un refuso lo spegnerebbe in silenzio."""
    sezione = _analizza(percorso, id_sezione)
    atteso = (sezione.attributi_contenitore or {}).get("data-x-challenge-section")
    sorgente = (TEMPLATES / percorso).read_text(encoding="utf-8")
    assert f'id="{atteso}"' in sorgente, (
        f'{percorso}: `data-x-challenge-section="{atteso}"` non corrisponde a '
        "nessun id nel template."
    )
