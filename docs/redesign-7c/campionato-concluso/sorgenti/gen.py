"""Artboard della vetrina di un campionato concluso.

I pezzi sono definiti una volta sola e ricomposti: le schermate portano gli
stessi identici dati, cambia solo dove sta il campione. Valori presi da
`static/css/tokens-7c.css` e dalla sezione `.c7-vt__*` di `theme-7c.css`
(le regole desktop dal blocco `min-width: 992px`); il podio a posti da
`.c7-podio-finale`, i chip delle medaglie da `.c7-pos`.

Scelta dell'utente il 2026-09-14: la A, il campione sulla targa. La A e'
`Main.dc.html`; B, C e la pagina di oggi restano come alternative.

    python docs/redesign-7c/campionato-concluso/sorgenti/gen_pagine.py
"""

from pathlib import Path

OUT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------- i dati
CAMPIONATO = "Campionato Sociale 2026"
PERIODO = "giu – nov 2026"
# Gli username, come li mostra l'app: le stesse persone in tutte le pagine.
GARE = [
    ("14", "giu", "Gara 1", "m.rossi"),
    ("19", "lug", "Gara 2", "a.verdi"),
    ("13", "set", "Gara 3", "e.furlan"),
    ("17", "ott", "Gara 4", "m.rossi"),
    ("14", "nov", "Gara 5", "p.neri"),
    ("28", "nov", "Finale playoff", "a.verdi"),
]
CLASSIFICA = [
    ("m.rossi", 21),
    ("a.verdi", 20),
    ("p.neri", 17),
    ("e.furlan", 15),
    ("g.ferri", 12),
    ("d.conti", 11),
    ("l.berti", 9),
    ("s.moro", 7),
]
GIOCATORI = 18


def iniziali(nome):
    return (nome[0] + nome[2]).upper()


# ---------------------------------------------------------------- lo stile
CSS = """
:root{
  --c7-bg:#E4E8E7; --c7-card:#F5F7F6; --c7-sunken:#ECEEED;
  --c7-ink:#1B2124; --c7-ink-soft:#3D474A; --c7-ink-muted:#6B7679; --c7-ink-faint:#9AA3A6;
  --c7-on-ink:#F2F5F4; --c7-on-ink-muted:#9AA6A9;
  --c7-line:#D3D8D7; --c7-line-soft:#E4E8E7;
  --c7-accent:#2C4A52; --c7-accent-ink:#F2F8F7; --c7-accent-bright:#8FCDE8; --c7-accent-dim:#A9C4C7;
  --c7-ok-bg:#E4EDE9; --c7-ok-ink:#1D5F4A; --c7-ok:#2C8A6B;
  --c7-oro:#C9A84C; --c7-oro-ink:#4A3A0E; --c7-argento:#B4BDBF; --c7-argento-ink:#39434B;
  --c7-bronzo:#B98A5E; --c7-bronzo-ink:#4A2F16;
  --c7-font:"Manrope",system-ui,-apple-system,"Segoe UI",sans-serif;
  --c7-font-mono:"JetBrains Mono",ui-monospace,"SFMono-Regular",monospace;
  --c7-r-pill:999px; --c7-r-card:22px; --c7-r-card-lg:26px; --c7-r-field:18px;
  --c7-gutter:18px;
}
*{box-sizing:border-box}
body{margin:0;background:var(--c7-bg);color:var(--c7-ink);font-family:var(--c7-font);
  font-weight:600;font-size:14px;line-height:1.5;text-wrap:pretty;-webkit-font-smoothing:antialiased}
h1,h2,h3{font-weight:800;letter-spacing:-.025em;color:var(--c7-ink);margin:0}
a{color:var(--c7-accent);text-decoration:none}
a:hover{color:var(--c7-ink)}
p{margin:0}
.ic{width:16px;height:16px;stroke:currentColor;fill:none;stroke-width:1.9;stroke-linecap:round;stroke-linejoin:round;flex-shrink:0}
.mono{font-family:var(--c7-font-mono);font-variant-numeric:tabular-nums}
.page{min-height:100%;background:var(--c7-bg);padding-bottom:40px}
.top{display:flex;align-items:center;justify-content:space-between;padding:14px var(--c7-gutter);position:relative;z-index:2}
.wordmark{font-size:12px;font-weight:800;letter-spacing:.14em;text-transform:uppercase;color:var(--c7-ink-muted)}
.iconbtn{width:46px;height:46px;border:0;border-radius:50%;background:var(--c7-card);color:var(--c7-ink-soft);display:grid;place-items:center}
.hero{margin-top:-58px}
.hero img{display:block;width:100%;height:205px;object-fit:cover}
.plate{position:relative;margin:-34px var(--c7-gutter) 0;background:var(--c7-ink);color:var(--c7-on-ink);border-radius:var(--c7-r-card-lg);padding:20px}
.ovr{font-size:10px;font-weight:800;letter-spacing:.12em;text-transform:uppercase;color:var(--c7-accent-bright)}
.plate h1{font-size:31px;line-height:1.08;color:var(--c7-on-ink);margin-top:8px}
.when{display:flex;align-items:center;gap:8px;margin-top:14px;color:var(--c7-on-ink-muted);font-size:13px;font-weight:700}
.when .mono{color:var(--c7-on-ink);font-weight:700}
.badge{margin-top:16px;display:inline-flex;align-items:center;height:28px;padding:0 12px;border-radius:var(--c7-r-pill);
  font-size:10px;font-weight:800;letter-spacing:.06em;text-transform:uppercase;background:rgba(255,255,255,.14);color:var(--c7-on-ink)}
.body{padding:0 var(--c7-gutter)}
.facts{margin:26px 0 0}
.fact{display:flex;align-items:baseline;justify-content:space-between;gap:16px;padding:13px 0;border-bottom:1px solid var(--c7-line)}
.fact:first-child{border-top:1px solid var(--c7-line)}
.fact dt{display:flex;align-items:center;gap:7px;font-size:10px;font-weight:800;letter-spacing:.12em;text-transform:uppercase;color:var(--c7-ink-muted);flex-shrink:0}
.fact dd{margin:0;text-align:right;font-size:15px;font-weight:800;letter-spacing:-.02em}
.fact dd small{display:block;font-size:12px;font-weight:600;color:var(--c7-ink-muted);letter-spacing:0;margin-top:1px}
.sec{margin-top:28px}
.sech{display:flex;align-items:baseline;justify-content:space-between;gap:12px;margin-bottom:12px}
.sech h2{font-size:17px;letter-spacing:-.02em}
.sech span{font-size:10px;font-weight:800;letter-spacing:.12em;text-transform:uppercase;color:var(--c7-ink-muted)}
.leg{display:flex;align-items:center;gap:13px;margin-bottom:8px;padding:13px 14px;border-radius:var(--c7-r-field);background:var(--c7-card);color:var(--c7-ink)}
.legd{width:48px;flex-shrink:0;text-align:center;line-height:1.05;font-family:var(--c7-font-mono);font-variant-numeric:tabular-nums}
.legd b{display:block;font-size:19px;font-weight:800;letter-spacing:-.04em}
.legd span{font-size:10px;font-weight:700;text-transform:uppercase;color:var(--c7-ink-muted)}
.legb{flex:1;min-width:0}
.legb b{display:block;font-size:14px;font-weight:800;letter-spacing:-.02em}
.legb span{font-size:12px;font-weight:600;color:var(--c7-ink-muted)}
.legs{flex-shrink:0;font-size:10px;font-weight:800;letter-spacing:.06em;text-transform:uppercase;color:var(--c7-ok-ink);background:var(--c7-ok-bg);border-radius:var(--c7-r-pill);padding:5px 10px}
.std{border-radius:var(--c7-r-card);background:var(--c7-card);overflow:hidden}
.stdr{display:flex;align-items:center;gap:12px;padding:12px 16px;border-bottom:1px solid var(--c7-line-soft)}
.stdr:last-child{border-bottom:0}
.stdp{width:20px;flex-shrink:0;font-family:var(--c7-font-mono);font-weight:800;font-size:14px;color:var(--c7-ink-muted)}
.stdr--podio .stdp{color:var(--c7-accent)}
.stdn{flex:1;min-width:0;font-size:14px;font-weight:800;letter-spacing:-.02em}
.stdv{font-family:var(--c7-font-mono);font-variant-numeric:tabular-nums;font-weight:800;font-size:15px}
.stdv small{font-weight:600;font-size:11px;color:var(--c7-ink-muted)}
.panel{margin-top:28px;background:var(--c7-card);border-radius:var(--c7-r-card);padding:16px}
.kicker{font-size:10px;font-weight:800;letter-spacing:.12em;text-transform:uppercase;color:var(--c7-ink-muted)}
.out{margin-top:12px;display:flex;align-items:center;justify-content:center;gap:9px;height:56px;border:1.5px solid var(--c7-line);border-radius:var(--c7-r-field);font-size:15px;font-weight:800;color:var(--c7-ink)}
.who{margin-top:22px;display:flex;align-items:center;gap:8px;color:var(--c7-ink-muted);font-size:12px;font-weight:700}
.who b{color:var(--c7-ink-soft)}
/* chip di posizione (.c7-pos) e medaglie */
.pos{width:24px;height:24px;border-radius:8px;background:var(--c7-bg);display:grid;place-items:center;font-family:var(--c7-font-mono);font-size:11px;font-weight:800;color:var(--c7-ink-muted);flex-shrink:0}
.pos--lg{width:30px;height:30px;border-radius:10px;font-size:13px}
.pos--1,.av.av--oro{background:var(--c7-oro);color:var(--c7-oro-ink)}
.pos--2,.av.av--argento{background:var(--c7-argento);color:var(--c7-argento-ink)}
.pos--3,.av.av--bronzo{background:var(--c7-bronzo);color:var(--c7-bronzo-ink)}
.av{width:34px;height:34px;border-radius:50%;background:var(--c7-accent);color:#fff;display:grid;place-items:center;font-size:12px;font-weight:800;flex-shrink:0}
/* A · il campione sulla targa */
.champ{margin-top:18px;padding-top:16px;border-top:1px solid rgba(255,255,255,.14);display:flex;align-items:center;gap:13px}
.champ__av{width:52px;height:52px;font-size:15px}
.champ__nome{margin-top:3px;font-size:22px;font-weight:800;letter-spacing:-.03em;line-height:1.1;color:var(--c7-on-ink)}
.champ__podio{margin-top:14px;display:flex;flex-wrap:wrap;gap:8px 18px}
.champ__alt{display:inline-flex;align-items:center;gap:8px;font-size:13px;font-weight:700;color:var(--c7-on-ink-muted)}
"""

# Il blocco `min-width: 992px` della vetrina: senza barra laterale,
# impaginazione centrata su 1160px, colonna a destra da 392px che resta ferma.
CSS_DESKTOP = """
.dpage{padding-bottom:64px}
.dbar{max-width:1160px;margin:0 auto;padding:20px 28px;display:flex;align-items:center;justify-content:space-between}
.dbar .wordmark{font-size:13px}
.dshell{max-width:1160px;margin:0 auto;padding:0 28px;display:grid;grid-template-columns:minmax(0,1fr) 392px;gap:40px;align-items:start}
.dhero img{display:block;width:100%;aspect-ratio:1200/630;object-fit:cover;border-radius:var(--c7-r-card-lg)}
.dpage .plate{margin:-46px 0 0;padding:32px 34px}
.dpage .ovr,.dpage .sech span{font-size:11px}
.dpage .plate h1{font-size:44px;line-height:1.04;letter-spacing:-.035em}
.dpage .when{font-size:15px;margin-top:20px}
.dpage .champ{margin-top:24px;padding-top:22px;gap:16px}
.dpage .champ__av{width:64px;height:64px;font-size:18px}
.dpage .champ__nome{font-size:30px}
.dpage .champ__podio{gap:10px 26px}
.dpage .champ__alt{font-size:15px}
.dpage .facts{margin-top:34px}
.dpage .fact{padding:16px 4px}
.dpage .fact dt{font-size:11px}
.dpage .fact dd{font-size:17px}
.dpage .fact dd small{font-size:13px}
.dpage .sec{margin-top:36px}
.dpage .sech h2{font-size:21px}
.dpage .leg{padding:16px 20px;gap:18px;border-radius:var(--c7-r-card)}
.dpage .legd{width:58px}
.dpage .legd b{font-size:23px}
.dpage .legb b{font-size:16px}
.dpage .legb span{font-size:13px}
.dpage .legs{font-size:11px}
.drail{position:sticky;top:24px}
.drail .sec:first-child{margin-top:0}
.dpage .out{height:auto;min-height:60px;padding:0 22px;border-radius:var(--c7-r-card)}
.dpage .who{margin-top:20px;font-size:13px}
"""

ICONS = """<svg style="display:none" aria-hidden="true">
  <symbol id="i-cal" viewBox="0 0 24 24"><rect x="3" y="5" width="18" height="16" rx="3"/><path d="M8 3v4M16 3v4M3 10h18"/></symbol>
  <symbol id="i-cup" viewBox="0 0 24 24"><path d="M7 4h10v5a5 5 0 0 1-10 0z"/><path d="M17 5h3v2a3 3 0 0 1-3 3M7 5H4v2a3 3 0 0 0 3 3"/><path d="M12 14v4M9 21h6"/></symbol>
  <symbol id="i-pin" viewBox="0 0 24 24"><path d="M12 21s7-6.2 7-11a7 7 0 1 0-14 0c0 4.8 7 11 7 11z"/><circle cx="12" cy="10" r="2.6"/></symbol>
  <symbol id="i-user" viewBox="0 0 24 24"><circle cx="12" cy="8" r="3.5"/><path d="M5 20a7 7 0 0 1 14 0"/></symbol>
  <symbol id="i-share" viewBox="0 0 24 24"><circle cx="18" cy="5" r="2.6"/><circle cx="6" cy="12" r="2.6"/><circle cx="18" cy="19" r="2.6"/><path d="M8.3 10.8l7.4-4.3M8.3 13.2l7.4 4.3"/></symbol>
  <symbol id="i-org" viewBox="0 0 24 24"><circle cx="12" cy="8" r="3.5"/><path d="M5 20a7 7 0 0 1 14 0"/></symbol>
</svg>"""

TESTATA_TELEFONO = """  <div class="top">
    <span class="wordmark">Tornei Biliardo</span>
    <span class="iconbtn"><svg class="ic"><use href="#i-share"/></svg></span>
  </div>
  <div class="hero"><img src="locandina.png" alt="Locandina del campionato"></div>"""


def documento(corpo, css_extra="", telefono=True):
    testata = TESTATA_TELEFONO if telefono else ""
    classe = "page" if telefono else "page dpage"
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <script src="./support.js"></script>
</head>
<body>
<x-dc>
<helmet>
  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Manrope:wght@600;700;800&family=JetBrains+Mono:wght@500;700;800&display=swap">
  <style>{CSS}{css_extra}
  </style>
</helmet>
{ICONS}
<div class="{classe}">
{testata}
{corpo}
</div>
</x-dc>
</body>
</html>
"""


# ---------------------------------------------------------------- i pezzi
def targa(ovr="Campionato", badge=True, dentro="", conteggio="5 gare + finale"):
    b = '\n    <span class="badge">Campionato concluso</span>' if badge else ""
    return f"""  <div class="plate">
    <div class="ovr">{ovr}</div>
    <h1>{CAMPIONATO}</h1>
    <div class="when"><svg class="ic"><use href="#i-cal"/></svg><span class="mono">{PERIODO}</span><span>·</span><span>{conteggio}</span></div>{b}{dentro}
  </div>"""


def fatti():
    return f"""    <dl class="facts">
      <div class="fact"><dt><svg class="ic"><use href="#i-pin"/></svg>Dove</dt><dd>Sala Centrale<small>Udine</small></dd></div>
      <div class="fact"><dt><svg class="ic"><use href="#i-cup"/></svg>Formula</dt><dd>Classifica a vittorie</dd></div>
      <div class="fact"><dt><svg class="ic"><use href="#i-user"/></svg>Giocatori</dt><dd class="mono">{GIOCATORI}</dd></div>
    </dl>"""


def gare(sotto="tutte giocate"):
    righe = "\n".join(
        f"""      <div class="leg"><div class="legd"><b>{g}</b><span>{m}</span></div>
        <div class="legb"><b>{nome}</b><span>Vince {chi}</span></div><span class="legs">Conclusa</span></div>"""
        for g, m, nome, chi in GARE
    )
    n = len(GARE)
    return f"""    <div class="sec">
      <div class="sech"><h2>Le gare</h2><span>{sotto}</span></div>
{righe}
    </div>"""


def classifica(titolo, sotto):
    righe = "\n".join(
        f"""        <div class="stdr{' stdr--podio' if i <= 3 else ''}"><span class="stdp">{i}</span><span class="stdn">{nome}</span><span class="stdv">{v} <small>V</small></span></div>"""
        for i, (nome, v) in enumerate(CLASSIFICA, 1)
    )
    return f"""    <div class="sec">
      <div class="sech"><h2>{titolo}</h2><span>{sotto}</span></div>
      <div class="std">
{righe}
      </div>
    </div>"""


def classifica_medaglie():
    """Variante C: i primi tre con i chip delle medaglie, il primo annunciato."""
    righe = []
    for i, (nome, v) in enumerate(CLASSIFICA, 1):
        if i == 1:
            righe.append(
                f"""        <div class="stdr stdr--campione"><span class="pos pos--lg pos--1">1</span>
          <span class="stdn"><span class="kicker" style="display:block;color:var(--c7-oro-ink)">Campione</span><span class="nome1">{nome}</span></span>
          <span class="stdv">{v} <small>V</small></span></div>"""
            )
        else:
            medaglia = f" pos--{i}" if i <= 3 else ""
            righe.append(
                f"""        <div class="stdr"><span class="pos{medaglia}">{i}</span><span class="stdn">{nome}</span><span class="stdv">{v} <small>V</small></span></div>"""
            )
    corpo = "\n".join(righe)
    return f"""    <div class="sec" style="margin-top:22px">
      <div class="sech"><h2>Classifica finale</h2><span>definitiva</span></div>
      <div class="std">
{corpo}
      </div>
    </div>"""


def podio_gradini():
    """Il podio della gara conclusa (`direttore/_podio.html`): 2° · 1° · 3°."""
    ordine = [(1, "argento"), (0, "oro"), (2, "bronzo")]
    posti = []
    for i, metallo in ordine:
        nome = CLASSIFICA[i][0]
        posti.append(
            f"""        <div class="pf__posto pf__posto--{metallo}">
          <span class="av pf__av av--{metallo}">{iniziali(nome)}</span>
          <div class="pf__nome">{nome}</div>
          <div class="pf__pos mono">{i + 1}°</div>
        </div>"""
        )
    return '      <div class="pf">\n' + "\n".join(posti) + "\n      </div>"


def campione_sulla_targa():
    """A: dentro la targa, sotto il titolo. Secondo e terzo in una riga."""
    campione, secondo, terzo = (c[0] for c in CLASSIFICA[:3])
    return f"""
    <div class="champ">
      <span class="av av--oro champ__av">{iniziali(campione)}</span>
      <div style="min-width:0">
        <div class="ovr" style="color:var(--c7-oro)">Campione</div>
        <div class="champ__nome">{campione}</div>
      </div>
    </div>
    <div class="champ__podio">
      <span class="champ__alt"><span class="pos pos--2">2</span>{secondo}</span>
      <span class="champ__alt"><span class="pos pos--3">3</span>{terzo}</span>
    </div>"""


def chiusura():
    return """    <a class="out" href="#" style="margin-top:28px"><svg class="ic"><use href="#i-share"/></svg>Condividi il campionato</a>
    <div class="who"><svg class="ic"><use href="#i-org"/></svg><span>Organizza <b>pa</b></span></div>"""


# ---------------------------------------------------------------- le schermate
def oggi():
    corpo = f"""{targa(conteggio="6 gare")}
  <div class="body">
{fatti()}
{gare(sotto="6 di 6 giocate")}
{classifica("Classifica", f"dopo {len(GARE)} gare")}
    <div class="panel">
      <div class="kicker">Iscrizioni</div>
      <p style="margin-top:8px;font-size:13px;color:var(--c7-ink-soft)">Nessuna gara ha le iscrizioni aperte in questo momento. Condividi la pagina o torna a controllare: il calendario è qui sopra.</p>
      <a class="out" href="#"><svg class="ic"><use href="#i-share"/></svg>Condividi il campionato</a>
    </div>
    <div class="who"><svg class="ic"><use href="#i-org"/></svg><span>Organizza <b>pa</b></span></div>
  </div>"""
    return documento(corpo)


def variante_a():
    corpo = f"""{targa(ovr="Campionato concluso", badge=False, dentro=campione_sulla_targa())}
  <div class="body">
{fatti()}
{classifica("Classifica finale", "definitiva")}
{gare()}
{chiusura()}
  </div>"""
    return documento(corpo)


def variante_a_desktop():
    """A su desktop: la colonna di destra, che oggi ha solo le iscrizioni,
    prende la classifica finale; sul telefono la stessa sta prima delle gare."""
    corpo = f"""  <div class="dbar">
    <span class="wordmark">Tornei Biliardo</span>
    <span class="iconbtn"><svg class="ic"><use href="#i-share"/></svg></span>
  </div>
  <div class="dshell">
    <div class="dcol">
      <div class="dhero"><img src="locandina.png" alt="Locandina del campionato"></div>
{targa(ovr="Campionato concluso", badge=False, dentro=campione_sulla_targa())}
{fatti()}
{gare()}
    </div>
    <div class="drail">
{classifica("Classifica finale", "definitiva")}
{chiusura()}
    </div>
  </div>"""
    return documento(corpo, CSS_DESKTOP, telefono=False)


def variante_b():
    campione = CLASSIFICA[0][0]
    css = """
.fascia{margin:14px var(--c7-gutter) 0;background:var(--c7-accent);color:var(--c7-accent-ink);border-radius:var(--c7-r-card);padding:16px}
.fascia .kicker{color:var(--c7-accent-dim)}
.fascia__titolo{margin-top:5px;font-size:19px;font-weight:800;letter-spacing:-.025em;color:inherit}
.pf{margin-top:18px;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;align-items:end}
.pf__posto{text-align:center;min-width:0}
.pf__av{width:46px;height:46px;font-size:14px;margin:0 auto}
.pf__posto--oro .pf__av{width:56px;height:56px;font-size:16px}
.pf__nome{margin-top:8px;font-size:15px;font-weight:800;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.pf__posto--oro .pf__nome{font-size:17px}
.pf__pos{font-size:12px;font-weight:800}
.pf__posto--oro .pf__pos{color:var(--c7-oro)}
.pf__posto--argento .pf__pos{color:var(--c7-argento)}
.pf__posto--bronzo .pf__pos{color:var(--c7-bronzo)}
"""
    corpo = f"""{targa(badge=False)}
  <section class="fascia">
    <div class="kicker">Campionato concluso</div>
    <h3 class="fascia__titolo">Campione {campione}</h3>
{podio_gradini()}
  </section>
  <div class="body">
{fatti()}
{classifica("Classifica finale", "definitiva")}
{gare()}
{chiusura()}
  </div>"""
    return documento(corpo, css)


def variante_c():
    css = """
.stdr--campione{padding:14px 16px}
.nome1{display:block;margin-top:2px;font-size:18px;font-weight:800;letter-spacing:-.03em;line-height:1.15}
.stdr--campione .stdv{font-size:17px}
"""
    corpo = f"""{targa()}
  <div class="body">
{classifica_medaglie()}
{fatti()}
{gare()}
{chiusura()}
  </div>"""
    return documento(corpo, css)


SCHERMATE = [
    ("Main", variante_a),
    ("VetrinaDesktop", variante_a_desktop),
    ("Oggi", oggi),
    ("ComeFinita", variante_b),
    ("Classifica", variante_c),
]


def scrivi():
    for nome, fn in SCHERMATE:
        (OUT / f"{nome}.dc.html").write_text(fn(), encoding="utf-8")
    return [f"{nome}.dc.html" for nome, _ in SCHERMATE]


if __name__ == "__main__":
    print("\n".join(scrivi()))
