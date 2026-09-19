# -*- coding: utf-8 -*-
"""Genera le tre varianti della home dell'ospite.

Stessi identici contenuti in tutte e tre — quelli che `HomepageService`
produce davvero: la gara in diretta coi tavoli, le gare con iscrizioni
aperte, il campionato in corso con la testa della classifica, quella in
arrivo. Cambia una cosa sola, ed e' la domanda: **dove si chiede l'account**.

Una nota che vale per tutte e tre: qui il blocco dei campionati e' disegnato
in 7c. Nell'app e' l'unico pezzo rimasto a Bootstrap legacy (list-group,
alert, medaglie in emoji), e non e' in discussione: va rifatto comunque.
"""

import pathlib

OUT = pathlib.Path(__file__).parent


def head():
    return """  <header class="c7-head">
    <span class="c7-head__back"><svg viewBox="0 0 24 24" class="ico ico-lg"><use href="#i-nodes"></use></svg></span>
    <div class="c7-head__title">
      <span class="c7-title">Tornei Biliardo</span>
      <span class="c7-head__sub">Vista pubblica</span>
    </div>
    <span class="btn btn-secondary btn-sm btn-secondary--onpage">Login</span>
  </header>
"""


def sez(titolo, corpo, conteggio="", link="Tutte le gare", dot=False):
    d = '<span class="c7-live__dot"></span>' if dot else ""
    c = f' <span class="count">{conteggio}</span>' if conteggio else ""
    a = f'\n        <a href="#" style="font-size:12px">{link}</a>' if link else ""
    return f"""    <section class="sec">
      <div class="sec-head">{d}
        <h2>{titolo}{c}</h2>{a}
      </div>
{corpo}    </section>
"""


def screen(contenuto):
    return f"""<div class="screen screen--nonav">

{head()}
  <main class="c7-content">

{contenuto}
  </main>
</div>
"""


# ── I pezzi ──────────────────────────────────────────────────────────────────
ONBOARDING_FULL = """    <section class="c7-card c7-card--accent" style="padding:24px 20px">
      <div class="c7-kicker">Come si partecipa</div>
      <h2 style="margin:6px 0 0;color:inherit;font-size:22px">Iscriviti, gioca, scala la classifica</h2>
      <div style="display:grid;gap:14px;margin-top:20px">
        <div style="display:flex;gap:12px;align-items:flex-start">
          <span class="c7-num" style="color:var(--c7-accent-bright);width:20px">1</span>
          <span>
            <span style="display:block;font-weight:800;font-size:14px">Accedi</span>
            <span style="display:block;font-size:12px;color:var(--c7-accent-dim);margin-top:2px">Hai già un account? Entra. Altrimenti registrati, è gratis.</span>
          </span>
        </div>
        <div style="display:flex;gap:12px;align-items:flex-start">
          <span class="c7-num" style="color:var(--c7-accent-bright);width:20px">2</span>
          <span>
            <span style="display:block;font-weight:800;font-size:14px">Iscriviti a una gara</span>
            <span style="display:block;font-size:12px;color:var(--c7-accent-dim);margin-top:2px">Scegli fra le gare con iscrizioni aperte.</span>
          </span>
        </div>
        <div style="display:flex;gap:12px;align-items:flex-start">
          <span class="c7-num" style="color:var(--c7-accent-bright);width:20px">3</span>
          <span>
            <span style="display:block;font-weight:800;font-size:14px">Gioca</span>
            <span style="display:block;font-size:12px;color:var(--c7-accent-dim);margin-top:2px">Segna i triangoli dal telefono, la classifica si aggiorna da sola.</span>
          </span>
        </div>
      </div>
      <div style="display:flex;gap:10px;margin-top:22px">
        <span class="btn btn-bright btn-fill">Accedi</span>
        <span class="btn btn-ghost btn-fill">Registrati</span>
      </div>
    </section>
"""

ACCOUNT_STRIP = """    <section class="c7-card c7-card--accent" style="padding:20px">
      <div class="c7-kicker">Per iscriverti</div>
      <h2 style="margin:6px 0 0;color:inherit;font-size:20px">Serve un account. È gratis.</h2>
      <p style="margin-top:8px;font-size:13px;font-weight:600;color:var(--c7-accent-dim)">
        Poi ti iscrivi con un tocco, segni i triangoli dal telefono e la classifica si aggiorna da sola.
      </p>
      <div style="display:flex;gap:10px;margin-top:18px">
        <span class="btn btn-bright btn-fill">Registrati</span>
        <span class="btn btn-ghost btn-fill">Accedi</span>
      </div>
    </section>
"""

LIVE = """      <article class="c7-card c7-card--accent">
        <div class="rowtop">
          <div class="fill">
            <div class="c7-kicker">Campionato Sociale 2026</div>
            <h3 style="margin:4px 0 0">Gara 3 &mdash; Palla 8</h3>
          </div>
          <span class="c7-state c7-state--live">Live</span>
        </div>
        <div style="margin-top:12px;font-size:12px;font-weight:700;color:var(--c7-accent-dim)">
          Turno <span class="c7-num">3/5</span>
          <span class="c7-sep">&middot;</span> Biliardo Club Udine
          <span class="c7-sep">&middot;</span> <span class="c7-num">14</span> iscritti
        </div>
        <div style="margin-top:14px;padding-top:12px;border-top:1px solid rgba(255,255,255,.12)">
          <div class="c7-kicker">Ai tavoli adesso</div>
          <div style="display:flex;flex-direction:column;gap:7px;margin-top:8px">
            <div class="row" style="font-size:13px">
              <span class="c7-num" style="color:var(--c7-accent-dim)">T1</span>
              <span class="trunc">Elena Furlan <span class="c7-num">4&ndash;1</span> Sara De Rossi</span>
            </div>
            <div class="row" style="font-size:13px">
              <span class="c7-num" style="color:var(--c7-accent-dim)">T2</span>
              <span class="trunc">Andrea Zanin <span class="c7-num">2&ndash;2</span> Paolo Rizzo</span>
            </div>
            <div class="row" style="font-size:13px">
              <span class="c7-num" style="color:var(--c7-accent-dim)">T4</span>
              <span class="trunc">Marco Bassi <span class="c7-num">3&ndash;2</span> Luca Berti</span>
            </div>
          </div>
        </div>
        <span class="btn btn-bright btn-w" style="margin-top:16px">Segui la diretta</span>
      </article>
"""


def card_aperta(
    kicker, nome, meta, iscritti, pct, posti, posti_tono, chiusura, azione, nota=""
):
    k = f'<div class="c7-kicker">{kicker}</div>' if kicker else ""
    return f"""      <article class="c7-card cardstack">
        <div class="rowtop">
          <div class="fill">
            {k}
            <h3 style="margin:4px 0 0">{nome}</h3>
          </div>
          <span class="c7-state c7-state--{posti_tono}">{posti}</span>
        </div>
        <div class="meta">{meta}</div>
        <div>
          <div class="progress"><div class="progress-bar" style="width:{pct}%"></div></div>
          <div class="row" style="margin-top:7px;font-size:12px;font-weight:700">
            <span class="fill muted"><span class="c7-num">{iscritti}</span> iscritti</span>
            <span class="muted">chiudono il <span class="c7-num">{chiusura}</span></span>
          </div>
        </div>
{azione}{nota}      </article>
"""


CAMPIONATO = """      <article class="c7-card cardstack">
        <div class="rowtop">
          <div class="fill">
            <div class="cardtitle">Campionato Sociale 2026</div>
            <div class="meta">amalfi <span class="c7-sep">&middot;</span> 5 gare <span class="c7-sep">&middot;</span> prossima <span class="c7-num">12/09</span></div>
          </div>
          <span class="c7-state c7-state--err">In corso</span>
        </div>
        <div class="inset">
          <div class="c7-kicker">Classifica generale</div>
          <div class="c7-rows" style="margin-top:4px">
            <div class="c7-rows__row" style="border-color:var(--c7-line)">
              <span class="c7-pos c7-pos--1">1</span>
              <span class="fill trunc" style="font-size:13px;font-weight:800">Elena Furlan</span>
              <span class="c7-num muted" style="font-size:12px">7 vittorie</span>
            </div>
            <div class="c7-rows__row" style="border-color:var(--c7-line)">
              <span class="c7-pos c7-pos--2">2</span>
              <span class="fill trunc" style="font-size:13px;font-weight:800">Marco Bassi</span>
              <span class="c7-num muted" style="font-size:12px">6 vittorie</span>
            </div>
            <div class="c7-rows__row" style="border-color:var(--c7-line)">
              <span class="c7-pos c7-pos--3">3</span>
              <span class="fill trunc" style="font-size:13px;font-weight:800">Luca Berti</span>
              <span class="c7-num muted" style="font-size:12px">6 vittorie</span>
            </div>
          </div>
        </div>
        <span class="btn btn-secondary btn-sm btn-w">Classifica e risultati</span>
      </article>
"""

IN_ARRIVO = """      <div class="c7-card">
        <a class="listrow" href="#">
          <span class="fill">
            <span style="display:block;font-size:14px;font-weight:800">Gara 5 &mdash; Palla 8</span>
            <span class="meta"><span class="c7-num">03/10</span> <span class="c7-sep">&middot;</span> iscrizioni dal <span class="c7-num">20/09</span></span>
          </span>
          <span class="c7-state c7-state--muted">In preparazione</span>
        </a>
      </div>
"""

M4 = (
    '<span class="c7-num" style="color:var(--c7-ink)">12/09/2026</span> '
    '<span class="c7-sep">&middot;</span> Palla 9 '
    '<span class="c7-sep">&middot;</span> Biliardo Club Udine'
)
MT = (
    '<span class="c7-num" style="color:var(--c7-ink)">04/09/2026</span> '
    '<span class="c7-sep">&middot;</span> Palla 8 '
    '<span class="c7-sep">&middot;</span> Sala Da Vinci, Pordenone'
)

BTN_ACCEDI = (
    '        <span class="btn btn-success btn-w">Accedi per iscriverti</span>\n'
)
BTN_VEDI = '        <span class="btn btn-secondary btn-sm btn-w">Vedi la gara</span>\n'
BTN_ISCRIVITI = '        <span class="btn btn-success btn-w">Iscriviti</span>\n'
BTN_ATTESA = '        <span class="btn btn-warning btn-w">Mettiti in lista d\u2019attesa</span>\n'
NOTA_ACCOUNT = (
    '        <div class="meta" style="text-align:center;margin-top:-4px">'
    "Serve un account gratuito &mdash; ci vogliono 30 secondi</div>\n"
)


def aperte(azione, nota="", azione_piena=None):
    """La seconda gara e' al completo: li' l'azione e' entrare in lista."""
    return card_aperta(
        "Campionato Sociale 2026",
        "Gara 4 &mdash; Palla 9",
        M4,
        "18/24",
        75,
        "6 posti",
        "ok",
        "10/09",
        azione,
        nota,
    ) + card_aperta(
        "",
        "Torneo del Giovedì",
        MT,
        "24/24",
        100,
        "Lista d'attesa",
        "warn",
        "03/09",
        azione_piena or azione,
        nota,
    )


# ── Le tre varianti ──────────────────────────────────────────────────────────
# A — com'e' oggi: il pitch prima di tutto, e ogni gara ripete l'invito.
a = (
    ONBOARDING_FULL
    + sez("In diretta ora", LIVE, dot=True)
    + sez("Iscrizioni aperte", aperte(BTN_ACCEDI), "2")
    + sez("Campionati in corso", CAMPIONATO, "1", "Vedi tutti")
    + sez("In arrivo", IN_ARRIVO, "", None)
)

# B — prima cosa succede, l'account chiesto una volta sola e dopo averlo
#     motivato. Sulle card il comando e' «guarda», non «accedi».
b = (
    sez("In diretta ora", LIVE, dot=True)
    + sez("Iscrizioni aperte", aperte(BTN_VEDI), "2")
    + ACCOUNT_STRIP
    + sez("Campionati in corso", CAMPIONATO, "1", "Vedi tutti")
    + sez("In arrivo", IN_ARRIVO, "", None)
)

# C — nessun blocco dedicato all'account: il comando resta «Iscriviti», e la
#     riga sotto dice cosa serve. Si chiede dove serve, non prima.
c = (
    sez("In diretta ora", LIVE, dot=True)
    + sez("Iscrizioni aperte", aperte(BTN_ISCRIVITI, NOTA_ACCOUNT, BTN_ATTESA), "2")
    + sez("Campionati in corso", CAMPIONATO, "1", "Vedi tutti")
    + sez("In arrivo", IN_ARRIVO, "", None)
)


if __name__ == "__main__":
    for nome, corpo in [("OspiteA", a), ("OspiteB", b), ("OspiteC", c)]:
        (OUT / f"{nome}.body").write_text(screen(corpo), encoding="utf-8")
        (OUT / f"{nome}.css").write_text(
            ".screen--nonav{padding-bottom:28px}\n", encoding="utf-8"
        )
        print("scritto", nome)
