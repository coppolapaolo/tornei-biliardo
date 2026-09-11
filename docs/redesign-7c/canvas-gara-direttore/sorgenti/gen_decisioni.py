#!/usr/bin/env python3
"""Canvas «Pagina gara del direttore» — la pagina delle decisioni.

Le cinque decisioni aperte dello STATO («Da decidere»), una riga ciascuna:
le alternative stanno fianco a fianco e portano **gli stessi dati** — cambia
solo dove stanno le cose e che comando hanno. Cosi' si giudica la forma, non
il contenuto.

Riusa i mattoni di gen_fasi.py e gen_gara_direttore.py. Scrive gli artboard
Dec*.dc.html e aggiunge la pagina «0 · Decisioni» in testa al canvas.json
che gen_fasi.main() ha appena riscritto. E' l'unico comando da lanciare:

    python3 sorgenti/gen_decisioni.py
"""

import json

import gen_fasi as F
import gen_gara_direttore as base
from gen_gara_direttore import I, doc, ico, phone

SRC = F.SRC
SUB = F.SUB
TABS4 = F.TABS_GIOCO
TABS_SETUP = F.TABS_SETUP

# --------------------------------------------------------------------------
# I dati del turno in gioco, uguali in ogni variante
# --------------------------------------------------------------------------

STATE_LIVE = '<span class="state state--accent">In corso</span>'
STATE_TODO = '<span class="state state--warn">Da giocare</span>'


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


CONSOLE_HEAD = """
      <section class="card" style="padding:14px 16px">
        <div class="row">
          <div class="grow">
            <div class="kicker">Turno 2 di 4</div>
            <div class="row" style="margin-top:4px;gap:8px">
              <div class="num" style="font-size:19px;font-weight:800">2/5</div>
              <div style="font-size:13px;font-weight:700" class="muted">partite chiuse</div>
            </div>
          </div>
          <div style="text-align:right">
            <div class="kicker">Tavoli</div>
            <div class="num" style="margin-top:4px;font-size:19px;font-weight:800">2/4</div>
          </div>
        </div>
        <div class="bar" style="margin-top:10px"><div class="bar__fill" style="width:40%"></div></div>
      </section>
"""

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


def sechead_turno(n, stato, cls=""):
    tone = "state--accent" if stato == "In corso" else "state--muted"
    return f"""
      <div class="sechead" style="margin-top:4px">
        <h3 class="{cls}">Turno {n}</h3>
        <span class="state {tone}" style="margin-left:auto">{stato}</span>
      </div>"""


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
    return sechead_turno(n, "Concluso", "muted") + f'<div class="rows">{out}</div>'


TURNO1 = partite_turno(1, base.R1)

# --------------------------------------------------------------------------
# La striscia di fase (decisione 2): quattro fasi non ci stanno con le
# etichette in 354 px, quindi le inattive mostrano solo l'icona.
# --------------------------------------------------------------------------

FASI = [("prep", "gear", "Preparazione"), ("iscr", "users", "Iscrizioni"),
        ("gioco", "play", "In gioco"), ("fine", "flag", "Chiusura")]


def strip(attiva):
    idx = [k for k, _, _ in FASI].index(attiva)
    parts = []
    for i, (key, icon, label) in enumerate(FASI):
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
    return ('<section style="display:flex;align-items:center;gap:8px;padding-top:14px">'
            + "".join(parts) + "</section>")


# --------------------------------------------------------------------------
# La preparazione: contenuto della sintesi (1.1) con la voce «Esercizi» a scelta
# --------------------------------------------------------------------------

def setup_content(esercizi):
    """`esercizi`: "nascosta" (la riga non c'e') o "spenta" (grigia, col perche')."""
    corpo = ("""
        <div style="margin-top:10px;font-size:13px;font-weight:600;
             color:var(--c7-accent-dim);line-height:1.45">
          Quando apri le iscrizioni la gara diventa pubblica e chi &egrave; in
          zona riceve la notifica.</div>""")
    azione = ('<div style="margin-top:14px">'
              + F.btn("Apri iscrizioni", "success", "play") + "</div>")
    riga_esercizi = ""
    if esercizi == "spenta":
        riga_esercizi = F.row(I["target"], "Esercizi di gara",
                              "solo con accoppiamento casuale", tone="locked")
    return f"""
      {F.band("In preparazione", "Nessuno vede ancora la gara", corpo, azione)}

      {F.sec("Da preparare", "3 di 4")}
      {F.rows(
        F.row(I["list"], "Turni e distanze", "4 turni &middot; Palla 8 &middot; al 5", tone="ok")
        + F.row(I["users"], "Direzione di gara", "solo tu &mdash; aggiungi un co-direttore", tone="ok")
        + F.row(I["table"], "Tavoli", "si scelgono con le iscrizioni aperte", tone="locked")
        + F.row(I["share"], "Vetrina", "nessuna locandina", tone="warn")
        + riga_esercizi)}

      {F.sec("Impostazioni di gioco")}
      {F.rows(
        F.row(I["grid"], "Accoppiamento", "Amalfi &middot; anti-reincontro attivo", tone="neutral")
        + F.row(I["scale"], "Chi riposa", "X a tavolino all'ultimo iscritto", tone="neutral")
        + F.row(I["crown"], "Apertura", "acchito &mdash; chi vince sceglie", tone="neutral"))}
"""


def regia_setup_content():
    """A in preparazione: la Gestione di oggi (_gara_management, _gara_directors,
    _round_management) con la fascia sopra. Tavoli e vetrina non ci sono
    perche' oggi non ci sono: i tavoli si scelgono a iscrizioni aperte, la
    vetrina e' una pagina del menu."""
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
# Decisione 1 — la forma
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
    return doc(phone(SUB, TABS_SETUP, setup_content("nascosta")))


# --------------------------------------------------------------------------
# Decisione 2 — linguette o striscia di fase (contenuto: la sintesi)
# --------------------------------------------------------------------------

def dec2_linguette_gioco():
    return dec1_b()


def dec2_striscia_gioco():
    content = (strip("gioco") + CONSOLE_HEAD + cards_console() + TURNO1
               + f"""
      <div class="rows">
        {base.todo_row(I["trophy"], "Classifica", "m.rossi in testa con 4 vinte", "neutral")}
        {base.todo_row(I["users"], "Iscritti", "10 attivi, nessuna riserva", "neutral")}
        {base.todo_row(I["gear"], "Impostazioni gara", "direttori, tavoli, squadre, turni", "neutral")}
      </div>""")
    return doc(phone(SUB, "", content, ACTIONBAR))


def dec2_linguette_setup():
    return dec1_s_setup()


def dec2_striscia_setup():
    return doc(phone(SUB, "", strip("prep") + setup_content("nascosta")))


# --------------------------------------------------------------------------
# Decisione 3 — il punteggio: sulla card o dal foglio
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
# Decisione 4 — la voce «Esercizi» con Amalfi
# --------------------------------------------------------------------------

def dec4_nascosta():
    return doc(phone(SUB, TABS_SETUP, setup_content("nascosta")))


def dec4_spenta():
    return doc(phone(SUB, TABS_SETUP, setup_content("spenta")))


# --------------------------------------------------------------------------
# Decisione 5 — «Riepilogo partite» a gara conclusa
# --------------------------------------------------------------------------

TABS_FINE = base.vtabs(["Turni", "Classifica", "Iscritti"], "Turni")

T4 = [("m.rossi", "5", "a.galli", "3", "1"), ("d.bianchi", "5", "l.ferrari", "4", "2"),
      ("g.verdi", "5", "p.marini", "2", "3"), ("s.conti", "5", "f.costa", "1", "1"),
      ("r.neri", "5", "e.sala", "3", "2")]


def fine_dopo_content(riepilogo):
    """`riepilogo`: "link" (una riga che apre l'elenco) o "sezione" (le
    partite restano in pagina, turno per turno)."""
    corpo = ("""
        <div style="margin-top:10px;font-size:13px;font-weight:600;
             color:var(--c7-accent-dim);line-height:1.45">
          10 partecipanti &middot; 20 partite giocate &middot; 4 turni.</div>""")
    riga = (F.row(I["list"], "Riepilogo partite", "20 partite, tutte validate", tone="neutral")
            if riepilogo == "link" else "")
    partite = ""
    if riepilogo == "sezione":
        partite = (F.sec("Partite", "20, tutte validate")
                   + partite_turno(4, T4) + partite_turno(3, base.R1))
    return f"""
      {F.band("Gara conclusa", "Ha vinto m.rossi", corpo)}

      {F.sec("Dopo la gara")}
      {F.rows(
        F.row(I["trophy"], "Classifica del campionato", "aggiornata con questa gara", tone="neutral")
        + F.row(I["share"], "Pagina pubblica", "torneibiliardo.it/g/gara-3-giovedi", tone="neutral")
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
# Registro della pagina «0 · Decisioni»
# --------------------------------------------------------------------------

COL = 560
RIGA = 1300
NOTE_W = 1060

# (stem, generatore, titolo, riga, colonna)
ARTBOARDS = [
    ("Dec1A", dec1_a, "1A · Regia — in gioco", 0, 0),
    ("Dec1B", dec1_b, "1B · Console — in gioco (la sintesi)", 0, 1),
    ("Dec1C", dec1_c, "1C · Fasi — in gioco", 0, 2),
    ("Dec1ASetup", dec1_a_setup, "1A · Regia — in preparazione", 0, 3),
    ("Dec1SSetup", dec1_s_setup, "1S · Sintesi — in preparazione", 0, 4),

    ("Dec2LGioco", dec2_linguette_gioco, "2L · Linguette — in gioco", 1, 0),
    ("Dec2SGioco", dec2_striscia_gioco, "2S · Striscia di fase — in gioco", 1, 1),
    ("Dec2LSetup", dec2_linguette_setup, "2L · Linguette — in preparazione", 1, 2),
    ("Dec2SSetup", dec2_striscia_setup, "2S · Striscia di fase — in preparazione", 1, 3),

    ("Dec3Card", dec3_card, "3C · Sulla card", 2, 0),
    ("Dec3Foglio", dec3_foglio, "3F · Dal foglio", 2, 1),
    ("Dec3FoglioAperto", dec3_foglio_aperto, "3F · Il foglio aperto", 2, 2),

    ("Dec4Nascosta", dec4_nascosta, "4N · Nascosta", 3, 0),
    ("Dec4Spenta", dec4_spenta, "4S · Spenta", 3, 1),

    ("Dec5Link", dec5_link, "5L · Link", 4, 0),
    ("Dec5Sezione", dec5_sezione, "5S · Sezione in pagina", 4, 1),
]

NOTE = [
    ("dec-come", -580,
     "COME SI SCEGLIE\n"
     "Ogni riga è una decisione. Le schermate di una riga portano gli stessi "
     "dati: cambia solo dove stanno le cose e che comando hanno. Si risponde "
     "con la sigla (1B, 2S, …), in chat o in un bigliettino qui accanto.\n"
     "Le decisioni 1 e 2 vengono prima: le altre tre si posano sulla forma "
     "scelta. Le pagine 1–5 restano la proposta completa, fase per fase."),

    ("dec-1", 0 * RIGA - 320,
     "DECISIONE 1 · LA FORMA — in gioco (le prime tre) e in preparazione (le ultime due)\n"
     "Stessi dati: turno 2 di 4, 2 partite chiuse su 5, m.rossi–g.verdi 4–2 al "
     "tavolo 1, d.bianchi–l.ferrari 3–3 al tavolo 2, s.conti–p.marini senza "
     "tavolo, turno 1 concluso.\n"
     "1A · Regia: la pagina di oggi (card partita con il tavolo, le quattro "
     "linguette) più una fascia che dice cosa tiene aperto il turno. Costa poco "
     "e non toglie niente; il punteggio resta fuori pagina (decisione 3).\n"
     "1B · Console: il turno è la pagina, il punteggio si segna sulla card, "
     "l'azione della fase sta nella barra in fondo. È ciò che le pagine 1–5 "
     "usano in gioco («la sintesi»). Costa il segnapunti.\n"
     "1C · Fasi: la striscia del ciclo al posto delle linguette, la fascia "
     "dice l'unica cosa da fare, la classifica in un commutatore, iscritti e "
     "impostazioni come righe. Costa un tap in più per tutto ciò che non è la "
     "fase.\n"
     "In preparazione: 1A è la Gestione di oggi (bottoni, select dei "
     "direttori, card dei turni) con la fascia sopra; 1S è la sintesi già "
     "disegnata nella pagina 1 (righe «da preparare» e impostazioni).\n"
     "Domanda: la sintesi (1B in gioco, fascia e righe nelle altre fasi) va "
     "bene, o una delle tre da sola?"),

    ("dec-2", 1 * RIGA - 320,
     "DECISIONE 2 · LINGUETTE O STRISCIA DI FASE — stesso contenuto (la "
     "sintesi), cambia solo la navigazione\n"
     "2L · Linguette: Turni · Classifica · Iscritti · Gestione come oggi (in "
     "preparazione solo Gestione · Iscritti). Sono un filtro CSS su un solo "
     "DOM: le sezioni ci sono tutte, la linguetta nasconde le altre. La "
     "classifica è a un tap, sempre nello stesso posto.\n"
     "2S · Striscia: dice in che fase è la gara (fatto ✓ · in corso · da "
     "fare); classifica, iscritti e impostazioni diventano righe in fondo. Le "
     "quattro fasi con le etichette non ci stanno in 354 px: le inattive "
     "mostrano solo l'icona. Cambia anche il meccanismo: non più un filtro, "
     "ma pagine o sezioni separate.\n"
     "Oggi: linguette. Domanda: striscia al posto delle linguette, o "
     "linguette con la fascia di fase dentro la pagina?"),

    ("dec-3", 2 * RIGA - 320,
     "DECISIONE 3 · IL PUNTEGGIO — dove si segna il risultato di una partita "
     "del turno\n"
     "3C · Sulla card: gli stepper stanno sulla card, ogni tocco scrive il "
     "punteggio; a 5 la partita si chiude e il tavolo si libera. Niente "
     "foglio, niente conferma. È la scelta più costosa: tocca il segnapunti "
     "(una scrittura per tocco, la conferma da ripensare).\n"
     "3F · Dal foglio: la card mostra il punteggio e «Segna il risultato»; il "
     "foglio ha gli stepper, la riga che dice chi vince secondo la regola del "
     "turno, «Imposta il risultato». È il meccanismo di oggi (il «risultato "
     "rapido» dalla card), rivestito.\n"
     "Oggi: bottone sulla card → modale del risultato rapido; il segnapunti a "
     "triangoli sta nella pagina della partita.\n"
     "Domanda: card o foglio?"),

    ("dec-4", 3 * RIGA - 320,
     "DECISIONE 4 · «ESERCIZI» CON AMALFI — in preparazione, gli esercizi di "
     "gara esistono solo con l'accoppiamento casuale (oggi il bottone non "
     "compare affatto con Amalfi)\n"
     "4N · Nascosta: la riga non c'è, «da preparare» conta quattro voci. Chi "
     "non sa che gli esercizi esistono non lo scopre qui.\n"
     "4S · Spenta: la riga c'è, grigia, e dice perché non si può: «solo con "
     "accoppiamento casuale». Un rigo in più per sempre, per una funzione che "
     "con Amalfi non si accenderà mai.\n"
     "Domanda: nascosta o spenta?"),

    ("dec-5", 4 * RIGA - 320,
     "DECISIONE 5 · «RIEPILOGO PARTITE» A GARA CONCLUSA — la pagina dopo la "
     "fine, vista Turni\n"
     "5L · Link: una riga «Riepilogo partite · 20 partite, tutte validate» che "
     "apre l'elenco. La pagina resta corta: fascia, dove sono finiti i punti, "
     "cosa non si tocca più.\n"
     "5S · Sezione: le partite restano in pagina, turno per turno, sotto le "
     "righe. È ciò che l'app fa oggi (la sezione Turni non sparisce). La "
     "pagina si allunga, ma chi cerca «chi ha giocato con chi» lo trova senza "
     "cambiare pagina.\n"
     "Domanda: link o sezione?"),
]

PAGINA = {"id": "page-0", "name": "0 · Decisioni"}


def main():
    F.main()  # riscrive tutti gli artboard delle fasi e il canvas.json

    canvas = json.loads((SRC / "canvas.json").read_text(encoding="utf-8"))
    canvas["pages"] = [PAGINA] + [p for p in canvas["pages"] if p["id"] != PAGINA["id"]]

    for stem, fn, titolo, riga, colonna in ARTBOARDS:
        nome = f"{stem}.dc.html"
        (SRC / nome).write_text(fn(), encoding="utf-8")
        canvas["artboards"].append({
            "file": nome, "title": titolo, "page": PAGINA["id"],
            "x": colonna * COL, "y": riga * RIGA, "w": 390, "h": 844})

    for nid, y, testo in NOTE:
        canvas["annotations"].append({"id": nid, "page": PAGINA["id"],
                                      "x": 0, "y": y, "w": NOTE_W, "text": testo})

    canvas["launch"] = {"view": "canvas", "page": PAGINA["id"]}
    (SRC / "canvas.json").write_text(
        json.dumps(canvas, ensure_ascii=False, indent=2), encoding="utf-8")

    files = list(dict.fromkeys(a["file"] for a in canvas["artboards"]))
    print(f"{len(files)} artboard su {len(canvas['pages'])} pagine, "
          f"{len(canvas['annotations'])} bigliettini")
    print("--artboard " + " --artboard ".join(files))


if __name__ == "__main__":
    main()
