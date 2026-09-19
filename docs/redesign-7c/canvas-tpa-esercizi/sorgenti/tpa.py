#!/usr/bin/env python3
"""Artboard del referto TPA. Stessa situazione in tutte le direzioni: Marco
Rossi (compila) contro Sara Neri, palla 9 al 5, 2-1, triangolo 3: Marco ha
appena annotato «3 M» (tre bilie, poi un tiro sbagliato). Il turno si puo'
chiudere: il motore ammette ancora P, N e n, tutto il resto e' spento.

Il tastierino e' quello dell'app originale (Accustat TPA/tpa.html): UNO solo,
sempre tutto visibile, tre colonne come un telefono — 0 / 1 2 3 / 4 5 6 /
7 8 9 (/ 10 a palla 10) — poi M K S / P G N / n x p in posizione fissa. I tasti
non ammessi si spengono e non spariscono. Ogni giocatore ha le SUE due caselle
(bianca e ombreggiata), come sul foglio.

Decisioni dell'utente del 19/09: il tavolo si passa toccando il riquadro
dell'avversario (nessun pulsante); gli annulla sono DUE — «cancella» toglie
l'annotazione parziale del turno, «indietro/avanti» scorre il referto e
permette di ripartire da un punto del passato; il TPA ha la stessa evidenza
del punteggio."""

from kit import I, desktop, ico, phone

SUB = "Sfida con Sara Neri &middot; Palla 9 &middot; al 5"
KEBAB = (
    f'<button class="head__act" aria-label="Altre azioni">{ico(I["dots"], 18)}</button>'
)

# dopo «3 M^n» + fallo P il motore non ammette piu' niente (available_buttons torna vuoto):
# il turno e' completo, restano «cancella» e il tocco sul riquadro di Sara
AMMESSI = set()


def nota(tot, lettera="", apice="", spaccata=None, vinto=False, calcio=None):
    """La notazione del referto, come la scrive il motore (`main_note`) e come
    la vuole il cartaceo Accu-Stats:
    * le bilie fatte in SPACCATA sono un numero piccolo in alto, prima del totale;
    * le note piccole n, x, p sono apici della lettera (M^n, S^x, S^p);
    * il triangolo VINTO non e' una «G»: e' un cerchio attorno alle bilie;
    * il PRIMO TIRO DI CALCIO e' il numero del giocatore (1 o 2) cerchiato in
      piccolo, in una riga SOPRA l'annotazione — cosi' fa l'originale
      (`kickSequence` / `.circle-kick`). Non e' una freccia: `calcio` = 1 o 2.
    Il fallo (P o N) non sta qui: sta nella casella ombreggiata accanto."""
    num = (f"<sup>{spaccata}</sup>" if spaccata is not None else "") + str(tot)
    out = f'<span class="nt__won">{num}</span>' if vinto else num
    if lettera:
        out += f"&nbsp;{lettera}" + (f"<sup>{apice}</sup>" if apice else "")
    out = f'<span class="nt">{out}</span>'
    if calcio:
        out = f'<span class="ntk"><span class="ntk__n">{calcio}</span>{out}</span>'
    return out


def fallo(lettera):
    """Il fallo nel referto a righe: la casella ombreggiata in piccolo."""
    return f'<span class="nt__foul">{lettera}</span>'


def keypad(h=50, captions=False, ammessi=AMMESSI, cancella=True):
    st = f' style="height:{h}px"'

    def k(label, cls="", cap="", aria=""):
        c = f'<span class="key__cap">{cap}</span>' if captions and cap else ""
        a = f' aria-label="{aria}"' if aria else ""
        off = "" if label in ammessi else " key--off"
        return f'<button class="key{cls}{off}"{st}{a}>{label}{c}</button>'

    # primo annulla: toglie l'annotazione PARZIALE del turno in corso («3 M»),
    # non tocca i turni gia' chiusi. Acceso solo se c'e' qualcosa da togliere.
    canc = (
        f'<button class="key key--clear{"" if cancella else " key--off"}" style="height:{h}px" '
        f'aria-label="Cancella l&rsquo;annotazione di questo turno">'
        f'{ico(I["x"], 15)}<span class="key__cap" style="margin:0">cancella</span></button>'
    )
    # a palla 9 il 10 non c'e': il posto resta vuoto, non si sposta niente
    return f"""
<div class="pad">
  {canc}{k("0")}<span{st}></span>
  {k("1")}{k("2")}{k("3")}
  {k("4")}{k("5")}{k("6")}
  {k("7")}{k("8")}{k("9")}
</div>
<div class="pad">
  {k("M", "", "sbagliato")}{k("K", "", "di sponda")}{k("S", "", "difesa")}
  {k("P", " key--foul", "in buca")}{k("G", " key--game", "triangolo")}{k("N", " key--foul", "non colpita")}
  {k("n", " key--small")}{k("x", " key--small")}{k("p", " key--small")}
</div>"""


WIDE = (
    f'<div class="pad"><button class="key key--wide key--off">{ico(I["rotate"], 15)}'
    f"Primo tiro di calcio?</button></div>"
)


def storia(pos="turno 9 di 9", avanti=False):
    """Secondo annulla: scorre il referto un turno alla volta. «Avanti» si
    accende solo quando si e' tornati indietro."""
    off = "" if avanti else " hist__btn--off"
    return f"""
<div class="hist">
  <button class="hist__btn" aria-label="Turno precedente">{ico(I["back"], 15)}Indietro</button>
  <span class="hist__pos">{pos}</span>
  <button class="hist__btn{off}" aria-label="Turno successivo">Avanti<span style="display:inline-grid;transform:scaleX(-1)">{ico(I["back"], 15)}</span></button>
</div>"""


def caselle(bianca, grigia="", attivo=False, h=44, calcio=None):
    """Le due caselle del giocatore. Le annotazioni stanno CENTRATE e sulla
    stessa riga (bianca e ombreggiata); il primo tiro di calcio sta subito
    SOPRA la casella bianca, fuori dal bianco. La riga del calcio c'e' sempre,
    anche vuota, cosi' le caselle dei due giocatori restano allineate."""
    hint = (
        '<span class="tpa-box__hint" style="font-family:var(--c7-font)">bilie?</span>'
        if attivo and not bianca
        else ""
    )
    bg = (
        "background:var(--c7-card);color:var(--c7-ink)"
        if attivo
        else "background:rgba(242,248,247,.10);color:inherit"
    )
    bg2 = (
        "background:var(--c7-sunken)" if attivo else "background:rgba(242,248,247,.05)"
    )
    k = f'<span class="ntk__n" style="font-size:11px">{calcio}</span>' if calcio else ""
    return (
        f'<span style="display:grid;grid-template-columns:1fr 38px;gap:3px 5px;margin-top:4px">'
        f'<span class="kickrow">{k}</span><span></span>'
        f'<span class="tpa-box" style="min-height:{h}px;padding:4px;font-size:18px;align-items:center;{bg};font-family:var(--c7-font-mono)">{bianca}{hint}</span>'
        f'<span class="tpa-box" style="min-height:{h}px;padding:4px;font-size:16px;align-items:center;{bg2}">{grigia}</span></span>'
    )


def cifre(rack, tpa, size=34):
    """Punteggio e TPA alla pari: stessa cifra, stessa riga, un'etichetta ciascuno."""
    return (
        f'<span class="figs"><span class="fig"><span class="fig__k">Triangoli</span>'
        f'<span class="fig__v" style="font-size:{size}px">{rack}</span></span>'
        f'<span class="fig"><span class="fig__k">TPA</span>'
        f'<span class="fig__v" style="font-size:{size}px">{tpa}</span></span></span>'
    )


def tabellone(size=34, m=None, s=None, passa=True):
    """Il riquadro dell'avversario E' il comando «passa il tavolo»: e' un
    pulsante intero, e la riga in fondo lo dice."""
    m = m or ("2", "571", "al tavolo &middot; 3 bilie", nota(3, "M", "n"), "P", 1)
    s = s or ("1", "666", "2 bilie &middot; 1 errore", nota(2, "S", "x"), "", None)
    tap = (
        f'<span class="half__tap">{ico(I["swap"], 13)}Tocca: tavolo a Sara</span>'
        if passa
        else ""
    )
    return f"""
<section class="card card--accent" style="padding:12px">
  <div class="duo">
    <div class="half half--on" style="padding:12px">
      <span class="half__name">Marco Rossi</span>
      {cifre(m[0], m[1], size)}
      <span class="half__meta">{m[2]}</span>
      {caselle(m[3], m[4], attivo=True, calcio=m[5])}
    </div>
    <button class="half{" half--tap" if passa else ""}" style="padding:12px" aria-label="Sara Neri">
      <span class="half__name">Sara Neri</span>
      {cifre(s[0], s[1], size)}
      <span class="half__meta">{s[2]}</span>
      {caselle(s[3], s[4], calcio=s[5])}
      {tap}
    </button>
  </div>
</section>"""


def turn(seat, who, note, cls=""):
    return (
        f'<div class="sheet__turn{cls}"><span class="sheet__seat">{seat}</span>'
        f'<span class="sheet__who">{who}</span><span class="sheet__note">{note}</span></div>'
    )


def foglio(full=True):
    rows = ""
    if full:
        rows += (
            '<div class="sheet__rack"><span>Triangolo 2</span><span>1 &ndash; 1</span></div>'
            + turn(2, "Sara Neri", nota(4, "S", "p", spaccata=1))
            + turn(1, "Marco Rossi", nota(0, "K") + fallo("P"))
            + turn(2, "Sara Neri", nota(5, vinto=True, calcio=2), " sheet__turn--won")
        )
    rows += (
        '<div class="sheet__rack"><span>Triangolo 3</span><span>2 &ndash; 1</span></div>'
        + turn(1, "Marco Rossi", nota(3, "M", spaccata=1))
        + turn(2, "Sara Neri", nota(2, "S", "x"))
    )
    return rows


FOGLIO_RIGA = f"""
<button class="rows" style="border:0;padding:0;text-align:left;font-family:inherit;width:100%">
  <span class="rows__row">
    <span class="tile tile--sm tile--neutral">{ico(I["sheet"], 17)}</span>
    <span class="grow"><span class="rows__title" style="display:block">Referto</span>
      <span class="rows__sub" style="display:block">Triangolo 3 &middot; in corso: Marco Rossi, 3 M&#8319; e fallo P</span></span>
    {ico(I["chevron"], 16)}
  </span>
</button>"""


# --------------------------------------------------------------------------
# A · Ordine — la pagina di oggi, messa in ordine (con la nav: scorre)
# --------------------------------------------------------------------------


def tpa_a():
    content = f"""
{tabellone()}
{keypad(h=48)}
{WIDE}
{storia()}
{FOGLIO_RIGA}"""
    return phone("Referto TPA", SUB, content, nav="Sfide", action=KEBAB, h=976)


# --------------------------------------------------------------------------
# B · Tavolo — schermata a fuoco: tutto il tastierino sotto il pollice
# --------------------------------------------------------------------------


def tpa_b():
    content = tabellone()
    dock = f"""
<div class="dock">
  {keypad(h=48, captions=True)}
  {WIDE}
  {storia()}
</div>"""
    return phone("Referto TPA", SUB, content, nav=None, dock=dock, action=KEBAB)


# --------------------------------------------------------------------------
# C · Foglio vivo — col tastierino intero, del foglio resta una riga
# --------------------------------------------------------------------------


def tpa_c():
    content = f"""
<div class="duo">
  <div class="card card--accent" style="padding:10px 14px">
    <div class="row"><span class="grow" style="font-size:13px;font-weight:800">Marco Rossi</span>
      <span class="tpa-player__racks" style="background:var(--c7-accent-bright);min-width:28px;height:28px">2</span></div>
    <div class="row" style="margin-top:2px"><span class="tpa-player__tpa" style="font-size:20px">571</span>
      <span style="font-size:11px;font-weight:700;color:var(--c7-accent-dim)">al tavolo</span></div>
  </div>
  <button class="card" style="padding:10px 14px;border:1.5px solid var(--c7-line);text-align:left;font-family:inherit;color:inherit" aria-label="Passa il tavolo a Sara Neri">
    <span class="row"><span class="grow" style="font-size:13px;font-weight:800">Sara Neri</span>
      <span class="tpa-player__racks" style="min-width:28px;height:28px">1</span></span>
    <span class="row" style="margin-top:2px"><span class="tpa-player__tpa" style="font-size:20px">666</span>
      <span style="font-size:11px;font-weight:700;color:var(--c7-ink-muted)">tocca: passa il tavolo</span></span>
  </button>
</div>
<div class="sheet">
  <div class="sheet__rack"><span>Triangolo 3 &middot; il referto continua sopra</span><span>2 &ndash; 1</span></div>
  {turn(2, "Sara Neri", nota(2, "S", "x"))}
  <div class="sheet__turn sheet__turn--now" style="grid-template-columns:22px 1fr 150px;padding:8px var(--c7-pad-card)">
    <span class="sheet__seat" style="background:var(--c7-accent);color:#fff">1</span>
    <span class="sheet__who">Marco Rossi <span class="ntk__n" style="font-size:10px;margin-left:4px">1</span></span>
    <span style="display:grid;grid-template-columns:1fr 38px;gap:5px">
      <span class="tpa-box tpa-box--white" style="min-height:40px;padding:4px;font-size:18px;align-items:center;font-family:var(--c7-font-mono)">{nota(3, "M", "n")}</span>
      <span class="tpa-box" style="min-height:40px;padding:4px;background:var(--c7-card);font-size:16px;align-items:center">P</span></span>
  </div>
</div>"""
    dock = f"""
<div class="dock">
  {keypad(h=48)}
  {WIDE}
  {storia()}
</div>"""
    return phone("Referto TPA", SUB, content, nav=None, dock=dock, action=KEBAB)


# --------------------------------------------------------------------------
# Desktop — tre colonne: giocatori, tastierino (sempre 3 colonne), foglio
# --------------------------------------------------------------------------


def tpa_desktop():
    actions = '<button class="btn btn--secondary btn--sm">Chiudi il referto</button>'
    content = f"""
<div style="display:grid;grid-template-columns:minmax(0,1fr) 340px 380px;gap:var(--c7-gap-lg);align-items:start">
  <div class="stack">
    {tabellone(size=44)}
    <section class="card">
      <div class="kicker">Cosa vuol dire ogni lettera</div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px 20px;margin-top:10px;font-size:12px;color:var(--c7-ink-muted)">
        <span><b style="color:var(--c7-ink)">M</b> &middot; tiro sbagliato</span>
        <span><b style="color:var(--c7-ink)">K</b> &middot; tiro di sponda obbligato</span>
        <span><b style="color:var(--c7-ink)">S</b> &middot; difesa</span>
        <span><b style="color:var(--c7-ink)">P</b> &middot; battente in buca o fuori</span>
        <span><b style="color:var(--c7-ink)">G</b> &middot; triangolo vinto: sul referto &egrave; un cerchio</span>
        <span><b style="color:var(--c7-ink)">N</b> &middot; bilia non colpita</span>
        <span><b style="color:var(--c7-ink)">n</b> &middot; sbagliato un tiro facile</span>
        <span><b style="color:var(--c7-ink)">x</b> &middot; difesa voluta</span>
        <span><b style="color:var(--c7-ink)">p</b> &middot; push out</span>
        <span><b style="color:var(--c7-ink)">&#9312;</b> sopra &middot; primo tiro di calcio, col numero di chi tira</span>
        <span><b style="color:var(--c7-ink)"><sup>1</sup>4</b> &middot; una in spaccata, quattro in tutto</span>
      </div>
    </section>
  </div>
  <div class="stack">
    {keypad(h=64, captions=True)}
    {WIDE}
    {storia()}
  </div>
  <div class="stack">
    <div class="sechead"><h3>Referto</h3><span class="sechead__more">Triangolo 3 di 9</span></div>
    <div class="sheet">
      <div class="sheet__rack"><span>Triangolo 1</span><span>1 &ndash; 0</span></div>
      {turn(1, "Marco Rossi", nota(4, "M", spaccata=1))}
      {turn(2, "Sara Neri", nota(1, "M", "n") + fallo("N"))}
      {turn(1, "Marco Rossi", nota(5, vinto=True), " sheet__turn--won")}
      {foglio(full=True)}
      {turn(1, "Marco Rossi", nota(3, "M", "n", calcio=1) + fallo("P"), " sheet__turn--now")}
    </div>
  </div>
</div>"""
    return desktop("Referto TPA", SUB, actions, content)


# --------------------------------------------------------------------------
# Referto chiuso — oggi e' la stessa pagina in sola lettura
# --------------------------------------------------------------------------


def tpa_chiuso():
    def err(label, a, b):
        return f'<div>{label}</div><div class="n">{a}</div><div class="n">{b}</div>'

    content = f"""
<section class="card card--accent" style="padding:12px">
  <div class="duo">
    <div class="half half--on"><span class="half__name">Marco Rossi</span>
      <span class="half__rack">5</span><span class="half__tpa">TPA 742</span>
      <span class="half__meta">23 bilie &middot; 8 errori</span></div>
    <div class="half"><span class="half__name">Sara Neri</span>
      <span class="half__rack">3</span><span class="half__tpa">TPA 655</span>
      <span class="half__meta">19 bilie &middot; 10 errori</span></div>
  </div>
  <div class="row" style="margin-top:10px;padding:0 4px">
    <span class="state state--onaccent">{ico(I["lock"], 11)}&nbsp;Referto chiuso</span>
    <span class="grow"></span>
    <span style="font-size:12px;font-weight:700;color:var(--c7-accent-dim)">8 triangoli giocati</span>
  </div>
</section>
<section class="card">
  <div class="kicker">Da dove vengono gli errori</div>
  <div class="errtab" style="margin-top:8px">
    <div class="h">&nbsp;</div><div class="h n">Marco</div><div class="h n">Sara</div>
    {err("Tiri sbagliati", 4, 5)}
    {err("Posizione", 2, 2)}
    {err("Difese", 1, 2)}
    {err("Spaccata", 1, 0)}
    {err("Tiri di sponda", 0, 1)}
  </div>
</section>
<div class="kpis">
  <div class="kpi"><div class="kpi__v">1</div><div class="kpi__l">Spacca e chiude</div></div>
  <div class="kpi"><div class="kpi__v">2</div><div class="kpi__l">Chiuse in un turno</div></div>
  <div class="kpi"><div class="kpi__v">1</div><div class="kpi__l">Triangoli perfetti</div></div>
</div>
<div class="sechead"><h3>Referto</h3><span class="sechead__more">Apri tutti</span></div>
<div class="sheet">
  <div class="sheet__rack"><span>Triangolo 1 &middot; Marco Rossi</span><span>1 &ndash; 0</span></div>
  {turn(1, "Marco Rossi", nota(4, "M", spaccata=1))}
  {turn(2, "Sara Neri", nota(1, "M", "n") + fallo("N"))}
  {turn(1, "Marco Rossi", nota(5, vinto=True), " sheet__turn--won")}
  <div class="sheet__rack"><span>Triangolo 2 &middot; Sara Neri</span><span>1 &ndash; 1</span></div>
  <div class="sheet__rack"><span>Triangolo 3 &middot; Marco Rossi &middot; spacca e chiude</span><span>2 &ndash; 1</span></div>
  <div class="sheet__rack"><span>Triangolo 4 &middot; Marco Rossi</span><span>3 &ndash; 1</span></div>
</div>
<button class="btn btn--secondary btn--w">Torna alla sfida</button>"""
    return phone(
        "Referto TPA",
        SUB,
        content,
        nav=None,
        h=1098,
        action=f'<button class="head__act" aria-label="Condividi">{ico(I["share"], 17)}</button>',
    )


# --------------------------------------------------------------------------
# B · Indietro nel referto — il secondo annulla: scorrere, e ripartire da li'
# --------------------------------------------------------------------------


def tpa_indietro():
    """Come nell'originale: scorrere e' sola lettura; per ripartire c'e' un
    passo esplicito, che dice quanti turni toglie."""
    avviso = f"""
<div class="state state--warn" style="height:auto;padding:9px 14px;gap:8px;justify-content:flex-start;font-size:12px;border-radius:var(--c7-r-control)">
  {ico(I["eye"], 15)}<span><b>Rileggi il turno 7 di 9</b> &middot; qui non si scrive</span></div>"""
    riparti = (
        '<button class="btn btn--primary btn--w" style="height:var(--c7-touch);font-size:14px">'
        "Riparti da questo turno&hellip;</button>"
    )
    return _passato(avviso=avviso, riparti=riparti)


def tpa_riparti():
    """La conferma: un foglio 7c al posto del confirm() nativo dell'originale."""
    overlay = f"""
<div class="veil"></div>
<div class="bottomsheet">
  <div class="grab"></div>
  <div style="font-size:18px;font-weight:800;letter-spacing:-.02em">Ripartire dal turno 7?</div>
  <div style="font-size:13px;font-weight:600;color:var(--c7-ink-soft);line-height:1.45">Il turno 7 si riapre vuoto e i <b>2 turni successivi</b> escono dal referto: quello di Sara Neri e quello di Marco Rossi. Punteggio e TPA si ricalcolano fin qui.</div>
  <div class="sheet">
    <div class="sheet__turn"><span class="sheet__seat">1</span><span class="sheet__who">Marco Rossi</span><span class="sheet__note">si riannota</span></div>
    <div class="sheet__turn" style="opacity:.5"><span class="sheet__seat">2</span><span class="sheet__who" style="text-decoration:line-through">Sara Neri</span><span class="sheet__note">{nota(2, "S", "x")}</span></div>
    <div class="sheet__turn" style="opacity:.5;border-bottom:0"><span class="sheet__seat">1</span><span class="sheet__who" style="text-decoration:line-through">Marco Rossi</span><span class="sheet__note">{nota(3, "M", "n", calcio=1)}{fallo("P")}</span></div>
  </div>
  <button class="btn btn--primary btn--w" style="height:var(--c7-touch)">Riparti dal turno 7</button>
  <button class="btn btn--secondary btn--w" style="height:var(--c7-touch)">Resta a guardare</button>
</div>"""
    return _passato(overlay=overlay)


def _passato(avviso="", riparti="", overlay=""):
    content = avviso + tabellone(
        m=("1", "500", "spaccata &middot; 3 bilie", nota(3, "M", spaccata=1), "", None),
        s=("1", "600", "7 bilie &middot; 2 errori", nota(5, vinto=True), "", 2),
        passa=False,
    )
    dock = f"""
<div class="dock">
  {keypad(h=44, captions=True, ammessi=set(), cancella=False)}
  {riparti}
  {storia(pos="turno 7 di 9", avanti=True)}
</div>"""
    return phone(
        "Referto TPA", SUB, content, nav=None, dock=dock, action=KEBAB, overlay=overlay
    )
