#!/usr/bin/env python3
"""Schede di allenamento (#172) e istruttori (#173).

SECONDO GIRO (decisioni dell'utente del 19/09): la scheda ha UNA forma sola.
La liberta' sta sulla VOCE — come si segna (fatto, riusciti su N, punteggio,
vinte) e quanto farne — e livello, soglia, giorni e durata sono interruttori
facoltativi della scheda. La soglia somma solo le voci «a riusciti». Il
GIOCATORE aggiunge o toglie i suoi istruttori e decide chi legge ogni scheda;
l'istruttore organizza gli allievi in gruppi con un periodo, che restano come
storico. Niente di questo esiste oggi nel codice (verificato il 19/09).

Il materiale di dominio resta il foglio che Ronin ASD usa oggi (scheda lv.3,
v0.6, vista il 19/09/2026):

* la scheda ha un LIVELLO e una SOGLIA per passare al successivo (40 su 50);
* ogni esercizio e' «riusciti su 5 tiri»: un'unita' sola, quindi si somma;
* molti esercizi si fanno a DESTRA e a SINISTRA, in due colonne distinte;
* il foglio e' il REGISTRO: una riga per seduta, l'andamento e' la griglia;
* si scrive una cifra per colonna: l'app deve costare un tocco, non di piu'.

I sei esercizi e i loro testi sono quelli del foglio."""

from kit import I, area_tabs, ball, freccia, ico, mezzo, ob, phone, seqstrip

CLOSE = f'<button class="head__act" aria-label="Chiudi">{ico(I["x"], 17)}</button>'
GRIP = '<span class="item__grip"><i></i><i></i><i></i></span>'

# Diagrammi su mezzo tavolo, buca d'angolo in alto a sinistra -----------------
_DRITTO = (
    ob(45, 120)
    + ball(105, 280)
    + freccia(98, 262, 52, 138, "#F5F7F6")
    + freccia(40, 106, 8, 22)
)
TANGENTE = (
    ob(130, 120)
    + ball(205, 245)
    + freccia(198, 233, 138, 134, "#F5F7F6")
    + freccia(120, 110, 14, 16)
    + freccia(142, 112, 240, 12, "#8FCDE8")
    + '<path d="M200 0H290" stroke="#8FCDE8" stroke-width="12" stroke-linecap="round"/>'
)
GHOST = (
    "".join(
        ob(x, y) for x, y in ((150, 70), (150, 120), (150, 170), (100, 170), (50, 170))
    )
    + ball(270, 300)
    + freccia(262, 286, 170, 136, "#F5F7F6")
    + freccia(138, 108, 16, 14)
)
ANGOLO = (
    ob(160, 100)
    + ball(240, 190)
    + freccia(232, 180, 170, 110, "#F5F7F6")
    + freccia(148, 92, 14, 12)
    + freccia(176, 118, 240, 300, "#8FCDE8")
    + '<rect x="190" y="290" width="100" height="100" fill="#8FCDE8" fill-opacity=".45"/>'
)

ESERCIZI = [
    ("1", TANGENTE, "Linea tangente", "5 tiri", False),
    ("2", GHOST, "Ghost ball", "5 tiri", False),
    ("3", _DRITTO, "Stop shot", "5 a destra, 5 a sinistra", True),
    ("4", _DRITTO, "Follow shot", "5 a destra, 5 a sinistra", True),
    ("5", _DRITTO, "Draw shot", "5 a destra, 5 a sinistra", True),
    ("6", ANGOLO, "Angolo naturale", "5 a destra, 5 a sinistra", True),
]
SEQ = ["Tangente", "Ghost", "Stop", "Follow", "Draw", "Angolo"]

# Le sedute: la prima e' la riga vera del foglio (14/09: 40 su 50).
SEDUTE = [
    ("14/09", [4, 5, 5, 5, 4, 2, 5, 5, 3, 2]),
    ("16/09", [4, 5, 4, 5, 5, 3, 5, 4, 4, 2]),
    ("18/09", [5, 5, 5, 5, 4, 3, 5, 5, 4, 3]),
]
COLONNE = [
    ("1", ""),
    ("2", ""),
    ("3", "dx"),
    ("3", "sx"),
    ("4", "dx"),
    ("4", "sx"),
    ("5", "dx"),
    ("5", "sx"),
    ("6", "dx"),
    ("6", "sx"),
]


def registro(vuote=2):
    out = (
        '<div class="hd">data</div>'
        + "".join(
            f'<div class="hd">{n}<small>{lato or "&nbsp;"}</small></div>'
            for n, lato in COLONNE
        )
        + '<div class="hd">tot</div>'
    )
    for data, voti in SEDUTE:
        out += f'<div class="dt">{data}</div>'
        for v in voti:
            cls = "hi" if v == 5 else ("lo" if v <= 2 else "")
            out += f'<div class="{cls}">{v}</div>'
        out += f'<div class="tot">{sum(voti)}</div>'
    for _ in range(vuote):
        out += (
            '<div class="dt">&nbsp;</div>'
            + '<div class="mt">&middot;</div>' * 10
            + '<div class="tot">&nbsp;</div>'
        )
    return f'<div class="reg">{out}</div>'


def thumb(scene, specchiato=False):
    return f'<div class="item__thumb">{mezzo(scene, specchiato)}</div>'


# --------------------------------------------------------------------------
# La scheda d'esempio: una sola, con voci di tipo diverso
# --------------------------------------------------------------------------

NOME = "Tecnica di base"
SUB = "di Luca Bianchi &middot; livello 3"
# (sezione, diagramma, nome, quanto farne, come si segna)
VOCI = [
    ("Riscaldamento", _DRITTO, "Rastrello", "10 tiri", "fatto"),
    ("Tecnica", _DRITTO, "Stop shot 2", "5 + 5 &middot; dx e sx", "riusciti"),
    ("Tecnica", _DRITTO, "Follow shot 1", "5 + 5 &middot; dx e sx", "riusciti"),
    ("Tecnica", _DRITTO, "Draw shot 1", "30 tiri", "riusciti"),
    ("Tecnica", GHOST, "Ghost ball 3", "10 tiri", "riusciti"),
    ("Gioco", TANGENTE, "Contro il ghost, palla 9", "5 partite", "vinte"),
]
SEQ6 = ["Rastrello", "Stop", "Follow", "Draw", "Ghost", "Partite"]


def _toggle(on):
    return f'<span class="toggle{" is-on" if on else ""}"></span>'


# --------------------------------------------------------------------------
# 1 · Le tue schede
# --------------------------------------------------------------------------


def elenco():
    def scheda(nome, chips_, stato, comando, accent=False):
        cls = "card card--accent" if accent else "card"
        btn = (
            f'<button class="btn btn--bright btn--sm">{comando}</button>'
            if accent
            else f'<button class="btn btn--secondary btn--sm">{comando}</button>'
        )
        ch = "".join(f'<span class="chip">{c}</span>' for c in chips_)
        return f"""
<section class="{cls}">
  <div class="row"><div class="grow"><h4>{nome}</h4>
    <div class="row" style="gap:5px;margin-top:6px;flex-wrap:wrap">{ch}</div></div></div>
  <div class="divider" style="margin:12px 0 10px;opacity:.5"></div>
  <div class="row"><span class="grow" style="font-size:12px;font-weight:700;opacity:.85">{stato}</span>{btn}</div>
</section>"""

    content = f"""
{scheda(NOME, ["di Luca Bianchi", "livello 3", "soglia 48 su 60"], "L&rsquo;ultima 51 su 60 &middot; la legge Luca", "Comincia", accent=True)}
{scheda("Tre giorni a settimana", ["tua", "giorni A &middot; B &middot; C", "6 settimane"], "Settimana 3 &middot; oggi tocca al giorno B", "Apri")}
{scheda("Prima della gara", ["tua"], "Fatta 2 volte &middot; l&rsquo;ultima 9 giorni fa", "Apri")}
<button class="btn btn--primary btn--w">{ico(I["plus"], 16)}Nuova scheda</button>"""
    return phone(
        "Schede", "Il tuo allenamento, in ordine", content, tabs=area_tabs("Schede")
    )


# --------------------------------------------------------------------------
# 2 · Comporre: una forma sola
# --------------------------------------------------------------------------


def _voce(scene, nome, dose, segno):
    return (
        f'<div class="item" style="grid-template-columns:20px 56px 1fr auto">{GRIP}{thumb(scene)}'
        f'<div><div class="item__t">{nome}</div><div class="item__s">si segna: {segno}</div></div>'
        f'<button class="pill" style="height:40px;padding:0 12px;background:var(--c7-bg)">'
        f'<span class="num" style="font-size:12px;color:var(--c7-ink)">{dose}</span></button></div>'
    )


def componi():
    def opz(t, sub, on, val=""):
        v = (
            f'<span class="num" style="font-size:13px;font-weight:800">{val}</span>'
            if val and on
            else ""
        )
        return (
            f'<div class="rows__row" style="padding:12px 18px"><div class="grow"><div class="rows__title">{t}</div>'
            f'<div class="rows__sub">{sub}</div></div>{v}{_toggle(on)}</div>'
        )

    out, last = "", None
    for sez, scene, nome, dose, segno in VOCI:
        if sez != last:
            out += f'<div class="label" style="margin-top:4px">{sez}</div>'
            last = sez
        out += _voce(scene, nome, dose, segno)
    content = f"""
<div><div class="label" style="margin-bottom:8px">Nome</div><div class="field field--filled">{NOME}</div></div>
<div class="stack" style="gap:8px">{out}</div>
<div class="duo"><button class="btn btn--secondary btn--sm">{ico(I["plus"], 15)}Esercizio</button>
  <button class="btn btn--secondary btn--sm">{ico(I["plus"], 15)}Sezione</button></div>
<div class="row"><span class="label grow">Se ti servono</span><span class="muted" style="font-size:11px;font-weight:700">tutto facoltativo</span></div>
<section class="rows">
  {opz("Livello", "la scheda &egrave; un gradino di una scala", True, "3")}
  {opz("Soglia", "somma le voci a riusciti: qui 60 tiri", True, "48 / 60")}
  {opz("Giorni", "A &middot; B &middot; C, ognuno con le sue voci", False)}
  {opz("Durata", "quante settimane", False)}
</section>
<button class="btn btn--secondary btn--w btn--sm">Parti da un esempio&hellip;</button>
<button class="btn btn--success btn--w">Salva la scheda</button>"""
    return phone(
        "Componi la scheda",
        "Ogni voce ha il suo &laquo;quanto farne&raquo;",
        content,
        h=1264,
        action=CLOSE,
        avatar="LU",
    )


# --------------------------------------------------------------------------
# 3 · Quanto farne: il foglio di una voce
# --------------------------------------------------------------------------


def voce_sheet():
    """Niente «serie × ripetizioni»: e' un concetto da palestra, al biliardo una
    voce e' un numero di tiri (o di partite, o di minuti). Deciso il 19/09."""

    def pills(voci, on):
        return "".join(
            f'<button class="pill{" is-active" if v == on else ""}">{v}</button>'
            for v in voci
        )

    def step(val):
        return (
            f'<div class="stepper"><button aria-label="Meno">{ico(I["minus"], 16, 2.4)}</button>'
            f'<span>{val}</span><button aria-label="Pi&ugrave;">{ico(I["plus"], 16, 2.4)}</button></div>'
        )

    base = "".join(_voce(sc, n, d, sg) for _s, sc, n, d, sg in VOCI[:3])
    overlay = f"""
<div class="veil"></div>
<div class="bottomsheet">
  <div class="grab"></div>
  <div style="font-size:18px;font-weight:800;letter-spacing:-.02em">Draw shot 1 &middot; quanto farne</div>
  <div><div class="label" style="margin-bottom:8px">Come si segna</div>
    <div class="row" style="flex-wrap:wrap;gap:6px">{pills(["Fatto", "Riusciti", "Punteggio", "Vinte", "Minuti"], "Riusciti")}</div></div>
  <div class="card row" style="padding:10px 14px"><div class="grow"><div class="rows__title">Quanti tiri</div>
    <div class="rows__sub">con &laquo;Vinte&raquo; diventano partite, con &laquo;Minuti&raquo; minuti</div></div>{step(30)}</div>
  <div class="card row" style="padding:10px 14px"><div class="grow"><div class="rows__title">Varianti</div>
    <div class="rows__sub">destra e sinistra, oppure A e B: si segnano separate, ognuna coi suoi tiri</div></div>
    <span class="muted" style="font-size:12px;font-weight:700">nessuna</span>{ico(I["chevron"], 14)}</div>
  <div style="font-size:12px;font-weight:700;color:var(--c7-ink-muted)">30 tiri a riusciti: entrano nella soglia della scheda.</div>
  <button class="btn btn--primary btn--w" style="height:var(--c7-touch)">Fatto</button>
</div>"""
    content = f"""
<div><div class="label" style="margin-bottom:8px">Nome</div><div class="field field--filled">{NOME}</div></div>
<div class="stack" style="gap:8px">{base}</div>"""
    return phone(
        "Componi la scheda",
        "Ogni voce ha il suo &laquo;quanto farne&raquo;",
        content,
        nav=None,
        action=CLOSE,
        avatar="LU",
        overlay=overlay,
    )


# --------------------------------------------------------------------------
# 4 · La seduta, su una voce «a riusciti» con varianti: un tocco per casella
# --------------------------------------------------------------------------


def _six(on=None):
    return (
        '<div class="six">'
        + "".join(
            (
                f'<button class="is-on">{n}</button>'
                if n == on
                else f"<button>{n}</button>"
            )
            for n in range(6)
        )
        + "</div>"
    )


def in_corso():
    content = f"""
{seqstrip(SEQ6, 2)}
<div class="duo">
  <div><div style="border-radius:var(--c7-r-control);overflow:hidden">{mezzo(_DRITTO)}</div>
    <div class="label" style="text-align:center;margin-top:6px">a destra</div></div>
  <div><div style="border-radius:var(--c7-r-control);overflow:hidden">{mezzo(_DRITTO, True)}</div>
    <div class="label" style="text-align:center;margin-top:6px">a sinistra</div></div>
</div>
<div><h3>Follow shot 1</h3>
  <p class="muted" style="font-size:13px;margin-top:4px">Imbucare e mandare anche la bianca in buca. 5 tiri a destra, 5 a sinistra.</p></div>
<div class="kpis" style="grid-template-columns:1fr 1fr">
  <div class="kpi"><div class="kpi__v">5</div><div class="kpi__l">L&rsquo;ultima volta, a destra</div></div>
  <div class="kpi"><div class="kpi__v" style="color:var(--c7-err-ink)">3</div><div class="kpi__l">L&rsquo;ultima volta, a sinistra</div></div>
</div>"""
    dock = f"""
<div class="dock" style="gap:10px">
  <div class="row"><span class="label grow">A destra &middot; quanti su 5?</span></div>
  {_six(4)}
  <div class="row"><span class="label grow">A sinistra &middot; quanti su 5?</span></div>
  {_six()}
  <div class="row" style="margin-top:2px"><span class="grow" style="font-size:13px;font-weight:800">13 su 15 finora</span>
    <span class="muted" style="font-size:12px;font-weight:700">soglia 48 su 60</span></div>
  <div class="bar"><div class="bar__fill" style="width:22%"></div></div>
  <div class="duo" style="grid-template-columns:auto 1fr">
    <button class="undo" style="width:120px">{ico(I["back"], 14)}Stop shot</button>
    <button class="btn btn--locked" style="height:var(--c7-touch);font-size:14px">Draw shot</button></div>
</div>"""
    return phone(
        NOME,
        "Seduta del 18/09 &middot; voce 3 di 6",
        content,
        nav=None,
        dock=dock,
        action=CLOSE,
    )


# --------------------------------------------------------------------------
# 5 · La stessa seduta, su una voce lunga: si conta tiro per tiro
# --------------------------------------------------------------------------


def seduta_serie():
    esiti = [1, 1, 0, 1, 1, 1, 0, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1]
    pips = "".join(
        f'<span class="pip{" is-on" if e else " is-miss"}" style="width:8px"></span>'
        for e in esiti
    ) + '<span class="pip" style="width:8px"></span>' * (30 - len(esiti))
    content = f"""
{seqstrip(SEQ6, 3)}
<div class="duo">
  <div><div style="border-radius:var(--c7-r-control);overflow:hidden">{mezzo(_DRITTO)}</div></div>
  <div><h3>Draw shot 1</h3>
    <p class="muted" style="font-size:12px;margin-top:4px">Imbucare richiamando la bianca: deve tornare oltre la posizione da cui &egrave; partita.</p>
    <div class="row" style="gap:5px;margin-top:8px;flex-wrap:wrap"><span class="chip chip--lvl">Liv. 3</span><span class="chip chip--gesto">draw</span></div></div>
</div>
<section class="card" style="padding:12px 14px">
  <div class="row"><span class="label grow">Tiro 23 di 30</span><span class="num" style="font-size:13px;font-weight:800">18 riusciti</span></div>
  <div class="pips" style="flex-wrap:wrap;gap:3px;margin-top:10px;justify-content:flex-start">{pips}</div>
  <div style="font-size:11px;font-weight:700;color:var(--c7-ink-muted);margin-top:8px">L&rsquo;ultima volta 22 su 30: a questo ritmo chiudi a 24.</div>
</section>"""
    dock = f"""
<div class="dock" style="gap:10px">
  <div class="duo">
    <button class="big" style="background:var(--c7-card);color:var(--c7-ink)">Sbagliato</button>
    <button class="big big--yes">Riuscito</button>
  </div>
  <div class="duo"><button class="undo">{ico(I["rotate"], 15)}Annulla</button><button class="undo">Scrivi il totale</button></div>
</div>"""
    return phone(
        NOME,
        "Seduta del 18/09 &middot; voce 4 di 6",
        content,
        nav=None,
        dock=dock,
        action=CLOSE,
    )


# --------------------------------------------------------------------------
# 6 · Il registro: le sedute, e voce per voce
# --------------------------------------------------------------------------


def il_registro():
    def voce(nome, ultimi, nota="", tone=""):
        col = f"color:var(--c7-{tone}-ink)" if tone else "color:var(--c7-ink-muted)"
        n = f'<div class="rows__sub" style="{col}">{nota}</div>' if nota else ""
        return (
            f'<div class="rows__row" style="padding:11px 18px"><div class="grow"><div class="rows__title">{nome}</div>{n}</div>'
            f'<span class="num" style="font-size:12px;color:var(--c7-ink-muted)">{ultimi}</span></div>'
        )

    def seduta(data, riga, val):
        return (
            f'<div class="rows__row" style="padding:11px 18px"><div class="grow"><div class="rows__title">{data}</div>'
            f'<div class="rows__sub">{riga}</div></div><span class="num-lg" style="font-size:18px">{val}</span></div>'
        )

    content = f"""
<div class="kpis">
  <div class="kpi"><div class="kpi__v">51</div><div class="kpi__l">L&rsquo;ultima, su 60</div></div>
  <div class="kpi"><div class="kpi__v">48,3</div><div class="kpi__l">Media di 3 sedute</div></div>
  <div class="kpi"><div class="kpi__v">2<span style="color:var(--c7-ok)">{ico(I["check"], 15, 3)}</span></div><div class="kpi__l">Volte sopra la soglia</div></div>
</div>
<div class="label">Voce per voce &middot; le ultime tre</div>
<section class="rows">
  {voce("Stop shot 2", "9 &middot; 9 &middot; 10")}
  {voce("Follow shot 1", "7 &middot; 8 &middot; 8", "a sinistra 2,7 di media, a destra 4,3", "err")}
  {voce("Draw shot 1", "19 &middot; 22 &middot; 24", "in crescita", "ok")}
  {voce("Ghost ball 3", "8 &middot; 9 &middot; 9")}
  {voce("Contro il ghost", "2 &middot; 1 &middot; 3 vinte", "fuori dalla soglia: non &egrave; a riusciti")}
</section>
<div class="label">Le sedute</div>
<section class="rows">
  {seduta("gio 18/09", "6 voci su 6 &middot; 52 minuti", "51")}
  {seduta("mar 16/09", "6 su 6 &middot; 48 minuti", "48")}
  {seduta("dom 14/09", "5 su 6 &middot; saltate le partite", "46")}
</section>"""
    dock = """
<div class="dock"><button class="btn btn--primary btn--w">Nuova seduta</button></div>"""
    return phone(NOME, SUB + " &middot; soglia 48 su 60", content, nav=None, dock=dock)


# --------------------------------------------------------------------------
# 7 · Fine seduta
# --------------------------------------------------------------------------


def fine():
    def riga(nome, oggi, prima, tone=""):
        col = f"var(--c7-{tone})" if tone else "var(--c7-ink-muted)"
        return (
            f'<div class="rows__row" style="padding:10px 18px"><span class="grow rows__title">{nome}</span>'
            f'<span class="num" style="font-size:12px;color:{col}">{prima}</span>'
            f'<span class="num-lg" style="font-size:18px;min-width:44px;text-align:right">{oggi}</span></div>'
        )

    content = f"""
<section class="card card--accent">
  <div class="kicker">Seduta finita</div>
  <div class="row" style="margin-top:6px;align-items:baseline;gap:8px">
    <span style="font-size:56px;font-weight:800;letter-spacing:-.04em;line-height:1">51</span>
    <span class="num" style="font-size:18px;color:var(--c7-accent-dim)">su 60</span>
    <span class="grow"></span><span class="state state--onaccent">sopra la soglia</span></div>
  <div style="font-size:13px;font-weight:700;color:var(--c7-accent-dim);margin-top:6px">Due sedute di fila a 48 o pi&ugrave; &middot; il tuo meglio su questa scheda</div>
</section>
<section class="rows">
  {riga("Stop shot 2", "10", "prima 9", "ok")}
  {riga("Follow shot 1", "8", "prima 8")}
  {riga("Draw shot 1", "24", "prima 22", "ok")}
  {riga("Ghost ball 3", "9", "prima 9")}
  {riga("Contro il ghost", "3 vinte", "prima 1", "ok")}
</section>
<div class="flash flash--ok"><span class="flash__ico">{ico(I["trophy"], 15)}</span>
  <div><div class="flash__title">Puoi chiedere il passaggio al livello 4</div>Luca Bianchi legge questa scheda: vede le sedute e conferma lui. &Egrave; un&rsquo;opzione della scheda (D8).</div></div>
<div><div class="label" style="margin-bottom:8px">Note della seduta</div>
  <div class="field field--area" style="min-height:64px">Tavolo 4. Sul follow a sinistra arrivo corto.</div></div>
<div class="duo"><button class="btn btn--secondary">Chiedi il passaggio</button>
  <button class="btn btn--success">Ho finito</button></div>"""
    return phone(
        NOME,
        "Seduta del 18/09 &middot; 52 minuti",
        content,
        nav=None,
        action=f'<button class="head__act" aria-label="Condividi">{ico(I["share"], 17)}</button>',
    )


# --------------------------------------------------------------------------
# 8 · Chi legge questa scheda. Il legame e' allievo–SCHEDA–istruttore: non
#     esiste «Luca mi segue», esiste «questa scheda la legge Luca» (19/09)
# --------------------------------------------------------------------------


def lettori():
    def chi(ini, nome, sub):
        return (
            f'<div class="rows__row"><div class="avatar">{ini}</div><div class="grow">'
            f'<div class="rows__title">{nome}</div><div class="rows__sub">{sub}</div></div>'
            f'<button class="btn btn--secondary btn--sm">Togli</button></div>'
        )

    content = f"""
<section class="card card--accent">
  <div class="kicker">{NOME}</div>
  <p style="margin-top:6px;font-size:14px">Ogni scheda ha i suoi lettori: li aggiungi e li togli tu, qui. Chi la legge vede le sedute e come procedi; non pu&ograve; cambiarla n&eacute; scriverci.</p>
</section>
<div class="label">La leggono</div>
<section class="rows">
  {chi("LU", "Luca Bianchi", "istruttore &middot; R&#333;nin ASD &middot; dal 02/09")}
  {chi("GM", "Giada Moretti", "istruttrice &middot; dal 10/09")}
</section>
<button class="btn btn--primary btn--w">{ico(I["plus"], 16)}Aggiungi un istruttore a questa scheda</button>
<div class="label">Cosa vede chi la legge</div>
<section class="rows">
  <div class="rows__row"><span class="tile tile--sm tile--ok">{ico(I["sheet"], 16)}</span><div class="grow"><div class="rows__title">Le sedute e il registro</div><div class="rows__sub">di questa scheda, voce per voce</div></div></div>
  <div class="rows__row"><span class="tile tile--sm tile--locked">{ico(I["lock"], 16)}</span><div class="grow"><div class="rows__title">Le note delle sedute</div><div class="rows__sub">restano tue, a meno che tu non le apra</div></div>{_toggle(False)}</div>
  <div class="rows__row"><span class="tile tile--sm tile--locked">{ico(I["lock"], 16)}</span><div class="grow"><div class="rows__title">Tutto il resto</div><div class="rows__sub">le altre schede, l&rsquo;andamento, partite ed Elo</div></div></div>
</section>
<p class="muted" style="font-size:12px">Tolto da qui, un istruttore smette subito di vedere questa scheda. Le altre non cambiano.</p>"""
    return phone("Chi la legge", NOME, content, nav=None, action=CLOSE)


# --------------------------------------------------------------------------
# 9 · Chi legge le mie schede: una VISTA, non un legame. Si ricava dalle schede
# --------------------------------------------------------------------------


def miei_istruttori():
    def istr(ini, nome, sub, schede_):
        righe = "".join(
            f'<div class="row" style="padding:8px 0;border-top:1px solid var(--c7-line-soft)"><span class="grow" style="font-size:13px;font-weight:700">{n}</span>'
            f'<span class="muted" style="font-size:11px;font-weight:700">{d}</span>{ico(I["chevron"], 13)}</div>'
            for n, d in schede_
        )
        return f"""
<section class="card">
  <div class="row"><div class="avatar avatar--lg">{ini}</div>
    <div class="grow"><h4>{nome}</h4><div class="rows__sub">{sub}</div></div></div>
  <div style="margin-top:12px">{righe}</div>
</section>"""

    content = f"""
<p class="muted" style="font-size:13px;line-height:1.45">Qui vedi in un colpo solo chi legge cosa. Non &egrave; un elenco a parte: un istruttore compare perch&eacute; gli hai aperto almeno una scheda, e sparisce quando lo togli dall&rsquo;ultima.</p>
{istr("LU", "Luca Bianchi", "istruttore &middot; R&#333;nin ASD", [(NOME, "dal 02/09"), ("Prima della gara", "dal 12/09")])}
{istr("GM", "Giada Moretti", "istruttrice", [(NOME, "dal 10/09")])}
<div class="label">Non le legge nessuno</div>
<section class="rows">
  <div class="rows__row"><span class="tile tile--sm tile--locked">{ico(I["lock"], 16)}</span><div class="grow"><div class="rows__title">Tre giorni a settimana</div><div class="rows__sub">solo tua</div></div>{ico(I["chevron"], 15)}</div>
</section>"""
    return phone(
        "Chi legge le mie schede", "Si decide scheda per scheda", content, tabs=""
    )


def aggiungi_istruttore():
    overlay = f"""
<div class="veil"></div>
<div class="bottomsheet">
  <div class="grab"></div>
  <div style="font-size:18px;font-weight:800;letter-spacing:-.02em">Chi pu&ograve; leggere &laquo;{NOME}&raquo;</div>
  <div class="field field--filled">{ico(I["search"], 17)}Luca Bi</div>
  <div class="card row" style="padding:12px 14px;background:var(--c7-accent);color:var(--c7-accent-ink)">
    <div class="avatar" style="background:var(--c7-accent-bright);color:#0D2A36">LU</div>
    <div class="grow"><div style="font-size:14px;font-weight:800">Luca Bianchi</div>
      <div style="font-size:11px;font-weight:700;color:var(--c7-accent-dim)">istruttore &middot; R&#333;nin ASD</div></div>{ico(I["check"], 18, 3)}</div>
  <div class="card row" style="padding:12px 14px"><div class="avatar">LB</div>
    <div class="grow"><div style="font-size:14px;font-weight:800">Luca Bindi</div>
      <div class="rows__sub">istruttore &middot; Udine</div></div></div>
  <div style="font-size:12px;font-weight:600;color:var(--c7-ink-muted);line-height:1.4">Si trovano solo gli utenti che hanno il ruolo di istruttore. Luca riceve una notifica e trova questa scheda fra quelle dei suoi allievi. Vale per questa scheda soltanto.</div>
  <button class="btn btn--primary btn--w" style="height:var(--c7-touch)">Apri la scheda a Luca Bianchi</button>
</div>"""
    content = f"""
<section class="card card--accent"><div class="kicker">{NOME}</div>
  <p style="margin-top:6px;font-size:14px">Ogni scheda ha i suoi lettori: li aggiungi e li togli tu, qui.</p></section>"""
    return phone("Chi la legge", NOME, content, nav=None, action=CLOSE, overlay=overlay)


# --------------------------------------------------------------------------
# 9b · Dove si diventa istruttore: nel profilo, come per l'esaminatore
# --------------------------------------------------------------------------


def diventa_istruttore():
    def ruolo(icon, t, sub, stato, tone):
        return (
            f'<div class="rows__row"><span class="tile tile--sm tile--neutral">{ico(I[icon], 16)}</span>'
            f'<div class="grow"><div class="rows__title">{t}</div><div class="rows__sub">{sub}</div></div>'
            f'<span class="state state--{tone}">{stato}</span></div>'
        )

    content = f"""
<div class="label">I tuoi ruoli</div>
<section class="rows">
  {ruolo("user", "Giocatore", "dal 12/03/2026", "attivo", "ok")}
  {ruolo("cert", "Esaminatore", "somministra gli esami certificati", "attivo", "ok")}
  {ruolo("sheet", "Istruttore", "legge le schede che gli allievi gli aprono", "richiesto", "warn")}
</section>
<section class="card">
  <div class="kicker">La tua richiesta di istruttore</div>
  <div style="margin-top:12px"><div class="label" style="margin-bottom:8px">Scuola o associazione</div>
    <div class="field field--filled">R&#333;nin ASD</div>
    <div class="rows__sub" style="margin-top:6px">facoltativa &middot; compare accanto al tuo nome quando un allievo ti cerca</div></div>
  <div style="margin-top:14px"><div class="label" style="margin-bottom:8px">Due righe su di te</div>
    <div class="field field--area field--filled" style="min-height:72px">Istruttore di secondo livello, tengo i corsi base del marted&igrave;.</div></div>
  <div class="divider" style="margin:14px 0"></div>
  <div class="row"><span class="grow" style="font-size:12px;font-weight:700;color:var(--c7-ink-muted)">Inviata il 17/09 &middot; la valuta un amministratore o un istruttore che pu&ograve; delegare</span></div>
</section>
<p class="muted" style="font-size:12px;line-height:1.45">&Egrave; lo stesso percorso di &laquo;Diventa esaminatore&raquo;, che c&rsquo;&egrave; gi&agrave;: richiesta, approvazione, e il ruolo si somma agli altri. Essere istruttore non d&agrave; accesso a niente: servir&agrave; che un allievo ti apra una scheda.</p>"""
    return phone("Profilo", "Ruoli", content, avatar="LU", h=860)


# --------------------------------------------------------------------------
# 10 · L'istruttore: i miei allievi, per gruppo (D12)
# --------------------------------------------------------------------------


def _allievo(ini, nome, riga, stato, tone):
    return (
        f'<div class="rows__row"><div class="avatar">{ini}</div><div class="grow">'
        f'<div class="rows__title">{nome}</div><div class="rows__sub">{riga}</div></div>'
        f'<span class="state state--{tone}">{stato}</span></div>'
    )


def allievi():
    gruppi = "".join(
        f'<button class="pill{" is-active" if c == "Base 1 &middot; autunno" else ""}">{c}</button>'
        for c in ("Tutti", "Base 1 &middot; autunno", "Intermedio 1", "Passati")
    )
    content = f"""
<div class="hscroll">{gruppi}</div>
<div class="label">Ti hanno appena aperto una scheda</div>
<section class="rows">
  <div class="rows__row"><div class="avatar">PV</div><div class="grow"><div class="rows__title">Paolo Verdi</div>
    <div class="rows__sub">dal 18/09 &middot; &laquo;Tre sponde&raquo;</div></div>
    <button class="btn btn--secondary btn--sm">Metti in un gruppo</button></div>
</section>
<section class="card">
  <div class="row"><div class="grow"><h4>Base 1 &middot; autunno 2026</h4>
    <div class="rows__sub">dal 15/09 al 15/12 &middot; 5 allievi &middot; scheda: {NOME}</div></div>{ico(I["chevron"], 15)}</div>
</section>
<div class="label">Aspettano te</div>
<section class="rows">
  {_allievo("MA", "Marco Rossi", "46, 48, 51 su 60 &middot; soglia 48", "passaggio", "accent")}
</section>
<div class="label">Da guardare</div>
<section class="rows">
  {_allievo("SN", "Sara Neri", "ferma a 38 da cinque sedute", "ferma", "warn")}
  {_allievo("GV", "Giulio Verdi", "non si allena da 16 giorni", "assente", "err")}
</section>
<div class="label">Tutto bene</div>
<section class="rows">
  {_allievo("ER", "Elena Ricci", "6 sedute su 7 previste", "costante", "ok")}
</section>"""
    return phone(
        "I miei allievi", "Luca Bianchi &middot; istruttore", content, avatar="LU"
    )


def gruppo():
    def passato(nome, periodo, esito):
        return (
            f'<div class="rows__row"><div class="grow"><div class="rows__title">{nome}</div>'
            f'<div class="rows__sub">{periodo}</div></div>'
            f'<span class="muted" style="font-size:12px;font-weight:700;text-align:right">{esito}</span>{ico(I["chevron"], 14)}</div>'
        )

    content = f"""
<section class="card card--accent">
  <div class="row"><div class="grow"><div class="kicker">Gruppo in corso</div><h3 style="margin-top:4px">Base 1 &middot; autunno 2026</h3></div>
    <span class="state state--onaccent">settimana 1 di 13</span></div>
  <div style="font-size:13px;font-weight:700;color:var(--c7-accent-dim);margin-top:8px">dal 15/09 al 15/12 &middot; 5 allievi</div>
</section>
<div class="kpis">
  <div class="kpi"><div class="kpi__v">5</div><div class="kpi__l">Allievi</div></div>
  <div class="kpi"><div class="kpi__v">11</div><div class="kpi__l">Sedute questa settimana</div></div>
  <div class="kpi"><div class="kpi__v">47</div><div class="kpi__l">Media del gruppo, su 60</div></div>
</div>
<section class="rows">
  <div class="rows__row"><span class="tile tile--sm tile--neutral">{ico(I["sheet"], 16)}</span><div class="grow"><div class="rows__title">Scheda del gruppo</div><div class="rows__sub">{NOME} &middot; la leggono in 4 su 5</div></div>{ico(I["chevron"], 15)}</div>
  <div class="rows__row"><span class="tile tile--sm tile--neutral">{ico(I["user"], 16)}</span><div class="grow"><div class="rows__title">Allievi</div><div class="rows__sub">fra chi ti ha aperto una scheda: aggiungi, sposta, togli</div></div>{ico(I["chevron"], 15)}</div>
</section>
<div class="label">Lo storico dei tuoi gruppi</div>
<section class="rows">
  {passato("Base 1 &middot; primavera 2026", "dal 02/03 al 30/05 &middot; 8 allievi", "5 al livello dopo")}
  {passato("Intermedio 1 &middot; primavera 2026", "dal 02/03 al 30/05 &middot; 4 allievi", "2 al livello dopo")}
  {passato("Base 1 &middot; autunno 2025", "dal 20/09 al 13/12 &middot; 6 allievi", "4 al livello dopo")}
</section>
<p class="muted" style="font-size:12px;line-height:1.45">Un gruppo chiuso resta com&rsquo;era: chi c&rsquo;era e com&rsquo;&egrave; andata. Se un allievo ti toglie da una scheda, da quel giorno di quella scheda non vedi pi&ugrave; niente di nuovo (D11).</p>
<button class="btn btn--primary btn--w">{ico(I["plus"], 16)}Nuovo gruppo</button>"""
    return phone(
        "Base 1 &middot; autunno 2026",
        "Un gruppo: nome, periodo, allievi",
        content,
        avatar="LU",
        h=880,
    )
