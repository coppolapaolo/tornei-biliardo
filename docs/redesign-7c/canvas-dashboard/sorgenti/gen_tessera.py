# -*- coding: utf-8 -*-
"""La pagina «Tessera»: la stessa gara, vista da chi ha fatti diversi.

Regola 1 del 2026-09-10 (STATO.md): il ruolo e' per elemento. Per ogni gara
contano tre fatti — sono iscritto, la dirigo, ho una partita aperta — e la
tessera si disegna da quelli: senza fatti e' quella dell'ospite, con due i
pezzi si sommano, sul conflitto vince il direttore. Qui la regola si vede:
ogni riga e' uno stato della gara, ogni colonna un insieme di fatti, e la
cella e' la tessera che ne discende.

La forma e' quella **decisa il 10/09 guardando le due basi possibili** (A
dalla dashboard, B dalla home dell'ospite, entrambe rimosse dal canvas):

* iscrizioni aperte: la barra di riempimento di B **e** i numeri di A;
* in corso: la tessera scura di B, per chiunque la guardi;
* nessun pulsante «piccolo» (`btn-sm`, 40px): sono difficili da tappare.
  Le azioni della tessera hanno l'altezza standard del tema (`--c7-btn-h`);
* niente «Gioca la tua partita»: il bersaglio e' il **riquadro della propria
  partita**, che sta piu' in alto e ha gia' tutto;
* chi dirige una gara in corso ha «Gestisci» (la pagina di amministrazione
  della gara) al posto di «Segui la diretta»;
* il podio porta le medaglie (icona `i-medal` nel chip di posizione).

Regola 2: le concluse in dashboard sono l'ultima piu' l'ultimo mese, di
tutti, riconoscibili; il resto nello storico. `Concluse` e `Storico` sono
quelle due schermate.

Riusa i pezzi dei generatori del 30/08: se cambia la card, cambia anche qui.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from gen_confronto import (  # noqa: E402
    DIRIGI, ISCRITTO, G_HEAD, NAV_GIOC, INSET_PARTITA, INSET_GARA_VIVA,
    screen, sez,
)

OUT = pathlib.Path(__file__).parent

PLAY = '<svg viewBox="0 0 24 24" class="ico ico-sm"><use href="#i-play"></use></svg>'
HAI_GIOCATO = '<span class="c7-state c7-state--accent">Hai giocato</span>'
HAI_DIRETTO = '<span class="c7-state c7-state--info">Hai diretto</span>'
DOT = '<span class="c7-live__dot"></span>'


def pastiglie(*xs):
    return ('<div style="display:flex;flex-wrap:wrap;justify-content:flex-end;'
            'align-items:flex-start;gap:6px;max-width:170px">' + "".join(xs) + '</div>')


def card(titolo, meta, past, corpo, azioni, accent=False, nota=""):
    cls = "c7-card cardstack" + (" c7-card--accent" if accent else "")
    if accent:
        # Sul fondo scuro l'inchiostro sparisce: i numeri in evidenza
        # passano al bianco del tema accent.
        meta = meta.replace("color:var(--c7-ink)", "color:var(--c7-accent-ink)")
    return f'''      <article class="{cls}">
        <div class="rowtop">
          <div class="fill">
            <div class="cardtitle">{titolo}</div>
            <div class="meta">{meta}</div>
          </div>
          {past}
        </div>
{corpo}{azioni}{nota}      </article>
'''


def btns(*bs):
    if len(bs) == 1:
        # Da solo in una colonna flex `btn-fill` (flex:1) lo schiaccia in
        # verticale: un pulsante solo va a larghezza piena, non a riempimento.
        return f'        {bs[0].replace("btn-fill", "btn-w")}\n'
    return ('        <div style="display:flex;gap:8px">\n'
            + "".join(f'          {b}\n' for b in bs)
            + '        </div>\n')


def b(testo, tipo="secondary", fill=True, icona=""):
    w = "btn-fill" if fill else "btn-w"
    return f'<span class="btn btn-{tipo} {w}">{icona}{testo}</span>'


NOTA = '        <div class="meta">{}</div>\n'

# ── Fixture ──────────────────────────────────────────────────────────────────
G4 = ("Gara 4 &mdash; Palla 9",
      'Campionato Sociale 2026 <span class="c7-sep">&middot;</span> Palla 9 '
      '<span class="c7-sep">&middot;</span> Al <span class="c7-num">4</span><br>'
      '<span class="c7-num" style="color:var(--c7-ink)">12/09/2026</span> '
      '<span class="c7-sep">&middot;</span> Biliardo Club Udine')
G3 = ("Gara 3 &mdash; Palla 8",
      'Campionato Sociale 2026 <span class="c7-sep">&middot;</span> Palla 8 '
      '<span class="c7-sep">&middot;</span> Al <span class="c7-num">5</span><br>'
      '<span class="c7-num" style="color:var(--c7-ink)">30/08/2026</span> '
      '<span class="c7-sep">&middot;</span> Biliardo Club Udine')
G2 = ("Gara 2 &mdash; Palla 8",
      'Campionato Sociale 2026 <span class="c7-sep">&middot;</span> Palla 8 '
      '<span class="c7-sep">&middot;</span> Al <span class="c7-num">5</span><br>'
      '<span class="c7-num" style="color:var(--c7-ink)">16/08/2026</span> '
      '<span class="c7-sep">&middot;</span> Biliardo Club Udine')


# ── Corpi per stato ──────────────────────────────────────────────────────────
APERTA = '''        <div>
          <div class="progress"><div class="progress-bar" style="width:75%"></div></div>
          <div class="row" style="margin-top:8px;font-size:12px;font-weight:700">
            <span class="fill muted">Quota <span class="c7-num">&euro;10,00</span></span>
            <span class="muted"><span class="c7-num">18/24</span> <span class="c7-sep">&middot;</span> <span class="c7-num">6</span> liberi</span>
          </div>
        </div>
        <div class="meta" style="color:var(--c7-warn)">Chiudono il <span class="c7-num">10/09/2026 20:00</span></div>
'''

TURNO = '''        <div class="row" style="font-size:12px;font-weight:700">
          <span class="fill">Turno <span class="c7-num">3/5</span>{extra}</span>
          <span class="muted"><span class="c7-num">14</span> giocatori</span>
        </div>
'''
CONFERMATE = ' <span class="c7-sep">&middot;</span> <span class="c7-num">6/7</span> confermate'


def tavoli(titolo, accent=False):
    """«Ai tavoli adesso» per chi non ha una partita; «Altre partite del
    turno» per chi ce l'ha, che la sua la vede sopra. Stesso dato."""
    line = 'rgba(255,255,255,.12)' if accent else 'var(--c7-line)'
    bg = ' style="background:rgba(255,255,255,.08)"' if accent else ""
    mut = 'var(--c7-accent-dim)' if accent else 'var(--c7-ink-muted)'
    return f'''        <div class="inset"{bg}>
          <div class="c7-kicker">{titolo}</div>
          <div style="display:flex;flex-direction:column;gap:5px;margin-top:6px;font-size:12px;font-weight:700">
            <div class="row"><span class="c7-num" style="color:{mut}">T1</span><span class="trunc">Elena Furlan <span class="c7-num">4&ndash;1</span> Sara De Rossi</span></div>
            <div class="row"><span class="c7-num" style="color:{mut}">T2</span><span class="trunc">Andrea Zanin <span class="c7-num">2&ndash;2</span> Paolo Rizzo</span></div>
            <div class="row"><span class="c7-num" style="color:{mut}">T4</span><span class="trunc">Marco Bassi <span class="c7-num">3&ndash;2</span> Luca Berti</span></div>
          </div>
          <div class="meta" style="margin-top:6px;color:{mut};border-top:1px solid {line};padding-top:6px">e altre <span class="c7-num">3</span> da giocare</div>
        </div>
'''


def _medaglia(pos, nome):
    return (f'<div><span class="c7-pos c7-pos--{pos}"><svg viewBox="0 0 24 24" class="ico"><use href="#i-medal"></use></svg></span>'
            f'<div class="c7-num" style="margin-top:6px;font-size:11px;color:var(--c7-ink-muted)">{pos}&deg;</div>'
            f'<div class="trunc" style="margin-top:2px;font-size:12px;font-weight:800">{nome}</div></div>')


PODIO = '''        <div class="inset">
          <div class="c7-kicker">Podio</div>
          <div class="podium" style="margin-top:10px">
            ''' + _medaglia(1, "Elena Furlan") + _medaglia(2, "Marco Bassi") + _medaglia(3, "Luca Berti") + '''
          </div>
{extra}        </div>
'''
TU = ('          <div class="meta" style="margin-top:10px">Sei arrivato '
      '<span class="c7-num" style="color:var(--c7-ink)">5&deg;</span> su <span class="c7-num">16</span> '
      '<span class="c7-sep">&middot;</span> <span class="c7-num">8</span> vittorie su <span class="c7-num">12</span></div>\n')
GIOCATORI16 = '''        <div class="row" style="font-size:12px;font-weight:700">
          <span class="fill muted">Turni finiti</span>
          <span class="muted"><span class="c7-num">16</span> giocatori</span>
        </div>
'''

NOTA_TURNO = NOTA.format("Il turno 4 si avvia quando finisce l&rsquo;ultima partita.")


# ── Le colonne: i fatti ──────────────────────────────────────────────────────
COLS = [
    ("Nessun fatto tuo", "la tessera dell&rsquo;ospite"),
    ("Sei iscritto", "&egrave; una tua gara"),
    ("La dirigi", "il comando che aspetta"),
    ("La dirigi e sei iscritto", "somma; sul conflitto vince il direttore"),
]


def riga_aperta():
    stato = '<span class="c7-state c7-state--ok">Iscrizioni aperte</span>'
    return [
        card(*G4, pastiglie(stato), APERTA, btns(b("Dettagli"), b("Iscriviti", "success"))),
        card(*G4, pastiglie(ISCRITTO, stato), APERTA, btns(b("Dettagli"), b("Disiscriviti", "danger"))),
        card(*G4, pastiglie(DIRIGI, stato), APERTA, btns(b("Gestisci"), b("Iscriviti", "success"))),
        card(*G4, pastiglie(DIRIGI, ISCRITTO, stato), APERTA, btns(b("Gestisci"), b("Disiscriviti", "danger"))),
    ]


MIA_PARTITA = '''        <a class="inset inset--go" href="#" style="background:rgba(255,255,255,.08)">
          <span class="fill">
            <span class="c7-kicker">La tua partita <span class="c7-sep">&middot;</span> Turno 3 <span class="c7-sep">&middot;</span> Tavolo 4</span>
            <span class="row" style="margin-top:6px">
              <span class="fill" style="font-size:14px;font-weight:800">vs Luca Berti</span>
              <span class="c7-num" style="font-size:20px">3 &mdash; 2</span>
            </span>
          </span>
          <svg viewBox="0 0 24 24" class="ico chev"><use href="#i-chev"></use></svg>
        </a>
'''
CLASSIFICA_VIVA = INSET_GARA_VIVA.replace(
    'class="inset"', 'class="inset" style="background:rgba(255,255,255,.08)"'
).replace("border-top:1px solid var(--c7-line)", "border-top:1px solid rgba(255,255,255,.12)")


def riga_in_corso():
    stato = '<span class="c7-state c7-state--live">Live</span>'
    turno = TURNO.format(extra="")
    turno_dir = TURNO.format(extra=CONFERMATE)
    segui = b("Segui la diretta", "bright")
    gest = b("Gestisci", "bright")
    avvia = b("Avvia il turno 4", "ghost")
    return [
        card(*G3, pastiglie(stato), turno + tavoli("Ai tavoli adesso", True), btns(segui), True),
        card(*G3, pastiglie(ISCRITTO, stato), turno + MIA_PARTITA + CLASSIFICA_VIVA, btns(segui), True),
        card(*G3, pastiglie(DIRIGI, stato), turno_dir + tavoli("Ai tavoli adesso", True),
             btns(gest, avvia), True, NOTA_TURNO),
        card(*G3, pastiglie(DIRIGI, ISCRITTO, stato), turno_dir + MIA_PARTITA + CLASSIFICA_VIVA,
             btns(gest, avvia), True, NOTA_TURNO),
    ]


def riga_conclusa():
    stato = '<span class="c7-state c7-state--muted">Conclusa</span>'
    ris = btns(b("Risultati"))
    return [
        card(*G2, pastiglie(stato), GIOCATORI16 + PODIO.format(extra=""), ris),
        card(*G2, pastiglie(HAI_GIOCATO, stato), GIOCATORI16 + PODIO.format(extra=TU), ris),
        card(*G2, pastiglie(HAI_DIRETTO, stato), GIOCATORI16 + PODIO.format(extra=""), ris),
        card(*G2, pastiglie(HAI_DIRETTO, HAI_GIOCATO, stato), GIOCATORI16 + PODIO.format(extra=TU), ris),
    ]


ROWS = [
    ("Iscrizioni aperte", "Gara 4 &middot; 12/09"),
    ("In corso", "Gara 3 &middot; turno 3 di 5"),
    ("Conclusa", "Gara 2 &middot; 16/08"),
]


def matrice(titolo, sotto, cols, rows, celle, ncol):
    out = [f'<div class="matrix" style="--cols:{ncol}">\n',
           f'  <div class="mx-title"><h2>{titolo}</h2><div class="meta">{sotto}</div></div>\n',
           '  <div></div>\n']
    for nome, sub in cols:
        out.append(f'  <div class="mx-col">{nome}<div class="meta">{sub}</div></div>\n')
    for (nome, sub), cards in zip(rows, celle):
        out.append(f'  <div class="mx-row">{nome}<div class="meta">{sub}</div></div>\n')
        for c in cards:
            out.append('  <div class="mx-cell">\n' + c + '  </div>\n')
    out.append('</div>\n')
    return "".join(out)


def tessera():
    return matrice(
        "La tessera decisa",
        "Barra e numeri sulle aperte, scura in corso, azioni all&rsquo;altezza standard, "
        "il riquadro della tua partita &egrave; il bersaglio, chi dirige ha Gestisci.",
        COLS, ROWS, [riga_aperta(), riga_in_corso(), riga_conclusa()], 4)


# ── Campionato ───────────────────────────────────────────────────────────────
def classifica(righe, finale=False):
    k = "Classifica finale" if finale else "Classifica generale"
    rows = "".join(righe)
    return f'''        <div class="inset">
          <div class="c7-kicker">{k}</div>
          <div class="c7-rows" style="margin-top:4px">
{rows}          </div>
        </div>
'''


def rr(pos, nome, v, tu=False, cls=""):
    c = f"c7-pos c7-pos--{pos}" if pos <= 3 else "c7-pos"
    n = f'{nome} &mdash; sei tu' if tu else nome
    st = ';color:var(--c7-ink)' if tu else ''
    sep = ' style="border-color:var(--c7-line);border-top-style:dashed"' if cls == "gap" else ' style="border-color:var(--c7-line)"'
    return (f'            <div class="c7-rows__row"{sep}>\n'
            f'              <span class="{c}">{pos}</span>\n'
            f'              <span class="fill trunc" style="font-size:13px;font-weight:800{st}">{n}</span>\n'
            f'              <span class="c7-num muted" style="font-size:12px">{v} vittorie</span>\n'
            f'            </div>\n')


TOP3 = [rr(1, "Elena Furlan", 7), rr(2, "Marco Bassi", 6), rr(3, "Luca Berti", 6)]
TOP3_TU = TOP3 + [rr(4, "marco", 5, tu=True, cls="gap")]
FIN3 = [rr(1, "Elena Furlan", 31), rr(2, "Marco Bassi", 28), rr(3, "Luca Berti", 27)]
FIN3_TU = FIN3 + [rr(6, "marco", 22, tu=True, cls="gap")]

PROSSIME = '''        <div class="inset">
          <div class="c7-kicker">Prossime gare</div>
          <div style="display:flex;flex-direction:column;gap:6px;margin-top:6px;font-size:12px;font-weight:700">
            <div class="row"><span class="c7-num muted">12/09</span><span class="trunc fill">Gara 4 <span class="c7-sep">&middot;</span> Palla 9 <span class="c7-sep">&middot;</span> Biliardo Club Udine</span></div>
            <div class="meta" style="color:var(--c7-warn)">Le iscrizioni chiudono il <span class="c7-num">10/09 20:00</span></div>
            <div class="row"><span class="c7-num muted">03/10</span><span class="trunc fill">Gara 5 <span class="c7-sep">&middot;</span> Palla 8 <span class="c7-sep">&middot;</span> Biliardo Club Udine</span></div>
          </div>
        </div>
'''

C_IN = ("Campionato Sociale 2026",
        'amalfi <span class="c7-sep">&middot;</span> 5 gare <span class="c7-sep">&middot;</span> '
        'prossima <span class="c7-num" style="color:var(--c7-ink)">12/09</span>')
C_FIN = ("Campionato Primavera 2026",
         'amalfi <span class="c7-sep">&middot;</span> 6 gare <span class="c7-sep">&middot;</span> '
         'ultima gara il <span class="c7-num" style="color:var(--c7-ink)">20/08</span>')
PEN = ('<span class="c7-iconbtn" style="width:56px;height:56px"><svg viewBox="0 0 24 24" class="ico ico-sm"><use href="#i-pen"></use></svg></span>')

COLS_C = [
    ("Nessun fatto tuo", "la tessera dell&rsquo;ospite"),
    ("Iscritto a una sua gara", "&egrave; un tuo campionato"),
    ("Lo dirigi", "la gestione al posto dei dettagli"),
]
ROWS_C = [("In corso", "5 gare, 3 giocate"), ("Concluso", "ultima gara il 20/08")]


def campionato():
    in_corso = '<span class="c7-state c7-state--err">In corso</span>'
    concluso = '<span class="c7-state c7-state--muted">Concluso</span>'
    cr = btns(b("Classifica e risultati"))
    gest = ('        <div style="display:flex;gap:8px">\n'
            f'          {b("Gestione")}\n          {PEN}\n        </div>\n')
    r1 = [
        card(*C_IN, pastiglie(in_corso), classifica(TOP3) + PROSSIME, cr),
        card(*C_IN, pastiglie(ISCRITTO, in_corso), classifica(TOP3_TU) + PROSSIME, cr),
        card(*C_IN, pastiglie(DIRIGI, in_corso), classifica(TOP3) + PROSSIME, gest),
    ]
    r2 = [
        card(*C_FIN, pastiglie(concluso), classifica(FIN3, True), cr),
        card(*C_FIN, pastiglie(HAI_GIOCATO, concluso), classifica(FIN3_TU, True), cr),
        card(*C_FIN, pastiglie(HAI_DIRETTO, concluso), classifica(FIN3, True), cr),
    ]
    return matrice("Campionato", "Stessa regola: la tessera dell&rsquo;ospite ha gi&agrave; la testa della classifica e le prossime gare; "
                   "chi ha un fatto ci aggiunge la sua riga, chi lo dirige cambia il pulsante.",
                   COLS_C, ROWS_C, [r1, r2], 3)


# ── Concluse in dashboard (regola 2) ─────────────────────────────────────────
def compatta(titolo, meta, past, extra="", locked=False):
    cls = "c7-card cardstack" + (" c7-card--locked" if locked else "")
    return f'''      <article class="{cls}">
        <div class="rowtop">
          <div class="fill">
            <div class="cardtitle">{titolo}</div>
            <div class="meta">{meta}</div>
          </div>
          {past}
        </div>
        <div class="meta"><span class="c7-num" style="color:var(--c7-ink)">1&deg;</span> Elena Furlan <span class="c7-sep">&middot;</span> <span class="c7-num">2&deg;</span> Marco Bassi <span class="c7-sep">&middot;</span> <span class="c7-num">3&deg;</span> Luca Berti</div>
{extra}        <span class="btn btn-secondary btn-w">Risultati</span>
      </article>
'''


CONCL = '<span class="c7-state c7-state--muted">Conclusa</span>'
M_G = ('Gara singola <span class="c7-sep">&middot;</span> Palla 8 <span class="c7-sep">&middot;</span> '
       '<span class="c7-num" style="color:var(--c7-ink)">04/09</span> <span class="c7-sep">&middot;</span> Sala Da Vinci, Pordenone')
M_2 = ('Campionato Sociale 2026 <span class="c7-sep">&middot;</span> Palla 8 <span class="c7-sep">&middot;</span> '
       '<span class="c7-num" style="color:var(--c7-ink)">16/08</span> <span class="c7-sep">&middot;</span> Biliardo Club Udine')
M_F = ('Gara singola <span class="c7-sep">&middot;</span> Palla 9 <span class="c7-sep">&middot;</span> '
       '<span class="c7-num" style="color:var(--c7-ink)">15/08</span> <span class="c7-sep">&middot;</span> Circolo Ferragosto, Grado')

TU_LINE = ('        <div class="meta">Sei arrivato <span class="c7-num" style="color:var(--c7-ink)">5&deg;</span> '
           'su <span class="c7-num">16</span></div>\n')

concluse_gare = (compatta("Torneo del Gioved&igrave;", M_G, pastiglie(HAI_DIRETTO, CONCL))
                 + compatta("Gara 2 &mdash; Palla 8", M_2, pastiglie(HAI_GIOCATO, CONCL), TU_LINE)
                 + compatta("Coppa di Ferragosto", M_F, pastiglie(CONCL)))

CAMP_CONCLUSO = f'''      <article class="c7-card cardstack">
        <div class="rowtop">
          <div class="fill">
            <div class="cardtitle">Campionato Primavera 2026</div>
            <div class="meta">amalfi <span class="c7-sep">&middot;</span> 6 gare <span class="c7-sep">&middot;</span> ultima gara il <span class="c7-num" style="color:var(--c7-ink)">20/08</span></div>
          </div>
          {pastiglie(HAI_GIOCATO, '<span class="c7-state c7-state--muted">Concluso</span>')}
        </div>
        <div class="meta"><span class="c7-num" style="color:var(--c7-ink)">1&deg;</span> Elena Furlan <span class="c7-sep">&middot;</span> <span class="c7-num">2&deg;</span> Marco Bassi <span class="c7-sep">&middot;</span> <span class="c7-num">3&deg;</span> Luca Berti</div>
        <div class="meta">Sei arrivato <span class="c7-num" style="color:var(--c7-ink)">6&deg;</span> su <span class="c7-num">14</span></div>
        <span class="btn btn-secondary btn-w">Classifica e risultati</span>
      </article>
'''

NOTA_FINESTRA = ('      <div class="meta" style="text-align:center">L&rsquo;ultima e quelle dell&rsquo;ultimo mese. '
                 'Le altre <span class="c7-num">31</span> sono nello storico.</div>\n')

concluse = (sez("Le tue gare", '      <div class="meta">&hellip; le gare vive, come sopra &hellip;</div>\n', "2", None)
            + sez("Concluse", concluse_gare + NOTA_FINESTRA, "3", "Storico")
            + sez("Campionati conclusi", CAMP_CONCLUSO, "1", "Storico"))


# ── Storico ──────────────────────────────────────────────────────────────────
def head_storico():
    return '''  <header class="c7-head">
    <span class="c7-head__back"><svg viewBox="0 0 24 24" class="ico ico-lg"><use href="#i-chev" transform="rotate(180 12 12)"></use></svg></span>
    <div class="c7-head__title">
      <span class="c7-title">Storico</span>
      <span class="c7-head__sub">Gare e campionati conclusi</span>
    </div>
  </header>
'''


def riga_storico(nome, meta, vinc, past=""):
    return f'''        <a class="listrow" href="#">
          <span class="fill">
            <span style="display:block;font-size:14px;font-weight:800">{nome}</span>
            <span class="meta" style="display:block">{meta}</span>
            <span class="meta" style="display:block"><span class="c7-num" style="color:var(--c7-ink)">1&deg;</span> {vinc}</span>
          </span>
          {past}<svg viewBox="0 0 24 24" class="ico chev"><use href="#i-chev"></use></svg>
        </a>
'''


def mese(nome, righe):
    return (f'      <div class="mese">{nome}</div>\n'
            '      <div class="c7-card">\n' + "".join(righe) + '      </div>\n')


STORICO = f'''    <div class="seg"><span class="is-on">Gare</span><span>Campionati</span></div>
    <div class="field"><svg viewBox="0 0 24 24" class="ico"><use href="#i-search"></use></svg>Cerca per nome o sala</div>
    <div class="chips">
      <span class="chip is-on">Tutte</span>
      <span class="chip">Che ho giocato</span>
      <span class="chip">Che ho diretto</span>
      <span class="chip">Nei primi <span class="c7-num">3</span> <svg viewBox="0 0 24 24" class="ico ico-sm"><use href="#i-chev" transform="rotate(90 12 12)"></use></svg></span>
      <span class="chip">2026 <svg viewBox="0 0 24 24" class="ico ico-sm"><use href="#i-chev" transform="rotate(90 12 12)"></use></svg></span>
    </div>
    <div class="meta"><span class="c7-num" style="color:var(--c7-ink)">34</span> gare concluse nel 2026 <span class="c7-sep">&middot;</span> <span class="c7-num">9</span> giocate, <span class="c7-num">4</span> dirette</div>
    <section class="sec" style="gap:8px">
{mese("Settembre 2026", [
    riga_storico("Torneo del Gioved&igrave;", "04/09 &middot; Palla 8 &middot; Sala Da Vinci", "Elena Furlan", HAI_DIRETTO),
])}{mese("Agosto 2026", [
    riga_storico("Campionato Primavera &middot; Gara 6", "20/08 &middot; Palla 8 &middot; Biliardo Club Udine", "Marco Bassi", HAI_GIOCATO),
    riga_storico("Gara 2 &mdash; Palla 8", "16/08 &middot; Campionato Sociale 2026", "Elena Furlan", HAI_GIOCATO),
    riga_storico("Coppa di Ferragosto", "15/08 &middot; Palla 9 &middot; Circolo Ferragosto, Grado", "Ivan Sartori"),
    riga_storico("Gara 1 &mdash; Palla 8", "02/08 &middot; Campionato Sociale 2026", "Luca Berti", HAI_GIOCATO),
])}{mese("Luglio 2026", [
    riga_storico("Notturna di luglio", "25/07 &middot; Palla 9 &middot; Sala Centrale, Trieste", "Giulia Nardin", HAI_DIRETTO),
    riga_storico("Campionato Primavera &middot; Gara 5", "12/07 &middot; Palla 8 &middot; Biliardo Club Udine", "Elena Furlan", HAI_GIOCATO),
])}      <span class="btn btn-secondary btn-secondary--onpage btn-w" style="margin-top:6px">Mostra altre <span class="c7-num">27</span></span>
    </section>
'''


if __name__ == "__main__":
    (OUT / "Tessera.body").write_text(tessera(), encoding="utf-8")
    (OUT / "TesseraCampionato.body").write_text(campionato(), encoding="utf-8")
    (OUT / "Concluse.body").write_text(screen(G_HEAD, concluse, NAV_GIOC), encoding="utf-8")
    (OUT / "Storico.body").write_text(screen(head_storico(), STORICO, NAV_GIOC), encoding="utf-8")
    for n in ["Tessera", "TesseraCampionato", "Concluse", "Storico"]:
        print("scritto", n)
