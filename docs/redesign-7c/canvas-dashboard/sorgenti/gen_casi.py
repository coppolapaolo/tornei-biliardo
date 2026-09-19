# -*- coding: utf-8 -*-
"""Gli altri casi dell'inventario, nella forma scelta il 30/08:
giocatore C (ogni cosa dentro cio' a cui appartiene), direttore B (comandi di
direzione sulla card), ospite C (l'account chiesto dove serve).

Riusa i pezzi dei due generatori del confronto invece di ricopiarli: se cambia
la card della gara, cambia anche qui.
"""

import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from gen_confronto import (  # noqa: E402
    CARD_GARA4,
    CARD_SFIDA,
    INSET_GARA_VIVA,
    INSET_PARTITA,
    INSET_PLAYOFF,
    G_HEAD,
    D_HEAD,
    NAV_GIOC,
    NAV_DIR,
    card_campionato,
    card_gara3,
    screen,
    sez,
    ISCRITTO,
)
from gen_ospite import (  # noqa: E402
    CAMPIONATO as CAMPIONATO_PUB,
    IN_ARRIVO,
    aperte,
    BTN_ISCRIVITI,
    BTN_ATTESA,
    NOTA_ACCOUNT,
    sez as sez_ospite,
    screen as screen_ospite,
)

OUT = pathlib.Path(__file__).parent

GIOCA_GARA = (
    '        <span class="btn btn-primary btn-w">'
    '<svg viewBox="0 0 24 24" class="ico ico-sm"><use href="#i-play"></use></svg>'
    "Gioca la tua partita</span>\n"
)

# Il blocco «Come stai andando» si prende **dall'artboard che ritrae l'app
# com'e' oggi**: e' l'unico posto in cui deve restare identico, e ricopiarlo a
# mano vorrebbe dire farlo divergere al primo ritocco.
_MAIN = (OUT / "Main.body").read_text(encoding="utf-8")
FEEDBACK = re.search(
    r'    <section class="c7-feedback">.*?\n    </section>\n', _MAIN, re.S
).group(0)


def vuoto(icona, titolo, testo, azioni=""):
    return f"""      <div class="c7-empty">
        <div class="c7-empty__ico"><svg viewBox="0 0 24 24" class="ico ico-lg"><use href="#i-{icona}"></use></svg></div>
        <div class="c7-empty__title">{titolo}</div>
        <p class="c7-empty__text">{testo}</p>
{azioni}      </div>
"""


# ── 1. Primo accesso della sessione ──────────────────────────────────────────
# L'unico momento in cui il saluto occupa il posto in cima. Sotto, la forma C.
primo = (
    FEEDBACK
    + sez(
        "Le tue gare",
        card_gara3(GIOCA_GARA, insets=INSET_PARTITA + INSET_GARA_VIVA),
        "1",
    )
    + sez("Sfide a due", CARD_SFIDA, "1", None)
    + sez("Aperte, puoi iscriverti", CARD_GARA4, "1")
    + sez("Campionati", card_campionato(extra=INSET_PLAYOFF), "1 attivo", "Vedi tutti")
)

# ── 2. Appena iscritto ───────────────────────────────────────────────────────
# Nessun numero da mostrare: al posto del blocco, i tre passi verso il primo
# dato vero. La stessa fetta di schermo, un contenuto diverso.
SETUP = """    <section class="c7-feedback">
      <div class="row" style="gap:14px">
        <span class="c7-feedback__donut" style="background:conic-gradient(var(--c7-accent) 0 33%, var(--c7-line) 0)">
          <span>1/3</span>
        </span>
        <div class="fill">
          <h2 style="font-size:17px">Il tuo profilo è pronto</h2>
          <p class="meta">Fai la prima attività e qui comparirà il tuo andamento.</p>
        </div>
      </div>
      <div class="inset" style="margin-top:14px">
        <div class="c7-rows">
          <div class="c7-rows__row" style="border-color:var(--c7-line)">
            <span class="c7-pos c7-pos--1"><svg viewBox="0 0 24 24" class="ico ico-sm"><use href="#i-check"></use></svg></span>
            <span class="fill">
              <span style="display:block;font-size:13px;font-weight:800">Account creato</span>
              <span class="meta">La tua città: Udine</span>
            </span>
          </div>
          <div class="c7-rows__row" style="border-color:var(--c7-line)">
            <span class="c7-pos"><svg viewBox="0 0 24 24" class="ico ico-sm"><use href="#i-circle"></use></svg></span>
            <span class="fill">
              <span style="display:block;font-size:13px;font-weight:800;color:var(--c7-ink-muted)">Gioca il primo match</span>
              <span class="meta">Da qui parte il tuo Elo</span>
            </span>
          </div>
          <div class="c7-rows__row" style="border-color:var(--c7-line)">
            <span class="c7-pos"><svg viewBox="0 0 24 24" class="ico ico-sm"><use href="#i-circle"></use></svg></span>
            <span class="fill">
              <span style="display:block;font-size:13px;font-weight:800;color:var(--c7-ink-muted)">Prova un esercizio</span>
              <span class="meta">Sblocca il punteggio di precisione</span>
            </span>
          </div>
        </div>
      </div>
    </section>
"""

nuovo = (
    SETUP
    + sez(
        "Le tue gare",
        vuoto(
            "target",
            "Non sei iscritto a nessuna gara",
            "Quando ti iscrivi a una gara la trovi qui, con la tua partita e la classifica.",
        ),
        "",
        None,
    )
    + sez("Aperte, puoi iscriverti", CARD_GARA4, "1")
    + sez("Campionati", card_campionato(), "1 attivo", "Vedi tutti")
)

# ── 3. Niente da nessuna parte ───────────────────────────────────────────────
# Quattro sezioni vuote sono quattro scatole uguali che dicono la stessa cosa.
# `c7-sections` gia' oggi nasconde le sezioni che non producono nulla: qui
# resta **una** schermata, che dice come stanno le cose e offre le due sole
# mosse che dipendono da chi legge.
vuoto_tot = """    <section class="sec" style="margin-top:8px">
      <div class="c7-empty">
        <div class="c7-empty__ico"><svg viewBox="0 0 24 24" class="ico ico-lg"><use href="#i-target"></use></svg></div>
        <div class="c7-empty__title">Non hai gare in corso</div>
        <p class="c7-empty__text">Non sei iscritto a nessuna gara, e in questo momento non ce n&rsquo;è nessuna con le iscrizioni aperte.</p>
        <div class="c7-empty__actions">
          <span class="btn btn-primary">Imposta le tue sale</span>
          <span class="btn btn-secondary btn-secondary--onpage">Sfoglia tutte le gare</span>
        </div>
      </div>
      <p class="meta" style="margin-top:12px;text-align:center">Con le sale impostate vedi qui le gare aperte della tua zona.</p>
    </section>
""" + sez(
    "Sfide a due",
    """      <div class="c7-card cardstack">
        <div class="c7-kicker">Nessuna proposta aperta</div>
        <p class="meta">Puoi sempre proporre una partita a qualcuno della tua sala, anche fuori da una gara.</p>
        <span class="btn btn-secondary btn-sm btn-w btn-secondary--onpage"><svg viewBox="0 0 24 24" class="ico ico-sm"><use href="#i-plus"></use></svg>Proponi un match</span>
      </div>
""",
    "",
    None,
)


# ── 4. La X da sostituire ────────────────────────────────────────────────────
# In forma C la X sta dentro la gara che l'ha prodotta. Due sotto-casi: con
# l'esercizio configurato e senza — nel secondo non c'e' niente da premere.
def inset_x(esercizio=True):
    if esercizio:
        azione = (
            '          <span class="btn btn-primary btn-sm btn-w" style="margin-top:12px">'
            '<svg viewBox="0 0 24 24" class="ico ico-sm"><use href="#i-play"></use></svg>'
            "Gioca l’esercizio</span>\n"
        )
        coda = ""
    else:
        azione = ""
        coda = (
            '          <div class="meta" style="margin-top:10px">Il direttore non ha ancora '
            "scelto l’esercizio: per ora non c’è niente da giocare.</div>\n"
        )
    return f"""        <div class="inset" style="background:var(--c7-warn-bg)">
          <div class="row">
            <span class="fill">
              <span class="c7-kicker" style="color:var(--c7-warn-ink)">Turno 4 <span class="c7-sep">&middot;</span> Resti senza avversario</span>
              <span style="display:block;margin-top:3px;font-size:14px;font-weight:800;color:var(--c7-warn-ink)">Hai un esercizio da giocare</span>
            </span>
          </div>
          <p class="meta" style="margin-top:6px;color:var(--c7-warn-body)">Invece di stare fermo giochi un esercizio: il punteggio diventa la tua differenza triangoli, fino a un massimo di <span class="c7-num">5</span>.</p>
{azione}{coda}        </div>
"""


def card_gara_x(titolo, meta, turno, giocatori, esercizio, classifica):
    return f"""      <article class="c7-card cardstack">
        <div class="rowtop">
          <div class="fill">
            <div class="cardtitle">{titolo}</div>
            <div class="meta">{meta}</div>
          </div>
          <div style="display:flex;flex-wrap:wrap;justify-content:flex-end;gap:6px;max-width:170px">{ISCRITTO}<span class="c7-state c7-state--err">In corso</span></div>
        </div>
        <div class="row" style="font-size:12px;font-weight:700">
          <span class="fill">Turno <span class="c7-num">{turno}</span></span>
          <span class="muted"><span class="c7-num">{giocatori}</span> giocatori</span>
        </div>
{inset_x(esercizio)}{classifica}        <span class="btn btn-secondary btn-sm btn-w">Vedi la gara</span>
      </article>
"""


M_X1 = (
    'Campionato Sociale 2026 <span class="c7-sep">&middot;</span> Palla 8 '
    '<span class="c7-sep">&middot;</span> <span class="c7-num">30/08</span> '
    '<span class="c7-sep">&middot;</span> Biliardo Club Udine'
)
M_X2 = (
    'Gara singola <span class="c7-sep">&middot;</span> Palla 9 '
    '<span class="c7-sep">&middot;</span> <span class="c7-num">28/08</span> '
    '<span class="c7-sep">&middot;</span> Sala Da Vinci, Pordenone'
)

ics = (
    sez(
        "Le tue gare",
        card_gara_x("Gara 3 &mdash; Palla 8", M_X1, "4/5", "13", True, INSET_GARA_VIVA)
        + card_gara_x("Coppa del Venerdì", M_X2, "2/4", "9", False, ""),
        "2",
    )
    + sez("Aperte, puoi iscriverti", CARD_GARA4, "1")
    + sez("Campionati", card_campionato(), "1 attivo", "Vedi tutti")
)

# ── 5. Gara conclusa, campionato concluso ────────────────────────────────────
from gen_tessera import podio as podio_medaglie  # noqa: E402

PODIO = podio_medaglie(
    '          <div class="meta" style="margin-top:10px">Sei arrivato '
    '<span class="c7-num" style="color:var(--c7-ink)">2&deg;</span> su <span class="c7-num">14</span> '
    '<span class="c7-sep">&middot;</span> <span class="c7-num">9</span> vittorie su <span class="c7-num">13</span></div>\n'
)

CARD_CONCLUSA = f"""      <article class="c7-card cardstack">
        <div class="rowtop">
          <div class="fill">
            <div class="cardtitle">Gara 3 &mdash; Palla 8</div>
            <div class="meta">Campionato Sociale 2026 <span class="c7-sep">&middot;</span> Palla 8 <span class="c7-sep">&middot;</span> <span class="c7-num">30/08/2026</span></div>
          </div>
          <span class="c7-state c7-state--muted">Conclusa</span>
        </div>
{PODIO}        <span class="btn btn-secondary btn-sm btn-w">Vedi i risultati</span>
      </article>
"""

CAMPIONATO_FINITO = """      <article class="c7-card c7-card--locked cardstack">
        <div class="rowtop">
          <div class="fill">
            <div class="cardtitle">Campionato Sociale 2026</div>
            <div class="meta">amalfi <span class="c7-sep">&middot;</span> 5 gare <span class="c7-sep">&middot;</span> concluso il <span class="c7-num">03/10</span></div>
          </div>
          <span class="c7-state c7-state--muted">Concluso</span>
        </div>
        <div class="inset" style="background:var(--c7-card)">
          <div class="c7-kicker">Classifica finale</div>
          <div class="c7-rows" style="margin-top:4px">
            <div class="c7-rows__row" style="border-color:var(--c7-line)">
              <span class="c7-pos c7-pos--1">1</span>
              <span class="fill trunc" style="font-size:13px;font-weight:800">Elena Furlan</span>
              <span class="c7-num muted" style="font-size:12px">31 vittorie</span>
            </div>
            <div class="c7-rows__row is-me">
              <span class="c7-pos c7-pos--2">2</span>
              <span class="fill trunc" style="font-size:13px;font-weight:800">marco</span>
              <span class="c7-num muted" style="font-size:12px">28 vittorie</span>
            </div>
            <div class="c7-rows__row" style="border-color:var(--c7-line)">
              <span class="c7-pos c7-pos--3">3</span>
              <span class="fill trunc" style="font-size:13px;font-weight:800">Luca Berti</span>
              <span class="c7-num muted" style="font-size:12px">27 vittorie</span>
            </div>
          </div>
        </div>
        <span class="btn btn-secondary btn-sm btn-w">Classifica e risultati</span>
      </article>
"""

concluse = (
    sez("Le tue gare", CARD_CONCLUSA, "1 conclusa")
    + sez("Aperte, puoi iscriverti", CARD_GARA4, "1")
    + sez("Campionati", CAMPIONATO_FINITO, "1 concluso", "Vedi tutti")
)

# ── 6. Direttore senza gare ──────────────────────────────────────────────────
AZIONI_DIR = (
    '        <div class="c7-empty__actions">\n'
    '          <span class="btn btn-primary">Crea la prima gara</span>\n'
    "        </div>\n"
)

dir_vuoto = sez(
    "Le tue gare",
    vuoto(
        "flag",
        "Non dirigi ancora nessuna gara",
        "Crea una gara singola, oppure un campionato con più gare in calendario. "
        "Qui compaiono anche le gare in cui giochi.",
        AZIONI_DIR,
    ),
    "",
    None,
) + sez("Aperte, puoi iscriverti", CARD_GARA4, "1")

# ── 7-8. Ospite ──────────────────────────────────────────────────────────────
ospite_quieto = (
    sez_ospite(
        "Iscrizioni aperte", aperte(BTN_ISCRIVITI, NOTA_ACCOUNT, BTN_ATTESA), "2"
    )
    + sez_ospite("Campionati in corso", CAMPIONATO_PUB, "1", "Vedi tutti")
    + sez_ospite("In arrivo", IN_ARRIVO, "", None)
)

OSPITE_VUOTO = """    <section class="sec" style="margin-top:40px">
      <div class="c7-empty">
        <div class="c7-empty__ico"><svg viewBox="0 0 24 24" class="ico ico-lg"><use href="#i-trophy"></use></svg></div>
        <div class="c7-empty__title">Non c&rsquo;è ancora niente da vedere</div>
        <p class="c7-empty__text">Nessuna gara aperta, nessun campionato in corso. Registrati adesso: quando parte la prima gara ti trovi già dentro.</p>
        <div class="c7-empty__actions">
          <span class="btn btn-success">Registrati</span>
          <span class="btn btn-secondary btn-secondary--onpage">Accedi</span>
        </div>
      </div>
    </section>
"""


# ── 9. Lista d'attesa ────────────────────────────────────────────────────────
# `WaitlistReason` ha due valori e l'interfaccia oggi non li distingue:
# CAPACITY (la gara e' piena) e PARITY (la gara non ammette la X, quindi
# serve un numero pari e l'ultimo iscritto aspetta). Il secondo caso, senza
# una spiegazione, si legge come un errore: sei in lista su una gara che
# mostra 17 posti occupati su 24. In entrambi i casi la promozione e'
# automatica, in ordine di posizione.
def inset_attesa(titolo, testo):
    return f"""        <div class="inset" style="background:var(--c7-warn-bg)">
          <div class="c7-kicker" style="color:var(--c7-warn-ink)">{titolo}</div>
          <p class="meta" style="margin-top:4px;color:var(--c7-warn-body)">{testo}</p>
        </div>
"""


def card_attesa(titolo, meta, pastiglie, riga, inset, azioni):
    return f"""      <article class="c7-card cardstack">
        <div class="rowtop">
          <div class="fill">
            <div class="cardtitle">{titolo}</div>
            <div class="meta">{meta}</div>
          </div>
          <div style="display:flex;flex-wrap:wrap;justify-content:flex-end;gap:6px;max-width:170px">{pastiglie}</div>
        </div>
        <div class="row" style="font-size:12px;font-weight:700">{riga}</div>
{inset}{azioni}      </article>
"""


AZ_ESCI = (
    '        <div style="display:flex;gap:8px">\n'
    '          <span class="btn btn-secondary btn-sm btn-fill">Dettagli</span>\n'
    '          <span class="btn btn-danger btn-sm btn-fill">Esci dalla lista</span>\n'
    "        </div>\n"
)
AZ_ENTRA = (
    '        <div style="display:flex;gap:8px">\n'
    '          <span class="btn btn-secondary btn-sm btn-fill">Dettagli</span>\n'
    '          <span class="btn btn-warning btn-sm btn-fill">Mettiti in lista</span>\n'
    "        </div>\n"
)

P_ATTESA3 = '<span class="c7-state c7-state--warn">Lista d\u2019attesa #3</span>'
P_ATTESA1 = '<span class="c7-state c7-state--warn">Lista d\u2019attesa #1</span>'
P_PIENA = '<span class="c7-state c7-state--warn">Massimo raggiunto</span>'
P_APERTE = '<span class="c7-state c7-state--ok">Iscrizioni aperte</span>'

attesa = (
    sez(
        "Le tue gare",
        card_attesa(
            "Torneo del Giovedì",
            'Gara singola <span class="c7-sep">&middot;</span> Palla 8 '
            '<span class="c7-sep">&middot;</span> <span class="c7-num">04/09</span> '
            '<span class="c7-sep">&middot;</span> Sala Da Vinci, Pordenone',
            P_ATTESA3 + P_APERTE,
            '<span class="fill muted">Quota <span class="c7-num">&euro;10,00</span></span>'
            '<span class="muted"><span class="c7-num">24/24</span> '
            '<span style="color:var(--c7-warn)">+3 in lista</span></span>',
            inset_attesa(
                "La gara è al completo",
                "Sei il terzo della lista. Se qualcuno si ritira entri tu, "
                "in ordine di posizione: succede da solo, non devi rifare l’iscrizione.",
            ),
            AZ_ESCI,
        )
        + card_attesa(
            "Coppa del Venerdì",
            'Gara singola <span class="c7-sep">&middot;</span> Palla 9 '
            '<span class="c7-sep">&middot;</span> <span class="c7-num">11/09</span> '
            '<span class="c7-sep">&middot;</span> Biliardo Club Udine',
            P_ATTESA1 + P_APERTE,
            '<span class="fill muted">Gratuita</span>'
            '<span class="muted"><span class="c7-num">17/24</span> '
            '<span style="color:var(--c7-warn)">+1 in lista</span></span>',
            inset_attesa(
                "Serve un numero pari",
                "Questa gara non prevede la X, quindi i giocatori devono essere pari "
                "e l’ultimo iscritto aspetta. Sei il primo della lista: appena si "
                "iscrive qualcun altro entri tu.",
            ),
            AZ_ESCI,
        ),
        "2",
    )
    + sez(
        "Aperte, puoi iscriverti",
        card_attesa(
            "Gara 4 &mdash; Palla 9",
            'Campionato Sociale 2026 <span class="c7-sep">&middot;</span> Palla 9 '
            '<span class="c7-sep">&middot;</span> <span class="c7-num">12/09</span> '
            '<span class="c7-sep">&middot;</span> Biliardo Club Udine',
            P_PIENA,
            '<span class="fill muted">Quota <span class="c7-num">&euro;10,00</span></span>'
            '<span class="muted"><span class="c7-num">24/24</span> '
            '<span style="color:var(--c7-warn)">+2 in lista</span></span>',
            "",
            AZ_ENTRA,
        ),
        "1",
    )
    + sez("Campionati", card_campionato(), "1 attivo", "Vedi tutti")
)

# ── 10. Partita senza tavolo ─────────────────────────────────────────────────
# `table_assignment` a NULL: il comando principale della card non puo' essere
# «Gioca», perche' non c'e' niente da aprire. Al suo posto serve l'unica cosa
# utile mentre si aspetta: chi sta occupando i tavoli e quanto manca.
INSET_SENZA_TAVOLO = """        <div class="inset">
          <div class="c7-kicker">La tua partita <span class="c7-sep">&middot;</span> Turno 4</div>
          <div class="row" style="margin-top:6px">
            <span class="fill" style="font-size:14px;font-weight:800">vs Giulia Nardin</span>
            <span class="c7-state c7-state--muted">In attesa del tavolo</span>
          </div>
          <div class="meta" style="margin-top:8px">I tavoli si assegnano da soli quando si liberano: la tua è una delle <span class="c7-num">2</span> ancora da assegnare.</div>
        </div>
"""

INSET_TAVOLI = """        <div class="inset">
          <div class="c7-kicker">Ai tavoli adesso</div>
          <div style="display:flex;flex-direction:column;gap:5px;margin-top:6px;font-size:12px;font-weight:700">
            <div class="row"><span class="c7-num muted">T1</span><span class="trunc">Elena Furlan <span class="c7-num">4&ndash;1</span> Sara De Rossi</span></div>
            <div class="row"><span class="c7-num muted">T2</span><span class="trunc">Andrea Zanin <span class="c7-num">2&ndash;2</span> Paolo Rizzo</span></div>
            <div class="row"><span class="c7-num muted">T3</span><span class="trunc">Marco Bassi <span class="c7-num">5&ndash;3</span> Ivan Sartori</span></div>
          </div>
          <div style="margin-top:10px;padding-top:10px;border-top:1px solid var(--c7-line)">
            <div class="c7-kicker">Classifica provvisoria</div>
            <div style="margin-top:2px;font-size:14px;font-weight:800">Sei <span class="c7-num">4&deg;</span> su <span class="c7-num">14</span></div>
          </div>
        </div>
"""

senza_tavolo = (
    sez(
        "Le tue gare",
        card_attesa(
            "Gara 3 &mdash; Palla 8",
            'Campionato Sociale 2026 <span class="c7-sep">&middot;</span> Palla 8 '
            '<span class="c7-sep">&middot;</span> <span class="c7-num">30/08</span> '
            '<span class="c7-sep">&middot;</span> Biliardo Club Udine',
            ISCRITTO + '<span class="c7-state c7-state--err">In corso</span>',
            '<span class="fill">Turno <span class="c7-num">4/5</span></span>'
            '<span class="muted"><span class="c7-num">14</span> giocatori</span>',
            INSET_SENZA_TAVOLO + INSET_TAVOLI,
            '        <span class="btn btn-secondary btn-sm btn-w">Vedi la gara</span>\n',
        ),
        "1",
    )
    + sez("Sfide a due", CARD_SFIDA, "1", None)
    + sez("Campionati", card_campionato(), "1 attivo", "Vedi tutti")
)


if __name__ == "__main__":
    giocatore = [
        ("CasoPrimoAccesso", primo),
        ("CasoNuovo", nuovo),
        ("CasoVuoto", vuoto_tot),
        ("CasoX", ics),
        ("CasoConcluse", concluse),
        ("CasoListaAttesa", attesa),
        ("CasoSenzaTavolo", senza_tavolo),
    ]
    for nome, corpo in giocatore:
        (OUT / f"{nome}.body").write_text(
            screen(G_HEAD, corpo, NAV_GIOC), encoding="utf-8"
        )
        print("scritto", nome)

    (OUT / "CasoDirettoreVuoto.body").write_text(
        screen(D_HEAD, dir_vuoto, NAV_DIR), encoding="utf-8"
    )
    print("scritto CasoDirettoreVuoto")

    for nome, corpo in [
        ("CasoOspiteQuieto", ospite_quieto),
        ("CasoOspiteVuoto", OSPITE_VUOTO),
    ]:
        (OUT / f"{nome}.body").write_text(screen_ospite(corpo), encoding="utf-8")
        (OUT / f"{nome}.css").write_text(
            ".screen--nonav{padding-bottom:28px}\n", encoding="utf-8"
        )
        print("scritto", nome)
