"""Mini-sito di aiuto (`/aiuto`).

Pagine di sola lettura costruite dai file YAML in `help_content/`: nessuna
query al database, nessuno stato utente. Sono raggiungibili anche senza
account — chi sta valutando se registrarsi e' esattamente la persona che ha
piu' bisogno di capire come funziona.

L'API `/aiuto/api/schermata/<endpoint>` e' la **predisposizione** per
l'interfaccia adattiva (presentazione alla prima visita, "?" accanto ai
comandi): restituisce i contenuti gia' scritti, per schermata, in una forma
che un componente lato client puo' consumare. Oggi nessuna pagina dell'app la
chiama; esiste perche' quando l'interfaccia adattiva verra' costruita i testi
siano gia' li', rivisti e verificati, invece di essere inventati allora.
"""

from __future__ import annotations

from flask import Blueprint, abort, jsonify, redirect, render_template, request, url_for
from flask_babel import get_locale, lazy_gettext as _l

from utils.help_content import (
    get_content,
    render_text,
    screen_payload,
    search as search_pages,
)

help_bp = Blueprint("help", __name__, url_prefix="/aiuto")


# Etichette dei metadati di pagina. Stanno qui e non nei file di contenuto
# perche' sono vocabolario dell'interfaccia (tradotto con l'app), non testo
# della guida: `kind: tutorial` e' una classificazione, "Passo passo" e' come
# la chiamiamo davanti all'utente.
_KIND_LABELS = {
    "introduzione": _l("Panoramica"),
    "tutorial": _l("Passo passo"),
    "approfondimento": _l("Approfondimento"),
    "riferimento": _l("Riferimento"),
}

_AUDIENCE_LABELS = {
    "tutti": _l("Tutti"),
    "giocatore": _l("Giocatore"),
    "direttore": _l("Direttore di gara"),
    "amministratore": _l("Amministratore"),
}


@help_bp.context_processor
def _help_helpers():
    return {
        "help_text": render_text,
        "kind_label": lambda kind: _KIND_LABELS.get(kind, kind),
        "audience_label": lambda who: _AUDIENCE_LABELS.get(who, who),
    }


def _content():
    """Contenuto nella lingua dell'utente, con ricaduta sull'italiano."""
    try:
        locale = str(get_locale() or "it")
    except Exception:  # fuori da una richiesta con Babel configurato
        locale = "it"
    return get_content(locale)


@help_bp.route("/")
def index():
    """Copertina del mini-sito: da dove si comincia, e cosa c'e' dentro."""
    content = _content()
    return render_template(
        "help/index.html",
        help=content,
        quick_start=[
            content.pages[slug]
            for slug in _quick_start_slugs(content)
            if slug in content.pages
        ],
    )


def _quick_start_slugs(content) -> list[str]:
    """I tutorial brevi, nell'ordine in cui sono dichiarati nelle sezioni.

    Sono l'ingresso naturale per chi apre la guida senza sapere cosa cercare,
    quindi la copertina li ripete in cima invece di lasciarli sepolti nella
    loro sezione.
    """
    slugs: list[str] = []
    for section in content.sections:
        for slug in section.page_slugs:
            page = content.pages.get(slug)
            if page and page.kind == "tutorial":
                slugs.append(slug)
    return slugs


@help_bp.route("/cerca")
def search():
    query = (request.args.get("q") or "").strip()
    results = search_pages(query, locale=_content().locale) if query else []
    return render_template(
        "help/search.html", help=_content(), query=query, results=results
    )


@help_bp.route("/microaiuto")
def hints_index():
    """Catalogo dei micro-aiuti, raggruppati per schermata.

    Non e' una pagina per l'utente finale: serve a chi scrive l'aiuto e a chi
    costruira' l'interfaccia adattiva per vedere, oggi, cosa dira' domani la
    "?" accanto a ogni comando — e accorgersi di cosa manca.
    """
    content = _content()
    by_screen: dict[str, list] = {}
    for hint in content.hints.values():
        for screen in hint.screens:
            by_screen.setdefault(screen, []).append(hint)
    for hints in by_screen.values():
        hints.sort(key=lambda hint: hint.label)

    return render_template(
        "help/hints.html",
        help=content,
        by_screen=dict(sorted(by_screen.items())),
        tours=content.tours,
    )


@help_bp.route("/api/schermata/<path:screen>")
def screen_api(screen: str):
    """Contenuti di aiuto di una schermata, in JSON (interfaccia adattiva)."""
    payload = screen_payload(screen, locale=_content().locale)
    if not payload["hints"] and not payload["tour"]:
        # Meglio un 404 esplicito che un oggetto vuoto: chi integra deve
        # accorgersi subito di aver scritto il nome dell'endpoint sbagliato.
        abort(404)
    return jsonify(payload)


@help_bp.route("/<section_id>/")
def section(section_id: str):
    content = _content()
    found = content.section(section_id)
    if not found:
        abort(404)
    return render_template(
        "help/section.html",
        help=content,
        section=found,
        pages=content.pages_of(found),
    )


@help_bp.route("/<section_id>/<slug>")
def page(section_id: str, slug: str):
    content = _content()
    found = content.pages.get(slug)
    if not found:
        abort(404)
    if found.section != section_id:
        # La pagina esiste ma sotto un'altra sezione: capita dopo un riordino
        # dell'indice, e i collegamenti vecchi (segnalibri, link condivisi) non
        # devono morire.
        return redirect(url_for("help.page", section_id=found.section, slug=slug))

    section_obj = content.section_of(found)
    siblings = content.pages_of(section_obj) if section_obj else []
    position = siblings.index(found) if found in siblings else -1
    return render_template(
        "help/page.html",
        help=content,
        page=found,
        section=section_obj,
        previous_page=siblings[position - 1] if position > 0 else None,
        next_page=(
            siblings[position + 1] if 0 <= position < len(siblings) - 1 else None
        ),
        related=[
            content.pages[slug] for slug in found.related if slug in content.pages
        ],
        hints=[hint for hint in content.hints.values() if hint.page == found.slug],
    )
