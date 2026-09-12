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
"""
    return doc(phone(SUB, TABS_SETUP, content))


def setup_tavoli():
    griglia = "".join([
        tavolo_chip("3", "scelto", "1&deg; scelta"),
        tavolo_chip("1", "scelto", "2&deg; scelta"),
        tavolo_chip("2", "scelto", "3&deg; scelta"),
        tavolo_chip("4", "libero", "tocca per usarlo"),
        tavolo_chip("5", "spento"),
        tavolo_chip("6", "spento"),
    ])
    content = f"""
      {sec("Tavoli della gara", "6 in sala")}
      <div style="font-size:13px;font-weight:600;color:var(--c7-ink-muted);line-height:1.45">
        Tocca i tavoli da usare, nell'ordine in cui vuoi assegnarli.
        Il primo scelto va alla partita di cartello.
      </div>
      <section class="card">
        <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px">{griglia}</div>
        <hr class="divider">
        {toggle("Assegna i tavoli in base alla classifica", False,
                "Dal secondo turno il primo tavolo va al match con il giocatore "
                "meglio piazzato. Disponibile solo con accoppiamento casuale.")}
      </section>
      {btn("Salva i tavoli", "primary", "check")}
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


def setup_desktop():
    sinistra = f"""
        <div class="stack">
          <section class="card card--accent" style="display:flex;align-items:center;
                   gap:22px;padding:20px 22px">
            <div class="grow">
              <div class="kicker">In preparazione</div>
              <h3 style="margin-top:4px;font-size:20px">Nessuno vede ancora la gara</h3>
              <div style="margin-top:6px;font-size:13px;font-weight:600;
                   color:var(--c7-accent-dim)">
                Resta da fare la vetrina. 4 tavoli nella sala, tutti in uso.</div>
            </div>
            <button class="btn btn--success">{ico(I["play"], 16)} Apri iscrizioni</button>
          </section>

          {sec("Configurazione turni", "Ripristina i default")}
          <section class="card">
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
              {"".join(f'''
              <div class="card--sunk" style="border-radius:var(--c7-r-card);padding:14px">
                <div class="row"><strong class="grow" style="font-size:14px;white-space:nowrap">Turno {n}</strong>
                  <span class="state state--{"warn" if n == 2 else "muted"}">{"modificato" if n == 2 else "default"}</span></div>
                <div style="margin-top:10px;display:grid;
                     grid-template-columns:1fr 92px;gap:10px">
                  {field("Disciplina", "Palla 9" if n == 2 else "Palla 8")}
                  {field("Triangoli", "3" if n == 2 else "5", mono=True)}
                </div>
              </div>''' for n in (1, 2, 3, 4))}
            </div>
          </section>

          {sec("Impostazioni di gioco", "Modifica gara")}
          {rows(
            row(I["grid"], "Accoppiamento", "Amalfi &middot; anti-reincontro attivo")
            + row(I["scale"], "Chi riposa", "X a tavolino all'ultimo iscritto")
            + row(I["crown"], "Apertura", "acchito &mdash; chi vince sceglie chi apre"))}
        </div>
"""
    destra = f"""
        <div class="stack">
          {sec("Da preparare", "3 di 4")}
          {rows(
            row(I["list"], "Turni e distanze", "4 turni &middot; Palla 8 &middot; al 5", tone="ok")
            + row(I["users"], "Direzione di gara", "solo tu", tone="ok")
            + row(I["table"], "Tavoli", "con le iscrizioni aperte", tone="locked")
            + row(I["share"], "Vetrina", "nessuna locandina", tone="warn"))}

          {sec("Informazioni gara", "Modifica")}
          <section class="card">
            <div style="display:grid;grid-template-columns:auto 1fr;gap:9px 16px;font-size:13px">
              <span class="muted">Sala</span><span style="font-weight:800">Biliardo Mimmo</span>
              <span class="muted">Data</span><span class="num">gio 3 set 2026, 20:00</span>
              <span class="muted">Accoppiamento</span><span style="font-weight:800">Amalfi</span>
              <span class="muted">Partecipanti</span><span class="num">8&ndash;16</span>
              <span class="muted">Chi riposa</span><span style="font-weight:800">Ultimo iscritto</span>
            </div>
          </section>
        </div>
"""
    content = f'<div class="cols">{sinistra}{destra}</div>'
    actions = ('<button class="btn btn--secondary btn--sm">'
               f'{ico(I["gear"], 15)} Modifica gara</button>')
    return doc(desktop(actions, content))


# ==========================================================================
# FASE 2 — ISCRIZIONI (gara.status = inscription)
# ==========================================================================

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


def iscr_elenco():
    elenco = (
        person("PA", "pa", "iscritto il 28/08 &middot; A",
               f'<button class="iconbtn">{ico(I["minus"], 14)}</button>')
        + person("MR", "m.rossi", "iscritto il 28/08 &middot; A",
                 f'<button class="iconbtn">{ico(I["minus"], 14)}</button>')
        + person("GV", "g.verdi", "iscritto il 29/08 &middot; B",
                 f'<button class="iconbtn">{ico(I["minus"], 14)}</button>')
        + person("DB", "d.bianchi", "iscritto il 29/08 &middot; B",
                 f'<button class="iconbtn">{ico(I["minus"], 14)}</button>'))
    content = f"""
      <div class="sechead">
        <h3>Iscritti</h3>
        <span class="state state--accent">7 attivi</span>
        <span class="state state--warn">+1 in attesa</span>
      </div>
      {rows(elenco)}

      <div class="sechead" style="margin-top:4px">
        <h3 class="muted">Lista d'attesa</h3>
      </div>
      {rows(person("SC", "s.conti", "in lista dal 30/08",
                   '<button class="btn btn--secondary btn--sm">Fai entrare</button>'))}

      {btn("Iscrivi un giocatore", "secondary", "plus")}
"""
    return doc(phone(SUB, TABS_ISCR2, content))


def iscr_aggiungi():
    corpo = f"""
    <div class="stack">
      {field("Cognome, nome o username", CURSORE % "ferr")}
      {rows(
        person("LF", "l.ferrari", "Luca Ferrari &middot; Biliardo Mimmo",
               '<button class="btn btn--secondary btn--sm">Iscrivi</button>')
        + person("AF", "a.ferrero", "Anna Ferrero &middot; Sala Nuova",
                 '<button class="btn btn--secondary btn--sm">Iscrivi</button>'))}
      <div style="font-size:12px;font-weight:600;color:var(--c7-ink-muted);text-align:center">
        2 giocatori trovati
      </div>
    </div>"""
    content = f"""
      <div class="sechead">
        <h3>Iscritti</h3>
        <span class="state state--accent">7 attivi</span>
      </div>
      {rows(person("PA", "pa", "iscritto il 28/08 &middot; A")
            + person("MR", "m.rossi", "iscritto il 28/08 &middot; A"))}
"""
    return doc(phone(SUB, TABS_ISCR2, content,
                     overlay=sheet("Iscrivi un giocatore", corpo, "")))


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

def gioco_tavolo():
    griglia = "".join([
        tavolo_chip("3", "occupato", "m.rossi"),
        tavolo_chip("1", "occupato", "d.bianchi"),
        tavolo_chip("2", "libero"),
    ])
    corpo = f"""
    <div class="stack">
      <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px">{griglia}</div>
      <div style="font-size:12px;font-weight:600;color:var(--c7-ink-muted);line-height:1.45">
        I tavoli occupati si liberano quando il risultato &egrave; validato.
      </div>
    </div>"""
    content = f"""
      {sec("Turno 2")}
      {base.stepper_card("m.rossi", "4", "g.verdi", "2", "3")}
"""
    return doc(phone(SUB, TABS_GIOCO, content,
                     overlay=sheet("Assegna il tavolo", corpo,
                                   btn("Assegna il tavolo 2", "primary", "check"),
                                   "s.conti vs p.marini")))


def gioco_valida():
    content = f"""
      {sec("Turno 2", "2 da validare")}

      <article class="card card--ok">
        <div class="row" style="justify-content:space-between">
          <span class="state state--ok">Chiusa dai giocatori</span>
          <span style="font-size:12px">Tavolo <span class="num">3</span></span>
        </div>
        <div class="row" style="margin-top:12px">
          <div class="grow" style="font-size:14px;font-weight:800">m.rossi
            <span class="num" style="font-size:19px">5</span></div>
          <div style="font-size:14px;font-weight:800;color:var(--c7-ink-muted)">g.verdi
            <span class="num" style="font-size:19px">2</span></div>
        </div>
        <div style="margin-top:12px">{btn("Valida il risultato", "success", "check")}</div>
        <div style="margin-top:8px;font-size:12px;font-weight:600;color:var(--c7-ok-body);
             line-height:1.45">
          Completa la partita e libera il tavolo 3.
        </div>
      </article>

      <article class="card">
        <div class="row" style="justify-content:space-between">
          <span class="state state--accent">In corso</span>
          <span class="muted" style="font-size:12px">Tavolo <span class="num">1</span></span>
        </div>
        <div class="row" style="margin-top:12px">
          <div class="grow" style="font-size:14px;font-weight:800">d.bianchi
            <span class="num" style="font-size:19px">3</span></div>
          <div style="font-size:14px;font-weight:800">l.ferrari
            <span class="num" style="font-size:19px">3</span></div>
        </div>
      </article>
"""
    return doc(phone(SUB, TABS_GIOCO, content))


def gioco_correggi():
    corpo = f"""
    <div class="stack">
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
        {stepper("a.galli", "5")}
        {stepper("r.neri", "1")}
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
      <article class="card card--locked">
        <div class="row" style="justify-content:space-between">
          <span class="state state--ok">Conclusa</span>
          <span style="font-size:12px">Tavolo <span class="num">3</span></span>
        </div>
        <div class="row" style="margin-top:12px">
          <div class="grow" style="font-size:14px;font-weight:800;color:var(--c7-ink)">a.galli
            <span class="num" style="font-size:19px">1</span></div>
          <div style="font-size:14px;font-weight:800">r.neri
            <span class="num" style="font-size:19px">5</span></div>
        </div>
      </article>
"""
    return doc(phone(SUB, TABS_GIOCO, content,
                     overlay=sheet("Correggi il risultato", corpo,
                                   btn("Correggi il risultato", "primary", "check"),
                                   "a.galli vs r.neri &middot; turno 1")))


def gioco_classifica():
    righe = [("1", "m.rossi", "2", "+7", ""), ("2", "a.galli", "2", "+4", ""),
             ("3", "d.bianchi", "1", "+1", ""), ("4", "l.ferrari", "1", "0", ""),
             ("5", "g.verdi", "1", "-2", ""), ("6", "p.marini", "0", "-5", "")]
    content = f"""
      <div class="sechead">
        <h3>Classifica</h3>
        <span class="sechead__note muted" style="font-size:12px;font-weight:700">dopo il turno 2</span>
      </div>
      <div style="display:flex;gap:6px">
        <button class="vtab is-active" style="flex:1">Prime 6</button>
        <button class="vtab" style="flex:1">Tutti (10)</button>
      </div>
      {classifica(righe)}
      <div style="font-size:12px;font-weight:600;color:var(--c7-ink-muted);line-height:1.45">
        Ordinata per vittorie, poi differenza triangoli. La X a tavolino vale
        una vittoria e zero differenza.
      </div>
"""
    return doc(phone(SUB, TABS_CLASS, content))


def gioco_turno_dopo():
    corpo = ("""
        <div style="margin-top:10px;font-size:13px;font-weight:600;
             color:var(--c7-accent-dim);line-height:1.45">
          Tutte e 5 le partite sono validate. Gli abbinamenti del turno 3
          sono gi&agrave; fissati dal sorteggio iniziale.</div>""")
    azione = ('<div style="margin-top:14px">'
              + btn("Avvia il turno 3", "success", "play") + "</div>")
    content = f"""
      {band("Turno 2 di 4 &middot; concluso", "Puoi avviare il turno 3", corpo, azione)}

      {sec("Se qualcosa non torna")}
      <section class="card stack">
        {btn("Annulla l'avvio del turno 2", "secondary", "rotate")}
        <div style="font-size:12px;font-weight:600;color:var(--c7-ink-muted);line-height:1.45">
          Si pu&ograve; solo finch&eacute; nessun risultato del turno &egrave; inserito.
        </div>
        <hr class="divider">
        {btn("Azzera i risultati del turno 2", "danger", "rotate")}
        <div style="font-size:12px;font-weight:600;color:var(--c7-ink-muted);line-height:1.45">
          Le partite tornano da giocare, gli abbinamenti restano.
        </div>
      </section>
"""
    return doc(phone(SUB, TABS_GEST, content))


def gioco_mio_match():
    content = f"""
      <section class="card card--accent c7-shortcut" style="display:flex;
               align-items:center;gap:14px">
        <div class="grow">
          <div class="kicker">Il tuo match &middot; tavolo 1</div>
          <div style="margin-top:4px;font-size:15px;font-weight:800">pa vs l.ferrari</div>
          <div class="num" style="margin-top:4px;font-size:17px;font-weight:800">3 &ndash; 2</div>
        </div>
        <span class="btn btn--bright btn--sm" style="height:42px">Apri</span>
      </section>

      {sec("Turno 2")}
      {base.stepper_card("m.rossi", "4", "g.verdi", "2", "3")}
      {base.pending_card("s.conti", "p.marini")}
"""
    return doc(phone(SUB, TABS_GIOCO, content))


# ==========================================================================
# FASE 4 — SPAREGGIO (gara.status = awaiting_ssr)
# ==========================================================================

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

def fine_classifica():
    podio = """
      <section class="card card--accent">
        <div class="kicker">Classifica finale</div>
        <div style="margin-top:12px;display:grid;grid-template-columns:1fr 1fr 1fr;
             gap:10px;align-items:end;text-align:center">
          <div>
            <div class="avatar avatar--lg" style="margin:0 auto;background:rgba(242,248,247,.16)">AG</div>
            <div style="margin-top:8px;font-size:13px;font-weight:800">a.galli</div>
            <div class="num" style="font-size:12px;color:var(--c7-accent-dim)">2&deg;</div>
          </div>
          <div>
            <div class="avatar avatar--lg" style="margin:0 auto;background:var(--c7-accent-bright);
                 color:#0D2A36;width:56px;height:56px;font-size:16px">MR</div>
            <div style="margin-top:8px;font-size:15px;font-weight:800">m.rossi</div>
            <div class="num" style="font-size:12px;color:var(--c7-accent-bright)">1&deg;</div>
          </div>
          <div>
            <div class="avatar avatar--lg" style="margin:0 auto;background:rgba(242,248,247,.16)">DB</div>
            <div style="margin-top:8px;font-size:13px;font-weight:800">d.bianchi</div>
            <div class="num" style="font-size:12px;color:var(--c7-accent-dim)">3&deg; &middot; SSR</div>
          </div>
        </div>
      </section>"""
    righe = [("4", "l.ferrari", "3", "+2", "SSR"), ("5", "g.verdi", "2", "-1", ""),
             ("6", "p.marini", "2", "-3", "")]
    content = f"""
      {podio}
      {classifica(righe)}
      <div class="flash flash--ok">
        <span class="flash__ico">{ico(I["check"], 14)}</span>
        <div><div class="flash__title">Gara conclusa</div>
          <div>I punti sono andati alla classifica del campionato.
            I punteggi non si modificano pi&ugrave;.</div></div>
      </div>
"""
    return doc(phone(SUB, vtabs(["Turni", "Classifica", "Iscritti"], "Classifica"), content))


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
# Registro: file, pagine, posizioni, bigliettini
# ==========================================================================

PHONE = (390, 844)
DESK = (1440, 900)

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
    ("SetupDirettori", setup_direttori, "1.4 Co-direttori", "page-1", 3, 0,
     "La ricerca mostra solo utenti con ruolo direttore vicini alla sede "
     "(GaraService.add_director rifiuta gli altri). Il titolare e' marcato: "
     "un co-direttore puo' fare tutto tranne togliere lui.\n\nOggi e' un "
     "select con tutti i direttori in zona e un bottone «Aggiungi»."),
    ("SetupVetrina", setup_vetrina, "1.5 Vetrina", "page-1", 4, 0,
     "Locandina, indirizzo pubblico e link esterno: oggi vivono in una pagina "
     "separata (admin/gara_vetrina.html), raggiungibile dal menu. Qui e' una "
     "voce della preparazione, dove il direttore la cerca.\n\nLa locandina si "
     "vede intera (PR #292): niente ritaglio."),
    ("SetupApri", setup_apri, "1.6 Apri le iscrizioni", "page-1", 5, 0,
     "Il foglio di apertura: date nel fuso di chi scrive (ADR-043), minimo e "
     "massimo. La frase sotto il bottone dice cosa cambia per gli altri — e' "
     "il gesto che rende pubblica la gara.\n\nOggi il modale ha solo le due "
     "date; minimo e massimo stanno nella modifica gara, cioe' altrove."),
    ("SetupDesktop", setup_desktop, "1.7 La stessa fase su desktop", "page-1", 0, 1,
     "Su desktop la preparazione ci sta tutta: i quattro turni affiancati a "
     "sinistra, l'elenco di cosa manca a destra. Nessuna linguetta: sopra i "
     "992px le viste non esistono."),

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
    ("GiocoTurnoDopo", gioco_turno_dopo, "3.6 Turno concluso", "page-3", 5, 0,
     "Le tre uscite del turno chiuso, separate per gravita': avviare il "
     "prossimo (verde), annullare l'avvio (possibile solo senza risultati), "
     "azzerare i risultati (distruttiva, fondo tenue).\n\nOggi sono tre "
     "bottoni della stessa forma, uno sotto l'altro."),
    ("GiocoMioMatch", gioco_mio_match, "3.7 Il direttore gioca", "page-3", 6, 0,
     "Se dirige ed e' iscritto, la sua partita e' la prima cosa: card scura "
     "con «Apri», che porta al segnapunti. Il resto del turno resta sotto, "
     "con i comandi da direttore.\n\nLa scorciatoia esiste gia' "
     "(_gara_my_match.html); qui convive con i comandi di direzione."),
    (None, None, "3.8 Il turno su desktop", "page-3", 0, 1,
     "Artboard «ConsoleDesktop»: le partite a sinistra, «da fare adesso» e i "
     "tavoli a destra."),

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
]

COL_PHONE = 560
COL_DESK = 1600
ROW_DESK_Y = 1010


def main():
    base.main()  # riscrive i sei artboard delle direzioni + il loro canvas.json

    artboards, note = [], []
    esistenti = iter(ESISTENTI)

    for stem, fn, titolo, pagina, colonna, riga, testo in SCHERMATE:
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
              "launch": {"view": "canvas", "page": "page-1"}}
    (SRC / "canvas.json").write_text(
        json.dumps(canvas, ensure_ascii=False, indent=2), encoding="utf-8")

    scritti = [a["file"] for a in artboards]
    print(f"{len(set(scritti))} artboard su {len(PAGINE)} pagine, "
          f"{len(note)} bigliettini")
    print("--artboard " + " --artboard ".join(dict.fromkeys(scritti)))


if __name__ == "__main__":
    main()
