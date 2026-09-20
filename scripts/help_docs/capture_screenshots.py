#!/usr/bin/env python3
"""Cattura le schermate del mini-sito di aiuto dall'app vera.

Le immagini sono generate, mai disegnate a mano: quando l'interfaccia cambia si
rilancia questo script e le pagine di aiuto tornano a mostrare cio' che l'utente
vede davvero. Un'immagine ritoccata a mano invece sopravvive alle modifiche e
diventa una bugia — e' l'errore piu' comune nella documentazione con schermate.

Il manifest sta in `help_content/screenshots.yaml`: aggiungere una schermata
significa aggiungere una voce li', non toccare questo file.

Uso:
    python scripts/help_docs/capture_screenshots.py               # tutte
    python scripts/help_docs/capture_screenshots.py --only home-giocatore
    python scripts/help_docs/capture_screenshots.py --serve    # avvia l'app da solo
    python scripts/help_docs/capture_screenshots.py --check    # verifica il manifest

Prerequisiti: database dimostrativo popolato (`seed_demo.py`) e app in ascolto
su `--base-url` con `DEBUG_MODE` attivo (serve `/debug/login/<username>`).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

MANIFEST = REPO_ROOT / "help_content" / "screenshots.yaml"
OUTPUT_DIR = REPO_ROOT / "static" / "img" / "help"

# L'app e' tradotta, quindi le schermate lo sono anche loro: una guida inglese
# con i pulsanti in italiano manderebbe il lettore a cercare comandi che nella
# sua interfaccia non esistono. Le catture finiscono in
# `static/img/help/<lingua>/` e il manifest dichiara quali lingue produrre.
DEFAULT_LOCALES = ["it"]

# Il tag BCP-47 passato al browser. Non decide la lingua dell'app (quella la
# imposta `/set_language/<lingua>`), ma il formato di date e numeri.
LOCALE_TAGS = {"it": "it-IT", "en": "en-GB"}

# Le due larghezze che il mini-sito dichiara di supportare. `deviceScaleFactor`
# 2 perche' le immagini vengono mostrate a meta' larghezza CSS: a fattore 1 il
# testo delle schermate risulta sgranato sui display densi.
VIEWPORTS = {
    "mobile": {
        "width": 390,
        "height": 844,
        "device_scale_factor": 2,
        "is_mobile": True,
    },
    "desktop": {
        "width": 1280,
        "height": 860,
        "device_scale_factor": 2,
        "is_mobile": False,
    },
    # Telefono ruotato. Non e' un vezzo: il tabellone della partita compare
    # solo dietro `(orientation: landscape) and (max-height: 520px) and
    # (pointer: coarse)`, quindi con i due viewport qui sopra non finirebbe in
    # nessuna immagine — e una guida che lo descrive senza mostrarlo chiede al
    # lettore di indovinare. `is_mobile` porta con se' `has_touch`, che e' cio'
    # che rende `pointer` grossolano.
    "landscape": {
        "width": 844,
        "height": 390,
        "device_scale_factor": 2,
        "is_mobile": True,
    },
}

# Elementi che non devono comparire: appartengono all'ambiente di sviluppo, non
# all'app che l'utente usa. Se finissero nelle immagini l'aiuto mostrerebbe
# comandi che in produzione non esistono.
HIDE_CSS = """
.debug-footer, .debug-banner, #debugFooter,
[data-help-capture-hide] { display: none !important; }
/* I messaggi flash: sono l'esito di un'azione appena compiuta, e nelle
   schermate della guida non c'e' nessuna azione appena compiuta — solo il
   login di servizio della cattura, che annuncia «Quick login effettuato
   come ...». E' un artefatto dello strumento, che nessun utente vede mai.
   Prima non si notava perche' la rinavigazione lo bruciava per strada; da
   quando la dashboard si fotografa dove il login atterra (vedi sotto), no. */
.c7-flashes { display: none !important; }
/* L'animazione di ingresso delle card lascia elementi a meta' dissolvenza se
   lo scatto arriva troppo presto: qui si spegne ogni transizione. */
*, *::before, *::after {
  transition: none !important;
  animation: none !important;
  caret-color: transparent !important;
}
html { scroll-behavior: auto !important; }
"""

# CSS per gli scatti che non sono la semplice finestra: `full_page` e `clip`.
#
# Un elemento `position: fixed` resta agganciato al viewport, e in entrambi i
# casi finisce dove non deve:
#
#   full_page  Playwright compone la pagina scorrendola, ma la barra viene
#              dipinta **una volta, in mezzo all'immagine**. E' il motivo per
#              cui `full_page` era documentato e non usato da nessuna voce.
#   clip       lo scatto di un elemento riprende la pagina gia' composta, e la
#              barra che gli passa sopra entra nel ritaglio — il foglio del
#              referto usciva coperto dopo una riga sola.
#
# Negli scatti normali la barra resta: e' vera, sta in fondo allo schermo, e
# nasconderla mostrerebbe un'app che non esiste. Qui invece copre contenuto
# che l'utente raggiunge scorrendo, quindi tenerla sarebbe la bugia.
#
# I selettori sono gli elementi sganciati dal flusso realmente presenti nel
# tema (theme-7c.css), non un elenco indovinato: un selettore inesistente non
# da' errore, semplicemente non nasconde niente, e il difetto tornerebbe in
# silenzio.
#
# `.c7-actionbar` non si nasconde, si riporta nel flusso: e' `position: sticky`
# e in `full_page` veniva dipinta a meta' immagine, sopra la scheda della foto
# (visto su `challenge-nuova`). Nasconderla toglierebbe pero' il pulsante
# principale della pagina — «Crea la challenge» — proprio dalla figura che deve
# mostrarlo. Da statica finisce dov'e' davvero: in fondo alla pagina.
#
# `.c7-head` e' `position: sticky`: in un ritaglio piu' alto della finestra
# Playwright scorre, e la testata veniva dipinta sopra il contenuto (visto su
# `referto-tpa-chiuso`, dove copriva le card dei giocatori). Da statica resta
# in cima alla pagina, fuori dal ritaglio.
#
# `.c7-run-dock` sono i comandi dell'allenamento: sotto lg stanno `fixed` in
# fondo allo schermo, e in `full_page` finivano dipinti a meta' immagine sopra
# «Imbucate» e «Posizione». Sono il comando principale della schermata, quindi
# valgono le ragioni di `.c7-actionbar`: statici, non nascosti. Lo spazio che
# il contenuto si riserva sotto di loro, invece, in figura non serve.
#
# `.c7-exam-dock` fa lo stesso mestiere nella sessione d'esame e nella seduta
# di una scheda: stessa regola, e senza il footer finiva tagliato a meta'.
OVERLAY_CSS = """
.c7-mobilenav, #chalky-container { display: none !important; }
.c7-actionbar, .c7-head, .c7-run-dock, .c7-exam-dock { position: static !important; }
body:has(.c7-run-dock) .c7-main,
body:has(.c7-exam-dock) .c7-main { padding-bottom: 16px !important; }
"""

# Cornice e numeri di richiamo. Ricalcano i token del design system (accento
# --c7-accent) perche' le schermate annotate stanno dentro le pagine di aiuto e
# devono sembrare parte dello stesso disegno.
ANNOTATE_JS = """
(items) => {
  const ACCENT = '#2C4A52';
  const BRIGHT = '#8FCDE8';
  items.forEach((item, index) => {
    const el = document.querySelector(item.selector);
    if (!el) return;
    const box = el.getBoundingClientRect();
    const ring = document.createElement('div');
    ring.setAttribute('data-help-annotation', '1');
    Object.assign(ring.style, {
      position: 'absolute',
      left: (box.left + window.scrollX - 6) + 'px',
      top: (box.top + window.scrollY - 6) + 'px',
      width: (box.width + 12) + 'px',
      height: (box.height + 12) + 'px',
      border: '3px solid ' + ACCENT,
      borderRadius: '16px',
      boxShadow: '0 0 0 3px ' + BRIGHT,
      pointerEvents: 'none',
      zIndex: '2147483000'
    });
    document.body.appendChild(ring);
    if (item.label) {
      const badge = document.createElement('div');
      badge.setAttribute('data-help-annotation', '1');
      badge.textContent = item.label;
      Object.assign(badge.style, {
        position: 'absolute',
        left: (box.left + window.scrollX - 20) + 'px',
        top: (box.top + window.scrollY - 20) + 'px',
        minWidth: '30px',
        height: '30px',
        lineHeight: '30px',
        padding: '0 8px',
        borderRadius: '999px',
        background: ACCENT,
        color: '#F2F8F7',
        font: '700 16px/30px Manrope, system-ui, sans-serif',
        textAlign: 'center',
        pointerEvents: 'none',
        zIndex: '2147483001'
      });
      document.body.appendChild(badge);
    }
  });
}
"""


class CaptureError(RuntimeError):
    pass


# Cache di processo per gli asset esterni (Bootstrap, Font Awesome, i font):
# le stesse cinque risorse servono a ogni schermata, e scaricarle una volta per
# scatto allungherebbe la cattura senza cambiarne il risultato.
_ASSET_CACHE: dict[str, tuple[int, str, bytes]] = {}

_BROWSER_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def _fetch_external(url: str) -> tuple[int, str, bytes]:
    """Scarica un asset esterno con Python invece che con il browser.

    Bootstrap, Font Awesome e i font arrivano da CDN: senza, le schermate
    mostrerebbero una pagina senza griglia e senza icone, cioe' un'app che non
    esiste. In molti ambienti di lavoro (container con proxy d'uscita, CI di
    rete chiusa) il browser non raggiunge quei domini mentre Python si', perche'
    rispetta le variabili `HTTP(S)_PROXY`. Il giro attraverso `urllib` rende la
    cattura indipendente dalla configurazione di rete del browser.

    Lo User-Agent e' quello di un browser perche' `fonts.googleapis.com`
    restituisce woff2 o ttf a seconda di chi chiede.
    """
    if url in _ASSET_CACHE:
        return _ASSET_CACHE[url]
    request = urllib.request.Request(url, headers={"User-Agent": _BROWSER_UA})
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = (
            response.status,
            response.headers.get("Content-Type", "application/octet-stream"),
            response.read(),
        )
    _ASSET_CACHE[url] = payload
    return payload


def _install_asset_proxy(context, base_url: str) -> None:
    def handler(route, request):
        if request.url.startswith(base_url):
            route.continue_()
            return
        try:
            status, content_type, body = _fetch_external(request.url)
        except (urllib.error.URLError, TimeoutError, OSError):
            # Una risorsa esterna irraggiungibile non deve far fallire lo
            # scatto: meglio una schermata con un'icona mancante che nessuna.
            route.abort()
            return
        route.fulfill(status=status, content_type=content_type, body=body)

    context.route("**/*", handler)


def load_manifest() -> dict:
    import yaml

    if not MANIFEST.exists():
        raise CaptureError(f"manifest mancante: {MANIFEST}")
    data = yaml.safe_load(MANIFEST.read_text(encoding="utf-8")) or {}
    shots = data.get("shots") or []
    if not shots:
        raise CaptureError("il manifest non contiene voci in `shots`")
    return data


def validate_manifest(data: dict) -> list[str]:
    """Controlli che si possono fare senza browser (usati anche dai test)."""
    problems: list[str] = []
    seen: set[str] = set()
    slug = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    for index, shot in enumerate(data.get("shots") or []):
        where = shot.get("id") or f"voce #{index + 1}"
        shot_id = shot.get("id")
        if not shot_id:
            problems.append(f"{where}: manca `id`")
        elif not slug.match(shot_id):
            problems.append(f"{where}: `id` deve essere in-minuscolo-con-trattini")
        elif shot_id in seen:
            problems.append(f"{where}: `id` duplicato")
        else:
            seen.add(shot_id)
        if not shot.get("route"):
            problems.append(f"{where}: manca `route`")
        if not shot.get("caption"):
            problems.append(f"{where}: manca `caption` (e' il testo alternativo)")
        for viewport in shot.get("viewports") or ["mobile"]:
            if viewport not in VIEWPORTS:
                problems.append(f"{where}: viewport sconosciuto «{viewport}»")
        role = shot.get("as", "anonimo")
        if role != "anonimo" and not isinstance(role, str):
            problems.append(f"{where}: `as` deve essere il nome utente o «anonimo»")
    return problems


def wait_for_app(base_url: str, timeout: float = 60.0) -> None:
    deadline = time.time() + timeout
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(base_url, timeout=5) as response:
                if response.status < 500:
                    return
        except Exception as exc:  # connessione rifiutata finche' non e' su
            last_error = exc
            time.sleep(1)
    raise CaptureError(f"app non raggiungibile su {base_url} ({last_error})")


def output_path(shot_id: str, viewport: str, locale: str) -> Path:
    suffix = "" if viewport == "mobile" else f"-{viewport}"
    return OUTPUT_DIR / locale / f"{shot_id}{suffix}.png"


def _launch_chromium(playwright):
    """Avvia Chromium, tollerando le installazioni fuori standard.

    Playwright cerca il browser in una cartella che dipende dalla sua versione:
    su una macchina dove il browser e' stato installato a parte (immagini CI,
    container preconfezionati) il lancio predefinito fallisce anche se un
    Chromium perfettamente valido c'e'. `CHROMIUM_PATH` permette di indicarlo.

    ⚠️ Vicolo cieco gia' percorso: i comandi che disegna **il browser** —
    il pulsante di `<input type=file>`, i selettori di data — non seguono il
    `locale` del contesto ma la lingua di avvio, e nella guida italiana escono
    in inglese («Choose File»). Non si risolve: l'avvio predefinito e'
    `chrome-headless-shell`, che porta un solo `.pak` di stringhe, quindi
    `--lang` non ha effetto; e il pacchetto completo (`channel="chromium"`),
    che i `.pak` li ha, non arriva mai a `networkidle` sulle pagine con lo
    script di Analytics — le catture vanno in timeout. Restano tre parole
    inglesi in una figura: e' il male minore.
    """
    override = os.environ.get("CHROMIUM_PATH")
    candidates = [override] if override else []
    candidates.append(None)  # percorso predefinito di Playwright
    candidates.append("/opt/pw-browsers/chromium")

    last_error: Exception | None = None
    for candidate in candidates:
        if candidate and not Path(candidate).exists():
            continue
        try:
            if candidate:
                return playwright.chromium.launch(executable_path=candidate)
            return playwright.chromium.launch()
        except Exception as exc:
            last_error = exc
    raise CaptureError(
        "Chromium non avviabile. Installa i browser di Playwright "
        f"(`playwright install chromium`) o esporta CHROMIUM_PATH. ({last_error})"
    )


def _shrink(path: Path) -> None:
    """Riduce il PNG a 256 colori.

    Le schermate sono interfaccia piatta: nessun gradiente, nessuna fotografia,
    poche decine di tinte reali (il design system lo impone). Una tavolozza di
    256 colori le rappresenta senza perdite visibili e pesa un terzo. Conta
    perche' queste immagini si rigenerano a ogni modifica dell'interfaccia:
    senza, ogni giro aggiungerebbe megabyte alla storia del repository.
    """
    try:
        from PIL import Image
    except ImportError:  # pragma: no cover - Pillow e' fra le dipendenze
        return
    with Image.open(path) as image:
        quantized = image.convert("RGB").quantize(colors=256, method=Image.MEDIANCUT)
        quantized.save(path, "PNG", optimize=True)


def capture_all(
    data: dict,
    base_url: str,
    only: list[str] | None,
    quiet: bool,
    locales: list[str],
) -> list[Path]:
    from playwright.sync_api import sync_playwright

    shots = data["shots"]
    if only:
        shots = [s for s in shots if s.get("id") in only]
        missing = set(only) - {s.get("id") for s in shots}
        if missing:
            raise CaptureError(
                f"id non presenti nel manifest: {', '.join(sorted(missing))}"
            )

    written: list[Path] = []

    with sync_playwright() as playwright:
        browser = _launch_chromium(playwright)
        try:
            for locale in locales:
                (OUTPUT_DIR / locale).mkdir(parents=True, exist_ok=True)
                for shot in shots:
                    for viewport in shot.get("viewports") or ["mobile"]:
                        path = _capture_one(browser, shot, viewport, base_url, locale)
                        _shrink(path)
                        written.append(path)
                        if not quiet:
                            print(f"  · {path.relative_to(REPO_ROOT)}")
        finally:
            browser.close()
    return written


def _capture_one(
    browser, shot: dict, viewport: str, base_url: str, locale: str
) -> Path:
    settings = VIEWPORTS[viewport]
    context = browser.new_context(
        viewport={"width": settings["width"], "height": settings["height"]},
        device_scale_factor=settings["device_scale_factor"],
        is_mobile=settings["is_mobile"],
        has_touch=settings["is_mobile"],
        locale=LOCALE_TAGS.get(locale, locale),
        timezone_id="Europe/Rome",
        # Il fuso influenza gli orari mostrati: senza fissarlo, due catture
        # dalla stessa macchina in stagioni diverse darebbero immagini diverse.
    )
    _install_asset_proxy(context, base_url)
    page = context.new_page()
    try:
        # La lingua dell'app la decide la sessione, non l'`Accept-Language` del
        # browser: senza questo passaggio le schermate uscirebbero tutte nella
        # lingua predefinita e la guida inglese mostrerebbe pulsanti italiani.
        page.goto(f"{base_url}/set_language/{locale}", wait_until="networkidle")

        role = shot.get("as", "anonimo")
        if role and role != "anonimo":
            page.goto(
                f"{base_url}/debug/login/{urllib.parse.quote(role)}",
                wait_until="networkidle",
            )
            if "/login" in page.url:
                raise CaptureError(
                    f"«{shot['id']}»: login come «{role}» fallito. "
                    "Serve DEBUG_MODE attivo e l'utente nel database dimostrativo."
                )

        # Se il login ci ha gia' portati dove volevamo, si resta li'.
        #
        # Non e' un risparmio: e' l'unico modo di fotografare la dashboard
        # **appena entrati**. Il riquadro «Come stai andando» (e la sua
        # variante «Come vanno le tue gare») si mostra una volta per sessione,
        # al primo ingresso dopo il login — e `/debug/login/<utente>` reindirizza
        # proprio alla dashboard, quindi era il redirect a consumare il turno.
        # La rinavigazione arrivava sempre seconda, e le catture della home non
        # hanno mai contenuto quel riquadro: le didascalie che lo descrivevano
        # promettevano una cosa che nell'immagine non c'era.
        destinazione = f"{base_url}{shot['route']}"
        if not _stessa_pagina(page.url, destinazione):
            page.goto(destinazione, wait_until="networkidle")
        page.add_style_tag(content=HIDE_CSS)
        if shot.get("full_page") or shot.get("clip"):
            page.add_style_tag(content=OVERLAY_CSS)

        for selector in shot.get("click") or []:
            # Click via JS invece di `page.click`: i comandi che ci interessano
            # sono linguette sotto una testata appiccicata, e il controllo di
            # "elemento stabile e visibile" di Playwright ci litiga — a volte
            # passa, a volte no, e una cattura che riesce a giorni alterni e'
            # peggio di una che fallisce sempre. Qui basta che il gestore parta.
            clicked = page.evaluate(
                """(sel) => {
                    const el = document.querySelector(sel);
                    if (!el) return false;
                    el.click();
                    return true;
                }""",
                selector,
            )
            if not clicked:
                raise CaptureError(
                    f"«{shot['id']}»: selettore `click` non trovato: {selector}"
                )
            page.wait_for_timeout(500)

        for selector in shot.get("tap") or []:
            # Un tocco **vero**, con i suoi eventi di puntatore, e non il
            # `click()` del DOM qui sopra: il panno dell'allenamento ascolta
            # `pointerdown` — gli serve sapere *dove* si è toccato, che un
            # `el.click()` non dice — e con l'altra strada non succederebbe
            # niente, in silenzio. Playwright tocca il centro dell'elemento,
            # quindi il selettore va scelto per il suo centro: `.c7-cloth__rings`
            # è il bersaglio, e il suo centro è il centro del bersaglio.
            if page.query_selector(selector) is None:
                raise CaptureError(
                    f"«{shot['id']}»: selettore `tap` non trovato: {selector}"
                )
            page.click(selector)
            page.wait_for_timeout(500)

        # I comandi che esistono **grazie** al tocco: il riquadro bersaglio
        # nasce toccando il panno, e solo dopo si può spuntare «Vale per il
        # punteggio». Un `click` normale arriverebbe prima, su un elemento che
        # ancora non c'è — e fallirebbe la cattura invece di dirlo.
        for selector in shot.get("click_after_tap") or []:
            clicked = page.evaluate(
                """(sel) => {
                    const el = document.querySelector(sel);
                    if (!el) return false;
                    el.click();
                    return true;
                }""",
                selector,
            )
            if not clicked:
                raise CaptureError(
                    f"«{shot['id']}»: selettore `click_after_tap` non trovato: "
                    f"{selector}"
                )
            page.wait_for_timeout(300)

        if shot.get("wait_for"):
            page.wait_for_selector(shot["wait_for"], timeout=10_000)
        page.wait_for_timeout(int(shot.get("settle_ms", 600)))

        annotations = shot.get("annotate") or []
        if annotations:
            page.evaluate(ANNOTATE_JS, annotations)

        path = output_path(shot["id"], viewport, locale)
        target = shot.get("clip")
        if target:
            element = page.query_selector(target)
            if element is None:
                raise CaptureError(
                    f"«{shot['id']}»: selettore `clip` non trovato: {target}"
                )
            element.screenshot(path=str(path))
        else:
            page.screenshot(
                path=str(path), full_page=bool(shot.get("full_page", False))
            )
        return path
    finally:
        context.close()


def _stessa_pagina(corrente: str, voluta: str) -> bool:
    """Se due indirizzi puntano alla stessa pagina, ignorando coda e barra finale.

    Serve a capire se il redirect del login ci ha gia' portati a destinazione.
    Il confronto e' sul solo percorso: la query string non compare mai nelle
    rotte del manifest, e la barra finale la mette o la toglie Flask a seconda
    della regola.
    """
    da_pulire = (corrente or "", voluta or "")
    percorsi = [urllib.parse.urlsplit(u).path.rstrip("/") or "/" for u in da_pulire]
    return percorsi[0] == percorsi[1]


def serve_app(base_url: str) -> subprocess.Popen:
    """Avvia l'app dimostrativa, dopo essersi assicurato che la porta sia libera.

    Il controllo non e' pignoleria. `--serve` avvia `app.py`, che se la porta e'
    gia' occupata muore in silenzio (lo stdout va nel nulla) — e la cattura
    prosegue fotografando **l'app che stava li' prima**, con il suo database.
    Il risultato non e' un errore: sono immagini verosimili e sbagliate, cioe'
    esattamente cio' che questa guida deve evitare. Con l'app di sviluppo
    aperta sulla stessa porta e' successo davvero.
    """
    port = int(os.environ.get("PORT", "5001"))
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        if probe.connect_ex(("127.0.0.1", port)) == 0:
            raise CaptureError(
                f"la porta {port} e' gia' occupata: `--serve` avvierebbe l'app "
                f"dimostrativa a vuoto e le schermate verrebbero da quella gia' "
                f"in ascolto, con il suo database. Chiudi l'altra app, oppure "
                f"usa un'altra porta:\n"
                f"    PORT=5099 python scripts/help_docs/capture_screenshots.py "
                f"--serve --base-url http://127.0.0.1:5099"
            )
    env = dict(os.environ, DEBUG_MODE="true", FLASK_ENV="development")
    return subprocess.Popen(
        [sys.executable, "app.py"],
        cwd=str(REPO_ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:5001")
    parser.add_argument("--only", nargs="*", help="cattura solo questi id")
    parser.add_argument(
        "--serve", action="store_true", help="avvia l'app e la chiude a fine cattura"
    )
    parser.add_argument(
        "--check", action="store_true", help="valida il manifest senza catturare"
    )
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument(
        "--lang",
        nargs="*",
        help="lingue da catturare (predefinito: quelle dichiarate nel manifest)",
    )
    parser.add_argument(
        "--json", action="store_true", help="stampa l'elenco dei file scritti in JSON"
    )
    args = parser.parse_args()

    try:
        data = load_manifest()
    except CaptureError as exc:
        print(f"ERRORE: {exc}", file=sys.stderr)
        return 2

    problems = validate_manifest(data)
    if problems:
        print("Manifest non valido:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 2

    locales = args.lang or data.get("locales") or DEFAULT_LOCALES
    if args.check:
        print(
            f"Manifest valido: {len(data['shots'])} schermate × "
            f"{len(locales)} lingue ({', '.join(locales)})."
        )
        return 0

    server = serve_app(args.base_url) if args.serve else None
    try:
        wait_for_app(args.base_url)
        written = capture_all(data, args.base_url, args.only, args.quiet, locales)
    except CaptureError as exc:
        print(f"ERRORE: {exc}", file=sys.stderr)
        return 1
    finally:
        if server:
            server.terminate()
            server.wait(timeout=15)

    if args.json:
        print(json.dumps([str(p.relative_to(REPO_ROOT)) for p in written], indent=2))
    elif not args.quiet:
        print(
            f"\n{len(written)} immagini scritte in {OUTPUT_DIR.relative_to(REPO_ROOT)}/"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
