#!/usr/bin/env python3
"""Canvas «Pagina gara del direttore» — la pagina delle decisioni.

Le cinque decisioni aperte dello STATO («Da decidere»), una riga ciascuna:
le alternative stanno fianco a fianco e portano **gli stessi dati** — cambia
solo dove stanno le cose e che comando hanno. Cosi' si giudica la forma, non
il contenuto. Le risposte del 12/09/2026 stanno nei bigliettini («SCELTA»)
e sono gia' applicate alle pagine 1-5; qui restano le alternative scartate,
per memoria, e i due punti che le risposte hanno aperto (decisioni 2 e 4).

Riusa i mattoni di gen_fasi.py e gen_gara_direttore.py. Scrive gli artboard
Dec*.dc.html e aggiunge la pagina «0 · Decisioni» in testa al canvas.json
che gen_fasi.main() ha appena riscritto. E' l'unico comando da lanciare:

    python3 sorgenti/gen_decisioni.py
"""

import json

import gen_fasi as F
import gen_gara_direttore as base
from gen_gara_direttore import CONSOLE_HEAD, I, doc, ico, phone

SRC = F.SRC
SUB = F.SUB
TABS4 = F.TABS_GIOCO
TABS_SETUP = F.TABS_SETUP

# --------------------------------------------------------------------------
# I dati del turno in gioco, uguali in ogni variante
# --------------------------------------------------------------------------

STATE_LIVE = '<span class="state state--accent">In corso</span>'
STATE_TODO = '<span class="state state--warn">Da giocare</span>'

ICO_MORE = ('<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">'
            '<circle cx="5" cy="12" r="2"/><circle cx="12" cy="12" r="2"/>'
            '<circle cx="19" cy="12" r="2"/></svg>')


def tavolo_txt(n):
    return (f'<span class="muted" style="font-size:12px">Tavolo '
            f'<span class="num">{n}</span></span>')


def cards_regia():
    """Le card di oggi: stato a sinistra, tavolo a destra, punteggio sotto."""
    return (base.match_card("m.rossi", "4", "g.verdi", "2", STATE_LIVE, tavolo_txt(1))
            + base.match_card("d.bianchi", "3", "l.ferrari", "3", STATE_LIVE, tavolo_txt(2))
            + base.match_card("s.conti", "0", "p.marini", "0", STATE_TODO,
                              '<button class="btn btn--warn btn--sm">Assegna tavolo</button>'))


def cards_console():
    """Le card della console: il punteggio si segna qui."""
    return (base.stepper_card("m.rossi", "4", "g.verdi", "2", "1")
            + base.stepper_card("d.bianchi", "3", "l.ferrari", "3", "2")
            + base.pending_card("s.conti", "p.marini"))


ACTIONBAR = f"""
  <div class="actionbar">
    <button class="btn btn--locked">{ico(I["play"], 16)} Avvia turno 3 &middot; 3 aperte</button>
  </div>
"""


def todo_accent(icon, testo):
    return f"""
          <div class="row" style="gap:10px">
            <span class="tile tile--sm" style="background:rgba(242,248,247,.14);
                  color:var(--c7-accent-bright)">{ico(icon, 15)}</span>
            <div class="grow" style="font-size:13px;font-weight:700">{testo}</div>
            <span style="color:var(--c7-accent-bright)">{ico(I["chevron"], 15)}</span>
          </div>"""


FASI_BAND = f"""
      <section class="card card--accent">
        <div class="kicker">Turno 2 di 4</div>
        <h3 style="margin-top:5px;font-size:19px">Mancano 3 partite</h3>
        <div class="row" style="margin-top:12px;gap:10px">
          <div class="num" style="font-size:13px;color:var(--c7-accent-bright)">2/5</div>
          <div class="bar grow"><div class="bar__fill" style="width:40%"></div></div>
        </div>
        <div class="stack" style="margin-top:14px;gap:8px">
          {todo_accent(I["table"], "1 tavolo da assegnare")}
          {todo_accent(I["clock"], "2 risultati mancanti")}
        </div>
      </section>
"""

TOGGLE_PARTITE = """
      <div style="display:flex;gap:6px">
        <button class="vtab is-active" style="flex:1">Partite</button>
        <button class="vtab" style="flex:1">Classifica</button>
      </div>
"""


def sechead_turno(n, stato, cls="", menu=False):
    tone = "state--accent" if stato == "In corso" else "state--muted"
    more = (f'<button class="iconbtn" style="background:var(--c7-card)">{ICO_MORE}</button>'
            if menu else "")
    return f"""
      <div class="sechead" style="margin-top:4px;align-items:center">
        <h3 class="{cls}">Turno {n}</h3>
        <span class="state {tone}" style="margin-left:auto">{stato}</span>
        {more}
      </div>"""


TURNO1 = F.partite_turno(1, base.R1)

# --------------------------------------------------------------------------
# La striscia di fase (decisione 2): quattro fasi non ci stanno con le
# etichette in 354 px, quindi le inattive mostrano solo l'icona. Lo
# spareggio compare solo nelle gare che ce l'hanno.
# --------------------------------------------------------------------------

FASI = [("prep", "gear", "Preparazione"), ("iscr", "users", "Iscrizioni"),
        ("gioco", "play", "In gioco"), ("ssr", "scale", "Spareggio"),
        ("fine", "flag", "Chiusura")]


def strip_bar(attiva, spareggio=False):
    """Sta al posto delle linguette, nello stesso slot del guscio."""
    fasi = [f for f in FASI if f[0] != "ssr" or spareggio or attiva == "ssr"]
    idx = [k for k, _, _ in fasi].index(attiva)
    parts = []
    for i, (key, icon, label) in enumerate(fasi):
        if i > 0:
            parts.append('<div style="height:2px;flex:1;background:var(--c7-line)"></div>')
        if i < idx:
            parts.append(
                '<div class="pill" style="height:34px;width:34px;padding:0;'
                'justify-content:center;background:var(--c7-ok-bg);color:var(--c7-ok-ink)">'
                f'{ico(I["check"], 14)}</div>')
        elif i == idx:
            parts.append(
                '<div class="pill is-active" style="height:34px;font-size:12px;padding:0 14px">'
                f'{ico(I[icon], 13)} {label}</div>')
        else:
            parts.append(
                '<div class="pill" style="height:34px;width:34px;padding:0;'
                f'justify-content:center;color:var(--c7-ink-faint)">{ico(I[icon], 13)}</div>')
    return ('<div style="display:flex;align-items:center;gap:8px;padding:14px 18px 12px">'
            + "".join(parts) + "</div>")


# --------------------------------------------------------------------------
# La preparazione: il contenuto della sintesi (1.1), con le voci a scelta
# --------------------------------------------------------------------------

def setup_content(esercizi="nessuno &mdash; facoltativo", esercizi_tone="neutral",
                  riposa="X a tavolino all'ultimo iscritto"):
    corpo = ("""
        <div style="margin-top:10px;font-size:13px;font-weight:600;
             color:var(--c7-accent-dim);line-height:1.45">
          Quando apri le iscrizioni la gara diventa pubblica e chi &egrave; in
          zona riceve la notifica.</div>""")
    azione = ('<div style="margin-top:14px">'
              + F.btn("Apri iscrizioni", "success", "play") + "</div>")
    return f"""
      {F.band("In preparazione", "Nessuno vede ancora la gara", corpo, azione)}

      {F.sec("Da preparare", "3 di 4")}
      {F.rows(
        F.row(I["list"], "Turni e distanze", "4 turni &middot; Palla 8 &middot; al 5", tone="ok")
        + F.row(I["users"], "Direzione di gara", "solo tu &mdash; aggiungi un co-direttore", tone="ok")
        + F.row(I["table"], "Tavoli", "4 nella sala &middot; tutti in uso", tone="ok")
        + F.row(I["target"], "Esercizi fra i turni", esercizi, tone=esercizi_tone)
        + F.row(I["share"], "Vetrina", "nessuna locandina", tone="warn"))}

      {F.sec("Impostazioni di gioco")}
      {F.rows(
        F.row(I["grid"], "Accoppiamento", "Amalfi &middot; anti-reincontro attivo", tone="neutral")
        + F.row(I["scale"], "Chi riposa", riposa, tone="neutral")
        + F.row(I["crown"], "Apertura", "acchito &mdash; chi vince sceglie", tone="neutral"))}
"""


def regia_setup_content():
    """A in preparazione: la Gestione di oggi (_gara_management, _gara_directors,
    _round_management) con la fascia sopra. Tavoli e vetrina non ci sono
    perche' oggi non ci sono: i tavoli si modificano solo a iscrizioni
    aperte, la vetrina e' una pagina del menu."""
    fascia = F.band(
        "In preparazione", "Nessuno vede ancora la gara",
        '<div style="margin-top:10px;font-size:13px;font-weight:600;'
        'color:var(--c7-accent-dim);line-height:1.45">Manca la vetrina. '
        'I tavoli si scelgono con le iscrizioni aperte.</div>')
    gestione = f"""
      <section class="card stack">
        <h3>Gestione</h3>
        {F.btn("Apri Iscrizioni", "success", "play")}
        <div class="num" style="background:var(--c7-sunken);border-radius:var(--c7-r-field);
             padding:14px 16px;font-size:13px;font-weight:700;color:var(--c7-ink-soft)">
          torneibiliardo.it/g/gara-3-giovedi</div>
        <div style="display:flex;gap:10px">
          {F.btn("Copia", "secondary", "link")}{F.btn("Condividi", "primary", "share")}
        </div>
      </section>"""
    direttori = f"""
      <section class="card stack">
        <h3>Direttori</h3>
        {F.rows(F.person("PA", "pa", "titolare", '<span class="state state--muted">tu</span>'))}
        {F.field("Aggiungi un co-direttore", 'Scegli un direttore&hellip; <span class="faint" style="margin-left:auto">&#9662;</span>')}
        {F.btn("Aggiungi", "secondary", "plus")}
      </section>"""

    def kv(k, v):
        return (f'<div><div class="kicker">{k}</div>'
                f'<div style="margin-top:4px;font-size:14px;font-weight:800">{v}</div></div>')

    def turno(n):
        return f"""
        <div class="card--sunk" style="border-radius:var(--c7-r-card);padding:14px">
          <div class="row" style="gap:8px">
            <strong class="grow" style="font-size:14px">Turno {n}</strong>
            <span class="state state--muted">Al 5</span>
            <button class="iconbtn" style="background:var(--c7-card)">{ico(I["rotate"], 14)}</button>
          </div>
          <div style="margin-top:12px">
            {F.field("Disciplina", 'Palla 8 (default) <span class="faint" style="margin-left:auto">&#9662;</span>')}
          </div>
          <div style="margin-top:12px">
            {F.field("Distanza", "5", mono=True)}
          </div>
        </div>"""

    turni = f"""
      <section class="card stack">
        <h3>Configurazione turni</h3>
        <div style="font-size:12px;font-weight:600;color:var(--c7-ink-muted);line-height:1.45">
          Puoi configurare disciplina e distanza diverse per ciascun turno.</div>
        <div class="card--sunk" style="border-radius:var(--c7-r-field);padding:14px;
             display:grid;grid-template-columns:1fr 1fr;gap:12px">
          {kv("Strategia", "Amalfi")}{kv("Turni totali", '<span class="num">4</span>')}
          {kv("Disciplina", "Palla 8")}{kv("Distanza", "Al 5")}
          {kv("Anti-reincontro", '<span style="color:var(--c7-ok)">Abilitato</span>')}
          {kv("Giocatori dispari", "X ultimo iscritto")}
        </div>
        {turno(1)}{turno(2)}
      </section>"""
    return fascia + gestione + direttori + turni


# --------------------------------------------------------------------------
# Decisione 1 — la forma (scelta: 1B in gioco con la card scura, 1S in preparazione)
# --------------------------------------------------------------------------

def dec1_a():
    content = (base.REGIA_BAND_MOBILE + sechead_turno(2, "In corso")
               + cards_regia() + TURNO1)
    return doc(phone(SUB, TABS4, content))


def dec1_b():
    content = CONSOLE_HEAD + cards_console() + TURNO1
    return doc(phone(SUB, TABS4, content, ACTIONBAR))


def dec1_c():
    content = (base.PHASE_STRIP + FASI_BAND + TOGGLE_PARTITE + cards_regia() + TURNO1
               + f"""
      <div class="rows">
        {base.todo_row(I["users"], "Iscritti", "10 attivi, nessuna riserva", "neutral")}
        {base.todo_row(I["gear"], "Impostazioni gara", "direttori, tavoli, squadre, turni", "neutral")}
      </div>""")
    return doc(phone(SUB, "", content))


def dec1_a_setup():
    return doc(phone(SUB, TABS_SETUP, regia_setup_content()))


def dec1_s_setup():
    return doc(phone(SUB, TABS_SETUP, setup_content()))


# --------------------------------------------------------------------------
# Decisione 2 — linguette o striscia di fase (scelta: la striscia; aperto
# come si arriva alla gestione del turno e della gara)
# --------------------------------------------------------------------------

ROWS_FONDO = f"""
      <div class="rows">
        {base.todo_row(I["trophy"], "Classifica", "m.rossi in testa con 4 vinte", "neutral")}
        {base.todo_row(I["users"], "Iscritti", "10 attivi, nessuna riserva", "neutral")}
        {base.todo_row(I["gear"], "Impostazioni gara", "direttori, tavoli, vetrina, esercizi, turni", "neutral")}
      </div>"""


def dec2_linguette_gioco():
    return dec1_b()


def striscia_gioco_content():
    return (CONSOLE_HEAD + sechead_turno(2, "In corso", menu=True) + cards_console()
            + TURNO1 + ROWS_FONDO)


def dec2_striscia_gioco():
    return doc(phone(SUB, strip_bar("gioco"), striscia_gioco_content(), ACTIONBAR))


def dec2_striscia_menu_turno():
    """Il menu del turno, dai tre puntini accanto a «Turno 2»: i comandi che
    oggi stanno nella Gestione (_gara_management.html, stato PLAYING)."""
    corpo = f"""
    <div class="stack">
      {F.btn("Annulla l'avvio del turno 2", "secondary", "rotate")}
      <div style="font-size:12px;font-weight:600;color:var(--c7-ink-muted);line-height:1.45">
        Si pu&ograve; solo finch&eacute; nessun risultato del turno &egrave; inserito.
      </div>
      <hr class="divider" style="margin:2px 0">
      {F.btn("Azzera i risultati del turno 2", "danger", "rotate")}
      <div style="font-size:12px;font-weight:600;color:var(--c7-ink-muted);line-height:1.45">
        Le partite tornano da giocare, gli abbinamenti restano.
      </div>
    </div>"""
    return doc(phone(SUB, strip_bar("gioco"), striscia_gioco_content(), ACTIONBAR,
                     overlay=F.sheet("Turno 2", corpo, "", "In corso &middot; 2 partite chiuse su 5")))


def dec2_striscia_impostazioni():
    """«Impostazioni gara», dalla riga in fondo: cio' che oggi sta sotto la
    linguetta Gestione e non riguarda il turno in corso."""
    content = f"""
      {F.sec("Direzione")}
      {F.rows(
        F.row(I["users"], "Direttori", "tu e m.neri", tone="neutral")
        + F.row(I["share"], "Vetrina", "locandina, indirizzo, link esterno", tone="neutral")
        + F.row(I["link"], "Link pubblico", "torneibiliardo.it/g/gara-3-giovedi", tone="neutral"))}

      {F.sec("Gioco")}
      {F.rows(
        F.row(I["table"], "Tavoli", "1, 2, 3 in uso &mdash; cambia prima del turno 3", tone="neutral")
        + F.row(I["list"], "Turni e distanze", "4 turni &middot; al 5 &middot; turno 3 al 3", tone="neutral")
        + F.row(I["target"], "Esercizi fra i turni", "nessuno", tone="neutral")
        + F.row(I["grid"], "Squadre e categorie", "fissate all'avvio", tone="locked"))}

      {F.sec("Gara")}
      {F.rows(
        F.row(I["flag"], "Termina la gara", "quando tutti i turni sono chiusi", tone="locked")
        + F.row(I["minus"], "Elimina la gara", "iscritti e partite compresi", tone="locked"))}
"""
    return doc(phone("Gara 3 &middot; Gioved&igrave;", "", content, title="Impostazioni gara"))


def dec2_striscia_spareggio():
    """La striscia durante lo spareggio: la fase compare solo qui, fra il
    gioco e la chiusura. Contenuto: la 4.1 della pagina 4."""
    return F.ssr_rilevato().replace(F.TABS_GEST, strip_bar("ssr"))


def dec2_linguette_setup():
    return dec1_s_setup()


def dec2_striscia_setup():
    return doc(phone(SUB, strip_bar("prep"), setup_content()))


# --------------------------------------------------------------------------
# Decisione 3 — il punteggio (scelta: 3C, sulla card)
# --------------------------------------------------------------------------

def dec3_card():
    content = f"""
      {sechead_turno(2, "In corso")}
      <div style="font-size:12px;font-weight:600;color:var(--c7-ink-muted);line-height:1.45">
        Il punteggio si scrive a ogni tocco. A 5 la partita si chiude e il
        tavolo si libera.</div>
      {cards_console()}
"""
    return doc(phone(SUB, TABS4, content))


def cards_foglio():
    segna = '<button class="btn btn--primary btn--sm">Segna il risultato</button>'
    return (base.match_card("m.rossi", "4", "g.verdi", "2",
                            STATE_LIVE + tavolo_txt(1), segna)
            + base.match_card("d.bianchi", "3", "l.ferrari", "3",
                              STATE_LIVE + tavolo_txt(2), segna)
            + base.match_card("s.conti", "0", "p.marini", "0", STATE_TODO,
                              '<button class="btn btn--warn btn--sm">Assegna tavolo</button>'))


def dec3_foglio():
    return doc(phone(SUB, TABS4, sechead_turno(2, "In corso") + cards_foglio()))


def dec3_foglio_aperto():
    corpo = f"""
    <div class="stack">
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
        {F.stepper("m.rossi", "4")}
        {F.stepper("g.verdi", "2")}
      </div>
      <div class="flash flash--info">
        <span class="flash__ico">{ico(I["clock"], 14)}</span>
        <div><div class="flash__title">Nessuno &egrave; ancora a 5</div>
          <div>Al 5: vince chi arriva a 5 triangoli.</div></div>
      </div>
    </div>"""
    return doc(phone(SUB, TABS4, sechead_turno(2, "In corso") + cards_foglio(),
                     overlay=F.sheet("Segna il risultato", corpo,
                                     F.btn("Imposta il risultato", "primary", "check"),
                                     "m.rossi vs g.verdi &middot; tavolo 1")))


# --------------------------------------------------------------------------
# Decisione 4 — gli esercizi: le due forme, entrambe con Amalfi
# --------------------------------------------------------------------------

def dec4_due_forme():
    return doc(phone(SUB, TABS_SETUP, setup_content(
        esercizi="1 dopo il turno 2 &middot; classifica a parte", esercizi_tone="ok",
        riposa="X con esercizio &laquo;Stop shot&raquo; &middot; all'ultimo iscritto")))


# --------------------------------------------------------------------------
# Decisione 5 — «Riepilogo partite» (scelta: 5S, le partite restano in pagina)
# --------------------------------------------------------------------------

TABS_FINE = base.vtabs(["Turni", "Classifica", "Iscritti"], "Turni")


def fine_dopo_content(riepilogo):
    corpo = ("""
        <div style="margin-top:10px;font-size:13px;font-weight:600;
             color:var(--c7-accent-dim);line-height:1.45">
          10 partecipanti &middot; 20 partite giocate &middot; 4 turni.</div>""")
    riga = (F.row(I["list"], "Riepilogo partite", "20 partite, tutte validate", tone="neutral")
            if riepilogo == "link" else "")
    partite = ""
    if riepilogo == "sezione":
        partite = (F.sec("Partite", "20, tutte validate")
                   + F.partite_turno(4, F.T4) + F.partite_turno(3, base.R1))
    return f"""
      {F.band("Gara conclusa", "Ha vinto m.rossi", corpo)}

      {F.sec("Dopo la gara")}
      {F.rows(
        F.row(I["trophy"], "Classifica del campionato", "aggiornata con questa gara", tone="neutral")
        + F.row(I["share"], "Pagina pubblica", "con la classifica finale", tone="neutral")
        + riga)}

      {partite}

      {F.sec("Resta bloccato")}
      {F.rows(
        F.row(I["minus"], "Punteggi", "non si modificano a gara conclusa", tone="locked")
        + F.row(I["users"], "Iscritti", "elenco definitivo", tone="locked"))}
"""


def dec5_link():
    return doc(phone(SUB, TABS_FINE, fine_dopo_content("link")))


def dec5_sezione():
    return doc(phone(SUB, TABS_FINE, fine_dopo_content("sezione")))


# --------------------------------------------------------------------------
# Registro della pagina «0 · Decisioni»: una riga per decisione
# --------------------------------------------------------------------------

COL = 560
RIGA = 1300
NOTE_W = 1060

RIGHE = [
    ("dec-1",
     "DECISIONE 1 · LA FORMA — in gioco (le prime tre) e in preparazione (le ultime due)\n"
     "SCELTA (12/09): 1B in gioco, con la card riassuntiva scura come la fascia; 1S in "
     "preparazione. Applicata alle pagine 1–5. Nota: i tavoli si scelgono sempre, di "
     "solito prima di avviare un turno; la riga mostra quanti ne ha la sala.\n"
     "Stessi dati: turno 2 di 4, 2 partite chiuse su 5, m.rossi–g.verdi 4–2 al "
     "tavolo 1, d.bianchi–l.ferrari 3–3 al tavolo 2, s.conti–p.marini senza "
     "tavolo, turno 1 concluso.\n"
     "1A · Regia: la pagina di oggi più una fascia che dice cosa tiene aperto il turno.\n"
     "1B · Console: il turno è la pagina, il punteggio si segna sulla card, l'azione "
     "della fase sta nella barra in fondo.\n"
     "1C · Fasi: la striscia del ciclo al posto delle linguette, la fascia dice l'unica "
     "cosa da fare, classifica in un commutatore, iscritti e impostazioni come righe.",
     [("Dec1A", dec1_a, "1A · Regia — in gioco"),
      ("Dec1B", dec1_b, "1B · Console — in gioco (scelta)"),
      ("Dec1C", dec1_c, "1C · Fasi — in gioco"),
      ("Dec1ASetup", dec1_a_setup, "1A · Regia — in preparazione"),
      ("Dec1SSetup", dec1_s_setup, "1S · Sintesi — in preparazione (scelta)")]),

    ("dec-2",
     "DECISIONE 2 · LINGUETTE O STRISCIA DI FASE — stesso contenuto, cambia la navigazione\n"
     "SCELTA (12/09): la striscia. APERTO: come si arriva alla gestione nelle altre "
     "fasi, per esempio per annullare il turno. Proposta nelle tre schermate 2S in "
     "mezzo:\n"
     "• i comandi DEL TURNO (annulla l'avvio, azzera i risultati) stanno con il turno: "
     "tre puntini accanto a «Turno 2» aprono il foglio con i due comandi, gli stessi "
     "della 3.6 «Turno concluso»;\n"
     "• i comandi DELLA GARA (direttori, vetrina, link, tavoli, turni e distanze, "
     "esercizi, squadre e categorie, termina, elimina) stanno in «Impostazioni gara», "
     "la riga in fondo alla pagina, che apre una pagina a righe;\n"
     "• l'azione della fase (avvia il turno 3, termina la gara) resta nella barra in "
     "fondo, come in 1B.\n"
     "Lo spareggio ha la sua tacca nella striscia, fra il gioco e la chiusura, e "
     "compare solo nelle gare che ce l'hanno (schermata 2S · Spareggio, contenuto "
     "della 4.1).\n"
     "2L · Linguette: Turni · Classifica · Iscritti · Gestione come oggi. Filtro CSS su "
     "un solo DOM. 2S · Striscia: le quattro fasi con le etichette non ci stanno in "
     "354 px, le inattive mostrano solo l'icona; classifica, iscritti e impostazioni "
     "diventano righe in fondo.",
     [("Dec2LGioco", dec2_linguette_gioco, "2L · Linguette — in gioco"),
      ("Dec2SGioco", dec2_striscia_gioco, "2S · Striscia — in gioco (scelta)"),
      ("Dec2SMenuTurno", dec2_striscia_menu_turno, "2S · Il menu del turno"),
      ("Dec2SImpostazioni", dec2_striscia_impostazioni, "2S · Impostazioni gara"),
      ("Dec2SSpareggio", dec2_striscia_spareggio, "2S · Striscia — nello spareggio"),
      ("Dec2LSetup", dec2_linguette_setup, "2L · Linguette — in preparazione"),
      ("Dec2SSetup", dec2_striscia_setup, "2S · Striscia — in preparazione")]),

    ("dec-3",
     "DECISIONE 3 · IL PUNTEGGIO — dove si segna il risultato di una partita del turno\n"
     "SCELTA (12/09): 3C, sulla card. La 3.3 «Segna il risultato» è uscita dalla "
     "pagina 3.\n"
     "3C · Sulla card: gli stepper stanno sulla card, ogni tocco scrive il punteggio; a "
     "5 la partita si chiude e il tavolo si libera. Niente foglio, niente conferma. "
     "Tocca il segnapunti: una scrittura per tocco, la conferma da ripensare.\n"
     "3F · Dal foglio: la card mostra il punteggio e «Segna il risultato»; il foglio ha "
     "gli stepper e la riga che dice chi vince. Era il meccanismo di oggi (il "
     "«risultato rapido» dalla card), rivestito.",
     [("Dec3Card", dec3_card, "3C · Sulla card (scelta)"),
      ("Dec3Foglio", dec3_foglio, "3F · Dal foglio"),
      ("Dec3FoglioAperto", dec3_foglio_aperto, "3F · Il foglio aperto")]),

    ("dec-4",
     "DECISIONE 4 · GLI ESERCIZI — le due forme, entrambe anche con Amalfi\n"
     "La domanda «nascosta o spenta» era posta male: la spunta di oggi copre una sola "
     "forma. Ce ne sono due, e la schermata le mostra insieme su una gara Amalfi:\n"
     "• ESERCIZI FRA I TURNI: uno o più esercizi che si giocano dopo un turno "
     "(GaraChallenge.round_number), con tentativi contati e una classifica a parte "
     "accanto a quella della gara. Riga «Esercizi fra i turni» in «Da preparare», "
     "facoltativa. Oggi l'app li mostra solo con l'accoppiamento casuale, ma il "
     "limite sta nei template (_gara_management.html, _gara_challenges_display.html): "
     "il servizio non lo impone. Con Amalfi va aperto.\n"
     "• X CON ESERCIZIO: la policy dei dispari «Bye+Challenge», chi riposa gioca "
     "l'esercizio e prende una vittoria e una differenza pari al punteggio "
     "(SPECIFICHE.md riga 138). È una voce di «Chi riposa», non degli esercizi. Oggi "
     "l'app la offre con qualunque strategia tranne i tabelloni "
     "(x_challenge_section.js).\n"
     "Da confermare: i due testi delle righe.",
     [("Dec4Due", dec4_due_forme, "4 · Le due forme, con Amalfi")]),

    ("dec-5",
     "DECISIONE 5 · «RIEPILOGO PARTITE» A GARA CONCLUSA — la pagina dopo la fine, vista Turni\n"
     "SCELTA (12/09): 5S, le partite restano in pagina. Applicata alla 5.2. La pagina "
     "pubblica a gara conclusa mostra la classifica finale (vetrina_gara.html, "
     "`vetrina.conclusa`): la riga ora lo dice.\n"
     "5L · Link: una riga che apre l'elenco, pagina corta. 5S · Sezione: le partite in "
     "pagina, turno per turno; è ciò che l'app fa oggi.",
     [("Dec5Link", dec5_link, "5L · Link"),
      ("Dec5Sezione", dec5_sezione, "5S · Sezione in pagina (scelta)")]),
]

NOTA_COME = (
    "COME SI SCEGLIE\n"
    "Ogni riga è una decisione. Le schermate di una riga portano gli stessi dati: "
    "cambia solo dove stanno le cose e che comando hanno. Si risponde con la sigla, "
    "in chat o in un bigliettino qui accanto.\n"
    "Il 12/09 le cinque hanno avuto risposta (le righe «SCELTA»); le scelte sono "
    "applicate alle pagine 1–5, che restano la proposta completa. Restano aperti due "
    "punti: la gestione con la striscia (decisione 2) e i testi degli esercizi "
    "(decisione 4).")

PAGINA = {"id": "page-0", "name": "0 · Decisioni"}


def main():
    F.main()  # riscrive tutti gli artboard delle fasi e il canvas.json

    canvas = json.loads((SRC / "canvas.json").read_text(encoding="utf-8"))
    canvas["pages"] = [PAGINA] + [p for p in canvas["pages"] if p["id"] != PAGINA["id"]]
    canvas["annotations"].append({"id": "dec-come", "page": PAGINA["id"],
                                  "x": 0, "y": -600, "w": NOTE_W, "text": NOTA_COME})

    for riga, (nid, testo, schermate) in enumerate(RIGHE):
        y = riga * RIGA
        canvas["annotations"].append({"id": nid, "page": PAGINA["id"],
                                      "x": 0, "y": y - 340, "w": NOTE_W, "text": testo})
        for colonna, (stem, fn, titolo) in enumerate(schermate):
            nome = f"{stem}.dc.html"
            (SRC / nome).write_text(fn(), encoding="utf-8")
            canvas["artboards"].append({
                "file": nome, "title": titolo, "page": PAGINA["id"],
                "x": colonna * COL, "y": y, "w": 390, "h": 844})

    canvas["launch"] = {"view": "canvas", "page": PAGINA["id"]}
    (SRC / "canvas.json").write_text(
        json.dumps(canvas, ensure_ascii=False, indent=2), encoding="utf-8")

    files = list(dict.fromkeys(a["file"] for a in canvas["artboards"]))
    print(f"{len(files)} artboard su {len(canvas['pages'])} pagine, "
          f"{len(canvas['annotations'])} bigliettini")
    print("--artboard " + " --artboard ".join(files))


if __name__ == "__main__":
    main()
