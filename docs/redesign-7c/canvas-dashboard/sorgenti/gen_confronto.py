# -*- coding: utf-8 -*-
"""Genera i sei artboard di confronto (giocatore A/B/C, direttore A/B/C).

Le tre varianti di una riga mostrano **gli stessi identici dati**: cambia solo
dove stanno e che pulsante portano. Per questo i pezzi sono definiti una volta
sola qui — se cambia la card della gara, cambia in tutte e tre insieme,
altrimenti il confronto mente.

Quattro cose valgono in **tutte** le varianti, perche' non sono in discussione
(vengono dai commenti sul canvas, 30/08):

1. la testata non ripete «Dashboard Giocatore»: porta il saluto, e il blocco
   del saluto sparisce dal contenuto;
2. le gare sono divise fra «le tue» e «aperte»: oggi sono un elenco solo che
   contiene tutte le gare vive del sistema, iscritto o no;
3. la gara in corso porta la posizione in classifica provvisoria e le altre
   partite del turno;
4. la sfida a due in corso compare: oggi il servizio la calcola
   (`vm.individual_matches`) e nessun template la disegna.

Stato ritratto: la visita **ordinaria**, non la prima della sessione, quindi
senza il blocco «Come stai andando» — che al primo ingresso c'e' e resta com'e'.
"""

import pathlib

OUT = pathlib.Path(__file__).parent


# ── Guscio ───────────────────────────────────────────────────────────────────
def head(saluto, ruolo, avatar, livello, azioni=""):
    return f"""  <header class="c7-head">
    <span class="c7-head__back"><svg viewBox="0 0 24 24" class="ico ico-lg"><use href="#i-nodes"></use></svg></span>
    <div class="c7-head__title">
      <span class="c7-title">{saluto}</span>
      <span class="c7-head__sub">{ruolo}</span>
    </div>
    <span class="gami-badge">
      <span class="gami-badge__ring"><svg viewBox="0 0 24 24" class="ico ico-sm"><use href="#i-trophy"></use></svg></span>
      <span class="gami-badge__level">Lv {livello}</span>
    </span>
    <span class="c7-avatar c7-avatar--lg">{avatar}</span>
{azioni}  </header>
"""


NAV_GIOC = """  <nav class="c7-mobilenav">
    <a href="#" class="is-active"><svg viewBox="0 0 24 24" class="ico"><use href="#i-gauge"></use></svg>Dashboard</a>
    <a href="#"><svg viewBox="0 0 24 24" class="ico"><use href="#i-users"></use></svg>Sfide</a>
    <a href="#"><svg viewBox="0 0 24 24" class="ico"><use href="#i-target"></use></svg>Esercizi</a>
    <a href="#"><svg viewBox="0 0 24 24" class="ico"><use href="#i-bell"></use></svg>Notifiche</a>
  </nav>
"""
NAV_DIR = NAV_GIOC.replace(
    '<a href="#"><svg viewBox="0 0 24 24" class="ico"><use href="#i-target"></use></svg>Esercizi</a>',
    '<a href="#"><svg viewBox="0 0 24 24" class="ico"><use href="#i-venue"></use></svg>Sale</a>',
)


def sechead(titolo, conteggio="", link="Vedi tutte"):
    c = f' <span class="count">{conteggio}</span>' if conteggio else ""
    a = f'\n        <a href="#" style="font-size:12px">{link}</a>' if link else ""
    return f"""      <div class="sec-head">
        <h2>{titolo}{c}</h2>{a}
      </div>
"""


def sez(titolo, corpo, conteggio="", link="Vedi tutte"):
    return (
        '    <section class="sec">\n'
        + sechead(titolo, conteggio, link)
        + corpo
        + "    </section>\n"
    )


def screen(headhtml, contenuto, nav):
    return f"""<div class="screen">

{headhtml}
  <main class="c7-content">

{contenuto}
  </main>

{nav}</div>
"""


# ── I pezzi ──────────────────────────────────────────────────────────────────
CARD_PLAYOFF = """      <article class="c7-card c7-card--warn">
        <div class="rowtop">
          <div class="fill">
            <div class="c7-kicker">Campionato Sociale 2026</div>
            <h3 style="margin:5px 0 0">Finale Playoff</h3>
          </div>
          <span class="c7-state c7-state--warn">In attesa</span>
        </div>
        <hr class="c7-divider">
        <dl style="display:grid;grid-template-columns:auto 1fr;gap:8px 14px;font-size:13px">
          <dt class="muted" style="font-weight:700">Posizione</dt>
          <dd class="c7-num" style="text-align:right">3</dd>
          <dt class="muted" style="font-weight:700">Quando</dt>
          <dd class="c7-num" style="text-align:right">21/09/2026 20:30</dd>
          <dt class="muted" style="font-weight:700">Sala</dt>
          <dd style="text-align:right">Sala Centrale, Trieste</dd>
          <dt class="muted" style="font-weight:700">Rispondi entro</dt>
          <dd class="c7-num" style="text-align:right">05/09/2026 23:59</dd>
        </dl>
        <div style="display:flex;gap:8px;margin-top:16px">
          <span class="btn btn-success btn-fill">Accetta</span>
          <span class="btn btn-secondary">Rifiuta</span>
        </div>
      </article>
"""

CARD_MATCH_GARA = """      <article class="c7-card cardstack">
        <div class="rowtop">
          <div class="fill">
            <div class="c7-kicker">Gara 3 <span class="c7-sep">&middot;</span> Turno 3 <span class="c7-sep">&middot;</span> Tavolo 4</div>
            <div class="cardtitle" style="margin-top:4px">vs Luca Berti</div>
            <div class="meta">Campionato Sociale 2026</div>
          </div>
          <span class="c7-state c7-state--err">In corso</span>
        </div>
        <div class="c7-num" style="font-size:22px">3 &mdash; 2</div>
        <div class="meta">Palla 8 <span class="c7-sep">&middot;</span> Al <span class="c7-num">5</span></div>
        <span class="btn btn-primary btn-sm btn-w"><svg viewBox="0 0 24 24" class="ico ico-sm"><use href="#i-play"></use></svg>Gioca</span>
      </article>
"""

# La sfida a due ha lo stesso stato `playing` di una partita di gara, ma non
# ha una gara a cui appartenere. Oggi non compare da nessuna parte.
CARD_SFIDA = """      <article class="c7-card cardstack">
        <div class="rowtop">
          <div class="fill">
            <div class="c7-kicker">Sfida a due <span class="c7-sep">&middot;</span> Sala Da Vinci</div>
            <div class="cardtitle" style="margin-top:4px">vs Andrea Zanin</div>
            <div class="meta">Palla 9 <span class="c7-sep">&middot;</span> Al <span class="c7-num">7</span></div>
          </div>
          <span class="c7-state c7-state--err">In corso</span>
        </div>
        <div class="c7-num" style="font-size:22px">3 &mdash; 4</div>
        <span class="btn btn-primary btn-sm btn-w"><svg viewBox="0 0 24 24" class="ico ico-sm"><use href="#i-play"></use></svg>Gioca</span>
      </article>
"""

# Dove sei e come stanno andando gli altri: senza, «gara in corso» dice solo
# che la gara esiste.
INSET_GARA_VIVA = """        <div class="inset">
          <div class="c7-kicker">Classifica provvisoria</div>
          <div style="margin-top:2px;font-size:14px;font-weight:800">Sei <span class="c7-num">4&deg;</span> su <span class="c7-num">14</span></div>
          <div style="margin-top:10px;padding-top:10px;border-top:1px solid var(--c7-line)">
            <div class="c7-kicker">Altre partite del turno</div>
            <div style="display:flex;flex-direction:column;gap:5px;margin-top:6px;font-size:12px;font-weight:700">
              <div class="row"><span class="c7-num muted">T1</span><span class="trunc">Elena Furlan <span class="c7-num">4&ndash;1</span> Sara De Rossi</span></div>
              <div class="row"><span class="c7-num muted">T2</span><span class="trunc">Andrea Zanin <span class="c7-num">2&ndash;2</span> Paolo Rizzo</span></div>
              <div class="row"><span class="c7-num muted">T3</span><span class="trunc">Giulia Nardin <span class="c7-num">5&ndash;3</span> Ivan Sartori</span></div>
            </div>
            <div class="meta" style="margin-top:6px">e altre <span class="c7-num">3</span> da giocare</div>
          </div>
        </div>
"""

INSET_PARTITA = """        <div class="inset">
          <div class="c7-kicker">La tua partita <span class="c7-sep">&middot;</span> Turno 3 <span class="c7-sep">&middot;</span> Tavolo 4</div>
          <div class="row" style="margin-top:6px">
            <span class="fill" style="font-size:14px;font-weight:800">vs Luca Berti</span>
            <span class="c7-num" style="font-size:20px">3 &mdash; 2</span>
          </div>
        </div>
"""


def card_gara3(azioni, insets=""):
    return f"""      <article class="c7-card cardstack">
        <div class="rowtop">
          <div class="fill">
            <div class="cardtitle">Gara 3 &mdash; Palla 8</div>
            <div class="meta">Campionato Sociale 2026 <span class="c7-sep">&middot;</span> Palla 8 <span class="c7-sep">&middot;</span> Al <span class="c7-num">5</span></div>
            <div class="meta"><span class="c7-num" style="color:var(--c7-ink)">30/08/2026</span> <span class="c7-sep">&middot;</span> Biliardo Club Udine</div>
          </div>
          <span class="c7-state c7-state--err">In corso</span>
        </div>
        <div class="row" style="font-size:12px;font-weight:700">
          <span class="fill">Turno <span class="c7-num">3/5</span></span>
          <span class="muted"><span class="c7-num">14</span> giocatori</span>
        </div>
{insets}{azioni}      </article>
"""


CARD_GARA4 = """      <article class="c7-card cardstack">
        <div class="rowtop">
          <div class="fill">
            <div class="cardtitle">Gara 4 &mdash; Palla 9</div>
            <div class="meta">Campionato Sociale 2026 <span class="c7-sep">&middot;</span> Palla 9 <span class="c7-sep">&middot;</span> Al <span class="c7-num">4</span></div>
            <div class="meta"><span class="c7-num" style="color:var(--c7-ink)">12/09/2026</span> <span class="c7-sep">&middot;</span> Biliardo Club Udine</div>
          </div>
          <span class="c7-state c7-state--ok">Aperta</span>
        </div>
        <div class="row" style="font-size:12px;font-weight:700">
          <span class="fill muted">Quota <span class="c7-num">&euro;10,00</span></span>
          <span class="muted"><span class="c7-num">18/24</span></span>
        </div>
        <div class="meta"><span style="color:var(--c7-warn)">Chiudono il <span class="c7-num">10/09/2026 20:00</span></span></div>
        <div style="display:flex;gap:8px">
          <span class="btn btn-secondary btn-sm btn-fill">Dettagli</span>
          <span class="btn btn-success btn-sm btn-fill">Iscriviti</span>
        </div>
      </article>
"""

INSET_PLAYOFF = """        <div class="inset">
          <span class="c7-kicker">Playoff <span class="c7-sep">&middot;</span> 3&deg; posto</span>
          <span style="display:block;margin-top:3px;font-size:14px;font-weight:800">Sei qualificato alla finale</span>
          <span class="meta">21/09 20:30 <span class="c7-sep">&middot;</span> rispondi entro il <span class="c7-num">05/09</span></span>
          <div style="display:flex;gap:8px;margin-top:10px">
            <span class="btn btn-success btn-sm btn-fill">Accetta</span>
            <span class="btn btn-secondary btn-sm">Rifiuta</span>
          </div>
        </div>
"""


def card_campionato(extra=""):
    return f"""      <article class="c7-card cardstack">
        <div class="rowtop">
          <div class="fill">
            <div class="cardtitle">Campionato Sociale 2026</div>
            <div class="meta">amalfi <span class="c7-sep">&middot;</span> 5 gare <span class="c7-sep">&middot;</span> sei <span class="c7-num">4&deg;</span> su <span class="c7-num">14</span></div>
          </div>
          <span class="c7-state c7-state--err">In corso</span>
        </div>
        <div class="meta">Prossima: <span class="c7-num" style="color:var(--c7-ink)">12/09/2026</span></div>
{extra}        <span class="btn btn-secondary btn-sm btn-w">Dettagli</span>
      </article>
"""


# ── GIOCATORE ────────────────────────────────────────────────────────────────
G_HEAD = head("Ciao marco", "Giocatore", "MA", 7)

VEDI_GARA = '        <span class="btn btn-secondary btn-sm btn-w">Vedi la gara</span>\n'
GIOCA_GARA = (
    '        <span class="btn btn-primary btn-w">'
    '<svg viewBox="0 0 24 24" class="ico ico-sm"><use href="#i-play"></use></svg>'
    "Gioca la tua partita</span>\n"
)

a = (
    sez("Sei qualificato", CARD_PLAYOFF, "1", None)
    + sez("I tuoi match", CARD_MATCH_GARA + CARD_SFIDA, "2", None)
    + sez("Le tue gare", card_gara3(VEDI_GARA, insets=INSET_GARA_VIVA), "1")
    + sez("Aperte, puoi iscriverti", CARD_GARA4, "1")
    + sez("Campionati", card_campionato(), "1 attivo", "Vedi tutti")
)

FASCIA = """    <section class="c7-card c7-card--accent now">
      <div class="now__head"><h2>Da fare</h2><span class="now__count">3</span></div>

      <a class="now__row" href="#">
        <span class="now__body">
          <span class="now__ctx">
            <span class="c7-live__dot"></span>
            <span class="c7-kicker">Gara 3 <span class="c7-sep">&middot;</span> Turno 3 <span class="c7-sep">&middot;</span> Tavolo 4</span>
          </span>
          <span class="now__what">La tua partita &egrave; al tavolo</span>
          <span class="now__meta">vs Luca Berti <span class="c7-sep">&middot;</span> <span class="c7-num">3&ndash;2</span> <span class="c7-sep">&middot;</span> al 5</span>
        </span>
        <span class="now__go">Gioca</span>
      </a>

      <a class="now__row" href="#">
        <span class="now__body">
          <span class="now__ctx">
            <span class="c7-live__dot"></span>
            <span class="c7-kicker">Sfida a due <span class="c7-sep">&middot;</span> Sala Da Vinci</span>
          </span>
          <span class="now__what">Sfida con Andrea Zanin</span>
          <span class="now__meta">Palla 9 <span class="c7-sep">&middot;</span> <span class="c7-num">3&ndash;4</span> <span class="c7-sep">&middot;</span> al 7</span>
        </span>
        <span class="now__go">Gioca</span>
      </a>

      <a class="now__row" href="#">
        <span class="now__body">
          <span class="now__ctx">
            <span class="c7-kicker">Playoff</span>
            <span class="now__when">entro il 05/09</span>
          </span>
          <span class="now__what">Sei qualificato alla finale</span>
          <span class="now__meta">3&deg; posto <span class="c7-sep">&middot;</span> 21/09 20:30 <span class="c7-sep">&middot;</span> Sala Centrale</span>
        </span>
        <span class="now__go now__go--soft">Rispondi</span>
      </a>
    </section>
"""

b = (
    FASCIA
    + sez("Le tue gare", card_gara3(VEDI_GARA, insets=INSET_GARA_VIVA), "1")
    + sez("Aperte, puoi iscriverti", CARD_GARA4, "1")
    + sez("Campionati", card_campionato(), "1 attivo", "Vedi tutti")
)

c = (
    sez(
        "Le tue gare",
        card_gara3(GIOCA_GARA, insets=INSET_PARTITA + INSET_GARA_VIVA),
        "1",
    )
    + sez("Sfide a due", CARD_SFIDA, "1", None)
    + sez("Aperte, puoi iscriverti", CARD_GARA4, "1")
    + sez("Campionati", card_campionato(extra=INSET_PLAYOFF), "1 attivo", "Vedi tutti")
)


# ── DIRETTORE ────────────────────────────────────────────────────────────────
# Una gara puo' essere insieme «che dirigo» e «in cui gioco»: `can_inscribe()`
# non vieta al direttore di iscriversi alla propria gara, e in un circolo
# piccolo e' la norma. Quindi l'elenco e' **uno**, e ogni card porta cio' che
# quella gara e' per te: la tua partita se ci giochi, i comandi se la dirigi,
# tutte e due se le due cose coincidono. Restano due varianti, e riguardano
# una domanda sola: i comandi di direzione stanno sulla card o si apre la gara?
D_AZIONI = """    <div class="c7-head__actions">
      <span class="btn btn-secondary btn-sm btn-secondary--onpage"><svg viewBox="0 0 24 24" class="ico ico-sm"><use href="#i-plus"></use></svg>Nuova Gara</span>
      <span class="btn btn-primary btn-sm"><svg viewBox="0 0 24 24" class="ico ico-sm"><use href="#i-wand"></use></svg>Nuovo Campionato</span>
    </div>
"""
D_HEAD = head("Ciao paolo", "Direttore di gara", "PA", 12, D_AZIONI)

DIRIGI = '<span class="c7-state c7-state--info">Dirigi</span>'
ISCRITTO = '<span class="c7-state c7-state--accent">Iscritto</span>'


def card_gara_dir(titolo, meta, pastiglie, righe, insets="", azioni=""):
    return f"""      <article class="c7-card cardstack">
        <div class="rowtop">
          <div class="fill">
            <div class="cardtitle">{titolo}</div>
            <div class="meta">{meta}</div>
          </div>
          <div style="display:flex;flex-wrap:wrap;justify-content:flex-end;align-items:flex-start;gap:6px;max-width:170px">{pastiglie}</div>
        </div>
        <div class="row" style="font-size:12px;font-weight:700">{righe}</div>
{insets}{azioni}      </article>
"""


M3 = (
    'Campionato Sociale 2026 <span class="c7-sep">&middot;</span> Palla 8 '
    '<span class="c7-sep">&middot;</span> <span class="c7-num">30/08</span> '
    '<span class="c7-sep">&middot;</span> Biliardo Club Udine'
)
M2 = (
    'Campionato Sociale 2026 <span class="c7-sep">&middot;</span> Palla 8 '
    '<span class="c7-sep">&middot;</span> <span class="c7-num">16/08</span> '
    '<span class="c7-sep">&middot;</span> Biliardo Club Udine'
)
M5 = (
    'Campionato Sociale 2026 <span class="c7-sep">&middot;</span> Palla 8 '
    '<span class="c7-sep">&middot;</span> <span class="c7-num">03/10</span> '
    '<span class="c7-sep">&middot;</span> Biliardo Club Udine'
)
MT = (
    'Gara singola <span class="c7-sep">&middot;</span> Palla 8 '
    '<span class="c7-sep">&middot;</span> Al <span class="c7-num">5</span>'
)

R3 = (
    '<span class="fill">Turno <span class="c7-num">3/5</span> '
    '<span class="c7-sep">&middot;</span> <span class="c7-num">6/7</span> confermate</span>'
    '<span class="muted"><span class="c7-num">14</span> giocatori</span>'
)
R2 = (
    '<span class="fill">Turni finiti <span class="c7-sep">&middot;</span> 2 a pari merito</span>'
    '<span class="muted"><span class="c7-num">16</span> giocatori</span>'
)
R5 = (
    '<span class="fill muted">Nessun iscritto</span>'
    '<span class="muted">quota <span class="c7-num">&euro;10,00</span></span>'
)
RT = (
    '<span class="fill">Turno <span class="c7-num">2/4</span></span>'
    '<span class="muted"><span class="c7-num">12</span> giocatori</span>'
)

INSET_MIA_ATTESA = """        <div class="inset">
          <div class="c7-kicker">La tua partita <span class="c7-sep">&middot;</span> Turno 2 <span class="c7-sep">&middot;</span> In attesa del tavolo</div>
          <div class="row" style="margin-top:6px">
            <span class="fill" style="font-size:14px;font-weight:800">vs Elena Furlan</span>
            <span class="c7-num" style="font-size:20px">2 &mdash; 4</span>
          </div>
        </div>
"""

NOTA_TURNO = '        <div class="meta">Il turno 4 si avvia quando finisce l\u2019ultima partita.</div>\n'

CARD_SFIDA_DIR = CARD_SFIDA.replace("vs Andrea Zanin", "vs Marco Bassi")


def gare_direttore(comandi):
    """Le quattro combinazioni: dirigo+gioco, solo dirigo (x2), solo gioco."""
    if comandi:
        a3 = (
            '        <div style="display:flex;gap:8px">\n'
            '          <span class="btn btn-secondary btn-sm btn-fill">Vedi la gara</span>\n'
            '          <span class="btn btn-primary btn-sm btn-fill">'
            '<svg viewBox="0 0 24 24" class="ico ico-sm"><use href="#i-play"></use></svg>Gioca</span>\n'
            "        </div>\n"
        ) + NOTA_TURNO
        a2 = (
            '        <div style="display:flex;gap:8px">\n'
            '          <span class="btn btn-secondary btn-sm btn-fill">Vedi la gara</span>\n'
            '          <span class="btn btn-primary btn-sm btn-fill">Avvia Spareggio</span>\n'
            "        </div>\n"
        )
        a5 = (
            '        <div style="display:flex;gap:8px">\n'
            '          <span class="btn btn-secondary btn-sm btn-fill">Gestisci</span>\n'
            '          <span class="btn btn-success btn-sm btn-fill">Apri Iscrizioni</span>\n'
            "        </div>\n"
        )
    else:
        a3 = (
            '        <div style="display:flex;gap:8px">\n'
            '          <span class="btn btn-secondary btn-sm btn-fill">Vedi la gara</span>\n'
            '          <span class="btn btn-primary btn-sm btn-fill">'
            '<svg viewBox="0 0 24 24" class="ico ico-sm"><use href="#i-play"></use></svg>Gioca</span>\n'
            "        </div>\n"
        )
        a2 = (
            '        <span class="btn btn-secondary btn-sm btn-w">Vedi la gara</span>\n'
        )
        a5 = '        <span class="btn btn-secondary btn-sm btn-w">Gestisci</span>\n'

    return (
        card_gara_dir(
            "Gara 3 &mdash; Palla 8",
            M3,
            DIRIGI + ISCRITTO + '<span class="c7-state c7-state--err">In corso</span>',
            R3,
            insets=INSET_PARTITA + INSET_GARA_VIVA,
            azioni=a3,
        )
        + card_gara_dir(
            "Gara 2 &mdash; Palla 8",
            M2,
            DIRIGI + '<span class="c7-state c7-state--warn">Spareggi</span>',
            R2,
            azioni=a2,
        )
        + card_gara_dir(
            "Gara 5 &mdash; Palla 8",
            M5,
            DIRIGI + '<span class="c7-state c7-state--muted">In preparazione</span>',
            R5,
            azioni=a5,
        )
        + card_gara_dir(
            "Torneo del Giovedì",
            MT,
            ISCRITTO + '<span class="c7-state c7-state--err">In corso</span>',
            RT,
            insets=INSET_MIA_ATTESA,
            azioni='        <span class="btn btn-secondary btn-sm btn-w is-disabled">In attesa del tavolo</span>\n',
        )
    )


def dashboard_direttore(comandi):
    return (
        sez("Le tue gare", gare_direttore(comandi), "4")
        + sez("Aperte, puoi iscriverti", CARD_GARA4, "1")
        + sez("Sfide a due", CARD_SFIDA_DIR, "1", None)
        + sez("Campionati", card_campionato(), "1 attivo", "Vedi tutti")
    )


da = dashboard_direttore(comandi=False)
db = dashboard_direttore(comandi=True)


if __name__ == "__main__":
    for nome, corpo, h, nav in [
        ("GiocatoreA", a, G_HEAD, NAV_GIOC),
        ("GiocatoreC", c, G_HEAD, NAV_GIOC),
        ("DirettoreA", da, D_HEAD, NAV_DIR),
        ("DirettoreB", db, D_HEAD, NAV_DIR),
    ]:
        (OUT / f"{nome}.body").write_text(screen(h, corpo, nav), encoding="utf-8")
        print("scritto", nome)
