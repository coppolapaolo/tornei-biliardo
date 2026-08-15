"""Caricamento del mini-sito di aiuto (`help_content/`).

Il contenuto dell'aiuto e' **dato**, non markup: sta in file YAML e viene
impaginato dai template. Questo separa due cose che nella documentazione
tendono a incollarsi, e che hanno bisogni opposti:

- chi **scrive** l'aiuto vuole aggiungere un passaggio, una nota o una
  schermata senza toccare HTML;
- chi **costruisce** l'interfaccia adattiva (la "?" accanto ai comandi, il giro
  di presentazione alla prima visita) ha bisogno degli stessi testi come dati
  interrogabili per schermata, non come pagine da leggere.

Un mini-sito scritto direttamente in HTML soddisfa il primo bisogno a fatica e
il secondo per niente: i testi dei suggerimenti finirebbero riscritti una
seconda volta dentro l'app e divergerebbero al primo aggiornamento. Da qui la
scelta di una sorgente sola con due letture diverse — `get_page` per il sito,
`hints_for_screen` per l'interfaccia adattiva.

Struttura sul disco::

    help_content/
        screenshots.yaml         manifest delle catture (condiviso fra le lingue)
        it/
            site.yaml            sezioni, ordine, testi della home
            hints.yaml           micro-aiuto e giri di presentazione
            pages/<slug>.yaml    una pagina per file

Le lingue sono cartelle sorelle sotto `help_content/`. Oggi c'e' solo `it`; una
lingua mancante ricade sull'italiano invece di mostrare una pagina vuota.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from html import escape
from typing import Any, Iterable, Optional

from flask import current_app, url_for
from markupsafe import Markup

# Lingua in cui l'aiuto e' scritto per intero: ogni altra vi ricade.
FALLBACK_LOCALE = "it"

# Tipi di blocco riconosciuti dai template. Un tipo sconosciuto e' un errore di
# battitura nel contenuto, non un blocco da ignorare in silenzio: `validate`
# lo segnala, cosi' non sparisce un paragrafo senza che nessuno se ne accorga.
BLOCK_TYPES = {
    "heading",
    "text",
    "steps",
    "shot",
    "note",
    "list",
    "options",
    "faq",
}

NOTE_TONES = {"info", "warning", "tip"}

# Chi e' il destinatario di una pagina. Serve ai filtri del sito e, domani, a
# non proporre a un giocatore il giro di presentazione del direttore.
AUDIENCES = {"tutti", "giocatore", "direttore", "amministratore"}

PAGE_KINDS = {"introduzione", "tutorial", "approfondimento", "riferimento"}


# ---------------------------------------------------------------------------
# Strutture
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Shot:
    """Una schermata catturata dall'app (voce di `screenshots.yaml`).

    Le catture sono **per lingua**: l'app e' tradotta, quindi una guida inglese
    con le schermate in italiano mostrerebbe pulsanti che nell'interfaccia del
    lettore non esistono — cioe' proprio l'errore che la guida dovrebbe evitare.
    Da qui `static/img/help/<lingua>/<id>.png` e il `locale` gia' risolto in
    `caption`.
    """

    id: str
    caption: str
    route: str
    role: str
    viewports: tuple[str, ...]
    locale: str = FALLBACK_LOCALE

    @property
    def filename(self) -> str:
        return f"img/help/{self.locale}/{self.id}.png"

    @property
    def desktop_filename(self) -> Optional[str]:
        if "desktop" not in self.viewports:
            return None
        return f"img/help/{self.locale}/{self.id}-desktop.png"


@dataclass(frozen=True)
class Page:
    slug: str
    title: str
    section: str
    kind: str
    audience: tuple[str, ...]
    summary: str
    minutes: Optional[int]
    blocks: tuple[dict[str, Any], ...]
    related: tuple[str, ...]
    screens: tuple[str, ...]  # endpoint Flask spiegati da questa pagina

    @property
    def headings(self) -> list[dict[str, str]]:
        """Titoli interni, per l'indice «in questa pagina» e per le ancore.

        Sono anche il bersaglio dei micro-aiuti: un suggerimento rimanda a
        `pagina#titolo`, quindi l'ancora deve esistere davvero (lo verifica
        `validate`, altrimenti il collegamento porta in cima e sembra rotto).
        """
        return [
            {"id": block.get("id", ""), "title": block.get("title", "")}
            for block in self.blocks
            if isinstance(block, dict) and block.get("type") == "heading"
        ]


@dataclass(frozen=True)
class Section:
    id: str
    title: str
    summary: str
    icon: str
    kicker: str
    page_slugs: tuple[str, ...]


@dataclass(frozen=True)
class Hint:
    """Micro-aiuto agganciabile a un elemento dell'interfaccia.

    E' la **predisposizione** per l'interfaccia adattiva descritta nella guida:
    `anchor` e' il valore che l'elemento esporra' in `data-help`, `screens` dice
    su quali schermate compare, `page`/`section` dove leggerne di piu'. Oggi
    nessuna pagina dell'app li consuma: esistono, sono verificati dai test e
    interrogabili via API, e questo e' quanto serve perche' lo sviluppo
    dell'interfaccia adattiva parta da contenuti gia' scritti e gia' rivisti.
    """

    id: str
    label: str
    short: str
    anchor: str
    screens: tuple[str, ...]
    page: Optional[str]
    section: Optional[str]


@dataclass(frozen=True)
class TourStep:
    title: str
    text: str
    hint: Optional[str]
    anchor: Optional[str]


@dataclass(frozen=True)
class Tour:
    """Presentazione mostrata la prima volta che si apre una schermata."""

    screen: str
    title: str
    intro: str
    audience: tuple[str, ...]
    steps: tuple[TourStep, ...]


@dataclass
class HelpContent:
    locale: str
    title: str
    tagline: str
    intro: str
    sections: tuple[Section, ...]
    pages: dict[str, Page]
    shots: dict[str, Shot]
    hints: dict[str, Hint]
    tours: dict[str, Tour]
    problems: tuple[str, ...] = field(default=())

    def section(self, section_id: str) -> Optional[Section]:
        for section in self.sections:
            if section.id == section_id:
                return section
        return None

    def pages_of(self, section: Section) -> list[Page]:
        return [self.pages[slug] for slug in section.page_slugs if slug in self.pages]

    def section_of(self, page: Page) -> Optional[Section]:
        return self.section(page.section)


# ---------------------------------------------------------------------------
# Caricamento
# ---------------------------------------------------------------------------


def content_root() -> str:
    """Cartella dei contenuti, sovrascrivibile per i test."""
    configured = None
    try:
        configured = current_app.config.get("HELP_CONTENT_DIR")
    except RuntimeError:  # fuori da un contesto applicativo (script, test)
        configured = None
    if configured:
        return configured
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "help_content"
    )


def available_locales() -> list[str]:
    root = content_root()
    if not os.path.isdir(root):
        return []
    return sorted(
        name
        for name in os.listdir(root)
        if os.path.isdir(os.path.join(root, name))
        and os.path.exists(os.path.join(root, name, "site.yaml"))
    )


def _read_yaml(path: str) -> Any:
    import yaml

    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _as_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    return tuple(str(item) for item in value)


def _load_shots(root: str, locale: str, problems: list[str]) -> dict[str, Shot]:
    """Manifest delle catture, con didascalie nella lingua richiesta.

    La parte tecnica (quale percorso, con quale utente, a quale larghezza) e'
    una sola per tutte le lingue: descrive l'app, non il testo. Le didascalie
    sono per lingua e stanno in `<lingua>/captions.yaml`, perche' sono il testo
    alternativo dell'immagine — cioe' cio' che legge chi non vede la figura.
    """
    data = _read_yaml(os.path.join(root, "screenshots.yaml")) or {}
    captions = _read_yaml(os.path.join(root, locale, "captions.yaml")) or {}
    shots: dict[str, Shot] = {}
    for entry in data.get("shots") or []:
        shot_id = entry.get("id")
        if not shot_id:
            problems.append("screenshots.yaml: una voce non ha `id`")
            continue
        shots[shot_id] = Shot(
            id=shot_id,
            caption=captions.get(shot_id) or entry.get("caption", ""),
            route=entry.get("route", ""),
            role=entry.get("as", "anonimo"),
            viewports=_as_tuple(entry.get("viewports")) or ("mobile",),
            locale=locale,
        )
    return shots


def _load_pages(locale_dir: str, problems: list[str]) -> dict[str, Page]:
    pages_dir = os.path.join(locale_dir, "pages")
    pages: dict[str, Page] = {}
    if not os.path.isdir(pages_dir):
        problems.append("manca la cartella `pages/`")
        return pages

    for filename in sorted(os.listdir(pages_dir)):
        if not filename.endswith((".yaml", ".yml")):
            continue
        slug = os.path.splitext(filename)[0]
        data = _read_yaml(os.path.join(pages_dir, filename)) or {}
        blocks = tuple(data.get("blocks") or ())
        pages[slug] = Page(
            slug=slug,
            title=data.get("title", slug),
            section=data.get("section", ""),
            kind=data.get("kind", "approfondimento"),
            audience=_as_tuple(data.get("audience")) or ("tutti",),
            summary=data.get("summary", ""),
            minutes=data.get("minutes"),
            blocks=blocks,
            related=_as_tuple(data.get("related")),
            screens=_as_tuple(data.get("screens")),
        )
    return pages


def _load_hints(locale_dir: str) -> tuple[dict[str, Hint], dict[str, Tour]]:
    data = _read_yaml(os.path.join(locale_dir, "hints.yaml")) or {}

    hints: dict[str, Hint] = {}
    for entry in data.get("hints") or []:
        hint_id = entry.get("id")
        if not hint_id:
            continue
        hints[hint_id] = Hint(
            id=hint_id,
            label=entry.get("label", ""),
            short=entry.get("short", ""),
            anchor=entry.get("anchor", hint_id.replace(".", "-")),
            screens=_as_tuple(entry.get("screens")),
            page=entry.get("page"),
            section=entry.get("section"),
        )

    tours: dict[str, Tour] = {}
    for entry in data.get("tours") or []:
        screen = entry.get("screen")
        if not screen:
            continue
        steps = []
        for step in entry.get("steps") or []:
            hint_id = step.get("hint")
            source = hints.get(hint_id) if hint_id else None
            steps.append(
                TourStep(
                    # Un passo che rimanda a un micro-aiuto ne eredita testo ed
                    # etichetta: scriverli due volte significa vederli divergere.
                    title=step.get("title") or (source.label if source else ""),
                    text=step.get("text") or (source.short if source else ""),
                    hint=hint_id,
                    anchor=step.get("anchor") or (source.anchor if source else None),
                )
            )
        tours[screen] = Tour(
            screen=screen,
            title=entry.get("title", ""),
            intro=entry.get("intro", ""),
            audience=_as_tuple(entry.get("audience")) or ("tutti",),
            steps=tuple(steps),
        )
    return hints, tours


def _load(locale: str) -> HelpContent:
    root = content_root()
    problems: list[str] = []
    locale_dir = os.path.join(root, locale)

    site = _read_yaml(os.path.join(locale_dir, "site.yaml")) or {}
    sections = tuple(
        Section(
            id=entry.get("id", ""),
            title=entry.get("title", ""),
            summary=entry.get("summary", ""),
            icon=entry.get("icon", "fa-circle-info"),
            kicker=entry.get("kicker", ""),
            page_slugs=_as_tuple(entry.get("pages")),
        )
        for entry in site.get("sections") or []
    )

    pages = _load_pages(locale_dir, problems)
    shots = _load_shots(root, locale, problems)
    hints, tours = _load_hints(locale_dir)

    return HelpContent(
        locale=locale,
        title=site.get("title", "Guida"),
        tagline=site.get("tagline", ""),
        intro=site.get("intro", ""),
        sections=sections,
        pages=pages,
        shots=shots,
        hints=hints,
        tours=tours,
        problems=tuple(problems),
    )


_CACHE: dict[str, HelpContent] = {}


def get_content(locale: Optional[str] = None) -> HelpContent:
    """Contenuto dell'aiuto per la lingua richiesta (con cache).

    In sviluppo la cache e' spenta: si sta scrivendo l'aiuto, e dover riavviare
    l'app dopo ogni frase renderebbe la scrittura insopportabile.
    """
    locale = (locale or FALLBACK_LOCALE).split("-")[0].split("_")[0]
    if locale not in available_locales():
        locale = FALLBACK_LOCALE

    cache_enabled = True
    try:
        cache_enabled = not current_app.config.get("DEBUG_MODE", False)
    except RuntimeError:
        cache_enabled = False

    if cache_enabled and locale in _CACHE:
        return _CACHE[locale]
    content = _load(locale)
    if cache_enabled:
        _CACHE[locale] = content
    return content


def clear_cache() -> None:
    _CACHE.clear()


# ---------------------------------------------------------------------------
# Interfaccia adattiva (predisposizione)
# ---------------------------------------------------------------------------


def hints_for_screen(screen: str, locale: Optional[str] = None) -> list[Hint]:
    """Micro-aiuto dichiarato per una schermata (endpoint Flask)."""
    content = get_content(locale)
    return [hint for hint in content.hints.values() if screen in hint.screens]


def tour_for_screen(screen: str, locale: Optional[str] = None) -> Optional[Tour]:
    return get_content(locale).tours.get(screen)


def screen_payload(screen: str, locale: Optional[str] = None) -> dict[str, Any]:
    """Tutto cio' che l'interfaccia adattiva dovra' sapere di una schermata.

    Forma stabile e volutamente povera: un oggetto JSON che un componente
    lato client possa consumare senza conoscere il resto dell'aiuto.
    """
    content = get_content(locale)
    tour = content.tours.get(screen)
    hints = hints_for_screen(screen, locale)

    def page_url(hint: Hint) -> Optional[str]:
        """Il collegamento «leggi tutto» del micro-aiuto.

        Costruito con `url_for` e non a mano: la pagina sta sotto la sua
        sezione (`/aiuto/<sezione>/<slug>`), e un path scritto in questo file
        smetterebbe di corrispondere alla route senza che nulla se ne accorga.
        """
        if not hint.page:
            return None
        page = content.pages.get(hint.page)
        if page is None:
            return None
        fragment = f"#{hint.section}" if hint.section else ""
        return url_for("help.page", section_id=page.section, slug=page.slug) + fragment

    return {
        "screen": screen,
        "locale": content.locale,
        "tour": (
            {
                "title": tour.title,
                "intro": tour.intro,
                "audience": list(tour.audience),
                "steps": [
                    {
                        "title": step.title,
                        "text": step.text,
                        "anchor": step.anchor,
                        "hint": step.hint,
                    }
                    for step in tour.steps
                ],
            }
            if tour
            else None
        ),
        "hints": [
            {
                "id": hint.id,
                "label": hint.label,
                "short": hint.short,
                "anchor": hint.anchor,
                "url": page_url(hint),
            }
            for hint in hints
        ],
    }


# ---------------------------------------------------------------------------
# Ricerca
# ---------------------------------------------------------------------------


def _page_text(page: Page) -> str:
    """Tutto il testo di una pagina, per la ricerca."""
    parts = [page.title, page.summary]
    for block in page.blocks:
        for key in ("text", "title", "caption"):
            if isinstance(block.get(key), str):
                parts.append(block[key])
        for item in block.get("items") or []:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.extend(
                    str(item[key])
                    for key in ("title", "text", "q", "a", "name", "values")
                    if item.get(key)
                )
    return " ".join(parts)


def search(query: str, locale: Optional[str] = None, limit: int = 20) -> list[Page]:
    """Ricerca per parole, ordinata per pertinenza.

    Volutamente ingenua (nessun indice, nessuno stemming): l'aiuto sono poche
    decine di pagine e un indice andrebbe tenuto aggiornato — altro lavoro che
    si dimentica di fare.

    I pesi dicono dove sta l'argomento di una pagina, non dove compare la
    parola. Lo **slug** pesa piu' di tutto perche' e' il nome che la pagina si
    e' data: chi cerca «classifiche» vuole la pagina sulle classifiche, non le
    cinque che le nominano di sfuggita. Il corpo conta al massimo cinque
    occorrenze per parola, altrimenti una pagina lunga vincerebbe sempre per
    ripetizione.
    """
    words = [word for word in re.split(r"\W+", query.lower()) if len(word) > 1]
    if not words:
        return []

    results: list[tuple[int, Page]] = []
    for page in get_content(locale).pages.values():
        slug = page.slug.lower()
        title = page.title.lower()
        summary = page.summary.lower()
        body = _page_text(page).lower()
        score = 0
        for word in words:
            if word in slug:
                score += 14
            if word in title:
                score += 10
            if word in summary:
                score += 4
            score += min(body.count(word), 5)
        if score:
            results.append((score, page))

    results.sort(key=lambda pair: (-pair[0], pair[1].title))
    return [page for _score, page in results[:limit]]


# ---------------------------------------------------------------------------
# Testo formattato
# ---------------------------------------------------------------------------

_BOLD = re.compile(r"\*\*(.+?)\*\*")
_CODE = re.compile(r"`([^`]+)`")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def render_text(raw: Optional[str]) -> Markup:
    """Converte il minimo markup ammesso nei testi dell'aiuto.

    Solo grassetto, codice e collegamenti: e' un sottoinsieme deliberato di
    Markdown. Un renderer completo inviterebbe a mettere nei testi tabelle,
    titoli e immagini — cioe' struttura — mentre la struttura qui la esprimono i
    blocchi, che sono anche cio' che l'interfaccia adattiva sa riusare. Il testo
    e' sempre messo in sicurezza prima: i contenuti stanno nel repository, ma
    una guida che sa produrre HTML arbitrario e' un'arma puntata al piede.
    """
    if not raw:
        return Markup("")
    text = escape(str(raw))
    text = _CODE.sub(r"<code>\1</code>", text)
    text = _BOLD.sub(r"<strong>\1</strong>", text)

    def link(match: re.Match) -> str:
        label, target = match.group(1), match.group(2)
        # Solo percorsi interni e http(s): niente `javascript:` per distrazione.
        if not re.match(r"^(https?://|/|#)", target):
            return label
        external = target.startswith("http")
        extra = ' target="_blank" rel="noopener"' if external else ""
        return f'<a href="{target}"{extra}>{label}</a>'

    text = _LINK.sub(link, text)
    return Markup(text)


# ---------------------------------------------------------------------------
# Verifica
# ---------------------------------------------------------------------------


def validate(
    locale: Optional[str] = None,
    known_endpoints: Optional[Iterable[str]] = None,
    static_dir: Optional[str] = None,
) -> list[str]:
    """Elenca le incoerenze del contenuto (usata dai test e dalla skill).

    Serve a rendere impossibili i guasti silenziosi tipici della documentazione:
    la pagina tolta dall'indice ma ancora collegata, l'immagine citata e mai
    catturata, il rimando a una schermata che nel frattempo ha cambiato nome.
    Ognuno lascia la guida "apparentemente giusta" mentre sta gia' mentendo.
    """
    content = get_content(locale)
    problems: list[str] = list(content.problems)

    indexed: set[str] = set()
    for section in content.sections:
        if not section.id:
            problems.append("site.yaml: una sezione non ha `id`")
        for slug in section.page_slugs:
            if slug not in content.pages:
                problems.append(
                    f"site.yaml: la sezione «{section.id}» elenca la pagina "
                    f"«{slug}», che non esiste in pages/"
                )
            indexed.add(slug)

    for slug, page in sorted(content.pages.items()):
        if slug not in indexed:
            problems.append(
                f"{slug}: la pagina non compare in nessuna sezione di site.yaml "
                "(sarebbe irraggiungibile)"
            )
        if page.section and content.section(page.section) is None:
            problems.append(
                f"{slug}: `section: {page.section}` non esiste in site.yaml"
            )
        if page.kind not in PAGE_KINDS:
            problems.append(
                f"{slug}: `kind: {page.kind}` sconosciuto "
                f"(ammessi: {', '.join(sorted(PAGE_KINDS))})"
            )
        for audience in page.audience:
            if audience not in AUDIENCES:
                problems.append(f"{slug}: destinatario «{audience}» sconosciuto")
        if not page.summary:
            problems.append(f"{slug}: manca `summary` (compare negli elenchi)")
        for related in page.related:
            if related not in content.pages:
                problems.append(
                    f"{slug}: `related` rimanda a «{related}», che non esiste"
                )

        problems.extend(_validate_blocks(slug, page, content, static_dir))

        if known_endpoints is not None:
            for screen in page.screens:
                if screen not in known_endpoints:
                    problems.append(
                        f"{slug}: `screens` cita l'endpoint «{screen}», che non "
                        "esiste nell'app"
                    )

    problems.extend(_validate_hints(content, known_endpoints))
    return problems


def _validate_blocks(
    slug: str, page: Page, content: HelpContent, static_dir: Optional[str]
) -> list[str]:
    problems: list[str] = []
    for index, block in enumerate(page.blocks, 1):
        where = f"{slug}: blocco #{index}"
        if not isinstance(block, dict):
            problems.append(f"{where}: non e' una mappa YAML")
            continue
        block_type = block.get("type")
        if block_type not in BLOCK_TYPES:
            problems.append(
                f"{where}: `type: {block_type}` sconosciuto "
                f"(ammessi: {', '.join(sorted(BLOCK_TYPES))})"
            )
            continue
        if block_type == "note" and block.get("tone", "info") not in NOTE_TONES:
            problems.append(f"{where}: `tone: {block.get('tone')}` sconosciuto")
        if block_type == "heading" and not (block.get("id") and block.get("title")):
            problems.append(f"{where}: un titolo richiede sia `id` sia `title`")
        if block_type in {"steps", "list", "options", "faq"} and not block.get("items"):
            problems.append(f"{where}: un blocco «{block_type}» senza `items`")

        for shot_id, variant in _shots_in_block(block):
            if shot_id not in content.shots:
                problems.append(
                    f"{where}: la schermata «{shot_id}» non e' dichiarata in "
                    "screenshots.yaml"
                )
                continue
            shot = content.shots[shot_id]
            if variant and variant not in shot.viewports:
                problems.append(
                    f"{where}: chiede la variante «{variant}» di «{shot_id}», che "
                    f"non e' fra i suoi `viewports` ({', '.join(shot.viewports)})"
                )
                continue
            filename = (
                shot.desktop_filename
                if variant == "desktop" and shot.desktop_filename
                else shot.filename
            )
            if static_dir and not os.path.exists(os.path.join(static_dir, filename)):
                problems.append(
                    f"{where}: la schermata «{shot_id}» e' dichiarata ma il file "
                    f"{filename} non e' stato catturato "
                    "(`python scripts/help_docs/capture_screenshots.py`)"
                )
    return problems


def _shots_in_block(block: dict[str, Any]) -> list[tuple[str, Optional[str]]]:
    """Coppie (id schermata, variante) citate da un blocco."""
    shots: list[tuple[str, Optional[str]]] = []
    if block.get("shot"):
        shots.append((block["shot"], block.get("variant")))
    for item in block.get("items") or []:
        if isinstance(item, dict) and item.get("shot"):
            shots.append((item["shot"], item.get("variant")))
    return shots


def _validate_hints(
    content: HelpContent, known_endpoints: Optional[Iterable[str]]
) -> list[str]:
    problems: list[str] = []
    anchors: dict[str, str] = {}

    for hint in content.hints.values():
        if not hint.short:
            problems.append(f"suggerimento «{hint.id}»: manca `short`")
        if len(hint.short) > 220:
            # Il testo va dentro un fumetto accanto a un comando: oltre due righe
            # non e' piu' un suggerimento, e' un paragrafo nel posto sbagliato.
            problems.append(
                f"suggerimento «{hint.id}»: `short` troppo lungo "
                f"({len(hint.short)} caratteri, massimo 220)"
            )
        if hint.anchor in anchors and anchors[hint.anchor] != hint.id:
            problems.append(
                f"suggerimento «{hint.id}»: `anchor: {hint.anchor}` e' gia' usato "
                f"da «{anchors[hint.anchor]}»"
            )
        anchors[hint.anchor] = hint.id
        if hint.page and hint.page not in content.pages:
            problems.append(f"suggerimento «{hint.id}»: `page: {hint.page}` non esiste")
        elif hint.page and hint.section:
            anchors_in_page = {
                heading["id"] for heading in content.pages[hint.page].headings
            }
            if hint.section not in anchors_in_page:
                problems.append(
                    f"suggerimento «{hint.id}»: `section: {hint.section}` non e' un "
                    f"titolo di «{hint.page}» (il collegamento porterebbe in cima)"
                )
        if not hint.screens:
            problems.append(
                f"suggerimento «{hint.id}»: nessuna `screens` — non comparirebbe "
                "su nessuna schermata"
            )
        if known_endpoints is not None:
            for screen in hint.screens:
                if screen not in known_endpoints:
                    problems.append(
                        f"suggerimento «{hint.id}»: l'endpoint «{screen}» non "
                        "esiste nell'app"
                    )

    for tour in content.tours.values():
        if known_endpoints is not None and tour.screen not in known_endpoints:
            problems.append(
                f"presentazione «{tour.screen}»: l'endpoint non esiste nell'app"
            )
        if not tour.steps:
            problems.append(f"presentazione «{tour.screen}»: nessun passo")
        for step in tour.steps:
            if step.hint and step.hint not in content.hints:
                problems.append(
                    f"presentazione «{tour.screen}»: il passo rimanda al "
                    f"suggerimento «{step.hint}», che non esiste"
                )
            if not step.text:
                problems.append(f"presentazione «{tour.screen}»: un passo senza testo")
    return problems
