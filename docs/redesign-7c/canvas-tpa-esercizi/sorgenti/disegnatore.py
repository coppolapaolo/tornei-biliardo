#!/usr/bin/env python3
"""Il disegnatore di esercizi (#179). Gli strumenti di oggi restano tutti:
Sposta, Bilie, Tiro, Linea libera, Testo, annulla/ripeti, posizioni standard.
Nuovi: Bersaglio (riquadro o cerchi), Posizioni numerate, Richiamo, Marcatore.
Sul tavolo c'e' la notazione del drill F5 di Billiard University."""

from kit import I, ball, bullseye, desktop, freccia, ico, line, mezzo, ob, phone, table

SEL = "#8FCDE8"


def zona(x, y, w, h, filled=False, n=None, selected=False):
    fill = 'fill="#1B2124" fill-opacity=".28"' if filled else 'fill="none"'
    out = f'<rect x="{x}" y="{y}" width="{w}" height="{h}" {fill} stroke="#F5F7F6" stroke-width="3.5"/>'
    if n is not None:
        out += (
            f'<text x="{x + w / 2}" y="{y + h / 2 + 9}" text-anchor="middle" font-size="26" '
            f'font-weight="800" fill="#F5F7F6" font-family="Manrope,sans-serif">{n}</text>'
        )
    if selected:
        out += (
            f'<rect x="{x - 8}" y="{y - 8}" width="{w + 16}" height="{h + 16}" fill="none" '
            f'stroke="{SEL}" stroke-width="2.5" stroke-dasharray="8 6"/>'
            + "".join(
                f'<rect x="{cx - 7}" y="{cy - 7}" width="14" height="14" rx="3" fill="{SEL}"/>'
                for cx, cy in (
                    (x - 8, y - 8),
                    (x + w + 8, y - 8),
                    (x - 8, y + h + 8),
                    (x + w + 8, y + h + 8),
                )
            )
        )
    return out


def donut(x, y):
    return (
        f'<circle cx="{x}" cy="{y}" r="12" fill="none" stroke="#F5F7F6" stroke-width="2.2" '
        f'stroke-dasharray="4 4"/>'
    )


def fuori(n, x):
    """Numero di posizione fuori dal tavolo, sopra la sponda lunga."""
    return (
        f'<text x="{x}" y="-46" text-anchor="middle" font-size="24" font-weight="800" '
        f'fill="#1B2124" font-family="Manrope,sans-serif">{n}</text>'
    )


def richiamo(x, y, tx, ty, testo):
    w = len(testo) * 9.2 + 24
    return (
        line(tx, ty, x, y, dashed=False, color="#F5F7F6")
        + f'<circle cx="{x}" cy="{y}" r="4" fill="#F5F7F6"/>'
        + f'<rect x="{tx - w / 2}" y="{ty - 20}" width="{w}" height="34" rx="9" fill="#F5F7F6"/>'
        + f'<text x="{tx}" y="{ty + 3}" text-anchor="middle" font-size="16" font-weight="800" '
        f'fill="#1B2124" font-family="Manrope,sans-serif">{testo}</text>'
    )


BU = (
    zona(100, 0, 200, 100, n=1)
    + zona(300, 0, 200, 100, n=2, selected=True)
    + zona(500, 0, 200, 100, n=3)
    + zona(700, 100, 100, 200, filled=True, n=4)
    + ball(150, 300)
    + ball(400, 300, 3)
    + line(162, 300, 388, 300)
    + donut(400, 200)
    + donut(600, 200)
    + richiamo(400, 300, 560, 360, "la 3 a mezzo diamante")
)

BU_CERCHI = (
    ball(180, 300)
    + ball(560, 110, 3)
    + line(192, 294, 548, 116)
    + bullseye(560, 250, 86)
    + f'<circle cx="560" cy="250" r="98" fill="none" stroke="{SEL}" stroke-width="2.5" stroke-dasharray="8 6"/>'
)


def tool(icon, label, on=False, new=False):
    cls = "tool" + (" is-on" if on else "") + (" tool--new" if new else "")
    return f'<button class="{cls}">{ico(I[icon], 19)}{label}</button>'


STRUMENTI = [
    ("move", "Sposta", False, False),
    ("target", "Bilie", False, False),
    ("cue", "Tiro", False, False),
    ("pen", "Linea", False, False),
    ("type", "Testo", False, False),
    ("rect", "Bersaglio", True, True),
    ("hash", "Posizioni", False, True),
    ("callout", "Richiamo", False, True),
    ("donut", "Marcatore", False, True),
]


def _stepper(v, lab):
    return (
        f'<div class="row"><span class="grow rows__title">{lab}</span><div class="stepper stepper--sm">'
        f'<button aria-label="Meno">{ico(I["minus"], 13, 2.6)}</button><span>{v}</span>'
        f'<button aria-label="Pi&ugrave;">{ico(I["plus"], 13, 2.6)}</button></div></div>'
    )


def _misura(v, lab):
    """Misura in diamanti a passi da un quarto, come la griglia: ¼ · ½ · ¾."""
    return (
        f'<div class="row"><span class="grow"><span class="rows__title" style="display:block">{lab}</span>'
        f'<span class="rows__sub" style="display:block">in diamanti &middot; passi da &frac14;</span></span>'
        f'<div class="stepper stepper--sm"><button aria-label="Un quarto in meno">{ico(I["minus"], 13, 2.6)}</button>'
        f'<span style="min-width:44px">{v}</span>'
        f'<button aria-label="Un quarto in pi&ugrave;">{ico(I["plus"], 13, 2.6)}</button></div></div>'
    )


def _forma(on):
    def b(icon, t, s, sel):
        return (
            f'<button class="choice{" is-on" if sel else ""}" style="min-height:64px">{ico(I[icon], 20)}'
            f'<span><span class="choice__t">{t}</span><span class="choice__s">{s}</span></span></button>'
        )

    return b("rect", "Riquadro", "dentro o fuori", on == "rect") + b(
        "ring", "Cerchi", "quanto vicino", on == "ring"
    )


# --------------------------------------------------------------------------
# Desktop: il tavolo al centro, strumenti a sinistra, proprieta' a destra
# --------------------------------------------------------------------------


def d_desktop():
    rail = "".join(tool(*t) for t in STRUMENTI)
    actions = (
        f'<button class="btn btn--secondary btn--sm">{ico(I["rotate"], 15)}Annulla</button>'
        '<button class="btn btn--secondary btn--sm">Ripeti</button>'
        '<button class="btn btn--secondary btn--sm">Posizioni standard</button>'
        '<button class="btn btn--success btn--sm">Salva l&rsquo;esercizio</button>'
    )
    content = f"""
<div style="display:grid;grid-template-columns:84px 1fr 320px;gap:var(--c7-gap-lg);align-items:start">
  <div class="card" style="padding:6px;display:grid;gap:2px">{rail}</div>
  <div class="stack">
    <div class="stage" style="padding:64px 40px 40px">{table(BU + "".join(fuori(n, x) .replace('fill="#1B2124"', 'fill="#F5F7F6"') for n, x in ((7, 100), (6, 200), (5, 300))))}</div>
    <div class="row"><span class="chip chip--cat">Riquadro 2 selezionato</span>
      <span class="muted grow" style="font-size:12px;font-weight:700">Trascina gli angoli: si aggancia ai diamanti. Alt lo libera.</span>
      <span class="num" style="font-size:12px;color:var(--c7-ink-muted)">griglia e misure a &frac14; di diamante</span></div>
    <section class="card">
      <div class="sechead"><h4>Sul tavolo</h4><span class="sechead__more">11 oggetti</span></div>
      <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;margin-top:12px">
        <button class="choice" style="min-height:48px;background:var(--c7-bg)"><span class="choice__t">Riquadro 1</span></button>
        <button class="choice is-on" style="min-height:48px"><span class="choice__t">Riquadro 2</span></button>
        <button class="choice" style="min-height:48px;background:var(--c7-bg)"><span class="choice__t">Riquadro 3</span></button>
        <button class="choice" style="min-height:48px;background:var(--c7-bg)"><span class="choice__t">Riquadro 4 &middot; pieno</span></button>
        <button class="choice" style="min-height:48px;background:var(--c7-bg)"><span class="choice__t">Posizioni 7 &rarr; 5</span></button>
        <button class="choice" style="min-height:48px;background:var(--c7-bg)"><span class="choice__t">Richiamo sulla 3</span></button>
        <button class="choice" style="min-height:48px;background:var(--c7-bg)"><span class="choice__t">Battente</span></button>
        <button class="choice" style="min-height:48px;background:var(--c7-bg)"><span class="choice__t">Bilia 3</span></button>
        <button class="choice" style="min-height:48px;background:var(--c7-bg)"><span class="choice__t">2 marcatori</span></button>
      </div>
      <p class="muted" style="font-size:12px;margin-top:10px">Un oggetto piccolo o coperto si prende da qui. Le posizioni numerate sono una scala sola: inserirne una in mezzo rinumera le altre.</p>
    </section>
  </div>
  <div class="stack">
    <section class="card">
      <div class="kicker">Bersaglio</div>
      <div class="stack" style="gap:8px;margin-top:10px">{_forma("rect")}</div>
    </section>
    <section class="card"><div class="stack" style="gap:12px">
      {_misura("2&frac12;", "Largo")}
      {_misura("1&frac14;", "Alto")}
      <div class="row"><span class="grow rows__title">Riempito</span><span class="toggle"></span></div>
      <div class="row"><span class="grow rows__title">Ruotato di 90&deg;</span><span class="toggle"></span></div>
      <div class="row"><span class="grow rows__title">Numero dentro</span><span class="toggle is-on"></span></div>
    </div></section>
    <section class="card">
      <div class="row"><div class="grow"><div class="rows__title">Vale per il punteggio</div>
        <div class="rows__sub">la battente qui dentro d&agrave; punti, quando l&rsquo;esercizio si fa colpo per colpo</div></div>
        <span class="toggle is-on"></span></div>
      <div class="divider" style="margin:12px 0"></div>
      {_stepper("1", "Punti se si ferma dentro")}
    </section>
    <button class="btn btn--danger btn--w btn--sm">Elimina il bersaglio</button>
  </div>
</div>"""
    return desktop(
        "Disegna l&rsquo;esercizio",
        "Posizione in quattro zone &middot; bozza salvata alle 21:14",
        actions,
        content,
        active="Esercizi",
        who=("LU", "Luca Bianchi", "direttore &middot; Lv 3", "direzione gara"),
    )


# --------------------------------------------------------------------------
# Telefono: il tavolo resta in vista, lo strumento apre il suo foglio
# --------------------------------------------------------------------------


def d_mobile():
    strip = "".join(tool(*t) for t in STRUMENTI[:6])
    content = f"""
<div class="stage" style="padding:10px">{table(BU)}</div>
<div class="toolstrip" style="overflow:hidden">{strip}</div>
<section class="card">
  <div class="row"><span class="kicker grow">Bersaglio &middot; riquadro 2</span>
    <button class="iconbtn" style="width:48px;height:48px;margin:-8px -6px;background:var(--c7-err-bg);color:var(--c7-err-ink)" aria-label="Elimina">{ico(I["x"], 15)}</button></div>
  <div class="duo" style="margin-top:12px">{_forma("rect")}</div>
  <div class="stack" style="gap:12px;margin-top:14px">
    {_misura("2&frac12;", "Largo")}
    {_misura("1&frac14;", "Alto")}
    <div class="row"><span class="grow rows__title">Riempito</span><span class="toggle"></span></div>
    <div class="row"><span class="grow rows__title">Vale per il punteggio</span><span class="toggle is-on"></span></div>
  </div>
</section>"""
    dock = f"""
<div class="dock"><div class="duo" style="grid-template-columns:auto auto 1fr">
  <button class="undo" style="width:56px" aria-label="Annulla">{ico(I["rotate"], 16)}</button>
  <button class="undo" style="width:56px" aria-label="Altri strumenti">{ico(I["dots"], 16)}</button>
  <button class="btn btn--success" style="height:var(--c7-touch);font-size:14px">Salva l&rsquo;esercizio</button></div></div>"""
    return phone(
        "Disegna l&rsquo;esercizio",
        "Posizione in quattro zone",
        content,
        nav=None,
        dock=dock,
        action=f'<button class="head__act" aria-label="Chiudi">{ico(I["x"], 17)}</button>',
        avatar="LU",
    )


# --------------------------------------------------------------------------
# Telefono: i cerchi, cioe' il bersaglio come dato (#183)
# --------------------------------------------------------------------------


def d_cerchi():
    def anello(colore, nome, pt):
        return (
            f'<div class="row"><span style="width:18px;height:18px;border-radius:50%;background:{colore};flex-shrink:0"></span>'
            f'<span class="grow rows__title">{nome}</span><div class="stepper stepper--sm">'
            f'<button aria-label="Meno">{ico(I["minus"], 13, 2.6)}</button><span>{pt}</span>'
            f'<button aria-label="Pi&ugrave;">{ico(I["plus"], 13, 2.6)}</button></div></div>'
        )

    strip = "".join(tool(*t) for t in STRUMENTI[:6])
    content = f"""
<div class="stage" style="padding:10px">{table(BU_CERCHI)}</div>
<div class="toolstrip" style="overflow:hidden">{strip}</div>
<section class="card">
  <div class="kicker">Bersaglio &middot; dove deve fermarsi la battente</div>
  <div class="duo" style="margin-top:12px">{_forma("ring")}</div>
  <div class="stack" style="gap:12px;margin-top:14px">
    {_misura("1&frac12;", "Raggio")}
    {anello("rgba(201,168,76,.95)", "Centro", 3)}
    {anello("rgba(201,168,76,.55)", "Anello di mezzo", 2)}
    {anello("rgba(201,168,76,.28)", "Anello esterno", 1)}
  </div>
  <p class="muted" style="font-size:12px;margin-top:12px">Fuori dai cerchi vale zero. Con un bersaglio cos&igrave; l&rsquo;esercizio si pu&ograve; fare colpo per colpo.</p>
</section>"""
    dock = f"""
<div class="dock"><div class="duo" style="grid-template-columns:auto auto 1fr">
  <button class="undo" style="width:56px" aria-label="Annulla">{ico(I["rotate"], 16)}</button>
  <button class="undo" style="width:56px" aria-label="Altri strumenti">{ico(I["dots"], 16)}</button>
  <button class="btn btn--success" style="height:var(--c7-touch);font-size:14px">Salva l&rsquo;esercizio</button></div></div>"""
    return phone(
        "Disegna l&rsquo;esercizio",
        "Ferma nel cerchio",
        content,
        nav=None,
        dock=dock,
        h=860,
        action=f'<button class="head__act" aria-label="Chiudi">{ico(I["x"], 17)}</button>',
        avatar="LU",
    )


# --------------------------------------------------------------------------
# Telefono: cio' che i diagrammi di Ronin usano e il disegnatore non sa fare
# --------------------------------------------------------------------------


def d_varianti():
    scena = (
        ob(160, 100)
        + ball(240, 190)
        + freccia(232, 180, 170, 110, "#F5F7F6")
        + freccia(148, 92, 14, 12)
        + freccia(176, 118, 240, 300, "#8FCDE8")
        + '<rect x="190" y="290" width="100" height="100" fill="#8FCDE8" fill-opacity=".45"/>'
        + '<path d="M60 0H150" stroke="#8FCDE8" stroke-width="12" stroke-linecap="round"/>'
    )

    def ch(t, s, on=False):
        return (
            f'<button class="choice{" is-on" if on else ""}" style="min-height:52px;padding:8px 12px">'
            f'<span><span class="choice__t" style="font-size:13px">{t}</span>'
            f'<span class="choice__s">{s}</span></span></button>'
        )

    content = f"""
<div class="duo">
  <div><div class="stage" style="padding:6px">{mezzo(scena)}</div>
    <div class="label" style="text-align:center;margin-top:6px">a destra &middot; la disegni tu</div></div>
  <div><div class="stage" style="padding:6px">{mezzo(scena, True)}</div>
    <div class="label" style="text-align:center;margin-top:6px">a sinistra &middot; la fa l&rsquo;app</div></div>
</div>
<section class="card">
  <div class="kicker">Varianti</div>
  <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;margin-top:10px">
    {ch("Nessuna", "un disegno")}{ch("Destra e sinistra", "specchio", on=True)}{ch("A, B&hellip;", "pi&ugrave; posizioni")}</div>
  <p class="muted" style="font-size:12px;margin-top:10px">Ogni variante si registra per conto suo: &egrave; l&igrave; che si vede il lato debole.</p>
</section>
<section class="card">
  <div class="kicker">Inquadratura</div>
  <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;margin-top:10px">
    {ch("Tavolo", "intero")}{ch("Mezzo", "tavolo", on=True)}{ch("Angolo", "un quarto")}</div>
</section>
<section class="card">
  <div class="kicker">Bersaglio</div>
  <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;margin-top:10px">
    {ch("Riquadro", "sul panno")}{ch("Cerchi", "graduato")}{ch("Tratto", "di sponda", on=True)}</div>
</section>"""
    dock = f"""
<div class="dock"><div class="duo" style="grid-template-columns:auto auto 1fr">
  <button class="undo" style="width:56px" aria-label="Annulla">{ico(I["rotate"], 16)}</button>
  <button class="undo" style="width:56px" aria-label="Altri strumenti">{ico(I["dots"], 16)}</button>
  <button class="btn btn--success" style="height:var(--c7-touch);font-size:14px">Salva l&rsquo;esercizio</button></div></div>"""
    return phone(
        "Disegna l&rsquo;esercizio",
        "6 &middot; Angolo naturale",
        content,
        nav=None,
        dock=dock,
        action=f'<button class="head__act" aria-label="Chiudi">{ico(I["x"], 17)}</button>',
        avatar="LU",
    )


# --------------------------------------------------------------------------
# Telefono: l'inquadratura — come si fa l'immagine di un solo pezzo di tavolo
# --------------------------------------------------------------------------


def d_inquadratura():
    """Risposta a «come si creano le immagini di un solo pezzo?»: si disegna
    SEMPRE sul tavolo intero; l'inquadratura e' una cornice che si sposta e si
    ridimensiona, e decide solo cosa finisce nell'immagine."""
    scena = (
        ob(160, 100)
        + ball(240, 190)
        + freccia(232, 180, 170, 110, "#F5F7F6")
        + freccia(148, 92, 14, 12)
        + freccia(176, 118, 240, 300, "#8FCDE8")
        + '<rect x="190" y="290" width="100" height="100" fill="#8FCDE8" fill-opacity=".45"/>'
    )
    # velo sul resto del tavolo + cornice con le quattro maniglie
    fx, fy, fw, fh = -40, -40, 470, 470
    velo = (
        f'<path d="M-40 -40H840V440H-40Z M{fx} {fy}V{fy + fh}H{fx + fw}V{fy}Z" fill="#14181A" '
        f'fill-opacity=".62" fill-rule="evenodd"/>'
    )
    cornice = (
        f'<rect x="{fx + 3}" y="{fy + 3}" width="{fw - 6}" height="{fh - 6}" fill="none" stroke="#8FCDE8" '
        f'stroke-width="5" stroke-dasharray="14 8" rx="22"/>'
        + "".join(
            f'<circle cx="{x}" cy="{y}" r="15" fill="#8FCDE8" stroke="#14181A" stroke-width="3"/>'
            for x, y in (
                (fx + fw - 3, fy + fh - 3),
                (fx + fw - 3, fy + fh / 2),
                (fx + fw / 2, fy + fh - 3),
            )
        )
    )

    def ch(t, sub, on=False):
        return (
            f'<button class="choice{" is-on" if on else ""}" style="min-height:52px;padding:8px 12px">'
            f'<span><span class="choice__t" style="font-size:13px">{t}</span>'
            f'<span class="choice__s">{sub}</span></span></button>'
        )

    strip = "".join(tool(*t) for t in STRUMENTI[:6])
    content = f"""
<div class="stage" style="padding:10px">{table(scena + velo + cornice)}</div>
<div class="toolstrip" style="overflow:hidden">{strip}</div>
<section class="card">
  <div class="kicker">Inquadratura &middot; cosa finisce nell&rsquo;immagine</div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-top:10px">
    {ch("Tavolo intero", "come oggi")}{ch("Mezzo tavolo", "un lato corto", on=True)}
    {ch("Un angolo", "un quarto")}{ch("Libera", "trascini la cornice")}</div>
  <p class="muted" style="font-size:12px;margin-top:10px;line-height:1.45">Si disegna sempre sul tavolo intero: la cornice si sposta e si allarga dalle maniglie, agganciata ai diamanti, e decide solo cosa si vede. Le bilie fuori cornice restano nel disegno, se un giorno la allarghi.</p>
</section>
<div class="row" style="gap:10px"><div style="width:96px;flex-shrink:0;border-radius:var(--c7-r-control);overflow:hidden">{mezzo(scena)}</div>
  <div><div class="rows__title">Cos&igrave; la vede chi si allena</div>
    <div class="rows__sub">nel catalogo, nella scheda, durante la seduta</div></div></div>"""
    dock = f"""
<div class="dock"><div class="duo" style="grid-template-columns:auto auto 1fr">
  <button class="undo" style="width:56px" aria-label="Annulla">{ico(I["rotate"], 16)}</button>
  <button class="undo" style="width:56px" aria-label="Altri strumenti">{ico(I["dots"], 16)}</button>
  <button class="btn btn--success" style="height:var(--c7-touch);font-size:14px">Salva l&rsquo;esercizio</button></div></div>"""
    return phone(
        "Disegna l&rsquo;esercizio",
        "6 &middot; Angolo naturale",
        content,
        nav=None,
        dock=dock,
        action=f'<button class="head__act" aria-label="Chiudi">{ico(I["x"], 17)}</button>',
        avatar="LU",
    )
