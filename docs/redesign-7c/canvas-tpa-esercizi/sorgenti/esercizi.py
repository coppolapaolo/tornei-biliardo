#!/usr/bin/env python3
"""Artboard dell'area esercizi. Ogni schermata dice nel bigliettino accanto
quale issue disegna e cosa, di quello che mostra, l'app oggi non fa."""

from kit import (
    I,
    area_tabs,
    ball,
    bullseye,
    ghost,
    ico,
    line,
    livechart,
    phone,
    radar,
    sparkline,
    table,
)

# Disposizioni ricorrenti ----------------------------------------------------
SPOT = (
    ball(200, 200)
    + ball(600, 200, 1)
    + line(212, 200, 588, 200)
    + line(612, 200, 790, 12, dashed=False, color="#E0B437")
)
POSIZIONE = (
    ball(180, 300)
    + ball(560, 110, 3)
    + ghost(538, 124)
    + line(192, 294, 530, 128)
    + line(572, 100, 790, 8, dashed=False, color="#B23B3B")
    + bullseye(560, 250, 70)
)
SPONDE = (
    ball(160, 120)
    + ball(640, 300, 7)
    + line(172, 124, 420, 398)
    + line(420, 398, 628, 306)
)
ELLE = (
    ball(120, 320)
    + "".join(ball(200 + i * 90, 100, i + 1) for i in range(5))
    + ball(650, 190, 6)
    + ball(650, 280, 7)
)


def chips(lvl, cats, gesti=()):
    """Abilita' (piene) e gesti (a contorno): due vocabolari, e un esercizio
    ha zero, una o piu' voci su ciascuno."""
    return (
        f'<span class="chip chip--lvl">Liv. {lvl}</span>'
        + "".join(f'<span class="chip chip--cat">{c}</span>' for c in cats)
        + "".join(f'<span class="chip chip--gesto">{g}</span>' for g in gesti)
    )


def voto(v, n):
    return (
        f'<span class="voto">{ico(I["star"], 12)}{v}</span>'
        f'<span class="muted" style="font-size:12px;font-weight:700"> &middot; {n} giocatori</span>'
    )


def ex_card(scene, title, lvl, cats, line_txt, fav=False, gesti=(), v="4,6", n=14):
    heart = "color:var(--c7-err)" if fav else "color:var(--c7-ink-faint)"
    return f"""
<article class="card" style="padding:9px 12px">
  <div class="ex">
    <div class="ex__thumb">{table(scene)}</div>
    <div>
      <div class="row" style="gap:6px"><span class="ex__title grow">{title}</span>
        <button class="iconbtn" style="width:48px;height:48px;margin:-10px -8px -10px 0;background:transparent;{heart}"
                aria-label="Preferito">{ico(I["heart"], 18)}</button></div>
      <div class="row" style="gap:5px;flex-wrap:wrap;margin-top:2px">{chips(lvl, cats, gesti)}</div>
      <div class="ex__line">{voto(v, n)}</div>
      <div class="ex__line" style="margin-top:2px">{line_txt}</div>
    </div>
  </div>
</article>"""


# --------------------------------------------------------------------------
# Trovare · A — catalogo che si filtra (#168)
# --------------------------------------------------------------------------


def trovare_a():
    gesti = ["Tutti", "Stop", "Stun", "Follow", "Draw", "Spin", "Forza", "Bank"]
    pills = "".join(
        f'<button class="pill{" is-active" if c == "Draw" else ""}">{c}</button>'
        for c in gesti
    )
    assi = "".join(
        f'<button class="vtab{" is-active" if x == "Gesto" else ""}" style="height:38px">{x}</button>'
        for x in ["Abilit&agrave;", "Gesto", "Livello", "Voto"]
    )
    content = f"""
<div class="field">{ico(I["search"], 18)}Cerca un esercizio</div>
<div style="display:flex;gap:6px">{assi}</div>
<div class="hscroll">{pills}</div>
<div class="row"><span class="label grow">5 esercizi col draw</span>
  <span class="muted" style="font-size:12px;font-weight:700">I pi&ugrave; provati</span>{ico(I["chevron"], 14)}</div>
{ex_card(POSIZIONE, "Ferma nel cerchio", 2, ["Posizione"], "Mai provato", gesti=["Draw"], v="4,8", n=212)}
{ex_card(ELLE, "Esercizio a L", 3, ["Posizione", "Tiro"], "Il tuo record 6 su 7 &middot; 9 prove", fav=True, gesti=["Draw", "Follow"], v="4,5", n=96)}
{ex_card(SPOT, "Draw dal punto", 1, [], "Media 63% &middot; ultime tre 89%", gesti=["Draw"], v="3,9", n=14)}"""
    action = f'<button class="head__act" aria-label="Nuovo esercizio" style="background:var(--c7-ok);color:#fff">{ico(I["plus"], 18)}</button>'
    return phone(
        "Esercizi",
        "42 esercizi &middot; 6 abilit&agrave;",
        content,
        action=action,
        tabs=area_tabs("Esercizi"),
    )


# --------------------------------------------------------------------------
# Trovare · B — la pagina si apre su «oggi» (#175, #172, #316)
# --------------------------------------------------------------------------


def trovare_b():
    content = f"""
<section class="card card--accent">
  <div class="kicker">Per oggi</div>
  <h3 style="margin-top:4px">Ferma nel cerchio</h3>
  <div class="row" style="gap:5px;margin-top:8px">{chips(2, ["Posizione", "Tiro"])}</div>
  <div style="border-radius:var(--c7-r-chip);overflow:hidden;margin-top:12px">{table(POSIZIONE)}</div>
  <p style="margin-top:12px;font-size:13px;color:var(--c7-accent-dim)">Perch&eacute; questo: il gioco di
    posizione &egrave; fra i tuoi obiettivi e in un mese l&rsquo;hai allenato due volte.</p>
  <div class="duo" style="margin-top:14px;grid-template-columns:1fr auto">
    <button class="btn btn--bright">Comincia</button>
    <button class="btn btn--locked" style="padding:0 16px">Un altro</button>
  </div>
</section>
<section class="card">
  <div class="row"><div class="grow"><div class="kicker">La tua scheda</div>
    <h4 style="margin-top:3px">Marted&igrave; in sala</h4></div>
    <span class="num" style="font-size:15px">2 di 5</span></div>
  <div class="bar" style="margin-top:10px"><div class="bar__fill" style="width:40%"></div></div>
  <div class="row" style="margin-top:12px"><span class="grow muted" style="font-size:12px;font-weight:700">Prossimo: Esercizio a L &middot; 10 colpi</span>
    <button class="btn btn--primary btn--sm">Riprendi</button></div>
</section>
<section class="card">
  <div class="sechead"><h4>I tuoi obiettivi</h4><span class="sechead__more">Cambia</span></div>
  <div class="goal__top" style="margin-top:12px"><span class="goal__t">Spot Shot Rally a 8 su 10</span><span class="goal__v">6,3 / 8</span></div>
  <div class="bar" style="margin-top:6px"><div class="bar__fill" style="width:78%"></div></div>
  <div class="goal__top" style="margin-top:14px"><span class="goal__t">Posizione: da &laquo;in crescita&raquo; a &laquo;solido&raquo;</span><span class="goal__v">61%</span></div>
  <div class="bar" style="margin-top:6px"><div class="bar__fill" style="width:61%"></div></div>
</section>
<div class="sechead"><h3>Tutti gli esercizi</h3><span class="sechead__more">Apri il catalogo</span></div>
{ex_card(SPOT, "Spot Shot Rally", 1, ["Tiro", "Posizione"], "Media 63% &middot; ultime tre 89%")}"""
    return phone("Esercizi", "Marted&igrave; 22 settembre", content, h=1024)


# --------------------------------------------------------------------------
# La scheda di un esercizio (#181, #174, #252, #253)
# --------------------------------------------------------------------------


def scheda():
    content = f"""
<div style="border-radius:var(--c7-r-card);overflow:hidden">{table(SPOT)}</div>
<div class="row" style="gap:5px;flex-wrap:wrap">{chips(1, ["Tiro", "Posizione"])}
  <span class="chip">A punteggio &middot; su 10</span></div>
<section class="card card--accent">
  <div class="kicker">Come si fa</div>
  <p style="margin-top:6px;font-size:14px">Dieci tiri dalla stessa posizione: la bilia bersaglio sul punto,
    la battente in mano. Un punto per ogni imbucata.</p>
</section>
<div class="kpis">
  <div class="kpi"><div class="kpi__v">63%</div><div class="kpi__l">Media</div></div>
  <div class="kpi"><div class="kpi__v">89%<span style="color:var(--c7-ok)">{ico(I["up"], 15, 2.6)}</span></div><div class="kpi__l">Ultime tre</div></div>
  <div class="kpi"><div class="kpi__v">10</div><div class="kpi__l">Record, su 10</div></div>
</div>
<section class="card">
  <div class="sechead"><h4>Le tue 9 prove</h4><span class="sechead__more">Tutte</span></div>
  <div style="margin-top:8px">{sparkline([50, 33, 67, 67, 83, 83, 100, 67, 100])}</div>
</section>
<section class="card">
  <div class="kicker">Quelli come te</div>
  <div class="row" style="margin-top:6px"><div class="grow"><div class="rows__title">Elo fra 1400 e 1600</div>
    <div class="rows__sub">media su 14 giocatori</div></div><span class="num-lg">58%</span></div>
  <div class="divider"></div>
  <div class="row"><div class="grow"><div class="rows__title">Livello 1 dichiarato</div>
    <div class="rows__sub">dai risultati sembra pi&ugrave; difficile: riesce al 41% di chi lo prova</div></div>
    <span class="state state--warn">misurato 2</span></div>
</section>
<section class="rows">
  <button class="rows__row" style="border:0;background:none;font-family:inherit;width:100%;text-align:left">
    <span class="tile tile--sm tile--neutral">{ico(I["pencil"], 16)}</span><span class="grow rows__title">Modifica l&rsquo;esercizio</span>{ico(I["chevron"], 15)}</button>
  <button class="rows__row" style="border:0;border-top:1px solid var(--c7-line-soft);background:none;font-family:inherit;width:100%;text-align:left">
    <span class="tile tile--sm tile--neutral">{ico(I["target"], 16)}</span><span class="grow rows__title">Modifica il disegno</span>{ico(I["chevron"], 15)}</button>
  <button class="rows__row" style="border:0;border-top:1px solid var(--c7-line-soft);background:none;font-family:inherit;width:100%;text-align:left">
    <span class="tile tile--sm tile--neutral">{ico(I["copy"], 16)}</span><span class="grow"><span class="rows__title" style="display:block">Duplica</span>
      <span class="rows__sub" style="display:block">per farne una variante senza toccare questo</span></span>{ico(I["chevron"], 15)}</button>
</section>
<div class="duo" style="grid-template-columns:1fr auto">
  <button class="btn btn--primary">Allenati</button>
  <button class="btn btn--secondary" style="padding:0 18px">Nella scheda</button>
</div>"""
    action = f'<button class="head__act" aria-label="Preferito" style="color:var(--c7-err)">{ico(I["heart"], 18)}</button>'
    return phone(
        "Spot Shot Rally",
        "di Luca Bianchi &middot; voto 4,6 &middot; 14 giocatori",
        content,
        h=1196,
        action=action,
    )


# --------------------------------------------------------------------------
# Eseguire — cinque momenti, una cornice sola
# --------------------------------------------------------------------------


def _progress(label, done, total, right):
    return f"""
<div>
  <div class="row"><span class="label grow">{label}</span><span class="num" style="font-size:13px">{right}</span></div>
  <div class="bar" style="margin-top:8px"><div class="bar__fill" style="width:{done * 100 // total}%"></div></div>
</div>"""


def _vivo(label, right, chart, sotto):
    """Il pezzo nuovo della cornice comune: l'avanzamento DAL VIVO. Cresce a
    ogni colpo, mostra quanto manca e ti confronta con te stesso."""
    return f"""
<section class="card" style="padding:12px 14px 10px">
  <div class="row"><span class="label grow">{label}</span><span class="num" style="font-size:13px;font-weight:800">{right}</span></div>
  <div style="margin-top:6px">{chart}</div>
  <div style="font-size:11px;font-weight:700;color:var(--c7-ink-muted);margin-top:2px">{sotto}</div>
</section>"""


CLOSE = f'<button class="head__act" aria-label="Chiudi l&rsquo;allenamento">{ico(I["x"], 17)}</button>'


def esegui_punteggio():
    pips = "".join(
        f'<span class="pip{" is-on" if i < 7 else ""}"></span>' for i in range(10)
    )
    content = f"""
<div style="border-radius:var(--c7-r-card);overflow:hidden">{table(SPOT)}</div>
{_vivo("Le prove di oggi", "quarta prova", livechart([6, 8, 7, 7], 6, 6.4, 10, "la tua media 6,4", bars=True),
       "Sei sopra la tua media da due prove. Record: 10.")}
<section class="rows">
  <div class="rows__row" style="padding:11px 18px"><span class="grow rows__title">Terza prova</span><span class="num" style="font-size:12px;color:var(--c7-ink-muted)">21:14</span><span class="num-lg" style="font-size:20px;min-width:34px;text-align:right">7</span></div>
  <div class="rows__row" style="padding:11px 18px"><span class="grow rows__title">Seconda prova</span><span class="num" style="font-size:12px;color:var(--c7-ink-muted)">21:06</span><span class="num-lg" style="font-size:20px;min-width:34px;text-align:right">8</span></div>
</section>"""
    dock = f"""
<div class="dock" style="gap:14px">
  <div class="scorepad">
    <button class="scorepad__btn" aria-label="Uno in meno">{ico(I["minus"], 22, 2.4)}</button>
    <div style="text-align:center"><div class="scorepad__v">7</div><div class="scorepad__max">su 10</div></div>
    <button class="scorepad__btn" aria-label="Uno in pi&ugrave;">{ico(I["plus"], 22, 2.4)}</button>
  </div>
  <div class="pips">{pips}</div>
  <button class="btn btn--primary btn--w">Registra la prova</button>
  <div class="duo">
    <button class="undo">{ico(I["rotate"], 15)}Annulla l&rsquo;ultima</button>
    <button class="btn btn--success" style="height:var(--c7-touch);font-size:14px">Ho finito</button>
  </div>
</div>"""
    return phone(
        "Spot Shot Rally",
        "A punteggio &middot; su 10",
        content,
        nav=None,
        dock=dock,
        action=CLOSE,
    )


def _colpi(esiti):
    """La striscia dei colpi: ogni colpo e' il suo punteggio, non un colore."""
    out = ""
    for e in esiti:
        if e is None:
            out += '<span class="shot shot--todo"></span>'
        elif e == "x":
            out += f'<span class="shot shot--miss">{ico(I["x"], 10, 3)}</span>'
        else:
            out += f'<span class="shot shot--v{e}">{e}</span>'
    return f'<div class="shots">{out}</div>'


def esegui_colpo():
    esiti = [2, 3, 1, "x", 2, 3] + [None] * 14
    corsa = [2, 5, 6, 6, 8, 11]
    content = f"""
{_vivo("Colpo 7 di 20", "11 punti", livechart(corsa, 20, 34, 42, "il tuo solito: 34", h=104, pace=True),
       "A questo ritmo chiudi a 37: tre punti sopra il tuo solito.")}
<div style="border-radius:var(--c7-r-card);overflow:hidden">{table(POSIZIONE)}</div>
{_colpi(esiti)}"""
    dock = f"""
<div class="dock">
  <p style="font-size:13px;text-align:center;color:var(--c7-ink-soft);line-height:1.4"><b style="color:var(--c7-ink)">Imbucata?</b> Tocca il panno dove si &egrave; fermata la bianca:<br>l&rsquo;anello d&agrave; i punti.</p>
  <button class="btn btn--w" style="height:56px;font-size:15px;background:var(--c7-card);color:var(--c7-ink)">Non &egrave; entrata &middot; 0 punti</button>
  <button class="undo">{ico(I["rotate"], 15)}Annulla l&rsquo;ultimo colpo</button>
</div>"""
    return phone(
        "Ferma nel cerchio",
        "Colpo per colpo &middot; 20 colpi",
        content,
        nav=None,
        dock=dock,
        action=CLOSE,
    )


def esegui_zoom():
    zoom = f"""
<svg viewBox="0 0 354 354" width="100%" style="display:block;border-radius:var(--c7-r-card)">
  <rect width="354" height="354" fill="#3F7F9B"/>
  <path d="M0 118H354M0 236H354M118 0V354M236 0V354" stroke="#F5F7F6" stroke-opacity=".18"/>
  {bullseye(177, 177, 160)}
  <path d="M232 0V354M0 139H354" stroke="#F5F7F6" stroke-width="1.4" stroke-dasharray="5 5"/>
  <circle cx="232" cy="139" r="22" fill="#F5F7F6" stroke="#1B2124" stroke-width="2"/>
</svg>"""
    content = f"""
{_progress("Colpo 7 di 20", 6, 20, "11 punti finora")}
{zoom}
<div class="kpis" style="grid-template-columns:1fr 1fr">
  <div class="kpi"><div class="kpi__v">0,4</div><div class="kpi__l">diamanti dal centro</div></div>
  <div class="kpi"><div class="kpi__v">2 punti</div><div class="kpi__l">l&rsquo;anello toccato</div></div>
</div>
<section class="card">
  <div class="kicker">I sei colpi di prima</div>
  <div style="margin-top:10px">{_colpi([2, 3, 1, "x", 2, 3])}</div>
</section>"""
    dock = """
<div class="dock">
  <p style="font-size:13px;text-align:center;color:var(--c7-ink-soft)">Trascina la battente per correggere il punto.</p>
  <div class="duo">
    <button class="btn btn--secondary">Tavolo intero</button>
    <button class="btn btn--primary">Conferma</button>
  </div>
</div>"""
    return phone(
        "Ferma nel cerchio",
        "Colpo per colpo &middot; 20 colpi",
        content,
        nav=None,
        dock=dock,
        action=CLOSE,
    )


def esegui_casuale():
    def voce(t, s, v, on=False):
        return (
            f'<button class="choice{" is-on" if on else ""}"><span><span class="choice__t">{t}</span>'
            f'<span class="choice__s">{s}</span></span><span class="choice__v">{v}</span></button>'
        )

    seven = (
        '<svg viewBox="0 0 60 60" width="60" height="60"><circle cx="30" cy="30" r="28" fill="#7A3B2E"/>'
        '<circle cx="30" cy="30" r="14" fill="#F5F7F6"/><text x="30" y="37" text-anchor="middle" '
        'font-size="20" font-weight="800" fill="#1B2124" font-family="Manrope,sans-serif">7</text></svg>'
    )
    content = f"""
{_vivo("Colpo 5 di 12", "14 punti", livechart([2, 2, 10, 14], 12, 31, 38, "il tuo record: 31", pace=True), "Sei avanti di 5 rispetto alla serie del record, allo stesso colpo.")}
<section class="card card--accent" style="padding:14px 18px">
  <div class="row"><span class="kicker grow">L&rsquo;app ha estratto</span>{ico(I["dice"], 18)}</div>
  <div class="row" style="margin-top:10px;gap:16px">
    {seven}
    <div><div style="font-size:26px;font-weight:800;letter-spacing:-.03em;line-height:1.1">3 o pi&ugrave; sponde</div>
      <div style="font-size:15px;font-weight:700;color:var(--c7-accent-dim);margin-top:2px">sulla bilia 7</div></div>
  </div>
</section>
<div class="label">Com&rsquo;&egrave; andata?</div>
<div class="stack" style="gap:8px">
  {voce("Mancata", "la 7 non l&rsquo;hai toccata", 0)}
  {voce("Colpita, senza sponda", "", 1)}
  {voce("Colpita regolare", "", 2)}
  {voce("Imbucata", "", 4)}
  {voce("Colpita, e difesa riuscita", "", 8)}
</div>
<section class="rows">
  <div class="rows__row" style="padding:10px 18px"><span class="sheet__seat">4</span><span class="grow rows__title">2 sponde, bilia 3</span><span class="rows__sub" style="margin:0">imbucata</span><span class="num-lg" style="font-size:18px;min-width:26px;text-align:right">4</span></div>
</section>"""
    dock = f"""
<div class="dock">
  <button class="undo">{ico(I["rotate"], 15)}Annulla l&rsquo;ultimo colpo</button>
</div>"""
    return phone(
        "Kicking Madness",
        "Con estrazione &middot; 12 colpi",
        content,
        nav=None,
        dock=dock,
        action=CLOSE,
    )


def esegui_fine():
    pts = [
        (560, 250),
        (548, 262),
        (575, 240),
        (590, 270),
        (532, 236),
        (566, 228),
        (612, 258),
        (598, 300),
        (640, 282),
        (570, 266),
        (555, 244),
        (625, 310),
        (662, 300),
        (585, 252),
        (604, 246),
        (700, 330),
    ]
    cloud = POSIZIONE + "".join(
        f'<circle cx="{x}" cy="{y}" r="9" fill="#F5F7F6" stroke="#1B2124" stroke-width="1.4"/>'
        for x, y in pts
    )
    content = f"""
<div style="border-radius:var(--c7-r-card);overflow:hidden">{table(cloud)}</div>
<div class="flash flash--info"><span class="flash__ico">{ico(I["info"], 16)}</span>
  <div><div class="flash__title">Arrivi lungo, e a destra</div>
    Undici battenti su sedici si sono fermate oltre il centro, verso la sponda corta: &egrave; forza, non mira.</div></div>
<div class="kpis">
  <div class="kpi"><div class="kpi__v">80%</div><div class="kpi__l">Imbucate</div><div class="kpi__band">solido</div></div>
  <div class="kpi"><div class="kpi__v">58%</div><div class="kpi__l">Posizione</div><div class="kpi__band" style="color:var(--c7-warn-ink)">in crescita</div></div>
  <div class="kpi"><div class="kpi__v">12</div><div class="kpi__l">di fila imbucate</div><div class="kpi__band">tuo record</div></div>
</div>
<div class="flash flash--ok"><span class="flash__ico">{ico(I["trophy"], 15)}</span>
  <div><div class="flash__title">Serie a bersaglio</div>Dieci colpi di fila dentro gli anelli. +40 XP</div></div>
<div>
  <div class="label" style="margin-bottom:8px">Note della sessione</div>
  <div class="field field--area" style="min-height:150px">Tavolo 4, panno lento. Stecca nuova.</div>
</div>
<div class="duo">
  <button class="btn btn--secondary">Altri 20 colpi</button>
  <button class="btn btn--success">Ho finito</button>
</div>"""
    return phone(
        "Ferma nel cerchio",
        "20 colpi &middot; 14 minuti",
        content,
        nav=None,
        action=f'<button class="head__act" aria-label="Condividi">{ico(I["share"], 17)}</button>',
    )


# --------------------------------------------------------------------------
# Andamento (#181, #184, #316)
# --------------------------------------------------------------------------


def andamento_gesto():
    return andamento("gesto")


def andamento(asse="abilita"):
    """Le categorizzazioni sono due (abilita' e gesto): anche il radar e' di due
    tipi. Stessa pagina, un interruttore in cima al grafico."""
    if asse == "abilita":
        labels = ["Posizione", "Tiro", "Battente", "Sponde", "Difesa", "Spaccata"]
        recent = [61, 78, 52, 44, 38, 66]
        prev = [48, 74, 55, 30, 40, 60]
    else:
        labels = ["stop", "stun", "follow", "draw", "spin", "forza", "bank", "kick"]
        recent = [82, 64, 71, 49, 35, 58, 41, 30]
        prev = [80, 55, 69, 38, 36, 50, 40, 22]

    def riga(cat, val, band, tone, delta):
        arrow = "up" if delta >= 0 else "down"
        col = "var(--c7-ok)" if delta >= 0 else "var(--c7-err)"
        return (
            f'<div class="rows__row"><div class="grow"><div class="rows__title">{cat}</div>'
            f'<div class="rows__sub">{band}</div></div>'
            f'<span style="color:{col}">{ico(I[arrow], 14, 2.6)}</span>'
            f'<span class="num" style="font-size:12px;color:{col};min-width:34px">{abs(delta)}</span>'
            f'<span class="num-lg" style="font-size:20px;min-width:52px;text-align:right">{val}%</span></div>'
        )

    if asse == "abilita":
        righe = (
            riga("Tiro", 78, "solido &middot; 31 prove", "ok", 4)
            + riga("Posizione", 61, "in crescita &middot; 12 prove", "ok", 13)
            + riga("Battente", 52, "in crescita &middot; 9 prove", "warn", -3)
            + riga("Sponde", 44, "da costruire &middot; 6 prove", "ok", 14)
        )
        poche = "Difesa e spaccata hanno"
    else:
        righe = (
            riga("stop", 82, "solido &middot; 24 prove", "ok", 2)
            + riga("follow", 71, "solido &middot; 18 prove", "ok", 2)
            + riga("stun", 64, "in crescita &middot; 11 prove", "ok", 9)
            + riga("draw", 49, "in crescita &middot; 15 prove", "ok", 11)
        )
        poche = "Bank e kick hanno"
    content = f"""
<div class="hscroll"><button class="pill is-active">Ultimi 30 giorni</button><button class="pill">3 mesi</button><button class="pill">Sempre</button></div>
<section class="card">
  <div class="duo" style="background:var(--c7-bg);border-radius:var(--c7-r-pill);padding:4px;gap:4px;margin-bottom:12px">
    <button class="pill{" is-active" if asse == "abilita" else ""}" style="width:100%;justify-content:center">Per abilit&agrave;</button>
    <button class="pill{" is-active" if asse == "gesto" else ""}" style="width:100%;justify-content:center">Per gesto</button></div>
  <div class="row"><div class="grow"><div class="kicker">Adesso</div><div class="num-xl">58%</div></div>
    <div style="text-align:right"><div class="kicker">Il mese prima</div><div class="num-xl" style="color:var(--c7-ink-muted)">51%</div></div></div>
  <div style="max-width:300px;margin:6px auto 0">{radar(labels, recent, prev)}</div>
  <div class="legend" style="justify-content:center;margin-top:4px">
    <span><i style="background:#2C4A52"></i>adesso</span><span><i style="background:#9AA3A6"></i>il mese prima</span></div>
</section>
<section class="rows">
  {righe}
</section>
<div class="flash flash--info"><span class="flash__ico">{ico(I["info"], 16)}</span>
  <div>{poche} meno di cinque prove: sul grafico ci sono, ma il numero non dice ancora niente.</div></div>
<section class="card">
  <div class="sechead"><h4>I tuoi obiettivi</h4><span class="sechead__more">2 di 3</span></div>
  <div class="goal__top" style="margin-top:12px"><span class="goal__t">Spot Shot Rally a 8 su 10</span><span class="goal__v">6,3 / 8</span></div>
  <div class="bar" style="margin-top:6px"><div class="bar__fill" style="width:78%"></div></div>
  <div class="goal__top" style="margin-top:14px"><span class="goal__t">Posizione &laquo;solida&raquo;</span><span class="goal__v">61 / 70%</span></div>
  <div class="bar" style="margin-top:6px"><div class="bar__fill" style="width:87%"></div></div>
  <button class="btn btn--secondary btn--w btn--sm" style="margin-top:14px">{ico(I["plus"], 15)}Aggiungi un obiettivo</button>
</section>"""
    return phone(
        "Il tuo allenamento",
        "58 prove &middot; 11 esercizi",
        content,
        h=1320,
        tabs=area_tabs("Andamento"),
    )


# --------------------------------------------------------------------------
# Imposta un obiettivo (#316, e la parte «obiettivi» di #175)
# --------------------------------------------------------------------------


def obiettivo():
    def ch(t, sub, on=False):
        return (
            f'<button class="choice{" is-on" if on else ""}"><span><span class="choice__t">{t}</span>'
            f'<span class="choice__s">{sub}</span></span></button>'
        )

    def pills(voci, on):
        return "".join(
            f'<button class="pill{" is-active" if v == on else ""}">{v}</button>'
            for v in voci
        )

    content = f"""
<div><div class="label" style="margin-bottom:8px">Che cosa vuoi ottenere</div>
  <div class="stack" style="gap:8px">
    {ch("Un risultato su un esercizio", "arrivare a un punteggio, e tenerlo", on=True)}
    {ch("Un&rsquo;abilit&agrave; che sale", "portare Posizione, Sponde&hellip; al livello successivo")}
    {ch("La costanza", "allenarmi con una certa frequenza")}
  </div></div>
<div><div class="label" style="margin-bottom:8px">Su quale esercizio</div>
  <button class="item" style="border:0;width:100%;text-align:left;font-family:inherit;grid-template-columns:64px 1fr auto">
    <span class="item__thumb">{table(SPOT)}</span>
    <span><span class="item__t" style="display:block">Spot Shot Rally</span>
      <span class="item__s" style="display:block">la tua media 6,3 &middot; record 10 &middot; 14 prove</span></span>
    {ico(I["chevron"], 14)}</button></div>
<div class="card row"><div class="grow"><div class="rows__title">Dove vuoi arrivare</div>
    <div class="rows__sub">su 10 &middot; oggi sei a 6,3</div></div>
  <div class="stepper"><button aria-label="Meno">{ico(I["minus"], 16, 2.4)}</button><span>8</span><button aria-label="Pi&ugrave;">{ico(I["plus"], 16, 2.4)}</button></div></div>
<div><div class="label" style="margin-bottom:8px">Quando vale raggiunto</div>
  <div class="row" style="flex-wrap:wrap;gap:6px">{pills(["Media delle ultime 5 prove", "Basta una volta"], "Media delle ultime 5 prove")}</div></div>
<div><div class="label" style="margin-bottom:8px">Entro quando</div>
  <div class="row" style="flex-wrap:wrap;gap:6px">{pills(["Un mese", "Tre mesi", "Senza scadenza"], "Tre mesi")}</div></div>
<section class="card">
  <div class="kicker">Da dove parti</div>
  <div style="margin-top:6px">{livechart([5, 6, 5, 7, 6, 6, 7], 12, 8, 10, "obiettivo: 8", h=84)}</div>
  <div style="font-size:12px;font-weight:700;color:var(--c7-ink-soft);margin-top:4px">A questo ritmo ci arrivi in cinque settimane circa. &Egrave; alla tua portata: ambizioso il giusto.</div>
</section>
<p class="muted" style="font-size:12px;line-height:1.45">Hai 2 obiettivi su 3. Un obiettivo si pu&ograve; cambiare o lasciare in ogni momento; raggiunto, resta nel tuo andamento con la data.</p>
<button class="btn btn--primary btn--w">Salva l&rsquo;obiettivo</button>"""
    return phone("Nuovo obiettivo", "Il tuo allenamento", content, h=980, tabs="")


# --------------------------------------------------------------------------
# Creare, modificare, duplicare (#168, #252, #253)
# --------------------------------------------------------------------------


def _form(title_val):
    cats = [
        ("Posizione", True),
        ("Tiro", True),
        ("Battente", False),
        ("Sponde", False),
        ("Difesa", False),
        ("Spaccata", False),
        ("Fondamentali", False),
    ]
    catp = "".join(
        f'<button class="pill{" is-active" if on else ""}">{c}</button>'
        for c, on in cats
    )
    gesti = [
        ("stop", False),
        ("stun", False),
        ("follow", False),
        ("draw", True),
        ("spin", False),
        ("forza", True),
        ("bank", False),
        ("kick", False),
        ("jump", False),
        ("mass&eacute;", False),
    ]
    gestp = "".join(
        f'<button class="pill{" is-active" if on else ""}">{c}</button>'
        for c, on in gesti
    )
    lvl = "".join(
        ('<button class="is-on">1</button>' if n == 1 else f"<button>{n}</button>")
        for n in range(1, 6)
    )

    def ch(t, s, on=False):
        return (
            f'<button class="choice{" is-on" if on else ""}"><span><span class="choice__t">{t}</span>'
            f'<span class="choice__s">{s}</span></span></button>'
        )

    return f"""
<div><div class="label" style="margin-bottom:8px">Titolo</div>
  <div class="field field--filled">{title_val}</div></div>
<div><div class="label" style="margin-bottom:8px">Come si fa</div>
  <div class="field field--area field--filled">Dieci tiri dalla stessa posizione: la bilia bersaglio sul punto, la battente in mano. Un punto per ogni imbucata.</div></div>
<div><div class="row" style="margin-bottom:8px"><span class="label grow">Cosa allena</span><span class="muted" style="font-size:11px;font-weight:700">fino a tre</span></div>
  <div class="row" style="flex-wrap:wrap;gap:6px">{catp}</div></div>
<div><div class="row" style="margin-bottom:8px"><span class="label grow">Con che gesto</span><span class="muted" style="font-size:11px;font-weight:700">zero, uno o pi&ugrave;</span></div>
  <div class="row" style="flex-wrap:wrap;gap:6px">{gestp}</div></div>
<div><div class="row" style="margin-bottom:8px"><span class="label grow">Livello</span><span class="muted" style="font-size:11px;font-weight:700">1 per chi comincia</span></div>
  <div class="lvl">{lvl}</div></div>
<section class="rows">
  <div class="rows__row" style="padding:12px 18px"><div class="grow"><div class="rows__title">Famiglia e passo</div>
    <div class="rows__sub">stop shot 1 &middot; 2 &middot; 3: lo stesso gesto, sempre pi&ugrave; difficile</div></div>
    <span class="muted" style="font-size:12px;font-weight:700">nessuna</span>{ico(I["chevron"], 14)}</div>
  <div class="rows__row" style="padding:12px 18px"><div class="grow"><div class="rows__title">La bianca</div>
    <div class="rows__sub">si rimette a ogni tiro, o resta dove si ferma</div></div>
    <span class="muted" style="font-size:12px;font-weight:700">si rimette</span>{ico(I["chevron"], 14)}</div>
  <div class="rows__row" style="padding:12px 18px"><div class="grow"><div class="rows__title">Varianti</div>
    <div class="rows__sub">destra e sinistra, oppure posizioni A e B: si registrano separate</div></div>
    <span class="muted" style="font-size:12px;font-weight:700">nessuna</span>{ico(I["chevron"], 14)}</div>
</section>
<div><div class="label" style="margin-bottom:8px">Come si registra</div>
  <div class="stack" style="gap:8px">
    {ch("Riuscito o no", "un tocco per prova")}
    {ch("A punteggio", "un numero a fine prova", on=True)}
    {ch("Colpo per colpo", "imbucato o sbagliato, e dove si ferma la battente")}
    {ch("Con estrazione", "a ogni colpo l&rsquo;app estrae la consegna")}
  </div></div>
<div class="card row"><div class="grow"><div class="rows__title">Punteggio massimo</div>
    <div class="rows__sub">lascia vuoto se si va avanti finch&eacute; si sbaglia</div></div>
  <div class="stepper"><button aria-label="Meno">{ico(I["minus"], 16, 2.4)}</button><span>10</span><button aria-label="Pi&ugrave;">{ico(I["plus"], 16, 2.4)}</button></div></div>
<div><div class="label" style="margin-bottom:8px">La disposizione</div>
  <div style="border-radius:var(--c7-r-card);overflow:hidden">{table(SPOT)}</div>
  <div class="duo" style="margin-top:8px">
    <button class="btn btn--secondary btn--sm">{ico(I["target"], 15)}Modifica il disegno</button>
    <button class="btn btn--secondary btn--sm">{ico(I["camera"], 15)}Usa una foto</button></div></div>"""


def crea_form():
    content = _form("Spot Shot Rally") + """
<button class="btn btn--success btn--w">Salva le modifiche</button>"""
    return phone(
        "Modifica l&rsquo;esercizio",
        "Spot Shot Rally &middot; 46 prove registrate",
        content,
        h=1640,
    )


def crea_copia():
    content = _form("Spot Shot Rally")
    overlay = """
<div class="veil"></div>
<div class="bottomsheet">
  <div class="grab"></div>
  <h3>Questo esercizio ha gi&agrave; 46 prove</h3>
  <p class="muted" style="font-size:13px">Hai cambiato il punteggio massimo, da 10 a 15. Se modifichi questo esercizio,
    i 46 punteggi gi&agrave; registrati da 14 giocatori si leggeranno su una scala che non &egrave; quella con cui sono stati fatti.</p>
  <button class="btn btn--primary btn--w">Crea una copia e modifica quella</button>
  <button class="btn btn--danger btn--w">Modifica comunque questo</button>
  <button class="btn btn--secondary btn--w">Torna al modulo</button>
</div>"""
    body = phone(
        "Modifica l&rsquo;esercizio",
        "Spot Shot Rally &middot; 46 prove registrate",
        content,
        nav=None,
        overlay=overlay,
    )
    return body
