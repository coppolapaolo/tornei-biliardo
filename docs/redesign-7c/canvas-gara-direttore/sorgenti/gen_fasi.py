#!/usr/bin/env python3
"""Canvas «Pagina gara del direttore» — le fasi, schermata per schermata.

Cinque pagine di canvas, una per fase del ciclo di vita della gara
(preparazione → iscrizioni → gioco → spareggio → conclusione), piu' la
pagina delle tre direzioni proposte al primo giro.

Ogni schermata mostra **comandi che esistono davvero**: le etichette e le
condizioni vengono da templates/components/_gara_management.html,
_round_management.html, _gara_tables_config.html, _gara_inscriptions.html,
_match_admin_controls.html, _ssr_section.html e admin/gara_vetrina.html.
Dove il mockup propone qualcosa che l'app non fa ancora, lo dice il
bigliettino accanto all'artboard.

Riusa il kit (token, guscio, card) di gen_gara_direttore.py.
"""

import json
import pathlib

import gen_gara_direttore as base
from gen_gara_direttore import I, desktop, doc, ico, phone, vtabs

SRC = pathlib.Path(__file__).resolve().parent

# --------------------------------------------------------------------------
# Mattoni comuni alle schermate di fase
# --------------------------------------------------------------------------


def band(kicker, titolo, corpo="", azione=""):
    """La fascia scura in cima: dove siamo, e l'unica cosa da fare adesso."""
    return f"""
      <section class="card card--accent">
        <div class="kicker">{kicker}</div>
        <h3 style="margin-top:5px;font-size:19px">{titolo}</h3>
        {corpo}
        {azione}
      </section>
"""


def progress(fatto, totale, testo, pct):
    return f"""
        <div class="row" style="margin-top:12px;gap:10px">
          <div class="num" style="font-size:13px;color:var(--c7-accent-bright)">{fatto}/{totale}</div>
          <div class="bar grow"><div class="bar__fill" style="width:{pct}%"></div></div>
        </div>
        <div style="margin-top:8px;font-size:12px;font-weight:700;color:var(--c7-accent-dim)">{testo}</div>
"""


def sec(titolo, more=""):
    more_html = f'<span class="sechead__more">{more}</span>' if more else ""
    return f'<div class="sechead"><h3>{titolo}</h3>{more_html}</div>'


def rows(inner):
    return f'<div class="rows">{inner}</div>'


def row(icona, titolo, sub="", right="", tone="neutral"):
    tile = {"neutral": "tile tile--neutral", "ok": "tile tile--ok",
            "warn": "tile tile--warn", "locked": "tile tile--locked",
            "accent": "tile"}[tone]
    sub_html = f'<div class="rows__sub">{sub}</div>' if sub else ""
    right_html = right or f'<span class="faint">{ico(I["chevron"], 15)}</span>'
    return f"""
        <div class="rows__row">
          <div class="{tile} tile--sm">{ico(icona, 16)}</div>
          <div class="grow">
            <div class="rows__title">{titolo}</div>
            {sub_html}
          </div>
          {right_html}
        </div>"""


def person(sigla, nome, sub, right=""):
    right_html = right or ""
    return f"""
        <div class="rows__row">
          <div class="avatar">{sigla}</div>
          <div class="grow">
            <div class="rows__title">{nome}</div>
            <div class="rows__sub">{sub}</div>
          </div>
          {right_html}
        </div>"""


def field(label, valore, hint="", mono=False):
    cls = "num" if mono else ""
    hint_html = (f'<div style="margin-top:6px;font-size:12px;font-weight:600;'
                 f'color:var(--c7-ink-muted);line-height:1.4">{hint}</div>' if hint else "")
    return f"""
        <div>
          <div class="label" style="margin-bottom:8px">{label}</div>
          <div class="{cls}" style="height:58px;border-radius:var(--c7-r-field);
               background:var(--c7-bg);padding:0 16px;display:flex;align-items:center;
               font-size:15px;font-weight:700">{valore}</div>
          {hint_html}
        </div>"""


def toggle(label, acceso, hint=""):
    knob_x = "22px" if acceso else "2px"
    track = "var(--c7-ok)" if acceso else "var(--c7-line)"
    hint_html = (f'<div style="margin-top:6px;font-size:12px;font-weight:600;'
                 f'color:var(--c7-ink-muted);line-height:1.4">{hint}</div>' if hint else "")
    return f"""
        <div>
          <div class="row" style="gap:12px">
            <div class="grow" style="font-size:14px;font-weight:700">{label}</div>
            <div style="width:46px;height:26px;border-radius:999px;background:{track};
                 position:relative;flex-shrink:0">
              <div style="position:absolute;top:2px;left:{knob_x};width:22px;height:22px;
                   border-radius:50%;background:#fff"></div>
            </div>
          </div>
          {hint_html}
        </div>"""


def sheet(titolo, corpo, azione, sottotitolo=""):
    """Foglio modale ancorato in fondo: nell'app sono i modal Bootstrap."""
    sub = (f'<div style="font-size:13px;font-weight:600;color:var(--c7-ink-muted);'
           f'line-height:1.45">{sottotitolo}</div>' if sottotitolo else "")
    return f"""
  <div style="position:absolute;inset:0;background:rgba(27,33,36,.5)"></div>
  <div style="position:absolute;left:0;right:0;bottom:0;background:var(--c7-card);
       border-radius:26px 26px 0 0;padding:14px 18px 24px;display:flex;
       flex-direction:column;gap:14px">
    <div style="width:44px;height:4px;border-radius:999px;background:var(--c7-line);
         margin:0 auto"></div>
    <h3>{titolo}</h3>
    {sub}
    {corpo}
    {azione}
  </div>
"""


def btn(label, kind="primary", icona=None, w=True):
    ic = f"{ico(I[icona], 16)} " if icona else ""
    width = " btn--w" if w else ""
    return f'<button class="btn btn--{kind}{width}">{ic}{label}</button>'


def tavolo_chip(n, stato, occupato_da=""):
    """Tessera tavolo: libero, occupato, scelto."""
    if stato == "occupato":
        style = "background:var(--c7-accent);color:var(--c7-accent-ink)"
        sub = f'<div style="font-size:10px;font-weight:700;color:var(--c7-accent-dim)">{occupato_da}</div>'
    elif stato == "scelto":
        style = "background:var(--c7-ink);color:#fff"
        sub = f'<div style="font-size:10px;font-weight:700;color:var(--c7-on-ink-muted)">{occupato_da}</div>'
    elif stato == "spento":
        style = "background:var(--c7-sunken);color:var(--c7-ink-faint)"
        sub = f'<div style="font-size:10px;font-weight:700">{occupato_da or "non usato"}</div>'
    else:
        style = "background:var(--c7-bg);color:var(--c7-ink)"
        sub = f'<div class="muted" style="font-size:10px;font-weight:700">{occupato_da or "libero"}</div>'
    return f"""
          <div style="border-radius:var(--c7-r-control);padding:12px 8px;text-align:center;{style}">
            <div class="num" style="font-size:19px;font-weight:800">{n}</div>
            {sub}
          </div>"""


def stepper(nome, valore):
    return base.score_side(nome, valore)


def classifica(righe, header=True):
    head = ("""
        <div class="rows__row" style="padding-top:11px;padding-bottom:11px">
          <div style="width:20px"></div>
          <div class="grow label" style="margin:0">Giocatore</div>
          <div class="label" style="margin:0">Vinte</div>
          <div class="label" style="margin:0;width:34px;text-align:right">Diff</div>
        </div>""" if header else "")
    body = ""
    for pos, nome, vinte, diff, extra in righe:
        sigla = (nome[0] + nome[2]).upper()
        badge = f'<span class="state state--warn">{extra}</span>' if extra else ""
        body += f"""
        <div class="rows__row">
          <div class="num" style="width:20px;font-size:15px;font-weight:800">{pos}</div>
          <div class="avatar">{sigla}</div>
          <div class="grow"><div class="rows__title">{nome}</div></div>
          {badge}
          <div class="num" style="font-size:15px;font-weight:800">{vinte}</div>
          <div class="num muted" style="width:34px;text-align:right;font-size:13px">{diff}</div>
        </div>"""
    return rows(head + body)


TABS_SETUP = vtabs(["Gestione", "Iscritti"], "Gestione")
TABS_ISCR = vtabs(["Gestione", "Iscritti"], "Gestione")
TABS_ISCR2 = vtabs(["Gestione", "Iscritti"], "Iscritti")
TABS_GIOCO = vtabs(["Turni", "Classifica", "Iscritti", "Gestione"], "Turni")
TABS_CLASS = vtabs(["Turni", "Classifica", "Iscritti", "Gestione"], "Classifica")
TABS_GEST = vtabs(["Turni", "Classifica", "Iscritti", "Gestione"], "Gestione")

SUB = "Biliardo Mimmo &middot; Al 5"
CURSORE = '%s<span class="faint">|</span>' 


# ==========================================================================
# FASE 1 — PREPARAZIONE (gara.status = setup)
# ==========================================================================

def setup_panoramica():
    corpo = ("""
        <div style="margin-top:10px;font-size:13px;font-weight:600;
             color:var(--c7-accent-dim);line-height:1.45">
          Quando apri le iscrizioni la gara diventa pubblica e chi &egrave; in
          zona riceve la notifica.</div>""")
    azione = ('<div style="margin-top:14px">'
              + btn("Apri iscrizioni", "success", "play") + "</div>")
    content = f"""
      {band("In preparazione", "Nessuno vede ancora la gara", corpo, azione)}

      {sec("Da preparare", "3 di 4")}
      {rows(
        row(I["list"], "Turni e distanze", "4 turni &middot; Palla 8 &middot; al 5", tone="ok")
        + row(I["users"], "Direzione di gara", "solo tu &mdash; aggiungi un co-direttore", tone="ok")
        + row(I["table"], "Tavoli", "4 nella sala &middot; tutti in uso", tone="ok")
        + row(I["target"], "Esercizi fra i turni", "nessuno &mdash; facoltativo", tone="neutral")
        + row(I["share"], "Vetrina", "nessuna locandina", tone="warn"))}

      {sec("Impostazioni di gioco")}
      {rows(
        row(I["grid"], "Accoppiamento", "Amalfi &middot; anti-reincontro attivo", tone="neutral")
        + row(I["scale"], "Chi riposa", "X a tavolino all'ultimo iscritto", tone="neutral")
        + row(I["crown"], "Apertura", "acchito &mdash; chi vince sceglie", tone="neutral"))}
"""
    return doc(phone(SUB, TABS_SETUP, content))


def setup_turni():
    def turno(n, disc, dist, override=False):
        cls = "card card--warn" if override else "card"
        pill = ('<span class="state state--warn">modificato</span>' if override
                else '<span class="state state--muted">default</span>')
        return f"""
      <article class="{cls}">
        <div class="row">
          <strong class="grow" style="font-size:14px">Turno {n}</strong>
          {pill}
          <button class="iconbtn">{ico(I["rotate"], 14)}</button>
        </div>
        <div style="margin-top:12px;display:grid;grid-template-columns:1fr 96px;gap:10px">
          {field("Disciplina", disc)}
          {field("Triangoli", dist, mono=True)}
        </div>
      </article>"""

    content = f"""
      {sec("Configurazione turni", "Ripristina")}
      <div style="font-size:13px;font-weight:600;color:var(--c7-ink-muted);line-height:1.45">
        Disciplina e distanza diverse per ciascun turno. Si modificano fino
        all'apertura delle iscrizioni.
      </div>
      <section class="card card--sunk" style="display:grid;
               grid-template-columns:1fr 1fr;gap:14px 10px">
        <div><div class="kicker">Strategia</div>
          <div style="margin-top:2px;font-size:14px;font-weight:800">Amalfi</div></div>
        <div><div class="kicker">Turni</div>
          <div class="num" style="margin-top:2px;font-size:14px">4</div></div>
        <div><div class="kicker">Anti-reincontro</div>
          <div style="margin-top:2px;font-size:14px;font-weight:800;color:var(--c7-ok)">Attivo</div></div>
        <div><div class="kicker">Dispari</div>
          <div style="margin-top:2px;font-size:14px;font-weight:800">X a tavolino</div></div>
      </section>
      {turno(1, "Palla 8", "5")}
      {turno(2, "Palla 9", "3", override=True)}
      {turno(3, "Palla 8", "5")}
      {_nav(0)}
"""
    return doc(phone(SUB, TABS_SETUP, content))




def setup_direttori():
    content = f"""
      {sec("Direzione di gara")}
      {rows(
        person("PA", "pa", "direttore &middot; sei tu",
               '<span class="state state--accent">titolare</span>')
        + person("MB", "m.bruni", "co-direttore &middot; Biliardo Mimmo",
                 f'<button class="iconbtn">{ico(I["minus"], 14)}</button>'))}

      {sec("Aggiungi un co-direttore")}
      <section class="card">
        {field("Cerca fra i direttori della zona", CURSORE % "bru")}
        <div style="margin-top:12px" class="stack">
          {person("GD", "g.donati", "direttore &middot; Biliardo Centrale &middot; 4 km",
                  '<button class="btn btn--secondary btn--sm">Aggiungi</button>')}
          {person("RS", "r.sanna", "direttore &middot; Sala Nuova &middot; 11 km",
                  '<button class="btn btn--secondary btn--sm">Aggiungi</button>')}
        </div>
        <div style="margin-top:12px;font-size:12px;font-weight:600;
             color:var(--c7-ink-muted);line-height:1.45">
          Solo utenti con ruolo direttore vicini alla sede della gara.
          Un co-direttore pu&ograve; fare tutto quello che fai tu, tranne
          togliere te dalla direzione.
        </div>
      </section>
      {_nav(3)}
"""
    return doc(phone(SUB, TABS_SETUP, content))


def setup_vetrina():
    content = f"""
      {sec("Vetrina", "Anteprima")}
      <section class="card">
        <div style="aspect-ratio:16/9;border-radius:var(--c7-r-field);
             background:var(--c7-sunken);display:grid;place-items:center;
             color:var(--c7-ink-faint)">
          <div style="text-align:center">
            {ico(I["share"], 26)}
            <div style="margin-top:8px;font-size:12px;font-weight:700">Nessuna locandina</div>
          </div>
        </div>
        <div style="margin-top:12px">{btn("Carica la locandina", "secondary", "plus")}</div>
        <div style="margin-top:8px;font-size:12px;font-weight:600;color:var(--c7-ink-muted)">
          PNG o JPG. Si vede intera, senza ritagli.
        </div>
      </section>

      <section class="card stack">
        {field("Indirizzo pubblico", "torneibiliardo.it/g/<strong>gara-3-giovedi</strong>")}
        {field("Link esterno (facoltativo)", "regolamento.pdf")}
        {field("Etichetta del link", "Regolamento")}
      </section>

      <div style="display:flex;gap:10px">
        {btn("Copia il link", "secondary", "link")}
        {btn("Salva", "primary", "check")}
      </div>
      {_nav(4)}
"""
    return doc(phone(SUB, TABS_SETUP, content))


def setup_apri():
    corpo = f"""
    <div class="stack">
      {field("Le iscrizioni aprono", "oggi, 18:00", "Nel tuo fuso orario.", mono=True)}
      {field("Le iscrizioni chiudono", "gio 3 set, 19:30", mono=True)}
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
        {field("Minimo", "8", mono=True)}
        {field("Massimo", "16", mono=True)}
      </div>
    </div>"""
    azione = f"""
    <div class="stack">
      {btn("Apri le iscrizioni", "success", "play")}
      <div style="font-size:12px;font-weight:600;color:var(--c7-ink-muted);
           text-align:center;line-height:1.45">
        Da qui la gara &egrave; pubblica: compare nell'elenco e chi &egrave;
        in zona riceve la notifica.
      </div>
    </div>"""
    content = f"""
      {band("In preparazione", "Tutto pronto")}
      {sec("Da preparare", "5 di 5")}
      {rows(row(I["list"], "Turni e distanze", "4 turni", tone="ok")
            + row(I["share"], "Vetrina", "locandina caricata", tone="ok"))}
"""
    return doc(phone(SUB, TABS_SETUP, content,
                     overlay=sheet("Apri le iscrizioni", corpo, azione)))


def _turno_card_desk(n, disc, dist, override=False):
    return f"""
              <div class="card--sunk" style="border-radius:var(--c7-r-card);padding:14px">
                <div class="row"><strong class="grow" style="font-size:14px;white-space:nowrap">Turno {n}</strong>
                  <span class="state state--{"warn" if override else "muted"}">{"modificato" if override else "default"}</span>
                  <button class="iconbtn">{ico(I["rotate"], 14)}</button></div>
                <div style="margin-top:10px;display:grid;grid-template-columns:1fr 92px;gap:10px">
                  {field("Disciplina", disc)}
                  {field("Triangoli", dist, mono=True)}
                </div>
              </div>"""


TURNI = [(1, "Palla 8", "5", False), (2, "Palla 9", "3", True),
         (3, "Palla 8", "5", False), (4, "Palla 8", "5", False)]


def _desktop_alto(actions, content, h):
    """Il guscio desktop con una pagina piu' alta di 900: la colonna
    laterale si allunga, il contenuto non si taglia."""
    return doc(desktop(actions, content)
               .replace('<div class="app">', f'<div class="app" style="height:{h}px">')
               .replace('<div class="dcontent">', '<div class="dcontent" style="overflow:visible">'))


def setup_desktop():
    """La preparazione su desktop e' una pagina sola che scorre: turni in
    sintesi (la pagina 1.10 si apre da «Modifica»), direzione di gara con
    la ricerca aperta in linea, tavoli, vetrina. La colonna destra e' la
    lista di cosa manca: ogni riga porta alla sua sezione."""
    def riga_tavolo(nome, nota):
        return f"""
            <div class="rows__row" style="gap:10px">
              <span class="faint">{ICO_DRAG}</span>
              <div class="num" style="width:110px;height:44px;border-radius:var(--c7-r-control);
                   background:var(--c7-bg);padding:0 14px;display:flex;align-items:center;
                   font-size:15px;font-weight:800">{nome}</div>
              <span class="rows__sub grow" style="margin:0">{nota}</span>
              <button class="iconbtn">{ICO_X}</button>
            </div>"""
    sinistra = f"""
        <div class="stack" style="gap:18px">
          {_band_desktop("In preparazione", "Nessuno vede ancora la gara",
                         "Resta da fare la vetrina. Quando apri le iscrizioni la gara diventa pubblica "
                         "e chi &egrave; in zona riceve la notifica.",
                         f'<button class="btn btn--success">{ico(I["play"], 16)} Apri iscrizioni</button>')}

          <div>
            {sec("Turni e distanze", "Modifica turni ed esercizi")}
            <section class="card" style="margin-top:12px">
              <div style="display:grid;grid-template-columns:repeat(4, minmax(0, 1fr));gap:12px">
                {"".join(f'''
                <div class="card--sunk" style="border-radius:var(--c7-r-control);padding:12px 14px">
                  <div class="row"><strong class="grow" style="font-size:13px">Turno {n}</strong>
                    <span class="state state--{"warn" if ov else "muted"}">{"modificato" if ov else "default"}</span></div>
                  <div style="margin-top:8px;font-size:15px;font-weight:800">{d} <span class="muted">&middot;</span> al <span class="num">{t}</span></div>
                </div>''' for n, d, t, ov in TURNI)}
              </div>
              <div class="row" style="margin-top:12px;gap:12px">
                <div class="tile tile--sm tile--neutral">{ico(I["target"], 16)}</div>
                <div class="grow">
                  <div class="rows__title">Esercizi fra i turni</div>
                  <div class="rows__sub">Stop shot dopo il turno 2 &middot; 2 tentativi &middot; classifica a parte</div>
                </div>
              </div>
            </section>
          </div>

          <div>
            {sec("Direzione di gara")}
            <section class="card" style="margin-top:12px;padding:0;overflow:hidden">
              <div class="rows" style="border-radius:0">
                {person("PA", "pa", "direttore &middot; sei tu",
                        '<span class="state state--accent">titolare</span>')}
                {person("MB", "m.bruni", "co-direttore &middot; Biliardo Mimmo",
                        f'<button class="iconbtn">{ico(I["minus"], 14)}</button>')}
              </div>
              <div style="padding:16px;border-top:1px solid var(--c7-line-soft)">
                {field("Aggiungi un co-direttore", CURSORE % "bru", "Solo utenti con ruolo direttore vicini alla sede. Un co-direttore pu&ograve; fare tutto quello che fai tu, tranne togliere te.")}
                <div class="rows" style="margin-top:12px">
                  {person("GD", "g.donati", "direttore &middot; Biliardo Centrale &middot; 4 km",
                          '<button class="btn btn--secondary btn--sm">Aggiungi</button>')}
                  {person("RS", "r.sanna", "direttore &middot; Sala Nuova &middot; 11 km",
                          '<button class="btn btn--secondary btn--sm">Aggiungi</button>')}
                </div>
              </div>
            </section>
          </div>

          <div>
            {sec("Tavoli", "3 su 6 della sala")}
            <section class="card" style="margin-top:12px">
              <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;align-items:start">
                <div class="rows" style="background:var(--c7-card);border:1px solid var(--c7-line-soft)">
                  {riga_tavolo("3", "1&deg; &middot; alla partita di cartello")}
                  {riga_tavolo("1", "2&deg;")}
                  {riga_tavolo("2", "3&deg;")}
                </div>
                <div class="stack">
                  <div>
                    <div class="label" style="margin-bottom:8px">Altri tavoli della sala</div>
                    <div style="display:flex;flex-wrap:wrap;gap:8px">
                      {chip_tavolo("4")}{chip_tavolo("5")}{chip_tavolo("6")}
                      <button class="pill" style="height:44px;gap:6px">{ico(I["plus"], 14)} Un altro nome</button>
                    </div>
                  </div>
                  {toggle("Assegna in base alla classifica", False,
                          "Dal secondo turno il primo tavolo va alla partita con il giocatore meglio piazzato. Solo con accoppiamento casuale.")}
                  <div style="font-size:12px;font-weight:600;color:var(--c7-ink-muted);line-height:1.45">
                    Dall'alto in basso &egrave; l'ordine di assegnazione. Si cambiano anche a iscrizioni
                    chiuse e fra un turno e l'altro.</div>
                </div>
              </div>
            </section>
          </div>

          <div>
            {sec("Vetrina", "Anteprima della pagina pubblica")}
            <section class="card" style="margin-top:12px">
              <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;align-items:start">
                <div>
                  <div style="aspect-ratio:1200/630;border-radius:var(--c7-r-field);background:var(--c7-sunken);
                       display:grid;place-items:center;color:var(--c7-ink-faint)">
                    <div style="text-align:center">{ico(I["share"], 26)}
                      <div style="margin-top:8px;font-size:12px;font-weight:700">Nessuna locandina &middot; 1200&times;630</div></div>
                  </div>
                  <div style="margin-top:12px">{btn("Carica la locandina", "secondary", "plus")}</div>
                </div>
                <div class="stack">
                  {field("Indirizzo pubblico", "torneibiliardo.it/g/<strong>gara-3-giovedi</strong>")}
                  {field("Link esterno (facoltativo)", "regolamento.pdf")}
                  {field("Etichetta del link", "Regolamento")}
                  <div style="display:flex;gap:10px">
                    {btn("Copia il link", "secondary", "link", w=False)}
                    {btn("Salva", "primary", "check", w=False)}
                  </div>
                </div>
              </div>
            </section>
          </div>
        </div>
"""
    destra = f"""
        <div class="stack">
          {sec("Da preparare", "3 di 5")}
          {rows(
            row(I["list"], "Turni e distanze", "4 turni &middot; Palla 8 al 5 &middot; turno 2 al 3", tone="ok")
            + row(I["target"], "Esercizi fra i turni", "1 &middot; Stop shot dopo il turno 2", tone="ok")
            + row(I["users"], "Direzione di gara", "tu e m.bruni", tone="ok")
            + row(I["table"], "Tavoli", "3, 1, 2 &middot; 6 nella sala", tone="ok")
            + row(I["share"], "Vetrina", "nessuna locandina", tone="warn"))}
          <div style="font-size:12px;font-weight:600;color:var(--c7-ink-muted);line-height:1.45">
            Ogni riga porta alla sua sezione, qui sotto. Turni ed esercizi aprono la loro pagina.
          </div>

          {sec("Informazioni gara", "Modifica")}
          <section class="card">
            <div style="display:grid;grid-template-columns:auto 1fr;gap:9px 16px;font-size:13px">
              <span class="muted">Sala</span><span style="font-weight:800">Biliardo Mimmo</span>
              <span class="muted">Data</span><span class="num">gio 3 set 2026, 20:00</span>
              <span class="muted">Accoppiamento</span><span style="font-weight:800">Amalfi</span>
              <span class="muted">Partecipanti</span><span class="num">8&ndash;16</span>
              <span class="muted">Chi riposa</span><span style="font-weight:800">Ultimo iscritto</span>
              <span class="muted">Apertura</span><span style="font-weight:800">acchito, chi vince sceglie</span>
            </div>
          </section>
        </div>
"""
    content = f'<div class="cols" style="align-items:start">{sinistra}{destra}</div>'
    actions = ('<button class="btn btn--secondary btn--sm">'
               f'{ico(I["gear"], 15)} Modifica gara</button>')
    return _desktop_alto(actions, content, ALTEZZE["SetupDesktop"])


def setup_turni_desktop():
    """La pagina «Turni e distanze» su desktop, aperta da 1.9: i quattro
    turni (ADR-027) e, sotto, gli esercizi fra i turni con il modulo di
    aggiunta in linea (i tre campi di _challenge_management_modal.html)."""
    sinistra = f"""
        <div class="stack" style="gap:18px">
          <div>
            {sec("Configurazione turni", "Ripristina i default")}
            <section class="card" style="margin-top:12px">
              <div style="display:grid;grid-template-columns:repeat(2, minmax(0, 1fr));gap:12px">
                {"".join(_turno_card_desk(*t) for t in TURNI)}
              </div>
            </section>
          </div>
          <div>
            {sec("Esercizi fra i turni", "1")}
            <div class="rows" style="margin-top:12px">
              {row(I["target"], "Stop shot", "dopo il turno 2 &middot; 2 tentativi &middot; punteggio 0&ndash;10", tone="accent",
                   right=f'<button class="iconbtn">{ICO_X}</button>')}
            </div>
            <section class="card" style="margin-top:12px">
              <div class="label" style="margin-bottom:12px">Aggiungi un esercizio</div>
              <div style="display:grid;grid-template-columns:1fr 150px 120px auto;gap:12px;align-items:end">
                {field("Esercizio", CURSORE % "tiro")}
                {field("Dopo il turno", '3 <span class="faint" style="margin-left:auto">&#9662;</span>')}
                {field("Tentativi", "2", mono=True)}
                {btn("Aggiungi", "primary", "plus", w=False)}
              </div>
              <div class="rows" style="margin-top:12px">
                {person("TL", "Tiro lungo in sponda", "s&igrave;/no &middot; 30 hanno provato",
                        '<span class="state state--accent">scelto</span>')}
              </div>
            </section>
          </div>
        </div>
"""
    destra = f"""
        <div class="stack">
          {sec("Come si gioca")}
          <section class="card" style="display:grid;grid-template-columns:1fr 1fr;gap:14px 10px">
            <div><div class="kicker">Strategia</div>
              <div style="margin-top:2px;font-size:14px;font-weight:800">Amalfi</div></div>
            <div><div class="kicker">Turni</div>
              <div class="num" style="margin-top:2px;font-size:14px">4</div></div>
            <div><div class="kicker">Anti-reincontro</div>
              <div style="margin-top:2px;font-size:14px;font-weight:800;color:var(--c7-ok)">Attivo</div></div>
            <div><div class="kicker">Dispari</div>
              <div style="margin-top:2px;font-size:14px;font-weight:800">X a tavolino</div></div>
          </section>
          <div style="font-size:12px;font-weight:600;color:var(--c7-ink-muted);line-height:1.45">
            Disciplina e distanza diverse per ciascun turno; si modificano fino
            all'apertura delle iscrizioni. Gli esercizi si giocano dopo il turno
            indicato, mentre gli altri finiscono, e fanno una classifica a parte.
          </div>
          {btn("Salva", "primary", "check")}
        </div>
"""
    actions = (f'<button class="btn btn--secondary btn--sm">{ico(I["back"], 14)} Preparazione</button>')
    return doc(desktop(actions, f'<div class="cols">{sinistra}{destra}</div>'))


def iscr_panoramica():
    corpo = progress(7, 16, "Servono almeno 8 iscritti &middot; chiudono gioved&igrave; 19:30", 44)
    azione = f"""
        <div class="row" style="margin-top:14px;gap:10px">
          <div class="grow" style="font-size:12px;font-weight:700;color:var(--c7-accent-dim)">
            Manca 1 iscritto</div>
          <button class="btn btn--locked btn--sm">Avvia la gara</button>
        </div>"""
    content = f"""
      {band("Iscrizioni aperte", "7 iscritti su 16", corpo, azione)}

      {sec("Condividi")}
      <section class="card">
        <div class="num" style="background:var(--c7-sunken);border-radius:var(--c7-r-field);
             padding:14px 16px;font-size:13px;font-weight:700;word-break:break-all;
             color:var(--c7-ink-soft)">torneibiliardo.it/g/gara-3-giovedi</div>
        <div style="margin-top:10px;display:flex;gap:10px">
          {btn("Copia", "secondary", "link")}
          {btn("Condividi", "primary", "share")}
        </div>
      </section>

      {sec("Da tenere d'occhio", "2")}
      {rows(
        row(I["table"], "Tavoli", "4 nella sala, tutti in uso &mdash; cambia prima di avviare", tone="neutral")
        + row(I["users"], "1 in lista d'attesa", "entra se qualcuno si ritira", tone="warn"))}
"""
    return doc(phone(SUB, TABS_ISCR, content))






def iscr_scadute():
    corpo = ("""
        <div style="margin-top:10px;font-size:13px;font-weight:600;
             color:var(--c7-accent-dim);line-height:1.45">
          Sono arrivati 6 iscritti sui 8 che servono. Puoi allungare i tempi
          o annullare la gara: in entrambi i casi gli iscritti ricevono la notifica.</div>""")
    content = f"""
      {band("Iscrizioni scadute", "Chiuse gioved&igrave; alle 19:30", corpo)}

      {sec("Cosa puoi fare")}
      <section class="card stack">
        {btn("Estendi le iscrizioni", "primary", "clock")}
        <div style="font-size:12px;font-weight:600;color:var(--c7-ink-muted);line-height:1.45">
          Sposta la scadenza e riapre la pagina pubblica.
        </div>
        <hr class="divider">
        {btn("Annulla la gara", "danger", "minus")}
        <div style="font-size:12px;font-weight:600;color:var(--c7-ink-muted);line-height:1.45">
          I 6 iscritti ricevono la notifica dell'annullamento.
        </div>
      </section>

      {sec("Iscritti", "6")}
      {rows(person("PA", "pa", "iscritto il 28/08")
            + person("MR", "m.rossi", "iscritto il 28/08"))}
"""
    return doc(phone(SUB, TABS_ISCR, content))


def iscr_avvio():
    corpo = f"""
    <div class="stack">
      {rows(
        row(I["users"], "10 iscritti", "tutti gli attivi entrano in gara", tone="ok")
        + row(I["grid"], "4 turni generati adesso", "Amalfi crea tutti i turni all'avvio", tone="ok")
        + row(I["scale"], "X a tavolino a s.conti", "l'ultimo iscritto, come da impostazione", tone="warn")
        + row(I["table"], "Tavoli 3, 1, 2", "in quest'ordine", tone="ok"))}
      <div style="font-size:12px;font-weight:600;color:var(--c7-ink-muted);line-height:1.45">
        Da qui le iscrizioni si chiudono e gli abbinamenti sono fissati.
        Finch&eacute; nessun risultato &egrave; inserito puoi ancora annullare l'avvio.
      </div>
    </div>"""
    content = f"""
      {band("Iscrizioni aperte", "10 iscritti su 16",
            progress(10, 16, "Minimo raggiunto", 62))}
"""
    return doc(phone(SUB, TABS_ISCR, content,
                     overlay=sheet("Avvia la gara", corpo,
                                   btn("Avvia la gara", "success", "play"))))


# ==========================================================================
# FASE 3 — GIOCO (gara.status = playing)
# ==========================================================================






def gioco_correggi():
    """Un risultato del turno 1 registrato al contrario (g.verdi 5-4
    p.marini, scritto 4-5): il foglio lo raddrizza. Dietro, il turno
    concluso con le card in sola lettura, la corretta in cima."""
    corpo = f"""
    <div class="stack">
      <div style="display:grid;grid-template-columns:repeat(2, minmax(0, 1fr));gap:10px">
        {stepper("g.verdi", "5")}
        {stepper("p.marini", "4")}
      </div>
      {field("Perch&eacute; (facoltativo)", CURSORE % "punteggio invertito")}
      <div class="flash flash--warn">
        <span class="flash__ico">{ico(I["clock"], 14)}</span>
        <div><div class="flash__title">I triangoli segnati uno per uno si cancellano</div>
          <div>Resta il punteggio finale. La correzione rimane scritta sulla
            partita: chi aveva visto il risultato di prima capisce perch&eacute;
            &egrave; cambiato.</div></div>
      </div>
    </div>"""
    content = f"""
      {sec("Turno 1", "Concluso")}
      {closed_card("g.verdi", "4", "p.marini", "5", "1",
                   right='<button class="btn btn--secondary btn--sm">Correggi</button>')}
      {closed_card("m.rossi", "5", "d.bianchi", "2", "1")}
      {closed_card("a.galli", "5", "s.conti", "3", "2")}
      {closed_card("l.ferrari", "5", "f.costa", "1", "3")}
"""
    return doc(phone(SUB, TABS_GIOCO, content,
                     overlay=sheet("Correggi il risultato", corpo,
                                   btn("Correggi il risultato", "primary", "check"),
                                   "g.verdi vs p.marini &middot; turno 1 &middot; tavolo 1")))


def ssr_rilevato():
    corpo = ("""
        <div style="margin-top:10px;font-size:13px;font-weight:600;
             color:var(--c7-accent-dim);line-height:1.45">
          Due giocatori sono a pari merito per il 3&deg; posto. Lo spareggio
          si gioca a Spot Shot Rally: tu inserisci i punti.</div>""")
    azione = ('<div style="margin-top:14px">'
              + btn("Avvia lo spareggio", "primary", "scale") + "</div>")
    content = f"""
      {band("Tutti i 4 turni conclusi", "Serve uno spareggio", corpo, azione)}

      {sec("Parimerito", "fino al 3&deg; posto")}
      {classifica([("3", "d.bianchi", "3", "+2", "pari"),
                   ("4", "l.ferrari", "3", "+2", "pari")], header=False)}

      {sec("Oppure")}
      <section class="card stack">
        {btn("Azzera i risultati del turno 4", "secondary", "rotate")}
        <div style="font-size:12px;font-weight:600;color:var(--c7-ink-muted);line-height:1.45">
          Se un punteggio &egrave; sbagliato, correggilo prima dello spareggio.
        </div>
      </section>
"""
    return doc(phone(SUB, TABS_GEST, content))


def ssr_punteggi():
    content = f"""
      <div class="sechead">
        <div class="kicker grow">Spareggio (Spot Shot Rally)</div>
        <span class="state state--warn">in attesa di punteggi</span>
      </div>

      <section class="card">
        <div class="row">
          <h3 class="grow">Parimerito per il 3&deg; posto</h3>
          <span class="state state--muted"><span class="num">2</span>&nbsp;triangoli</span>
        </div>
        <div style="margin-top:14px;display:grid;grid-template-columns:1fr 1fr;gap:10px">
          {stepper("d.bianchi", "4")}
          {stepper("l.ferrari", "2")}
        </div>
        <div style="margin-top:14px">{btn("Salva i punti SSR", "primary", "check")}</div>
      </section>

      <div style="font-size:12px;font-weight:600;color:var(--c7-ink-muted);line-height:1.45">
        Lo spareggio decide solo l'ordine fra chi &egrave; a pari merito:
        vittorie e differenza triangoli restano quelle della gara.
      </div>
"""
    return doc(phone(SUB, TABS_GEST, content))


def ssr_termina():
    corpo = ("""
        <div style="margin-top:10px;font-size:13px;font-weight:600;
             color:var(--c7-accent-dim);line-height:1.45">
          d.bianchi 4 &middot; l.ferrari 2. Il 3&deg; posto va a d.bianchi.</div>""")
    azione = ('<div style="margin-top:14px">'
              + btn("Termina la gara", "success", "flag") + "</div>")
    content = f"""
      {band("Spareggi risolti", "Puoi chiudere la gara", corpo, azione)}

      {sec("Se serve tornare indietro")}
      <section class="card stack">
        {btn("Annulla lo spareggio", "secondary", "rotate")}
        <div style="font-size:12px;font-weight:600;color:var(--c7-ink-muted);line-height:1.45">
          Riporta la gara in gioco per correggere i risultati.
          I punti SSR inseriti vengono azzerati.
        </div>
      </section>

      <div class="flash flash--warn">
        <span class="flash__ico">{ico(I["flag"], 14)}</span>
        <div><div class="flash__title">Terminare blocca la gara</div>
          <div>La classifica diventa definitiva, i punti vanno al campionato
            e i giocatori ricevono la notifica.</div></div>
      </div>
"""
    return doc(phone(SUB, TABS_GEST, content))


# ==========================================================================
# FASE 5 — CONCLUSA (gara.status = completed)
# ==========================================================================



T4 = [("m.rossi", "5", "a.galli", "3", "1"), ("d.bianchi", "5", "l.ferrari", "4", "2"),
      ("g.verdi", "5", "p.marini", "2", "3"), ("s.conti", "5", "f.costa", "1", "1"),
      ("r.neri", "5", "e.sala", "3", "2")]


def partite_turno(n, righe):
    """Un turno concluso come elenco raggruppato (come round1_rows del kit)."""
    out = ""
    for p1, s1, p2, s2, tbl in righe:
        out += f"""
        <div class="rows__row">
          <div class="grow">
            <div class="rows__title muted">{p1} <span class="faint">vs</span> {p2}</div>
          </div>
          <div class="num" style="font-size:14px;color:var(--c7-ink-soft)">{s1}&ndash;{s2}</div>
          <div class="rows__sub" style="width:58px;text-align:right">Tavolo {tbl}</div>
        </div>"""
    return f"""
      <div class="sechead" style="margin-top:4px">
        <h3 class="muted">Turno {n}</h3>
        <span class="state state--muted" style="margin-left:auto">Concluso</span>
      </div>
      <div class="rows">{out}</div>"""


def fine_dopo():
    corpo = ("""
        <div style="margin-top:10px;font-size:13px;font-weight:600;
             color:var(--c7-accent-dim);line-height:1.45">
          10 partecipanti &middot; 20 partite giocate &middot; 4 turni.</div>""")
    content = f"""
      {band("Gara conclusa", "Ha vinto m.rossi", corpo)}

      {sec("Dopo la gara")}
      {rows(
        row(I["trophy"], "Classifica del campionato", "aggiornata con questa gara", tone="neutral")
        + row(I["share"], "Pagina pubblica", "con la classifica finale", tone="neutral"))}

      {sec("Partite", "20, tutte validate")}
      {partite_turno(4, T4)}
      {partite_turno(3, base.R1)}

      {sec("Resta bloccato")}
      {rows(
        row(I["minus"], "Punteggi", "non si modificano a gara conclusa", tone="locked")
        + row(I["users"], "Iscritti", "elenco definitivo", tone="locked"))}
"""
    return doc(phone(SUB, vtabs(["Turni", "Classifica", "Iscritti"], "Turni"), content))


# ==========================================================================
# DESKTOP delle fasi 2, 4, 5 e lo schermo in sala (aggiunti il 12/09/2026:
# in preparazione si usa quasi sempre il desktop, e qualche direttore lo
# preferisce anche in gioco)
# ==========================================================================

def _band_desktop(kicker, titolo, corpo, azione=""):
    return f"""
          <section class="card card--accent" style="display:flex;align-items:center;
                   gap:22px;padding:20px 22px">
            <div class="grow">
              <div class="kicker">{kicker}</div>
              <h3 style="margin-top:4px;font-size:20px">{titolo}</h3>
              <div style="margin-top:6px;font-size:13px;font-weight:600;
                   color:var(--c7-accent-dim)">{corpo}</div>
            </div>
            {azione}
          </section>"""


def iscr_desktop():
    elenco = "".join(
        person(sigla, nome, f"iscritto il {data} &middot; {cat}",
               f'<button class="iconbtn">{ico(I["minus"], 14)}</button>')
        for sigla, nome, data, cat in [
            ("PA", "pa", "28/08", "A"), ("MR", "m.rossi", "28/08", "A"),
            ("GV", "g.verdi", "29/08", "B"), ("DB", "d.bianchi", "29/08", "B"),
            ("LF", "l.ferrari", "30/08", "A"), ("AG", "a.galli", "30/08", "C"),
            ("PM", "p.marini", "31/08", "B")])
    sinistra = f"""
        <div class="stack">
          {_band_desktop("Iscrizioni aperte", "7 iscritti su 16",
                         "Servono almeno 8 iscritti &middot; chiudono gioved&igrave; 19:30",
                         '<button class="btn btn--locked">Avvia la gara &middot; manca 1</button>')}
          <div class="sechead">
            <h3>Iscritti</h3>
            <span class="state state--accent">7 attivi</span>
            <span class="state state--warn">+1 in attesa</span>
            <span class="sechead__more">Iscrivi un giocatore</span>
          </div>
          {rows(elenco)}
        </div>
"""
    destra = f"""
        <div class="stack">
          {sec("Condividi")}
          <section class="card">
            <div class="num" style="background:var(--c7-sunken);border-radius:var(--c7-r-field);
                 padding:14px 16px;font-size:13px;font-weight:700;word-break:break-all;
                 color:var(--c7-ink-soft)">torneibiliardo.it/g/gara-3-giovedi</div>
            <div style="margin-top:10px;display:flex;gap:10px">
              {btn("Copia", "secondary", "link")}{btn("Condividi", "primary", "share")}
            </div>
          </section>

          {sec("Lista d'attesa", "1")}
          {rows(person("SC", "s.conti", "in lista dal 30/08",
                       '<button class="btn btn--secondary btn--sm">Fai entrare</button>'))}

          {sec("Da tenere d'occhio")}
          {rows(
            row(I["table"], "Tavoli", "4 nella sala, tutti in uso", tone="neutral")
            + row(I["clock"], "Chiusura iscrizioni", "gioved&igrave; 19:30 &mdash; estendi", tone="neutral"))}
        </div>
"""
    actions = ('<button class="btn btn--secondary btn--sm">'
               f'{ico(I["clock"], 15)} Modifica le date</button>')
    return doc(desktop(actions, f'<div class="cols">{sinistra}{destra}</div>'))


def ssr_desktop():
    righe = [("1", "m.rossi", "4", "+11", ""), ("2", "a.galli", "3", "+6", ""),
             ("3", "d.bianchi", "3", "+2", "PARI"), ("4", "l.ferrari", "3", "+2", "PARI"),
             ("5", "g.verdi", "2", "-1", ""), ("6", "p.marini", "2", "-3", "")]
    sinistra = f"""
        <div class="stack">
          {_band_desktop("Tutti i 4 turni conclusi", "Serve uno spareggio",
                         "Due giocatori sono a pari merito per il 3&deg; posto. "
                         "Lo spareggio si gioca a Spot Shot Rally: tu inserisci i punti.",
                         '<button class="btn btn--locked">Termina la gara</button>')}
          <section class="card">
            <div class="row">
              <h3 class="grow">Parimerito per il 3&deg; posto</h3>
              <span class="state state--muted"><span class="num">2</span>&nbsp;giocatori</span>
            </div>
            <div style="margin-top:14px;display:grid;grid-template-columns:1fr 1fr;gap:10px">
              {stepper("d.bianchi", "4")}
              {stepper("l.ferrari", "2")}
            </div>
            <div style="margin-top:14px;display:flex;gap:10px">
              {btn("Salva i punti SSR", "primary", "check", w=False)}
              {btn("Annulla lo spareggio", "secondary", "rotate", w=False)}
            </div>
          </section>
          <div style="font-size:12px;font-weight:600;color:var(--c7-ink-muted);line-height:1.45">
            Lo spareggio decide solo l'ordine fra chi &egrave; a pari merito: vittorie e
            differenza triangoli restano quelle della gara. Annullarlo riporta la gara
            in gioco e azzera i punti SSR.
          </div>
        </div>
"""
    destra = f"""
        <div class="stack">
          {sec("Classifica dopo il turno 4", "fino al 3&deg; posto")}
          {classifica(righe)}
        </div>
"""
    return doc(desktop("", f'<div class="cols">{sinistra}{destra}</div>'))






# ==========================================================================
# Revisione del 12/09/2026 sera: rilievi dell'utente sulle pagine 1-5
# ==========================================================================

ICO_DRAG = ('<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            'stroke-width="2" stroke-linecap="round"><path d="M4 7h16M4 12h16M4 17h16"/></svg>')
ICO_X = ('<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
         'stroke-width="2.2" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>')


def trend(t):
    """Freccia di tendenza rispetto al turno prima: su, giu', uguale."""
    if t == "up":
        return ('<svg width="14" height="14" viewBox="0 0 24 24" fill="var(--c7-ok)">'
                '<path d="M12 5l8 12H4z"/></svg>')
    if t == "down":
        return ('<svg width="14" height="14" viewBox="0 0 24 24" fill="var(--c7-err)">'
                '<path d="M12 19L4 7h16z"/></svg>')
    return ('<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--c7-ink-faint)" '
            'stroke-width="3" stroke-linecap="round"><path d="M5 12h14"/></svg>')


def stepnav(i, n, prev, nxt):
    """Avanti e indietro fra i passi della preparazione, senza tornare alla 1.1."""
    p = (f'<button class="btn btn--secondary btn--sm">{ico(I["back"], 14)} {prev}</button>'
         if prev else "<span></span>")
    x = (f'<button class="btn btn--secondary btn--sm">{nxt} '
         f'<span style="display:inline-block;transform:rotate(180deg)">{ico(I["back"], 14)}</span></button>'
         if nxt else "<span></span>")
    return f"""
      <div class="row" style="justify-content:space-between;margin-top:4px">
        {p}
        <span class="num muted" style="font-size:12px">{i} di {n}</span>
        {x}
      </div>"""


PASSI = ["Turni", "Tavoli", "Esercizi", "Direttori", "Vetrina"]


def _nav(i):
    return stepnav(i + 1, len(PASSI), PASSI[i - 1] if i > 0 else None,
                   PASSI[i + 1] if i + 1 < len(PASSI) else None)


def chip_tavolo(nome, aggiungi=True):
    """Un tavolo della sala non ancora nell'elenco: si tocca per aggiungerlo."""
    return (f'<button class="pill" style="height:44px;gap:6px;background:var(--c7-card);'
            f'color:var(--c7-accent);box-shadow:inset 0 0 0 2px var(--c7-accent-tint)">'
            f'{ico(I["plus"], 14)}<span class="num" style="font-size:15px">{nome}</span></button>')


def setup_tavoli():
    """I tavoli della gara come elenco ordinato: il nome si scrive, l'ordine
    si trascina, si toglie. Sotto, i tavoli della sala che non sono in
    elenco (TableAssignmentService.get_table_names: nomi personalizzati
    della sala o numeri) si aggiungono con un tocco; un tavolo con un altro
    nome si aggiunge a mano. Oggi l'elenco e' un campo di testo «3, 1, 2»
    e vuoto vuol dire «tutti i tavoli della sala»."""
    def riga(nome, nota):
        return f"""
        <div class="rows__row" style="gap:10px">
          <span class="faint">{ICO_DRAG}</span>
          <div class="num grow" style="height:44px;border-radius:var(--c7-r-control);
               background:var(--c7-bg);padding:0 14px;display:flex;align-items:center;
               font-size:15px;font-weight:800">{nome}</div>
          <span class="rows__sub" style="margin:0;width:64px">{nota}</span>
          <button class="iconbtn">{ICO_X}</button>
        </div>"""
    content = f"""
      {sec("Tavoli della gara", "3 su 6 della sala")}
      <div style="font-size:13px;font-weight:600;color:var(--c7-ink-muted);line-height:1.45">
        Dall'alto in basso &egrave; l'ordine di assegnazione: il primo va alla
        partita di cartello. Trascina per riordinare, tocca il nome per cambiarlo.
      </div>
      {rows(riga("3", "1&deg;") + riga("1", "2&deg;") + riga("2", "3&deg;"))}
      <div>
        <div class="label" style="margin-bottom:8px">Altri tavoli della sala</div>
        <div style="display:flex;flex-wrap:wrap;gap:8px">
          {chip_tavolo("4")}{chip_tavolo("5")}{chip_tavolo("6")}
          <button class="pill" style="height:44px;gap:6px">{ico(I["plus"], 14)} Un altro nome</button>
        </div>
      </div>
      <section class="card">
        {toggle("Assegna in base alla classifica", False,
                "Dal secondo turno il primo tavolo va alla partita con il giocatore "
                "meglio piazzato. Solo con accoppiamento casuale.")}
      </section>
      {btn("Salva i tavoli", "primary", "check")}
      {_nav(1)}
"""
    return doc(phone(SUB, TABS_SETUP, content))


def setup_esercizi():
    """Gli esercizi fra i turni (GaraChallenge): quale, dopo che turno,
    quanti tentativi. La classifica degli esercizi e' a parte."""
    content = f"""
      {sec("Esercizi fra i turni", "1")}
      <div style="font-size:13px;font-weight:600;color:var(--c7-ink-muted);line-height:1.45">
        Si giocano dopo il turno indicato, mentre gli altri finiscono.
        Fanno una classifica a parte, accanto a quella della gara.
      </div>
      {rows(row(I["target"], "Stop shot",
                "dopo il turno 2 &middot; 2 tentativi &middot; punteggio 0&ndash;10", tone="accent"))}
      {btn("Aggiungi un esercizio", "secondary", "plus")}
      {_nav(2)}
"""
    return doc(phone(SUB, TABS_SETUP, content))


def setup_esercizi_aggiungi():
    corpo = f"""
    <div class="stack">
      {field("Esercizio", CURSORE % "sto")}
      {rows(person("SS", "Stop shot", "punteggio 0&ndash;10 &middot; 12 hanno provato",
                   '<span class="state state--accent">scelto</span>')
            + person("TL", "Tiro lungo in sponda", "s&igrave;/no &middot; 30 hanno provato"))}
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
        {field("Dopo il turno", '2 <span class="faint" style="margin-left:auto">&#9662;</span>')}
        {field("Tentativi", "2", mono=True)}
      </div>
    </div>"""
    return doc(phone(SUB, TABS_SETUP, sec("Esercizi fra i turni", "0")
                     + rows(row(I["target"], "Nessun esercizio", "facoltativo", tone="locked")),
                     overlay=sheet("Aggiungi un esercizio", corpo,
                                   btn("Aggiungi", "primary", "check"))))


def _cat(sigla):
    return (f'<span class="state state--info" style="height:24px;padding:0 9px">{sigla} '
            f'<span class="faint">&#9662;</span></span>')


def iscr_elenco():
    """Il campo di ricerca sta in cima, sempre: iscrivere qualcuno e' il
    gesto principale della fase. La categoria e' un chip che si tocca
    (combo per riga, `_gara_inscriptions.html`: scrivere un nome nuovo crea
    la categoria). La lista d'attesa entra da sola quando qualcuno si
    ritira (`InscriptionService._promote_and_notify`): nessun «Fai entrare»."""
    elenco = (
        person("PA", "pa", "iscritto il 28/08", _cat("A") + f' <button class="iconbtn">{ico(I["minus"], 14)}</button>')
        + person("MR", "m.rossi", "iscritto il 28/08", _cat("A") + f' <button class="iconbtn">{ico(I["minus"], 14)}</button>')
        + person("GV", "g.verdi", "iscritto il 29/08", _cat("B") + f' <button class="iconbtn">{ico(I["minus"], 14)}</button>')
        + person("DB", "d.bianchi", "iscritto il 29/08", _cat("B") + f' <button class="iconbtn">{ico(I["minus"], 14)}</button>'))
    content = f"""
      {field("Iscrivi un giocatore", '<span class="faint">Cognome, nome o username</span>')}
      <div class="sechead">
        <h3>Iscritti</h3>
        <span class="state state--accent">7 attivi</span>
        <span class="state state--warn">+1 in attesa</span>
      </div>
      {rows(elenco)}

      <div class="sechead" style="margin-top:4px">
        <h3 class="muted">Lista d'attesa</h3>
      </div>
      {rows(person("SC", "s.conti", "in lista dal 30/08 &middot; entra se qualcuno si ritira"))}
"""
    return doc(phone(SUB, TABS_ISCR2, content))


def iscr_aggiungi():
    """Si scrive nel campo in cima e i risultati compaiono sotto, senza
    foglio: nessun tocco prima di poter scrivere."""
    content = f"""
      {field("Iscrivi un giocatore", CURSORE % "ferr")}
      {rows(
        person("LF", "l.ferrari", "Luca Ferrari &middot; Biliardo Mimmo",
               '<button class="btn btn--primary btn--sm">Iscrivi</button>')
        + person("AF", "a.ferrero", "Anna Ferrero &middot; Sala Nuova",
                 '<button class="btn btn--primary btn--sm">Iscrivi</button>'))}
      <div style="font-size:12px;font-weight:600;color:var(--c7-ink-muted);text-align:center">
        2 giocatori trovati
      </div>
      <div class="sechead" style="margin-top:4px">
        <h3>Iscritti</h3>
        <span class="state state--accent">7 attivi</span>
      </div>
      {rows(person("PA", "pa", "iscritto il 28/08", _cat("A"))
            + person("MR", "m.rossi", "iscritto il 28/08", _cat("A")))}
"""
    return doc(phone(SUB, TABS_ISCR2, content))



def tessera_tavolo(n, stato, chi=""):
    """Tessera del foglio «Assegna il tavolo»: la libera e' il comando."""
    if stato == "occupato":
        style = "background:var(--c7-accent);color:var(--c7-accent-ink)"
        sub = f'<div style="margin-top:4px;font-size:11px;font-weight:700;color:var(--c7-accent-dim);line-height:1.35">{chi}</div>'
    elif stato == "attuale":
        style = "background:var(--c7-ink);color:#fff"
        sub = '<div style="margin-top:4px;font-size:11px;font-weight:700;color:var(--c7-on-ink-muted)">tavolo attuale</div>'
    else:
        style = ("background:var(--c7-card);color:var(--c7-accent);"
                 "box-shadow:inset 0 0 0 2px var(--c7-accent)")
        sub = '<div style="margin-top:4px;font-size:11px;font-weight:800">libero &middot; tocca per assegnare</div>'
    return f"""
          <div style="border-radius:var(--c7-r-field);padding:14px 10px 12px;text-align:center;
               min-height:84px;display:flex;flex-direction:column;justify-content:center;{style}">
            <div class="num" style="font-size:24px;font-weight:800;line-height:1">{n}</div>
            {sub}
          </div>"""


def gioco_tavolo():
    """Il foglio di oggi (tableAssignmentModal in gara_detail.html) salva al
    tocco della tessera: selectTableFromModal fa subito la POST. Il bottone
    di conferma della prima versione non esisteva nell'app e non serviva."""
    griglia = "".join([
        tessera_tavolo("1", "occupato", "m.rossi<br>g.verdi"),
        tessera_tavolo("2", "occupato", "d.bianchi<br>l.ferrari"),
        tessera_tavolo("3", "occupato", "a.galli<br>r.neri"),
        tessera_tavolo("4", "libero"),
    ])
    corpo = f"""
    <div class="stack">
      <div style="display:grid;grid-template-columns:repeat(2, minmax(0, 1fr));gap:10px">{griglia}</div>
      <div style="font-size:12px;font-weight:600;color:var(--c7-ink-muted);line-height:1.45">
        Gli occupati si liberano quando il risultato &egrave; validato, e passano da soli
        alla prima partita in attesa.
      </div>
    </div>"""
    content = f"""
      {sec("Turno 2", "1 in attesa")}
      {base.pending_card("s.conti", "p.marini")}
      {valida_card()}
      {base.stepper_card("m.rossi", "4", "g.verdi", "2", "1")}
      {base.stepper_card("d.bianchi", "3", "l.ferrari", "3", "2")}
"""
    return doc(phone(SUB, TABS_GIOCO, content,
                     overlay=sheet("Assegna il tavolo", corpo, "",
                                   "s.conti vs p.marini &middot; in attesa")))


def score_read(name, score, winner=False, bg="var(--c7-bg)"):
    """Punteggio in sola lettura: nome sopra, numero grande sotto, la stessa
    geometria degli stepper. Chi ha vinto resta pieno, l'altro si spegne."""
    col = "" if winner else "color:var(--c7-ink-muted)"
    return f"""
          <div style="border-radius:var(--c7-r-field);background:{bg};padding:12px 10px 14px;text-align:center">
            <div style="font-size:12px;font-weight:800;white-space:nowrap;overflow:hidden;
                        text-overflow:ellipsis;{col}">{name}</div>
            <div class="num" style="margin-top:8px;font-size:34px;font-weight:800;line-height:1;{col}">{score}</div>
          </div>"""


def closed_card(p1, s1, p2, s2, table, right=""):
    """Partita chiusa: stessa card, punteggio in sola lettura."""
    w1, w2 = int(s1) > int(s2), int(s2) > int(s1)
    right_html = right or (f'<span style="font-size:12px;font-weight:700">'
                           f'Tavolo <span class="num">{table}</span></span>')
    return f"""
      <article class="card card--locked">
        <div class="row" style="justify-content:space-between">
          <span class="state state--muted">Conclusa</span>
          {right_html}
        </div>
        <div style="margin-top:12px;display:grid;grid-template-columns:repeat(2, minmax(0, 1fr));gap:10px">
          {score_read(p1, s1, w1, bg="var(--c7-card)")}
          {score_read(p2, s2, w2, bg="var(--c7-card)")}
        </div>
      </article>
"""


def valida_card(compatto=False):
    """La partita arrivata alla distanza dal segnapunti dei giocatori senza
    la doppia conferma (`is_at_distance and not is_player_validated`,
    _match_card.html). Il direttore ha due comandi, come oggi: correggere
    il punteggio (oggi «Inserisci risultato», qui gli stessi stepper delle
    altre card) e «Valida», che chiude la partita e libera il tavolo, il
    quale passa da solo alla prima partita in attesa
    (MatchValidationService.validate_and_complete →
    release_and_reassign_table)."""
    nota = "" if compatto else """
        <div style="margin-top:8px;font-size:12px;font-weight:600;color:var(--c7-ok-body);
             line-height:1.45">
          Chiusa dal segnapunti dei giocatori senza la doppia conferma. Se il
          punteggio non &egrave; quello, correggilo con &minus; e + prima di
          validare. Validare la completa: il tavolo 3 passa a s.conti vs p.marini.
        </div>"""
    return f"""
      <article class="card card--ok">
        <div class="row" style="justify-content:space-between">
          <span class="state state--ok">Da validare</span>
          <span style="font-size:12px;font-weight:700">Tavolo <span class="num">3</span></span>
        </div>
        <div style="margin-top:12px;display:grid;grid-template-columns:repeat(2, minmax(0, 1fr));gap:10px">
          {stepper("a.galli", "5")}
          {stepper("r.neri", "1")}
        </div>
        <div style="margin-top:12px">{btn("Valida il risultato", "success", "check")}</div>
        {nota}
      </article>
"""


def gioco_valida():
    """Tutto il turno 2 in pagina: la card verde e' l'unica che chiede
    qualcosa e sta in cima; sotto le due in corso, quella in attesa di
    tavolo e la conclusa, in sola lettura."""
    content = f"""
      {sec("Turno 2", "1 da validare")}
      {valida_card()}
      {base.stepper_card("m.rossi", "4", "g.verdi", "2", "1")}
      {base.stepper_card("d.bianchi", "3", "l.ferrari", "3", "2")}
      {base.pending_card("s.conti", "p.marini")}
      {closed_card("f.costa", "5", "e.sala", "3", "3")}
"""
    return doc(phone(SUB, TABS_GIOCO, content))


def _classifica_trend(righe, colonne):
    """Classifica con la freccia di tendenza rispetto al turno prima e le
    colonne del sistema (vittorie+diff, oppure triangoli+persi)."""
    head = "".join(f'<div class="label" style="margin:0;width:{w}px;text-align:right">{c}</div>'
                   for c, w in colonne)
    body = ""
    for pos, nome, t, valori in righe:
        sigla = (nome[0] + nome[2]).upper()
        cells = "".join(
            f'<div class="num" style="width:{w}px;text-align:right;font-size:{15 if i == 0 else 13}px;'
            f'font-weight:{800 if i == 0 else 700};{"" if i == 0 else "color:var(--c7-ink-muted)"}">{v}</div>'
            for i, (v, (_, w)) in enumerate(zip(valori, colonne)))
        body += f"""
        <div class="rows__row">
          <div class="num" style="width:20px;font-size:15px;font-weight:800">{pos}</div>
          <span style="width:14px">{trend(t)}</span>
          <div class="avatar">{sigla}</div>
          <div class="grow"><div class="rows__title">{nome}</div></div>
          {cells}
        </div>"""
    return rows(f"""
        <div class="rows__row" style="padding-top:11px;padding-bottom:11px">
          <div style="width:20px"></div><span style="width:14px"></span>
          <div class="grow label" style="margin:0;padding-left:46px">Giocatore</div>{head}
        </div>""" + body)


def gioco_classifica(sistema="vittorie"):
    """Due sistemi (ADR-047, `campionato.classification_system`): a vittorie
    si ordina per vinte e differenza triangoli; a RACK per triangoli vinti
    totali. La freccia dice come e' cambiata la posizione dal turno prima."""
    if sistema == "vittorie":
        righe = [("1", "m.rossi", "eq", ("2", "+7")), ("2", "a.galli", "up", ("2", "+4")),
                 ("3", "d.bianchi", "down", ("1", "+1")), ("4", "l.ferrari", "up", ("1", "0")),
                 ("5", "g.verdi", "down", ("1", "-2")), ("6", "p.marini", "eq", ("0", "-5"))]
        tab = _classifica_trend(righe, [("Vinte", 44), ("Diff", 40)])
        nota = ("Ordinata per vittorie, poi differenza triangoli. La X a tavolino "
                "vale una vittoria e zero differenza.")
        titolo = "Classifica"
    else:
        righe = [("1", "m.rossi", "eq", ("10", "3")), ("2", "a.galli", "up", ("9", "5")),
                 ("3", "l.ferrari", "up", ("8", "8")), ("4", "d.bianchi", "down", ("7", "6")),
                 ("5", "g.verdi", "down", ("6", "8")), ("6", "p.marini", "eq", ("3", "8"))]
        tab = _classifica_trend(righe, [("Vinti", 44), ("Persi", 40)])
        nota = ("Sistema RACK: ordinata per triangoli vinti in tutta la gara, poi "
                "punti SSR. La X a tavolino vale zero triangoli.")
        titolo = "Classifica (rack)"
    content = f"""
      <div class="sechead">
        <h3>{titolo}</h3>
        <span class="sechead__note muted" style="font-size:12px;font-weight:700">dopo il turno 2</span>
      </div>
      <div style="display:flex;gap:6px">
        <button class="vtab is-active" style="flex:1">Prime 6</button>
        <button class="vtab" style="flex:1">Tutti (10)</button>
      </div>
      {tab}
      <div style="font-size:12px;font-weight:600;color:var(--c7-ink-muted);line-height:1.45">
        {nota} La freccia confronta con il turno prima.
      </div>
"""
    return doc(phone(SUB, TABS_CLASS, content))


def gioco_classifica_rack():
    return gioco_classifica("rack")


def gioco_turno_dopo():
    """A turno concluso c'e' un solo comando: avviare il prossimo. Annullare
    l'avvio e avviare il turno dopo sono alternativi: si annulla finche'
    nessuna partita ha un triangolo (dal menu del turno), si avvia quando
    tutte sono alla distanza; in mezzo, nessuno dei due."""
    corpo = ("""
        <div style="margin-top:10px;font-size:13px;font-weight:600;
             color:var(--c7-accent-dim);line-height:1.45">
          Tutte e 5 le partite sono validate. Gli abbinamenti del turno 3
          sono gi&agrave; fissati dal sorteggio iniziale.</div>""")
    azione = ('<div style="margin-top:14px">'
              + btn("Avvia il turno 3", "success", "play") + "</div>")
    content = f"""
      {band("Turno 2 di 4 &middot; concluso", "Puoi avviare il turno 3", corpo, azione)}
      {sec("Turno 2", "concluso")}
      {partite_turno(2, T4).split("</div>", 2)[2] if False else rows("".join(f'''
        <div class="rows__row">
          <div class="grow"><div class="rows__title muted">{p1} <span class="faint">vs</span> {p2}</div></div>
          <div class="num" style="font-size:14px;color:var(--c7-ink-soft)">{s1}&ndash;{s2}</div>
          <div class="rows__sub" style="width:58px;text-align:right">Tavolo {tbl}</div>
        </div>''' for p1, s1, p2, s2, tbl in T4))}
      <div style="font-size:12px;font-weight:600;color:var(--c7-ink-muted);line-height:1.45">
        Per correggere una partita si tocca la sua riga: si pu&ograve;
        finch&eacute; il turno 3 non &egrave; avviato.
      </div>
"""
    return doc(phone(SUB, TABS_GIOCO, content))


def gioco_mio_match():
    """Se dirige ed e' iscritto, la sua partita e' la prima cosa: la card
    scura con i due giocatori nella geometria delle altre card (nome sopra,
    numero grande sotto, niente «vs»), e il segnapunti come unico comando."""
    def lato(nome, s, tu=False, dim=False):
        col = "color:var(--c7-accent-dim)" if dim else ""
        tu_html = ' <span style="color:var(--c7-accent-dim);font-weight:700">(tu)</span>' if tu else ""
        return f"""
          <div style="border-radius:var(--c7-r-field);background:rgba(242,248,247,.1);padding:12px 10px 14px;text-align:center">
            <div style="font-size:12px;font-weight:800;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{nome}{tu_html}</div>
            <div class="num" style="margin-top:8px;font-size:34px;font-weight:800;line-height:1;{col}">{s}</div>
          </div>"""
    content = f"""
      <article class="card card--accent">
        <div class="row" style="justify-content:space-between">
          <span class="state state--onaccent">La tua partita</span>
          <span style="font-size:12px;font-weight:700;color:var(--c7-accent-dim)">Tavolo <span class="num">1</span></span>
        </div>
        <div style="margin-top:12px;display:grid;grid-template-columns:repeat(2, minmax(0, 1fr));gap:10px">
          {lato("pa", "3", tu=True)}
          {lato("l.ferrari", "2", dim=True)}
        </div>
        <div style="margin-top:14px">{btn("Vai al segnapunti", "bright", "play")}</div>
      </article>

      {sec("Turno 2")}
      {base.stepper_card("m.rossi", "4", "g.verdi", "2", "3")}
      {base.pending_card("s.conti", "p.marini")}
      {closed_card("f.costa", "5", "e.sala", "3", "2")}
"""
    return doc(phone(SUB, TABS_GIOCO, content))


def _pos(pos, medaglie=True):
    cls = f" pos--{pos}" if medaglie and pos in ("1", "2", "3") else ""
    return (f'<div class="num pos{cls}">{pos}</div>')


def classifica_finale(righe):
    """Classifica finale con le medaglie e la freccia di tendenza rispetto
    al turno prima (o allo spareggio, dove ha deciso)."""
    body = ""
    for pos, nome, t, vinte, diff, extra in righe:
        sigla = (nome[0] + nome[2]).upper()
        badge = f'<span class="state state--warn">{extra}</span>' if extra else ""
        body += f"""
        <div class="rows__row">
          {_pos(pos)}
          <span style="width:14px">{trend(t)}</span>
          <div class="avatar">{sigla}</div>
          <div class="grow"><div class="rows__title">{nome}</div></div>
          {badge}
          <div class="num" style="font-size:15px;font-weight:800">{vinte}</div>
          <div class="num muted" style="width:34px;text-align:right;font-size:13px">{diff}</div>
        </div>"""
    return rows(body)


FINALE = [("1", "m.rossi", "eq", "4", "+11", ""), ("2", "a.galli", "up", "3", "+6", ""),
          ("3", "d.bianchi", "up", "3", "+2", "SSR"), ("4", "l.ferrari", "down", "3", "+2", "SSR"),
          ("5", "g.verdi", "eq", "2", "-1", ""), ("6", "p.marini", "down", "2", "-3", ""),
          ("7", "s.conti", "up", "1", "-4", ""), ("8", "f.costa", "eq", "1", "-6", "")]


def _podio(compatto=False):
    fs = 13 if compatto else 15
    return "".join(f"""
          <div style="text-align:center">
            <div class="avatar avatar--lg" style="margin:0 auto;background:var(--c7-{m});color:var(--c7-{m}-ink);{extra}">{sigla}</div>
            <div style="margin-top:8px;font-size:{fs if m != "oro" else fs + 2}px;font-weight:800">{nome}</div>
            <div class="num" style="font-size:12px;color:var(--c7-{m})">{pos}</div>
          </div>""" for sigla, nome, pos, m, extra in [
        ("AG", "a.galli", "2&deg;", "argento", ""),
        ("MR", "m.rossi", "1&deg;", "oro", "width:56px;height:56px;font-size:16px"),
        ("DB", "d.bianchi", "3&deg; &middot; SSR", "bronzo", "")])


def fine_classifica():
    righe = FINALE[:6]
    content = f"""
      <section class="card card--accent">
        <div class="kicker">Classifica finale</div>
        <div style="margin-top:12px;display:grid;grid-template-columns:1fr 1fr 1fr;
             gap:10px;align-items:end">{_podio()}</div>
      </section>
      {classifica_finale(righe)}
      <div style="font-size:12px;font-weight:600;color:var(--c7-ink-muted);line-height:1.45">
        La freccia confronta con la classifica dopo il turno 3: lo spareggio ha
        portato d.bianchi davanti a l.ferrari.
      </div>
      <div class="flash flash--ok">
        <span class="flash__ico">{ico(I["check"], 14)}</span>
        <div><div class="flash__title">Gara conclusa</div>
          <div>I punti sono andati alla classifica del campionato.
            I punteggi non si modificano pi&ugrave;.</div></div>
      </div>
"""
    return doc(phone(SUB, vtabs(["Turni", "Classifica", "Iscritti"], "Classifica"), content))


def fine_desktop():
    righe = FINALE
    sinistra = f"""
        <div class="stack">
          <section class="card card--accent" style="display:flex;align-items:center;gap:24px;padding:20px 22px">
            <div class="grow">
              <div class="kicker">Gara conclusa</div>
              <h3 style="margin-top:4px;font-size:20px">Ha vinto m.rossi</h3>
              <div style="margin-top:6px;font-size:13px;font-weight:600;color:var(--c7-accent-dim)">
                10 partecipanti &middot; 20 partite giocate &middot; 4 turni &middot;
                spareggio per il 3&deg; posto.</div>
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:18px;align-items:end">{_podio(True)}</div>
          </section>
          {sec("Classifica finale", "freccia: rispetto al turno 3")}
          {classifica_finale(righe)}
        </div>
"""
    destra = f"""
        <div class="stack">
          {sec("Dopo la gara")}
          {rows(
            row(I["trophy"], "Classifica del campionato", "aggiornata con questa gara", tone="neutral")
            + row(I["share"], "Pagina pubblica", "con la classifica finale", tone="neutral"))}
          {sec("Partite", "20, tutte validate")}
          {partite_turno(4, T4)}
        </div>
"""
    actions = ('<button class="btn btn--secondary btn--sm">'
               f'{ico(I["share"], 15)} Pagina pubblica</button>')
    return doc(desktop(actions, f'<div class="cols">{sinistra}{destra}</div>'))



def schermo_sala():
    """Lo schermo in sala, pubblico e senza menu (issue #153 chiedeva proprio
    di togliere la colonna quando si proietta). In testa la locandina della
    vetrina — il banner 1200x630 di admin/gara_vetrina.html — a tutta
    larghezza, ritagliata al centro come fanno le anteprime social; sopra,
    il nome della gara e il turno. Sotto, i tavoli riempiono l'altezza e la
    classifica dopo l'ultimo turno chiuso sta a destra, con il turno prima.
    Oggi non esiste: gara_detail_public rimanda alla pagina gara, la vetrina
    a gara in corso dice solo «Gara in corso» (SPECIFICHE.md 357)."""
    def tabellone(n, p1, s1, p2, s2, stato, tono):
        if p1 is None:
            return f"""
            <section class="card" style="padding:16px 24px;display:flex;align-items:center;gap:20px;flex:1;min-height:0">
              <div style="width:78px;align-self:stretch;border-radius:var(--c7-r-control);background:var(--c7-bg);
                   color:var(--c7-ink-faint);display:flex;flex-direction:column;align-items:center;justify-content:center;gap:2px">
                <div class="kicker" style="color:var(--c7-ink-faint);font-size:9px">Tavolo</div>
                <div class="num" style="font-size:34px;font-weight:800;line-height:1">{n}</div>
              </div>
              <div class="grow">
                <div class="kicker">Tavolo {n} &middot; libero</div>
                <div style="margin-top:6px;font-size:24px;font-weight:800;color:var(--c7-ink-muted)">Prossima: {s1}</div>
                <div style="margin-top:4px;font-size:14px;font-weight:700;color:var(--c7-ink-faint)">in attesa di tavolo</div>
              </div>
            </section>"""
        def lato(nome, s, vince):
            col = "" if vince else "color:var(--c7-ink-muted)"
            return (f'<div style="min-width:0">'
                    f'<div style="font-size:20px;font-weight:800;white-space:nowrap;overflow:hidden;'
                    f'text-overflow:ellipsis;{col}">{nome}</div>'
                    f'<div class="num" style="margin-top:2px;font-size:56px;font-weight:800;line-height:1;'
                    f'letter-spacing:-.04em;{col}">{s}</div></div>')
        return f"""
            <section class="card" style="padding:16px 24px;display:flex;gap:20px;align-items:center;flex:1;min-height:0">
              <div style="width:78px;align-self:stretch;border-radius:var(--c7-r-control);background:var(--c7-accent);
                   color:var(--c7-accent-bright);display:flex;flex-direction:column;align-items:center;justify-content:center;gap:2px">
                <div class="kicker" style="color:var(--c7-accent-dim);font-size:9px">Tavolo</div>
                <div class="num" style="font-size:34px;font-weight:800;line-height:1">{n}</div>
              </div>
              <div class="grow" style="display:grid;grid-template-columns:repeat(2, minmax(0, 1fr));gap:20px;align-items:center">
                {lato(p1, s1, int(s1) >= int(s2))}
                {lato(p2, s2, int(s2) >= int(s1))}
              </div>
              <span class="state state--{tono}" style="align-self:flex-start;height:30px;font-size:12px;padding:0 14px">{stato}</span>
            </section>"""

    righe = [("1", "r.neri", "1", "+5"), ("2", "l.ferrari", "1", "+4"), ("3", "m.rossi", "1", "+3"),
             ("4", "a.galli", "1", "+2"), ("5", "g.verdi", "1", "+1"), ("6", "p.marini", "0", "-1"),
             ("7", "e.sala", "0", "-2"), ("8", "s.conti", "0", "-2"), ("9", "d.bianchi", "0", "-3"),
             ("10", "f.costa", "0", "-4")]
    turno1 = "".join(f"""
            <div style="display:flex;align-items:center;gap:12px;font-size:15px;font-weight:700">
              <span class="grow" style="text-align:right;color:{'inherit' if int(s1) > int(s2) else 'var(--c7-ink-muted)'}">{p1}</span>
              <span class="num" style="font-size:17px;font-weight:800;width:52px;text-align:center">{s1}&ndash;{s2}</span>
              <span class="grow" style="color:{'inherit' if int(s2) > int(s1) else 'var(--c7-ink-muted)'}">{p2}</span>
            </div>""" for p1, s1, p2, s2, _ in base.R1)
    class_rows = "".join(f"""
            <div class="rows__row" style="padding:0 18px;flex:1;min-height:0">
              {_pos(pos)}
              <div class="grow" style="font-size:17px;font-weight:800">{nome}</div>
              <div class="num" style="font-size:18px;font-weight:800">{v}</div>
              <div class="num muted" style="width:44px;text-align:right;font-size:14px">{d}</div>
            </div>""" for pos, nome, v, d in righe)
    return doc(f"""
<div style="width:1440px;height:900px;overflow:hidden;background:var(--c7-bg);display:flex;flex-direction:column">
  <header style="flex-shrink:0">
    <div style="height:230px;overflow:hidden;background:var(--c7-ink)">
      <img src="locandina.png" alt="" style="width:100%;height:100%;object-fit:cover;display:block">
    </div>
    <div style="height:72px;background:var(--c7-ink);color:var(--c7-on-ink);padding:0 36px;display:flex;
         align-items:center;gap:28px">
      <div class="grow" style="display:flex;align-items:baseline;gap:16px;min-width:0">
        <h1 style="font-size:28px;font-weight:800;letter-spacing:-.025em;color:inherit;white-space:nowrap">Gara 3 &middot; Gioved&igrave;</h1>
        <div style="font-size:15px;font-weight:600;color:var(--c7-on-ink-muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis">
          Biliardo Mimmo &middot; gioved&igrave; 3 settembre &middot; Palla 8 &middot; Al 5 &middot; Amalfi &middot; 10 giocatori</div>
      </div>
      <div style="display:flex;align-items:center;gap:12px">
        <div class="kicker" style="color:var(--c7-accent-dim);font-size:12px">Turno</div>
        <div class="num" style="font-size:34px;font-weight:800;line-height:1">2<span style="font-size:18px;color:var(--c7-on-ink-muted)">/4</span></div>
        <span class="state state--onaccent" style="height:30px;font-size:12px;padding:0 14px">in corso</span>
      </div>
    </div>
  </header>
  <div style="padding:20px 36px 24px;display:grid;grid-template-columns:1fr 440px;gap:20px;flex:1;min-height:0">
    <div style="display:flex;flex-direction:column;gap:12px;min-height:0">
      {tabellone(1, "m.rossi", "4", "g.verdi", "2", "In corso", "accent")}
      {tabellone(2, "d.bianchi", "3", "l.ferrari", "3", "In corso", "accent")}
      {tabellone(3, "a.galli", "5", "r.neri", "1", "Alla distanza", "ok")}
      {tabellone(4, None, "s.conti vs p.marini", None, None, "", "")}
    </div>
    <div style="display:flex;flex-direction:column;gap:12px;min-height:0">
      <div class="sechead"><h3 style="font-size:20px">Classifica dopo il turno 1</h3></div>
      <div class="rows" style="flex:1;min-height:0;display:flex;flex-direction:column">{class_rows}</div>
      <div class="sechead" style="margin-top:2px"><h3 class="muted" style="font-size:16px">Turno 1</h3>
        <span class="state state--muted" style="margin-left:auto">Concluso</span></div>
      <section class="card" style="display:flex;flex-direction:column;gap:6px;padding:12px 18px">{turno1}</section>
    </div>
  </div>
</div>
""")


def _gara_tessera(nome, quando, stato, tono, sub):
    return row(I["flag"] if stato == "Conclusa" else I["play"] if stato == "In corso" else I["clock"],
               nome, f"{quando} &middot; {sub}",
               right=f'<span class="state state--{tono}">{stato}</span>', tone="neutral")


def _classifica_generale(righe, zona=8):
    """La classifica generale con la zona playoff: le prime `zona` righe
    hanno la barra accento e sopra di loro sta l'etichetta; dopo l'ultima
    qualificata una riga dice che da li' in giu' si e' fuori. NUOVO: oggi
    _campionato_general_classification.html non segna la zona."""
    colonne = [("Punti", 48), ("Gare", 40)]
    head = "".join(f'<div class="label" style="margin:0;width:{w}px;text-align:right">{c}</div>'
                   for c, w in colonne)
    def etichetta(testo, colore):
        return f"""
        <div class="rows__row" style="padding:7px 18px;background:var(--c7-bg)">
          <span class="kicker" style="color:{colore}">{testo}</span>
        </div>"""
    body = etichetta(f"Zona playoff &middot; primi {zona}", "var(--c7-accent)")
    for i, (pos, nome, t, valori) in enumerate(righe):
        if i == zona:
            body += etichetta("Fuori dai playoff", "var(--c7-ink-faint)")
        sigla = (nome[0] + nome[2]).upper()
        dentro = "box-shadow:inset 3px 0 0 var(--c7-accent)" if i < zona else ""
        cells = "".join(
            f'<div class="num" style="width:{w}px;text-align:right;font-size:{15 if j == 0 else 13}px;'
            f'font-weight:{800 if j == 0 else 700};{"" if j == 0 else "color:var(--c7-ink-muted)"}">{v}</div>'
            for j, (v, (_, w)) in enumerate(zip(valori, colonne)))
        body += f"""
        <div class="rows__row" style="{dentro}">
          <div class="num" style="width:20px;font-size:15px;font-weight:800">{pos}</div>
          <span style="width:14px">{trend(t)}</span>
          <div class="avatar">{sigla}</div>
          <div class="grow"><div class="rows__title">{nome}</div></div>
          {cells}
        </div>"""
    return rows(f"""
        <div class="rows__row" style="padding-top:11px;padding-bottom:11px">
          <div style="width:20px"></div><span style="width:14px"></span>
          <div class="grow label" style="margin:0;padding-left:46px">Giocatore</div>{head}
        </div>""" + body)


CG = [("1", "m.rossi", "eq", ("41", "3")), ("2", "a.galli", "up", ("36", "3")),
      ("3", "l.ferrari", "down", ("33", "3")), ("4", "d.bianchi", "up", ("29", "2")),
      ("5", "g.verdi", "eq", ("24", "3")), ("6", "p.marini", "down", ("19", "3")),
      ("7", "s.conti", "up", ("15", "2")), ("8", "r.neri", "eq", ("12", "2")),
      ("9", "e.sala", "down", ("11", "3")), ("10", "f.costa", "eq", ("9", "3"))]



def campionato_mobile():
    """La pagina del campionato per chi lo dirige: la stagione a che punto
    e', la classifica generale con le tendenze, le gare, e le righe di
    gestione (campionato_detail.html: direttori, playoff, vetrina, Nuova gara)."""
    corpo = ("""
        <div style="margin-top:10px;font-size:13px;font-weight:600;
             color:var(--c7-accent-dim);line-height:1.45">
          3 gare giocate su 6, poi il playoff fra i primi 8.</div>""")
    azione = f"""
        <div class="row" style="margin-top:14px;gap:10px">
          <div class="grow" style="font-size:12px;font-weight:700;color:var(--c7-accent-dim)">
            Prossima: gara 4, gio 17 set</div>
          <button class="btn btn--bright btn--sm">Nuova gara</button>
        </div>"""
    content = f"""
      {band("Stagione 2026 &middot; in corso", "Gara 3 conclusa gioved&igrave;", corpo, azione)}

      {sec("Classifica generale", "Prime 10 &middot; tutti (14)")}
      {_classifica_generale(CG)}

      {sec("Gare", "3 di 6")}
      {rows(
        _gara_tessera("Gara 4 &middot; Gioved&igrave;", "gio 17 set", "Iscrizioni", "info", "5 iscritti")
        + _gara_tessera("Gara 3 &middot; Gioved&igrave;", "gio 3 set", "Conclusa", "ok", "ha vinto m.rossi")
        + _gara_tessera("Gara 2 &middot; Gioved&igrave;", "gio 27 ago", "Conclusa", "ok", "ha vinto a.galli"))}

      {sec("Gestione")}
      {rows(
        row(I["trophy"], "Playoff", "primi 8 &middot; dopo la gara 6", tone="neutral")
        + row(I["users"], "Direttori", "tu e m.neri", tone="neutral")
        + row(I["share"], "Vetrina", "locandina caricata", tone="neutral")
        + row(I["gear"], "Impostazioni", "Palla 8 &middot; al 5 &middot; Amalfi &middot; 4 turni", tone="neutral"))}
"""
    return doc(phone("Stagione 2026", vtabs(["Classifica", "Gare", "Gestione"], "Classifica"),
                     content, title="Campionato del gioved&igrave;"))


INVITATI = [("MR", "m.rossi", "1&deg;", "Confermato", "ok"), ("AG", "a.galli", "2&deg;", "Confermato", "ok"),
            ("LF", "l.ferrari", "3&deg;", "In attesa", "warn"), ("DB", "d.bianchi", "4&deg;", "Confermato", "ok"),
            ("GV", "g.verdi", "5&deg;", "Rifiutato &middot; al suo posto s.conti", "err"),
            ("RN", "r.neri", "6&deg;", "Confermato", "ok"), ("PM", "p.marini", "7&deg;", "In attesa", "warn"),
            ("SC", "s.conti", "9&deg;", "In attesa &middot; invitato al posto di g.verdi", "warn")]


def _invitati(desktop=False):
    """Gli invitati; su chi e' in attesa il direttore risponde per conto
    del giocatore (playoff_respond_for_player: «Accetta» e «Rifiuta» con
    conferma, admin/campionato_detail.html). Chi ha risposto da solo o
    tramite il direttore lo dice la riga."""
    out = ""
    for s, n, p, lab, t in INVITATI:
        if t == "warn":
            azioni = (f'<button class="btn btn--success btn--sm">{ico(I["check"], 14)} Accetta</button>'
                      f'<button class="btn btn--secondary btn--sm">{ICO_X} Rifiuta</button>'
                      if desktop else
                      f'<button class="iconbtn" style="width:40px;height:40px;background:var(--c7-ok-bg);color:var(--c7-ok)">{ico(I["check"], 16)}</button>'
                      f'<button class="iconbtn" style="width:40px;height:40px;background:var(--c7-err-bg);color:var(--c7-err)">{ICO_X}</button>')
            right = f'<div class="row" style="gap:6px">{azioni}</div>'
            sub = f"{p} in classifica &middot; {lab.lower()}"
        else:
            right = f'<span class="state state--{t}">{lab.split(" &middot;")[0]}</span>'
            sub = f"{p} in classifica" + (" &middot; " + lab.split("&middot; ")[1] if "&middot;" in lab else "")
        out += person(s, n, sub, right)
    return out


def playoff_mobile():
    """La fase playoff, dopo «Passa ai playoff»: gli inviti partono con
    «Avvia i playoff» (PlayoffService.start_playoff, scadenza 7 giorni), chi
    rifiuta viene sostituito dal primo degli esclusi
    (find_replacement_player), e con i confermati si crea la gara playoff,
    che poi e' una gara come le altre. Il direttore puo' rispondere per un
    giocatore (playoff_respond_for_player)."""
    corpo = ("""
        <div style="margin-top:10px;font-size:13px;font-weight:600;
             color:var(--c7-accent-dim);line-height:1.45">
          Le 6 gare sono concluse. 4 confermati su 8: gli inviti scadono
          domenica 27.</div>""")
    azione = ('<div style="margin-top:14px">'
              + btn("Crea la gara playoff &middot; 4 confermati", "locked", "play") + "</div>")
    content = f"""
      {band("Fase playoff", "Inviti in attesa", corpo, azione)}
      <div class="sechead">
        <h3>Invitati</h3>
        <span class="state state--ok">4 s&igrave;</span>
        <span class="state state--warn">3 in attesa</span>
      </div>
      {rows(_invitati())}
      <div style="font-size:12px;font-weight:600;color:var(--c7-ink-muted);line-height:1.45">
        Chi rifiuta lascia il posto al primo degli esclusi. Se un giocatore
        te lo dice a voce, rispondi tu dalla sua riga: la risposta resta
        registrata a tuo nome.
      </div>
      {sec("Classifica finale")}
      {rows(
        row(I["scale"], "Come si decide", "campionato + gara di playoff &middot; peso 1", tone="neutral"))}
"""
    return doc(phone("Stagione 2026", vtabs(["Classifica", "Gare", "Playoff"], "Playoff"),
                     content, title="Campionato del gioved&igrave;"))


def campionato_desktop():
    sinistra = f"""
        <div class="stack">
          {_band_desktop("Stagione 2026 · in corso", "Gara 3 conclusa gioved&igrave;",
                         "3 gare giocate su 6, poi il playoff fra i primi 8. Prossima: gara 4, gio 17 set.",
                         '<button class="btn btn--bright">Nuova gara</button>')}
          {sec("Classifica generale", "Prime 10 &middot; tutti (14)")}
          {_classifica_generale(CG)}
        </div>
"""
    destra = f"""
        <div class="stack">
          {sec("Gare", "3 di 6")}
          {rows(
            _gara_tessera("Gara 4", "gio 17 set", "Iscrizioni", "info", "5 iscritti")
            + _gara_tessera("Gara 3", "gio 3 set", "Conclusa", "ok", "ha vinto m.rossi")
            + _gara_tessera("Gara 2", "gio 27 ago", "Conclusa", "ok", "ha vinto a.galli")
            + _gara_tessera("Gara 1", "gio 20 ago", "Conclusa", "ok", "ha vinto m.rossi"))}
          {sec("Gestione")}
          {rows(
            row(I["trophy"], "Playoff", "primi 8 &middot; dopo la gara 6", tone="neutral")
            + row(I["users"], "Direttori", "tu e m.neri", tone="neutral")
            + row(I["share"], "Vetrina", "locandina caricata", tone="neutral")
            + row(I["gear"], "Impostazioni", "Palla 8 &middot; al 5 &middot; Amalfi", tone="neutral"))}
        </div>
"""
    actions = ('<button class="btn btn--secondary btn--sm">'
               f'{ico(I["share"], 15)} Pagina pubblica</button>')
    return doc(desktop(actions, f'<div class="cols">{sinistra}{destra}</div>')
               .replace("Gara 3 &middot; Gioved&igrave;</h1>", "Campionato del gioved&igrave;</h1>")
               .replace("Biliardo Mimmo &middot; Al 5 &middot; Palla 8 &middot;\n          <span class=\"num\">gio 3 set 2026, 20:00</span>",
                        "Stagione 2026 &middot; Biliardo Mimmo &middot; 6 gare + playoff"))


def playoff_desktop():
    sinistra = f"""
        <div class="stack">
          {_band_desktop("Fase playoff", "Inviti in attesa",
                         "Le 6 gare sono concluse. 4 confermati su 8: gli inviti scadono domenica 27.",
                         '<button class="btn btn--locked">Crea la gara playoff &middot; 4 confermati</button>')}
          <div class="sechead">
            <h3>Invitati</h3>
            <span class="state state--ok">4 s&igrave;</span>
            <span class="state state--warn">3 in attesa</span>
            <span class="sechead__more">Su chi &egrave; in attesa rispondi tu, se te lo dice a voce</span>
          </div>
          {rows(_invitati(desktop=True))}
        </div>
"""
    destra = f"""
        <div class="stack">
          {sec("Classifica finale del campionato")}
          <section class="card stack">
            {toggle("Campionato + gara di playoff", True,
                    "Il punteggio della gara di playoff si somma a quello del campionato, moltiplicato per il peso.")}
            {field("Peso del playoff", "1", mono=True)}
            {btn("Salva", "secondary", "check")}
          </section>
          {sec("Classifica generale", "congelata")}
          {_classifica_generale(CG)}
        </div>
"""
    return doc(desktop("", f'<div class="cols">{sinistra}{destra}</div>')
               .replace("Gara 3 &middot; Gioved&igrave;</h1>", "Campionato del gioved&igrave;</h1>")
               .replace("Biliardo Mimmo &middot; Al 5 &middot; Palla 8 &middot;\n          <span class=\"num\">gio 3 set 2026, 20:00</span>",
                        "Stagione 2026 &middot; fase playoff"))


NOTE_REVISIONE = {
    "SetupTurni": (
        "Configurazione per turno (ADR-027). Il turno modificato si distingue "
        "dal default con la pastiglia.\n\nRILIEVO (12/09): la descrizione "
        "della gara — «Al 5 · Palla 8» in testa e nelle informazioni — prende "
        "sempre disciplina e distanza della creazione (gara_detail.html usa "
        "gara.distance): quando i turni cambiano, la descrizione dovrebbe "
        "dirlo, per esempio «Palla 8 al 5 · turno 2: Palla 9 al 3»."),
    "SetupTavoli": (
        "I tavoli della gara come elenco ordinato: il nome si scrive, "
        "l'ordine si trascina, si toglie. Sotto, i tavoli della sala che non "
        "sono in elenco (i nomi della sala, personalizzati o numerici: "
        "TableAssignmentService.get_table_names) si aggiungono con un tocco; "
        "«Un altro nome» aggiunge un tavolo che la sala non conosce. Oggi "
        "l'elenco e' un campo di testo «3, 1, 2», e vuoto vuol dire tutti i "
        "tavoli della sala: qui non c'e' uno stato vuoto, l'elenco parte "
        "pieno.\n\nPROBLEMA VERO: oggi "
        "si modificano solo a iscrizioni aperte, e lo vieta anche il servizio "
        "(update_tables_config → ConflictError). La regola: si scelgono "
        "sempre, anche a iscrizioni chiuse e fra un turno e l'altro."),
    "IscrElenco": (
        "Il campo per iscrivere sta in cima, sempre visibile: e' il gesto "
        "principale della fase. La categoria e' un chip che si tocca — oggi "
        "e' un combo per riga, e scrivere un nome nuovo crea la categoria "
        "(_gara_inscriptions.html). La lista d'attesa entra da sola quando un "
        "iscritto si ritira (InscriptionService._promote_and_notify): il «Fai "
        "entrare» della prima versione non esiste e non serve."),
    "IscrAggiungi": (
        "Si scrive nel campo in cima e i risultati compaiono sotto, con "
        "«Iscrivi» sulla riga: nessun tocco prima di poter scrivere. Ricerca "
        "per cognome, nome o username (PR #297)."),
    "IscrAvvio": (
        "Il foglio dice cosa succede prima che succeda: chi prende la X, che "
        "i 4 turni nascono tutti adesso, l'ordine dei tavoli.\n\nLa regola "
        "di oggi su turni, distanze, disciplina e X: si toccano solo in "
        "preparazione — la configurazione dei turni compare solo con "
        "status=setup (_round_management.html) e la gara si modifica solo "
        "senza iscritti (Gara.can_be_modified). Con le iscrizioni aperte "
        "nulla cambia sotto i piedi degli iscritti, e questo foglio riporta "
        "soltanto."),
    "GiocoTavolo": (
        "Si tocca la tessera libera e il tavolo e' assegnato: come nel foglio "
        "di oggi (tableAssignmentModal in gara_detail.html, "
        "selectTableFromModal salva al tocco), senza bottone di conferma. Gli "
        "occupati mostrano i due giocatori. Un tavolo libero con una partita "
        "in attesa capita quando lo si aggiunge a turno avviato: alla "
        "validazione il tavolo liberato passa da solo alla prima in attesa "
        "(release_and_reassign_table). Senza tavolo i comandi di punteggio "
        "restano spenti: e' una regola dell'app."),
    "GiocoValida": (
        "La partita da validare: arrivata alla distanza dal segnapunti dei "
        "giocatori senza la doppia conferma (`is_at_distance and not "
        "is_player_validated`, _match_card.html). «Valida» la chiude e libera "
        "il tavolo, che passa da solo alla prima partita in attesa "
        "(MatchValidationService.validate_and_complete → "
        "release_and_reassign_table): la card lo dice. L'alternativa a "
        "validare e' correggere: oggi sulla stessa card c'e' «Inserisci "
        "risultato» (openQuickResult) accanto alla spunta; qui sono gli "
        "stessi stepper delle altre card, e si valida dopo. Le concluse "
        "restano in sola lettura, nome sopra e numero grande sotto. Tutto il "
        "turno e' in pagina: la card verde e' l'unica che chiede qualcosa."),
    "GiocoClassifica": (
        "Sistema a vittorie: vinte, poi differenza triangoli; la X vale una "
        "vittoria e zero differenza (SPECIFICHE.md 64 e 71). La freccia dice "
        "se la posizione e' salita, scesa o ferma rispetto al turno prima."),
    "GiocoTurnoDopo": (
        "A turno concluso l'unico comando e' avviare il prossimo. Annullare "
        "l'avvio e avviare il turno dopo sono alternativi: si annulla finche' "
        "nessuna partita ha un triangolo (Gara.can_cancel_round; sta nel menu "
        "del turno), si avvia quando tutte sono alla distanza; in mezzo, "
        "nessuno dei due. L'azzeramento in blocco del turno della prima "
        "versione e' stato tolto: le partite si azzerano una per una, dalla "
        "loro card (reset_match)."),
    "GiocoMioMatch": (
        "Se dirige ed e' iscritto, la sua partita e' la prima cosa: card "
        "scura con i due giocatori nella geometria delle altre card — nome "
        "sopra, numero grande sotto, niente «vs» — e il segnapunti come unico "
        "comando. La scorciatoia esiste gia' (_gara_my_match.html)."),
    "GiocoCorreggi": (
        "Si puo' fare a gara in corso (issue #90). Dietro il foglio, il turno "
        "concluso con le card in sola lettura — nome sopra, numero grande "
        "sotto, chi ha vinto pieno — e «Correggi» sulla card da cui si parte. "
        "Il foglio dice le due conseguenze vere: i triangoli segnati uno per "
        "uno si cancellano, e la correzione resta scritta sulla partita. Il "
        "campo «perche'» e' facoltativo ma e' cio' che rende leggibile la "
        "correzione a chi aveva visto il risultato di prima."),
    "FineClassifica": (
        "A gara conclusa il soggetto e' la classifica. Podio e posizioni 1-3 "
        "nei colori delle medaglie dell'app (--c7-oro, --c7-argento, "
        "--c7-bronzo, tokens-7c.css); la pastiglia SSR dove lo spareggio ha "
        "deciso; la freccia confronta con la classifica dopo l'ultimo turno, "
        "cosi' si vede dove lo spareggio ha cambiato l'ordine. La linguetta "
        "«Gestione» sparisce."),
    "FineDesktop": (
        "Conclusa su desktop: il podio dentro la fascia, la classifica sotto "
        "con le medaglie e le frecce rispetto all'ultimo turno, a destra dove "
        "sono finiti i punti e le partite turno per turno (scelta 5S)."),
    "SetupDesktop": (
        "La preparazione su desktop e' una pagina sola che scorre (1560 px): "
        "la fascia, i turni in sintesi con gli esercizi fra i turni "
        "(«Modifica turni ed esercizi» apre la 1.10), la direzione di gara "
        "con la ricerca dei co-direttori aperta in linea, i tavoli con "
        "l'ordine e i chip della sala, la vetrina con lo spazio 1200x630. "
        "La colonna destra e' la lista di cosa manca: ogni riga scorre alla "
        "sua sezione, senza pagine in piu'."),
    "CampionatoMobile": (
        "La pagina del campionato per chi lo dirige: a che punto e' la "
        "stagione, la classifica generale con le tendenze e la ZONA PLAYOFF "
        "— barra accento sulle prime 8, etichetta sopra, «fuori dai playoff» "
        "sotto l'ottava (NUOVO: oggi _campionato_general_classification.html "
        "non la segna; il numero e' playoff_elite_participants) — le gare, "
        "le righe di gestione."),
    "CampionatoDesktop": (
        "Classifica generale con la zona playoff a sinistra, gare e gestione "
        "a destra. La zona e' NUOVA: oggi la classifica non la segna."),
    "PlayoffMobile": (
        "Dopo «Passa ai playoff» e «Avvia i playoff» (PlayoffService"
        ".start_playoff, scadenza 7 giorni): 8 inviti, chi rifiuta e' "
        "sostituito dal primo degli esclusi (find_replacement_player) e la "
        "riga lo dice. Su chi e' in attesa il direttore risponde per conto "
        "del giocatore dalla riga — «Accetta» e «Rifiuta», con conferma — "
        "come oggi in admin/campionato_detail.html "
        "(playoff_respond_for_player); la risposta resta registrata a suo "
        "nome. Con i confermati si crea la gara playoff (create_playoff_gara)."),
    "PlayoffDesktop": (
        "Invitati a sinistra, con «Accetta» e «Rifiuta» sulle righe in attesa "
        "(playoff_respond_for_player, con conferma); a destra la regola della "
        "classifica finale e la classifica congelata da cui nascono gli "
        "inviti, con la zona playoff."),
}


# ==========================================================================
# Registro: file, pagine, posizioni, bigliettini
# ==========================================================================

PHONE = (390, 844)
DESK = (1440, 900)
#: artboard desktop piu' alti di 900: pagine che scorrono
ALTEZZE = {"SetupDesktop": 1560}

# (stem, generatore | None se gia' scritto da gen_gara_direttore, titolo, pagina,
#  colonna, riga(0 telefono / 1 desktop), nota)
SCHERMATE = [
    # --- fase 1 ---
    ("SetupPanoramica", setup_panoramica, "1.1 Panoramica &mdash; in preparazione", "page-1", 0, 0,
     "Il direttore apre la gara appena creata. La fascia dice dove siamo, "
     "l'elenco dice cosa manca prima di poter aprire le iscrizioni. Il verde "
     "e' l'unica azione conclusiva della fase.\n\nI tavoli sono una voce "
     "della preparazione con il numero della sala (12/09): si scelgono "
     "sempre, di solito prima di avviare un turno. Gli esercizi fra i turni "
     "sono facoltativi e valgono anche con Amalfi (vedi pagina 0, "
     "decisione 4)."),
    ("SetupTurni", setup_turni, "1.2 Turni e distanze", "page-1", 1, 0,
     "Configurazione per turno (ADR-027). Il turno modificato si distingue "
     "dal default con la pastiglia, non con un fondo giallo pieno.\n\nOggi "
     "e' una griglia di card con select e campi numerici; qui distanza e "
     "disciplina sono campi larghi 58px, e il ripristino e' un'icona per turno."),
    ("SetupTavoli", setup_tavoli, "1.3 Tavoli", "page-1", 2, 0,
     "PROBLEMA VERO, non del mockup: oggi i tavoli si possono scegliere "
     "**solo a iscrizioni aperte** — lo vieta il template "
     "(_gara_tables_config.html) e lo vieta il servizio "
     "(GaraService.update_tables_config solleva ConflictError) — e si "
     "scrivono come «3, 1, 2» in un campo di testo. La regola vera (12/09): "
     "i tavoli si scelgono **sempre**, di solito prima di avviare un turno, "
     "perche' e' allora che si sa quanti ne servono. Qui sono tessere che si "
     "toccano nell'ordine di assegnazione.\n\nL'interruttore "
     "«assegna in base alla classifica» esiste solo con accoppiamento casuale."),
    ("SetupEsercizi", setup_esercizi, "1.4 Esercizi fra i turni", "page-1", 3, 0,
     "Gli esercizi fra i turni (GaraChallenge): quale, dopo che turno, quanti "
     "tentativi. Fanno una classifica a parte. Oggi il bottone compare solo "
     "col casuale, ma il limite sta nei template: il servizio accetta "
     "qualunque strategia. La X con esercizio e' un'altra cosa: sta in «Chi "
     "riposa» (pagina 0, decisione 4)."),
    ("SetupEserciziAggiungi", setup_esercizi_aggiungi, "1.5 Aggiungi un esercizio", "page-1", 4, 0,
     "Il foglio ha i tre campi del modale di oggi "
     "(_challenge_management_modal.html): l'esercizio, cercato per nome; "
     "dopo quale turno; quanti tentativi."),
    ("SetupDirettori", setup_direttori, "1.6 Co-direttori", "page-1", 5, 0,
     "La ricerca mostra solo utenti con ruolo direttore vicini alla sede "
     "(GaraService.add_director rifiuta gli altri). Il titolare e' marcato: "
     "un co-direttore puo' fare tutto tranne togliere lui.\n\nOggi e' un "
     "select con tutti i direttori in zona e un bottone «Aggiungi»."),
    ("SetupVetrina", setup_vetrina, "1.7 Vetrina", "page-1", 6, 0,
     "Locandina, indirizzo pubblico e link esterno: oggi vivono in una pagina "
     "separata (admin/gara_vetrina.html), raggiungibile dal menu. Qui e' una "
     "voce della preparazione, dove il direttore la cerca.\n\nLa locandina si "
     "vede intera (PR #292): niente ritaglio."),
    ("SetupApri", setup_apri, "1.8 Apri le iscrizioni", "page-1", 7, 0,
     "Il foglio di apertura: date nel fuso di chi scrive (ADR-043), minimo e "
     "massimo. La frase sotto il bottone dice cosa cambia per gli altri — e' "
     "il gesto che rende pubblica la gara.\n\nOggi il modale ha solo le due "
     "date; minimo e massimo stanno nella modifica gara, cioe' altrove."),
    ("SetupDesktop", setup_desktop, "1.9 La stessa fase su desktop", "page-1", 0, 1,
     "Su desktop la preparazione ci sta tutta: i quattro turni affiancati a "
     "sinistra, l'elenco di cosa manca a destra. Nessuna linguetta: sopra i "
     "992px le viste non esistono."),
    ("SetupTurniDesktop", setup_turni_desktop, "1.10 Turni e distanze su desktop", "page-1", 1, 1,
     "La pagina che si apre da «Modifica turni ed esercizi» in 1.9: i "
     "quattro turni con disciplina e distanza (ADR-027), e sotto gli "
     "esercizi fra i turni con il modulo di aggiunta in linea — i tre campi "
     "di _challenge_management_modal.html (esercizio, dopo quale turno, "
     "tentativi). Oggi gli esercizi stanno in Gestione, in un modale, e "
     "compaiono solo col casuale: il limite e' nei template."),

    # --- fase 2 ---
    ("IscrPanoramica", iscr_panoramica, "2.1 Panoramica &mdash; iscrizioni aperte", "page-2", 0, 0,
     "Il numero che conta e' «7 su 16, ne servono 8»: e' cio' che decide se "
     "la gara parte. L'avvio resta spento con scritto perche'.\n\nIl link "
     "pubblico e' qui e non in fondo alla Gestione: in questa fase "
     "condividerlo e' il lavoro principale."),
    ("IscrElenco", iscr_elenco, "2.2 Iscritti e lista d'attesa", "page-2", 1, 0,
     "Elenco raggruppato, non una card per iscritto. Categoria accanto al "
     "nome (serve con handicap, ADR-049); la lista d'attesa e' un gruppo a "
     "parte con «Fai entrare».\n\nLa disiscrizione manda una notifica: il "
     "mockup non mostra la conferma, che nell'app c'e'."),
    ("IscrAggiungi", iscr_aggiungi, "2.3 Iscrivi un giocatore", "page-2", 2, 0,
     "Ricerca per cognome, nome o username (PR #297). Il risultato e' una "
     "riga con «Iscrivi», non un menu a tendina da scorrere."),
    ("IscrScadute", iscr_scadute, "2.4 Iscrizioni scadute", "page-2", 3, 0,
     "Stato derivato, non salvato: la scadenza e' passata e gli iscritti non "
     "bastano. Le due uscite sono estendere o annullare, entrambe con "
     "notifica.\n\nSe invece il minimo e' raggiunto, la stessa schermata "
     "mostra «Avvia la gara» accanto a «Estendi»."),
    ("IscrAvvio", iscr_avvio, "2.5 Avvia la gara", "page-2", 4, 0,
     "Il foglio dice cosa succede **prima** che succeda: chi prende la X a "
     "tavolino, che i 4 turni nascono tutti adesso (Amalfi e casuale creano "
     "l'intero calendario all'avvio), in che ordine vanno i tavoli.\n\nOggi "
     "e' una conferma generica: il direttore scopre chi riposa dopo."),

    # --- fase 3 ---
    (None, None, "3.1 Panoramica &mdash; turno in corso", "page-3", 0, 0,
     "Artboard «Main»: la console del primo giro, riusata come panoramica "
     "della fase di gioco. Il punteggio si segna sulla card (scelta 3C del "
     "12/09: niente foglio), il tavolo e' sulla card, in fondo l'azione "
     "della fase. La card riassuntiva e' scura come la fascia (scelta 1B)."),
    ("GiocoTavolo", gioco_tavolo, "3.2 Assegna o cambia il tavolo", "page-3", 1, 0,
     "I tavoli occupati mostrano da chi. Nell'app la griglia c'e' gia', ma "
     "il tavolo occupato appariva grigio come «non disponibile» invece che "
     "evidenziato.\n\nSenza tavolo assegnato i comandi di punteggio restano "
     "spenti: e' una regola dell'app, non del mockup."),
    ("GiocoValida", gioco_valida, "3.3 Valida un risultato", "page-3", 2, 0,
     "Momento che nessuno dei tre mockup del primo giro mostrava. Quando i "
     "due giocatori chiudono la partita, il direttore valida: e' cio' che "
     "completa la partita e **libera il tavolo**.\n\nLa card verde e' l'unica "
     "che chiede qualcosa; le altre restano neutre."),
    ("GiocoCorreggi", gioco_correggi, "3.4 Correggi un risultato chiuso", "page-3", 3, 0,
     "Si puo' fare a gara in corso (issue #90). Il foglio dice le due "
     "conseguenze vere: i triangoli segnati uno per uno si cancellano, e la "
     "correzione resta scritta sulla partita.\n\nIl campo «perche'» e' "
     "facoltativo ma e' cio' che rende leggibile la correzione a chi aveva "
     "visto il risultato di prima."),
    ("GiocoClassifica", gioco_classifica, "3.5 Classifica dopo il turno", "page-3", 4, 0,
     "Prime sei o tutti, come nell'app. La nota in fondo spiega l'ordinamento "
     "e il valore della X a tavolino (una vittoria, zero differenza — "
     "SPECIFICHE.md righe 64 e 71).\n\nCon sistema RACK l'ordinamento e' un "
     "altro: la nota va scritta dal sistema di classifica, non fissa."),
    ("GiocoClassificaRack", gioco_classifica_rack, "3.6 Classifica (sistema RACK)", "page-3", 5, 0,
     "Lo stesso elenco quando il campionato ordina a triangoli (ADR-047): "
     "vinti e persi al posto di vinte e differenza. La freccia confronta la "
     "posizione col turno prima, in entrambi i sistemi."),
    ("GiocoTurnoDopo", gioco_turno_dopo, "3.7 Turno concluso", "page-3", 6, 0,
     "Le tre uscite del turno chiuso, separate per gravita': avviare il "
     "prossimo (verde), annullare l'avvio (possibile solo senza risultati), "
     "azzerare i risultati (distruttiva, fondo tenue).\n\nOggi sono tre "
     "bottoni della stessa forma, uno sotto l'altro."),
    ("GiocoMioMatch", gioco_mio_match, "3.8 Il direttore gioca", "page-3", 7, 0,
     "Se dirige ed e' iscritto, la sua partita e' la prima cosa: card scura "
     "con «Apri», che porta al segnapunti. Il resto del turno resta sotto, "
     "con i comandi da direttore.\n\nLa scorciatoia esiste gia' "
     "(_gara_my_match.html); qui convive con i comandi di direzione."),
    (None, None, "3.9 Il turno su desktop", "page-3", 0, 1,
     "Artboard «ConsoleDesktop»: le partite del turno a sinistra, in sei "
     "caselle — le cinque partite e il turno prima — che riempiono l'altezza; "
     "a destra «da fare adesso», i tavoli e la classifica dopo l'ultimo turno "
     "chiuso, fino in fondo. «Impostazioni gara» sale in testata: contiene "
     "solo direttori, vetrina e tavoli, le voci che si toccano in gioco. La "
     "partita da validare ha gli stepper attivi per correggere e «Valida» "
     "sotto, come oggi «Inserisci risultato» accanto alla spunta; e dice a "
     "chi passa il tavolo (release_and_reassign_table)."),

    # --- fase 4 ---
    ("SsrRilevato", ssr_rilevato, "4.1 Serve uno spareggio", "page-4", 0, 0,
     "L'app rileva i parimerito fino alla posizione configurata (qui la 3&ordf;). "
     "Prima di avviare lo spareggio la strada indietro c'e' ancora: azzerare "
     "il turno se un punteggio e' sbagliato."),
    ("SsrPunteggi", ssr_punteggi, "4.2 Inserisci i punti SSR", "page-4", 1, 0,
     "Un gruppo per posizione contesa. Gli stessi steppers del risultato: "
     "chi dirige usa un solo gesto in tutta l'app.\n\nLo spareggio ordina "
     "solo i pari merito — non tocca vittorie ne' differenza triangoli."),
    ("SsrTermina", ssr_termina, "4.3 Termina la gara", "page-4", 2, 0,
     "L'ultima azione, e cio' che comporta: classifica definitiva, punti al "
     "campionato, notifica ai giocatori. Accanto resta «Annulla lo spareggio», "
     "che riporta la gara in gioco azzerando i punti SSR."),

    # --- fase 5 ---
    ("FineClassifica", fine_classifica, "5.1 Classifica finale", "page-5", 0, 0,
     "A gara conclusa il soggetto e' la classifica, non la gestione. Il podio "
     "in card accento, il resto come elenco; la pastiglia SSR dice dove lo "
     "spareggio ha deciso l'ordine.\n\nLa linguetta «Gestione» sparisce: "
     "non contiene piu' niente (rilievo aperto in STATO.md)."),
    ("FineDopo", fine_dopo, "5.2 Cosa resta dopo", "page-5", 1, 0,
     "Dove sono finiti i punti, dov'e' la pagina pubblica, cosa non si tocca "
     "piu'. Serve a chiudere il ciclo invece di lasciare la pagina identica a "
     "prima ma spenta.\n\nScelta 5S del 12/09: le partite restano in pagina, "
     "turno per turno. La pagina pubblica mostra la classifica finale "
     "(vetrina_gara.html, `vetrina.conclusa`), per questo la riga lo dice."),

    # --- desktop delle altre fasi e schermo in sala (12/09) ---
    ("IscrDesktop", iscr_desktop, "2.6 La stessa fase su desktop", "page-2", 0, 1,
     "Iscrizioni su desktop: l'elenco a sinistra con la categoria, a destra il "
     "link da condividere, la lista d'attesa e le due cose da tenere d'occhio. "
     "L'avvio resta spento finche' manca il minimo."),
    ("SchermoSala", schermo_sala, "3.10 Schermo in sala (pubblico)", "page-3", 1, 1,
     "NUOVO, non esiste nell'app: la pagina pubblica della gara oggi rimanda "
     "alla pagina gara (routes/main.py, gara_detail_public) e la vetrina a "
     "gara in corso dice solo «Gara in corso». SPECIFICHE.md riga 357 chiede "
     "«i risultati dei match in tempo reale». In testa la locandina della "
     "vetrina (il banner 1200x630 di admin/gara_vetrina.html) a tutta "
     "larghezza, ritagliata al centro come nelle anteprime social, con nome "
     "della gara e turno sopra. Da leggere a tre metri: i tavoli riempiono "
     "l'altezza con i punteggi grandi, la classifica dopo l'ultimo turno "
     "chiuso e il turno prima stanno a destra. I dati arrivano dagli stessi "
     "eventi live della pagina gara (ADR-057). Per i tabelloni al posto "
     "della classifica va il tabellone: non disegnato."),
    ("SsrDesktop", ssr_desktop, "4.4 La stessa fase su desktop", "page-4", 0, 1,
     "Spareggio su desktop: gli stepper dei parimerito a sinistra, la "
     "classifica con la pastiglia PARI a destra. «Annulla lo spareggio» "
     "accanto a «Salva», come nell'app (riporta in gioco e azzera i punti SSR)."),
    ("FineDesktop", fine_desktop, "5.3 La stessa fase su desktop", "page-5", 0, 1,
     "Conclusa su desktop: il podio dentro la fascia, la classifica sotto, a "
     "destra dove sono finiti i punti e le partite turno per turno (scelta 5S)."),

    # --- pagina 7: campionato e playoff (12/09) ---
    ("CampionatoMobile", campionato_mobile, "7.1 Il campionato", "page-7", 0, 0,
     "La pagina del campionato per chi lo dirige: a che punto e' la "
     "stagione, la classifica generale con le tendenze, le gare, le righe di "
     "gestione. Oggi (campionato_detail.html) e' informazioni, direttori, "
     "statistiche, classifica, elenco gare in tabella, card playoff."),
    ("PlayoffMobile", playoff_mobile, "7.2 La fase playoff", "page-7", 1, 0,
     "Dopo «Passa ai playoff» (terminate_campionato) e «Avvia i playoff» "
     "(PlayoffService.start_playoff): gli inviti con scadenza a 7 giorni, chi "
     "rifiuta e' sostituito dal primo degli esclusi (find_replacement_player), "
     "il direttore puo' rispondere per un giocatore "
     "(playoff_respond_for_player). Con i confermati si crea la gara playoff "
     "(create_playoff_gara), che poi e' una gara come le altre; la modalita' "
     "di classifica finale e il peso sono di _playoff_scoring_form.html."),
    ("CampionatoDesktop", campionato_desktop, "7.3 Il campionato su desktop", "page-7", 0, 1,
     "Classifica generale a sinistra, gare e gestione a destra."),
    ("PlayoffDesktop", playoff_desktop, "7.4 La fase playoff su desktop", "page-7", 1, 1,
     "Invitati a sinistra; a destra la regola della classifica finale "
     "(campionato + playoff con peso, oppure solo il playoff) e la classifica "
     "congelata da cui nascono gli inviti."),

    # --- pagina 6: le tre direzioni del primo giro ---
    (None, None, "A &middot; Regia &mdash; telefono", "page-6", 0, 0, None),
    (None, None, "C &middot; Fasi &mdash; telefono", "page-6", 1, 0, None),
    (None, None, "A &middot; Regia &mdash; desktop", "page-6", 0, 1, None),
    (None, None, "C &middot; Fasi &mdash; desktop", "page-6", 1, 1, None),
]

# gli artboard gia' esistenti, nell'ordine in cui compaiono in SCHERMATE con stem None
ESISTENTI = ["Main.dc.html", "ConsoleDesktop.dc.html",
             "RegiaMobile.dc.html", "FasiMobile.dc.html",
             "RegiaDesktop.dc.html", "FasiDesktop.dc.html"]

PAGINE = [
    {"id": "page-1", "name": "1 · Preparazione"},
    {"id": "page-2", "name": "2 · Iscrizioni"},
    {"id": "page-3", "name": "3 · Gioco"},
    {"id": "page-4", "name": "4 · Spareggio"},
    {"id": "page-5", "name": "5 · Conclusa"},
    {"id": "page-6", "name": "Direzioni (primo giro)"},
    {"id": "page-7", "name": "7 · Campionato e playoff"},
]

COL_PHONE = 560
COL_DESK = 1600
ROW_DESK_Y = 1010


def main():
    base.main()  # riscrive i sei artboard delle direzioni + il loro canvas.json

    artboards, note = [], []
    esistenti = iter(ESISTENTI)

    for stem, fn, titolo, pagina, colonna, riga, testo in SCHERMATE:
        testo = NOTE_REVISIONE.get(stem or "", testo)
        if stem is None:
            nome = next(esistenti)
        else:
            nome = f"{stem}.dc.html"
            (SRC / nome).write_text(fn(), encoding="utf-8")

        if riga == 0:
            x, y, (w, h) = colonna * COL_PHONE, 0, PHONE
            note_y = -260
        else:
            x, y, (w, h) = colonna * COL_DESK, ROW_DESK_Y, DESK
            h = ALTEZZE.get(stem or "", h)
            note_y = ROW_DESK_Y - 260

        artboards.append({"file": nome, "title": titolo, "page": pagina,
                          "x": x, "y": y, "w": w, "h": h})
        if testo:
            note.append({"id": f"nota-{(stem or nome.split('.')[0]).lower()}",
                         "page": pagina, "x": x, "y": note_y, "w": 470,
                         "text": testo})

    # i bigliettini delle tre direzioni restano quelli del primo giro
    for n in base.CANVAS["annotations"]:
        n = dict(n)
        n["page"] = "page-6"
        n["x"] = {"nota-a": 0, "nota-c": COL_PHONE, "nota-b": COL_PHONE * 2}[n["id"]]
        n["y"] = -260
        note.append(n)

    canvas = {"pages": PAGINE, "artboards": artboards, "annotations": note,
              "launch": {"view": "canvas", "page": "page-3"}}
    (SRC / "canvas.json").write_text(
        json.dumps(canvas, ensure_ascii=False, indent=2), encoding="utf-8")

    scritti = [a["file"] for a in artboards]
    print(f"{len(set(scritti))} artboard su {len(PAGINE)} pagine, "
          f"{len(note)} bigliettini")
    print("--artboard " + " --artboard ".join(dict.fromkeys(scritti)))


if __name__ == "__main__":
    main()
