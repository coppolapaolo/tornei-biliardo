#!/usr/bin/env python3
"""Esami (ADR-042). I comandi sono quelli che l'app ha gia': «Prova da solo»,
«Chiedi un appuntamento», accetta / controproponi / rifiuta, apri la sessione,
registra prova per prova, superato / non superato, interrompi senza esito.
L'esito resta booleano e lo decide l'esaminatore: il redesign non lo tocca."""

from esercizi import ELLE, POSIZIONE, SPOT
from kit import I, area_tabs, ico, phone, seqstrip, table
from schede import GRIP

CLOSE = f'<button class="head__act" aria-label="Chiudi">{ico(I["x"], 17)}</button>'


# --------------------------------------------------------------------------
# 1 · Catalogo degli esami: cosa sei per ciascuno
# --------------------------------------------------------------------------


def catalogo():
    def esame(nome, riga, stato, tone, icon="list"):
        return (
            f'<div class="rows__row" style="padding:16px 18px"><span class="tile tile--sm tile--{tone}">{ico(I[icon], 17)}</span>'
            f'<div class="grow"><div class="rows__title">{nome}</div><div class="rows__sub">{riga}</div>'
            f'<div class="rows__sub" style="color:var(--c7-ink-soft)">{stato}</div></div>{ico(I["chevron"], 15)}</div>'
        )

    content = f"""
<section class="card card--accent">
  <div class="row"><span class="kicker grow">Il tuo prossimo appuntamento</span>{ico(I["cal"], 17)}</div>
  <div class="num-lg" style="margin-top:8px">sab 26 set &middot; 18:30</div>
  <div style="font-size:13px;font-weight:700;color:var(--c7-accent-dim);margin-top:2px">Fondamentali &mdash; livello 2 &middot; con Luca Bianchi &middot; Biliardo Centrale</div>
  <div class="duo" style="margin-top:14px;grid-template-columns:1fr auto">
    <button class="btn btn--bright btn--sm">Apri l&rsquo;appuntamento</button>
    <button class="btn btn--locked btn--sm">Tutti &middot; 2</button></div>
</section>
<div class="label">Esami disponibili</div>
<section class="rows">
  {esame("Fondamentali &mdash; livello 1", "3 esercizi &middot; 2 esaminatori", "Superato il 12/09 &middot; certificato da Luca Bianchi", "ok", "cert")}
  {esame("Fondamentali &mdash; livello 2", "4 esercizi &middot; 2 esaminatori", "Provato da solo 2 volte &middot; il tuo meglio 14 su 22", "neutral")}
</section>
<div class="label">Esami che somministro</div>
<section class="rows">
  <div class="rows__row" style="padding:16px 18px"><span class="tile tile--sm tile--warn">{ico(I["bell"], 16)}</span>
    <div class="grow"><div class="rows__title">2 richieste aspettano te</div>
      <div class="rows__sub">Elena Ricci, Giulio Verdi &middot; Fondamentali &mdash; livello 1</div></div>{ico(I["chevron"], 15)}</div>
</section>"""
    return phone(
        "Esami",
        "Pi&ugrave; esercizi in fila, davanti a un esaminatore",
        content,
        tabs=area_tabs("Esami"),
    )


# --------------------------------------------------------------------------
# 2 · Il dettaglio di un esame
# --------------------------------------------------------------------------


def dettaglio():
    def ex(n, scene, nome, come):
        return (
            f'<div class="item" style="grid-template-columns:28px 64px 1fr"><span class="seq__dot" '
            f'style="background:var(--c7-bg)">{n}</span><div class="item__thumb">{table(scene)}</div>'
            f'<div><div class="item__t">{nome}</div><div class="item__s">{come}</div></div></div>'
        )

    content = f"""
<section class="card card--accent">
  <div class="kicker">Cosa si fa</div>
  <p style="margin-top:6px;font-size:14px">Tre gesti di base, uno dopo l&rsquo;altro: il tiro dal punto, la serie senza
    errori e il controllo della battente.</p>
  <div class="row" style="gap:6px;margin-top:12px;flex-wrap:wrap"><span class="chip">3 esercizi</span>
    <span class="chip">fino a 22 punti</span><span class="chip">circa 30 minuti</span></div>
</section>
<div class="label">Gli esercizi, nell&rsquo;ordine in cui si fanno</div>
<div class="stack" style="gap:8px">
  {ex(1, SPOT, "Spot Shot Rally", "da 0 a 10 &middot; 3 prove, conta la migliore")}
  {ex(2, ELLE, "Serie da otto", "superato o no &middot; una prova")}
  {ex(3, POSIZIONE, "Ferma nel cerchio", "da 0 a 12 &middot; 2 prove, conta la migliore")}
</div>
<section class="card">
  <div class="kicker">Le tue volte</div>
  <div class="row" style="margin-top:8px"><div class="grow"><div class="rows__title">Da solo, 2 volte</div>
    <div class="rows__sub">14 su 22 l&rsquo;ultima &middot; 11 la prima</div></div><span class="state state--muted">allenamento</span></div>
  <div class="divider" style="margin:10px 0"></div>
  <div class="row"><div class="grow"><div class="rows__title">Davanti a un esaminatore, mai</div>
    <div class="rows__sub">&egrave; l&rsquo;unico modo per farlo valere</div></div></div>
</section>
<div class="label">Chi lo somministra</div>
<section class="rows">
  <div class="rows__row"><div class="avatar">LU</div><div class="grow"><div class="rows__title">Luca Bianchi</div><div class="rows__sub">ha composto l&rsquo;esame &middot; Biliardo Centrale</div></div></div>
  <div class="rows__row"><div class="avatar">AF</div><div class="grow"><div class="rows__title">Andrea Ferri</div><div class="rows__sub">Sala Ronin</div></div></div>
</section>
<div class="duo">
  <button class="btn btn--secondary">Prova da solo</button>
  <button class="btn btn--success">Chiedi un appuntamento</button>
</div>"""
    return phone(
        "Fondamentali &mdash; livello 2",
        "Esame &middot; di Luca Bianchi",
        content,
        h=908,
    )


# --------------------------------------------------------------------------
# 3 · L'appuntamento: la proposta sul tavolo e la sua risposta insieme
# --------------------------------------------------------------------------


def appuntamento():
    def passo(chi, quando, now=False):
        return (
            f'<span class="tl__dot{" is-now" if now else ""}"></span><div class="tl__body">'
            f'<div class="num" style="font-size:14px">{quando}</div>'
            f'<div class="rows__sub">{chi}</div></div>'
        )

    content = f"""
<section class="card card--accent">
  <div class="kicker">Proposta sul tavolo</div>
  <div class="num-xl" style="margin-top:6px">sab 26 set &middot; 18:30</div>
  <div style="font-size:13px;font-weight:700;color:var(--c7-accent-dim);margin-top:2px">Biliardo Centrale &middot; proposta da Luca Bianchi</div>
  <button class="btn btn--success btn--w" style="margin-top:14px">Accetto: ci vediamo l&igrave;</button>
</section>
<section class="card">
  <div class="kicker">Oppure controproponi</div>
  <div class="duo" style="margin-top:10px">
    <div class="field field--filled" style="padding:0 14px;font-size:14px">{ico(I["cal"], 16)}sab 26 set</div>
    <div class="field field--filled" style="padding:0 14px;font-size:14px">{ico(I["clock"], 16)}20:00</div>
  </div>
  <div class="field field--filled" style="margin-top:8px;font-size:14px">{ico(I["table"], 16)}Biliardo Centrale</div>
  <button class="btn btn--primary btn--w" style="margin-top:10px">Manda la controproposta</button>
</section>
<section class="card">
  <div class="kicker">Come ci siete arrivati</div>
  <div class="tl" style="margin-top:12px">
    {passo("tu &middot; Biliardo Centrale", "sab 26 set &middot; 16:00")}
    {passo("Luca Bianchi &middot; Biliardo Centrale", "sab 26 set &middot; 18:30", now=True)}
  </div>
  <div class="row" style="gap:6px;flex-wrap:wrap"><span class="chip chip--cat">Luca Bianchi sta trattando</span>
    <span class="chip">Andrea Ferri non ha risposto</span></div>
</section>
<button class="btn btn--danger btn--w">Ritira la richiesta</button>"""
    return phone(
        "Appuntamento d&rsquo;esame", "Fondamentali &mdash; livello 2", content, h=916
    )


# --------------------------------------------------------------------------
# 4 · La sessione dell'esaminatore: un esercizio alla volta
# --------------------------------------------------------------------------


def sessione():
    content = f"""
{seqstrip(["Spot Shot", "Serie da otto", "Nel cerchio"], 0)}
<section class="card row"><div class="avatar">ER</div><div class="grow"><div class="rows__title">Elena Ricci</div>
  <div class="rows__sub">ha accettato l&rsquo;inizio alle 18:34</div></div><span class="state state--info">certificata</span></section>
<div style="border-radius:var(--c7-r-card);overflow:hidden">{table(SPOT)}</div>
<div class="row"><div class="grow"><h3>Spot Shot Rally</h3>
  <div class="muted" style="font-size:12px;font-weight:700">Da 0 a 10 &middot; 3 prove, conta la migliore</div></div></div>
<div class="kpis">
  <div class="kpi"><div class="kpi__v">7</div><div class="kpi__l">Prima prova</div></div>
  <div class="kpi" style="background:var(--c7-ok-bg)"><div class="kpi__v" style="color:var(--c7-ok-ink)">8</div><div class="kpi__l" style="color:var(--c7-ok-body)">Seconda &middot; la migliore</div></div>
  <div class="kpi" style="background:var(--c7-accent-tint)"><div class="kpi__v" style="color:var(--c7-accent-tint-ink)">&hellip;</div><div class="kpi__l">Terza, adesso</div></div>
</div>"""
    dock = f"""
<div class="dock" style="gap:12px">
  <div class="scorepad">
    <button class="scorepad__btn" aria-label="Uno in meno">{ico(I["minus"], 22, 2.4)}</button>
    <div style="text-align:center"><div class="scorepad__v">6</div><div class="scorepad__max">su 10</div></div>
    <button class="scorepad__btn" aria-label="Uno in pi&ugrave;">{ico(I["plus"], 22, 2.4)}</button>
  </div>
  <button class="btn btn--primary btn--w">Registra la terza prova</button>
  <div class="duo">
    <button class="undo">{ico(I["rotate"], 15)}Correggi la seconda</button>
    <button class="undo">Rinuncia alla terza</button>
  </div>
</div>"""
    return phone(
        "Fondamentali &mdash; livello 1",
        "Sessione certificata &middot; 8 su 22",
        content,
        nav=None,
        dock=dock,
        action=CLOSE,
        avatar="LU",
    )


# --------------------------------------------------------------------------
# 5 · La chiusura: l'esito e' netto, e lo decide l'esaminatore
# --------------------------------------------------------------------------


def chiusura():
    def riga(nome, come, val):
        return (
            f'<div class="rows__row"><div class="grow"><div class="rows__title">{nome}</div>'
            f'<div class="rows__sub">{come}</div></div><span class="num-lg" style="font-size:20px">{val}</span></div>'
        )

    content = f"""
{seqstrip(["Spot Shot", "Serie da otto", "Nel cerchio"], 3)}
<section class="card card--accent">
  <div class="kicker">Elena Ricci</div>
  <div class="row" style="margin-top:6px;align-items:baseline"><span style="font-size:48px;font-weight:800;letter-spacing:-.04em;line-height:1">17</span>
    <span class="num" style="font-size:18px;color:var(--c7-accent-dim)">su 22</span></div>
</section>
<section class="rows">
  {riga("Spot Shot Rally", "7 &middot; 8 &middot; 6 &mdash; conta la migliore", "8")}
  {riga("Serie da otto", "una prova", "riuscita")}
  {riga("Ferma nel cerchio", "9 &middot; 7 &mdash; conta la migliore", "9")}
</section>
<p class="muted" style="font-size:12px">L&rsquo;esito &egrave; netto: superato oppure no. Nessun voto, nessuna nota. Il punteggio
  resta nello storico di Elena, l&rsquo;esito lo decidi tu.</p>"""
    dock = """
<div class="dock">
  <div class="duo">
    <button class="big big--no">Non superato</button>
    <button class="big" style="background:var(--c7-ok);color:#fff">Superato<span class="big__s">certificato da te, oggi</span></button>
  </div>
  <button class="undo">Interrompi senza esito</button>
</div>"""
    return phone(
        "Fondamentali &mdash; livello 1",
        "Sessione certificata &middot; tutte le prove fatte",
        content,
        nav=None,
        dock=dock,
        action=CLOSE,
        avatar="LU",
    )


# --------------------------------------------------------------------------
# 6 · Comporre un esame: lo stesso modulo della scheda
# --------------------------------------------------------------------------


def componi():
    def it(scene, nome, come, maxv, prove):
        def st(v, lab):
            return (
                f'<div style="text-align:center"><div class="stepper stepper--sm"><button aria-label="Meno">'
                f'{ico(I["minus"], 13, 2.6)}</button><span>{v}</span><button aria-label="Pi&ugrave;">'
                f'{ico(I["plus"], 13, 2.6)}</button></div><div class="item__s" style="margin-top:2px">{lab}</div></div>'
            )

        peso = (
            st(maxv, "vale")
            if maxv
            else '<span class="item__s" style="text-align:center">superato<br>o no</span>'
        )
        return (
            f'<div class="card" style="padding:10px 12px"><div class="item" style="padding:0;grid-template-columns:20px 64px 1fr">'
            f'{GRIP}<div class="item__thumb">{table(scene)}</div><div><div class="item__t">{nome}</div>'
            f'<div class="item__s">{come}</div></div></div>'
            f'<div class="row" style="margin-top:10px;justify-content:flex-end;gap:14px">{peso}{st(prove, "prove")}'
            f'<button class="iconbtn" style="width:48px;height:48px;color:var(--c7-err-ink);background:var(--c7-err-bg)" '
            f'aria-label="Togli">{ico(I["x"], 15)}</button></div></div>'
        )

    content = f"""
<div><div class="label" style="margin-bottom:8px">Nome</div>
  <div class="field field--filled">Fondamentali &mdash; livello 1</div></div>
<div class="row"><span class="label grow">Gli esercizi, in ordine</span>
  <span class="num" style="font-size:12px;color:var(--c7-ink-muted)">fino a 22 punti</span></div>
<div class="stack" style="gap:8px">
  {it(SPOT, "Spot Shot Rally", "nel catalogo vale 10", 10, 3)}
  {it(ELLE, "Serie da otto", "riuscito o no", None, 1)}
  {it(POSIZIONE, "Ferma nel cerchio", "nel catalogo vale 20", 12, 2)}
</div>
<button class="btn btn--secondary btn--w">{ico(I["search"], 16)}Aggiungi un esercizio dal catalogo</button>
<div class="label">Chi lo somministra</div>
<section class="rows">
  <div class="rows__row"><div class="avatar">LU</div><div class="grow"><div class="rows__title">Luca Bianchi</div><div class="rows__sub">tu</div></div></div>
  <div class="rows__row"><div class="avatar">AF</div><div class="grow"><div class="rows__title">Andrea Ferri</div><div class="rows__sub">aggiunto da te</div></div>
    <button class="iconbtn" style="width:48px;height:48px" aria-label="Togli">{ico(I["x"], 15)}</button></div>
</section>
<button class="btn btn--success btn--w">Salva l&rsquo;esame</button>"""
    return phone(
        "Componi l&rsquo;esame",
        "Trascina per cambiare l&rsquo;ordine",
        content,
        h=954,
        action=CLOSE,
        avatar="LU",
    )
