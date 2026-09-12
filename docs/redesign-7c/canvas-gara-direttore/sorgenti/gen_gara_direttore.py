#!/usr/bin/env python3
"""Genera gli artboard .dc.html del canvas «Pagina gara del direttore».

Sei artboard: tre direzioni (Regia · Console · Fasi) per due viewport
(telefono 390x844, desktop 1440x900), piu' canvas.json con la disposizione.

I valori (colori, raggi, altezze, tipografia) sono copiati **alla lettera** da
static/css/tokens-7c.css e static/css/theme-7c.css: il canvas deve somigliare
all'app, non a un'idea dell'app.
"""

import json
import pathlib

OUT = pathlib.Path(__file__).resolve().parent.parent
SRC = pathlib.Path(__file__).resolve().parent

# --------------------------------------------------------------------------
# CSS condiviso — token 7c verbatim + le classi che servono agli artboard
# --------------------------------------------------------------------------

CSS = """
:root{
  --c7-bg:#E4E8E7; --c7-card:#F5F7F6; --c7-sunken:#ECEEED;
  --c7-ink:#1B2124; --c7-ink-soft:#3D474A; --c7-ink-muted:#6B7679; --c7-ink-faint:#9AA3A6;
  --c7-on-ink:#F2F5F4; --c7-on-ink-muted:#9AA6A9;
  --c7-line:#D3D8D7; --c7-line-soft:#E4E8E7;
  --c7-accent:#2C4A52; --c7-accent-ink:#F2F8F7; --c7-accent-bright:#8FCDE8;
  --c7-accent-dim:#A9C4C7; --c7-accent-tint:#DDE9EE; --c7-accent-tint-ink:#23404A;
  --c7-ok-bg:#E4EDE9; --c7-ok-ink:#1D5F4A; --c7-ok-body:#37665A; --c7-ok:#2C8A6B;
  --c7-err-bg:#F3E2E0; --c7-err-ink:#8A2C2C; --c7-err-body:#7A4A48; --c7-err:#B23B3B;
  --c7-warn-bg:#F0E9D8; --c7-warn-ink:#6E5417; --c7-warn-body:#6E6047; --c7-warn:#8A6A1F;
  --c7-oro:#C9A84C; --c7-oro-ink:#4A3A0E; --c7-argento:#B4BDBF; --c7-argento-ink:#39434B;
  --c7-bronzo:#B98A5E; --c7-bronzo-ink:#4A2F16;
  --c7-font:"Manrope",system-ui,-apple-system,"Segoe UI",sans-serif;
  --c7-font-mono:"JetBrains Mono",ui-monospace,"SFMono-Regular",monospace;
  --c7-r-pill:999px; --c7-r-card:22px; --c7-r-card-lg:26px; --c7-r-field:18px;
  --c7-r-control:14px; --c7-r-chip:12px;
  --c7-gutter:18px; --c7-gutter-lg:28px; --c7-pad-card:16px; --c7-pad-card-lg:20px;
  --c7-gap:12px; --c7-gap-lg:16px;
  --c7-touch:48px; --c7-field-h:58px; --c7-btn-h:56px; --c7-side-w:244px;
  --c7-shadow-pop:0 18px 36px -20px rgba(27,33,36,.75);
}
*{box-sizing:border-box}
body{margin:0;background:var(--c7-bg);color:var(--c7-ink);font-family:var(--c7-font);
     font-weight:600;font-size:14px;line-height:1.5;-webkit-font-smoothing:antialiased;
     text-wrap:pretty}
h1,h2,h3,h4,h5{margin:0;font-weight:800;letter-spacing:-.025em;color:var(--c7-ink)}
h3{font-size:17px;letter-spacing:-.02em}
h4{font-size:15px;letter-spacing:-.02em}
p{margin:0}
a{color:var(--c7-accent);text-decoration:none;font-weight:700}
a:hover{color:var(--c7-ink)}
svg{display:block}
.num{font-family:var(--c7-font-mono);font-weight:700;letter-spacing:-.02em;
     font-variant-numeric:tabular-nums}
.num-lg{font-family:var(--c7-font-mono);font-weight:800;font-size:26px;letter-spacing:-.03em}
.num-xl{font-family:var(--c7-font-mono);font-weight:800;font-size:32px;letter-spacing:-.04em}
.kicker{font-size:10px;font-weight:800;letter-spacing:.12em;text-transform:uppercase;
        color:var(--c7-ink-muted)}
.label{font-size:12px;font-weight:800;letter-spacing:.06em;text-transform:uppercase;
       color:var(--c7-ink-muted)}
.muted{color:var(--c7-ink-muted)}
.faint{color:var(--c7-ink-faint)}
.stack{display:flex;flex-direction:column;gap:var(--c7-gap)}
.row{display:flex;align-items:center;gap:10px}
.grow{flex:1;min-width:0}

/* --- card ------------------------------------------------------------- */
.card{background:var(--c7-card);border:0;border-radius:var(--c7-r-card);
      padding:var(--c7-pad-card)}
.card--accent{background:var(--c7-accent);color:var(--c7-accent-ink)}
.card--accent .kicker{color:var(--c7-accent-dim)}
.card--accent h3,.card--accent h4{color:inherit}
.card--locked{background:var(--c7-sunken);color:var(--c7-ink-muted)}
.card--ok{background:var(--c7-ok-bg);color:var(--c7-ok-ink)}
.card--warn{background:var(--c7-warn-bg);color:var(--c7-warn-ink)}
.card--sunk{background:var(--c7-bg)}

/* --- pill / stato ----------------------------------------------------- */
.pill{height:38px;padding:0 16px;border-radius:var(--c7-r-pill);background:var(--c7-card);
      color:var(--c7-ink-muted);font-size:13px;font-weight:700;display:inline-flex;
      align-items:center;gap:8px;white-space:nowrap;border:0;flex-shrink:0}
.pill.is-active{background:var(--c7-ink);color:#fff;font-weight:800}
.state{height:26px;padding:0 11px;border-radius:var(--c7-r-pill);font-size:10px;
       font-weight:800;letter-spacing:.04em;text-transform:uppercase;
       display:inline-flex;align-items:center;justify-content:center;white-space:nowrap}
.state--ok{background:var(--c7-ok-bg);color:var(--c7-ok-ink)}
.state--warn{background:var(--c7-warn-bg);color:var(--c7-warn-ink)}
.state--err{background:var(--c7-err-bg);color:var(--c7-err-ink)}
.state--info{background:var(--c7-accent-tint);color:var(--c7-accent-tint-ink)}
.state--accent{background:var(--c7-accent);color:var(--c7-accent-ink)}
.state--muted{background:var(--c7-bg);color:var(--c7-ink-muted)}
.state--onaccent{background:rgba(242,248,247,.14);color:var(--c7-accent-bright)}

/* --- bottoni ---------------------------------------------------------- */
.btn{height:var(--c7-btn-h);border:0;border-radius:var(--c7-r-field);padding:0 20px;
     font-family:inherit;font-size:15px;font-weight:800;display:inline-flex;
     align-items:center;justify-content:center;gap:9px;white-space:nowrap}
.btn--primary{background:var(--c7-ink);color:#fff}
.btn--secondary{background:var(--c7-bg);color:var(--c7-ink-soft);font-weight:700}
.btn--success{background:var(--c7-ok);color:#fff}
.btn--warn{background:var(--c7-warn-bg);color:var(--c7-warn-ink)}
.btn--danger{background:var(--c7-err-bg);color:var(--c7-err-ink)}
.btn--bright{background:var(--c7-accent-bright);color:#0D2A36}
.btn--locked{background:var(--c7-sunken);color:var(--c7-ink-faint)}
.card--accent .btn--locked{background:rgba(242,248,247,.12);color:var(--c7-accent-dim)}
.btn--sm{height:40px;border-radius:var(--c7-r-chip);padding:0 15px;font-size:13px}
.btn--w{width:100%}
.iconbtn{width:34px;height:34px;border:0;border-radius:10px;background:var(--c7-bg);
         color:var(--c7-ink-soft);display:grid;place-items:center}

/* --- elenchi raggruppati / titoli / tessere --------------------------- */
.rows{background:var(--c7-card);border-radius:var(--c7-r-card-lg);overflow:hidden}
.rows__row{padding:15px 18px;display:flex;align-items:center;gap:12px}
.rows__row + .rows__row{border-top:1px solid var(--c7-line-soft)}
.rows__title{font-size:14px;font-weight:800}
.rows__sub{margin-top:2px;font-size:11px;font-weight:700;color:var(--c7-ink-muted)}
.sechead{display:flex;align-items:baseline;gap:10px}
.sechead h3{margin:0}
.sechead__more{margin-left:auto;font-size:13px;font-weight:700;color:var(--c7-accent)}
.tile{width:44px;height:44px;border-radius:var(--c7-r-control);background:var(--c7-accent);
      color:var(--c7-accent-bright);display:grid;place-items:center;flex-shrink:0}
.tile--sm{width:40px;height:40px;border-radius:var(--c7-r-chip)}
.tile--locked{background:var(--c7-bg);color:var(--c7-ink-faint)}
.tile--warn{background:var(--c7-warn-bg);color:var(--c7-warn)}
.tile--neutral{background:var(--c7-bg);color:var(--c7-ink-soft)}
.tile--ok{background:var(--c7-ok-bg);color:var(--c7-ok)}
.divider{height:1px;background:var(--c7-line-soft);border:0;margin:14px 0}
.avatar{width:34px;height:34px;border-radius:50%;background:var(--c7-accent);color:#fff;
        display:grid;place-items:center;font-size:11px;font-weight:800;flex-shrink:0}
.avatar--lg{width:46px;height:46px;font-size:14px}
.pos{width:26px;height:26px;border-radius:50%;display:grid;place-items:center;font-size:12px;
     font-weight:800;background:var(--c7-bg);color:var(--c7-ink);flex-shrink:0}
.pos--1{background:var(--c7-oro);color:var(--c7-oro-ink)}
.pos--2{background:var(--c7-argento);color:var(--c7-argento-ink)}
.pos--3{background:var(--c7-bronzo);color:var(--c7-bronzo-ink)}

/* --- barra di progresso ----------------------------------------------- */
.bar{height:8px;border-radius:999px;background:var(--c7-line);overflow:hidden}
.bar__fill{height:100%;background:var(--c7-accent)}
.card--accent .bar{background:rgba(242,248,247,.18)}
.card--accent .bar__fill{background:var(--c7-accent-bright)}

/* --- flash ------------------------------------------------------------ */
.flash{border-radius:var(--c7-r-field);padding:15px 16px;display:flex;gap:13px;
       align-items:flex-start;font-size:13px;font-weight:600;line-height:1.45}
.flash__ico{width:30px;height:30px;border-radius:50%;color:#fff;display:grid;
            place-items:center;flex-shrink:0}
.flash__title{font-size:14px;font-weight:800}
.flash--ok{background:var(--c7-ok-bg);color:var(--c7-ok-body)}
.flash--ok .flash__ico{background:var(--c7-ok)}
.flash--ok .flash__title{color:var(--c7-ok-ink)}
.flash--warn{background:var(--c7-warn-bg);color:var(--c7-warn-body)}
.flash--warn .flash__ico{background:var(--c7-warn)}
.flash--warn .flash__title{color:var(--c7-warn-ink)}
.flash--info{background:var(--c7-accent-tint);color:#40606A}
.flash--info .flash__ico{background:var(--c7-accent)}
.flash--info .flash__title{color:var(--c7-accent-tint-ink)}

/* --- guscio telefono --------------------------------------------------- */
.phone{position:relative;width:390px;height:844px;overflow:hidden;background:var(--c7-bg)}
.head{padding:20px var(--c7-gutter) 12px;display:flex;align-items:center;gap:12px}
.head__back{width:46px;height:46px;border:0;border-radius:50%;background:var(--c7-card);
            color:var(--c7-accent);display:grid;place-items:center;flex-shrink:0}
.head__title{flex:1;min-width:0;display:flex;flex-direction:column}
.head__title h1{font-size:18px;font-weight:800;letter-spacing:-.025em}
.head__sub{font-size:12px;font-weight:600;color:var(--c7-ink-muted)}
.vtabs{display:flex;gap:6px;padding:14px var(--c7-gutter) 12px;background:var(--c7-bg)}
.vtab{flex:1;min-width:0;height:42px;border:0;border-radius:var(--c7-r-pill);
      background:var(--c7-card);color:var(--c7-ink-muted);font-family:inherit;
      font-size:13px;font-weight:700;display:grid;place-items:center;white-space:nowrap}
.vtab.is-active{background:var(--c7-accent);color:var(--c7-accent-ink)}
.content{padding:0 var(--c7-gutter) 28px}
.mobilenav{position:absolute;left:12px;right:12px;bottom:14px;height:62px;padding:0 8px;
           border-radius:var(--c7-r-pill);background:var(--c7-card);
           box-shadow:var(--c7-shadow-pop);display:flex;align-items:center;
           justify-content:space-around}
.mobilenav a{flex:1;height:48px;border-radius:var(--c7-r-pill);display:flex;
             flex-direction:column;align-items:center;justify-content:center;gap:3px;
             color:var(--c7-ink-muted);font-size:10px;font-weight:700}
.mobilenav a.is-active{color:var(--c7-ink)}
.mobilenav a.is-active svg{color:var(--c7-accent)}
.actionbar{position:absolute;left:0;right:0;bottom:90px;padding:12px var(--c7-gutter) 14px;
           background:linear-gradient(to top,var(--c7-bg) 68%,rgba(228,232,231,0));
           display:flex;gap:10px}
.actionbar .btn{flex:1}

/* --- guscio desktop ---------------------------------------------------- */
.app{display:flex;width:1440px;height:900px;overflow:hidden;background:var(--c7-bg)}
.side{width:var(--c7-side-w);flex-shrink:0;background:var(--c7-ink);color:var(--c7-bg);
      padding:24px 16px;display:flex;flex-direction:column;gap:26px}
.side__brand{display:flex;align-items:center;gap:11px;padding:0 6px}
.side__mark{width:34px;height:34px;border-radius:10px;background:var(--c7-accent);
            color:var(--c7-accent-bright);display:grid;place-items:center}
.side__name{font-size:14px;font-weight:800;letter-spacing:-.01em}
.side__role{font-size:11px;font-weight:600;color:#8A9599}
.side__group{display:flex;flex-direction:column;gap:3px}
.side__grouplabel{font-size:10px;font-weight:800;letter-spacing:.12em;color:#6E797C;
                  padding:0 10px 8px}
.side a{height:42px;border-radius:12px;padding:0 12px;display:flex;align-items:center;
        gap:11px;font-size:13px;font-weight:600;color:#B6BEC0}
.side a.is-active{background:var(--c7-accent);color:#EAF6F8;font-weight:700}
.side__count{margin-left:auto;height:20px;min-width:20px;padding:0 6px;
             border-radius:var(--c7-r-pill);background:var(--c7-err);color:#fff;
             display:grid;place-items:center;font-family:var(--c7-font-mono);
             font-size:11px;font-weight:700}
.side__user{margin-top:auto;border-radius:var(--c7-r-control);background:#2A3033;
            padding:12px;display:flex;align-items:center;gap:11px}
.dmain{flex:1;min-width:0;display:flex;flex-direction:column;overflow:hidden}
.dhead{padding:22px var(--c7-gutter-lg) 20px;display:flex;align-items:center;gap:12px;
       border-bottom:1px solid var(--c7-line);background:var(--c7-bg)}
.dhead h1{font-size:22px;font-weight:800;letter-spacing:-.025em}
.dhead__actions{margin-left:auto;display:flex;align-items:center;gap:8px}
.dcontent{flex:1;padding:16px var(--c7-gutter-lg) 28px;overflow:hidden}
.cols{display:grid;grid-template-columns:1fr 380px;gap:var(--c7-gap-lg);align-items:start}
"""

FONTS = ('<link rel="stylesheet" '
         'href="https://fonts.googleapis.com/css2?'
         'family=Manrope:wght@600;700;800&amp;family=JetBrains+Mono:wght@700;800&amp;'
         'display=swap">')

# --------------------------------------------------------------------------
# Icone — SVG stroke, griglia 20/24, un solo stile
# --------------------------------------------------------------------------


def ico(path, size=18, sw=1.9, fill=""):
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" '
            f'stroke="currentColor" stroke-width="{sw}" stroke-linecap="round" '
            f'stroke-linejoin="round">{path}</svg>')


I = {
    "back": '<path d="M15 18l-6-6 6-6"></path>',
    "play": '<path d="M7 4l12 8-12 8V4z"></path>',
    "flag": '<path d="M5 21V4h13l-2.5 4L18 12H5"></path>',
    "check": '<path d="M20 6L9 17l-5-5"></path>',
    "clock": '<circle cx="12" cy="12" r="9"></circle><path d="M12 7v5l3 2"></path>',
    "table": ('<rect x="3" y="5" width="18" height="14" rx="3"></rect>'
              '<path d="M3 12h18M12 5v14"></path>'),
    "users": ('<circle cx="9" cy="8" r="3.2"></circle>'
              '<path d="M3.5 19c.6-3 2.8-4.6 5.5-4.6S13.9 16 14.5 19"></path>'
              '<path d="M16 6.5a3 3 0 010 6M18 19c-.2-1.6-.7-2.9-1.6-3.8"></path>'),
    "trophy": ('<path d="M7 4h10v5a5 5 0 01-10 0V4z"></path>'
               '<path d="M7 6H4.5v1A3.5 3.5 0 007 10.5M17 6h2.5v1A3.5 3.5 0 0117 10.5">'
               '</path><path d="M10 14v3M14 14v3M8.5 20h7"></path>'),
    "list": '<path d="M8 6h13M8 12h13M8 18h13M3.5 6h.01M3.5 12h.01M3.5 18h.01"></path>',
    "gear": ('<circle cx="12" cy="12" r="3"></circle>'
             '<path d="M19.4 15a1.6 1.6 0 00.3 1.8l.1.1a2 2 0 11-2.8 2.8l-.1-.1a1.6 1.6 0 '
             '00-1.8-.3 1.6 1.6 0 00-1 1.5V21a2 2 0 11-4 0v-.1A1.6 1.6 0 008 19.4a1.6 1.6 '
             '0 00-1.8.3l-.1.1a2 2 0 11-2.8-2.8l.1-.1a1.6 1.6 0 00.3-1.8 1.6 1.6 0 '
             '00-1.5-1H2a2 2 0 110-4h.1A1.6 1.6 0 003.6 8a1.6 1.6 0 00-.3-1.8l-.1-.1a2 2 0 '
             '112.8-2.8l.1.1a1.6 1.6 0 001.8.3H8a1.6 1.6 0 001-1.5V2a2 2 0 114 0v.1a1.6 1.6 '
             '0 001 1.5 1.6 1.6 0 001.8-.3l.1-.1a2 2 0 112.8 2.8l-.1.1a1.6 1.6 0 '
             '00-.3 1.8V8a1.6 1.6 0 001.5 1H22a2 2 0 110 4h-.1a1.6 1.6 0 00-1.5 1z"></path>'),
    "plus": '<path d="M12 5v14M5 12h14"></path>',
    "minus": '<path d="M5 12h14"></path>',
    "bell": ('<path d="M18 9a6 6 0 10-12 0c0 5-2 6-2 6h16s-2-1-2-6"></path>'
             '<path d="M10.5 20a2 2 0 003 0"></path>'),
    "home": ('<path d="M4 11l8-7 8 7"></path>'
             '<path d="M6.5 9.5V20h11V9.5"></path>'),
    "target": ('<circle cx="12" cy="12" r="8.5"></circle>'
               '<circle cx="12" cy="12" r="4"></circle><circle cx="12" cy="12" r="1"></circle>'),
    "swords": ('<path d="M4 4l9 9M4 8V4h4M20 4l-9 9M20 8V4h-4"></path>'
               '<path d="M14 14l6 6M10 14l-6 6"></path>'),
    "chevron": '<path d="M9 6l6 6-6 6"></path>',
    "link": ('<path d="M10 13a4 4 0 006 .5l2-2a4 4 0 10-5.7-5.7l-1 1"></path>'
             '<path d="M14 11a4 4 0 00-6-.5l-2 2A4 4 0 109.7 18.2l1-1"></path>'),
    "scale": ('<path d="M12 4v16M7 20h10M4 9l4-4 4 4"></path>'
              '<path d="M4 9a4 4 0 008 0M12 9l4-4 4 4"></path>'
              '<path d="M12 9a4 4 0 008 0"></path>'),
    "rotate": ('<path d="M4 10a8 8 0 0113.7-4.2L20 8"></path><path d="M20 4v4h-4"></path>'),
    "grid": ('<rect x="3" y="3" width="7" height="7" rx="2"></rect>'
             '<rect x="14" y="3" width="7" height="7" rx="2"></rect>'
             '<rect x="3" y="14" width="7" height="7" rx="2"></rect>'
             '<rect x="14" y="14" width="7" height="7" rx="2"></rect>'),
    "share": ('<circle cx="18" cy="5" r="2.6"></circle><circle cx="6" cy="12" r="2.6"></circle>'
              '<circle cx="18" cy="19" r="2.6"></circle>'
              '<path d="M8.4 10.8l7.2-4.1M8.4 13.2l7.2 4.1"></path>'),
    "crown": '<path d="M4 18h16M4 18L3 7l5 4 4-6 4 6 5-4-1 11"></path>',
}


# --------------------------------------------------------------------------
# Gusci
# --------------------------------------------------------------------------

MOBILENAV = f"""
  <nav class="mobilenav">
    <a class="is-active" href="#">{ico(I["home"], 16)}Dashboard</a>
    <a href="#">{ico(I["table"], 16)}Sale</a>
    <a href="#">{ico(I["swords"], 16)}Sfide</a>
    <a href="#">{ico(I["target"], 16)}Esercizi</a>
    <a href="#">{ico(I["bell"], 16)}Notifiche</a>
  </nav>
"""


def phone(head_sub, tabs, content, actionbar="", overlay="",
          title="Gara 3 &middot; Gioved&igrave;"):
    """Guscio telefono: testata unica del guscio, linguette, contenuto, nav.

    `overlay` e' il foglio modale che copre la pagina (assegna tavolo,
    imposta risultato, apri iscrizioni): nell'app sono modali Bootstrap.
    """
    return f"""
<div class="phone">
  <header class="head">
    <button class="head__back">{ico(I["back"], 17)}</button>
    <div class="head__title">
      <h1>{title}</h1>
      <div class="head__sub">{head_sub}</div>
    </div>
    <div class="avatar avatar--lg">PA</div>
  </header>
  {tabs}
  <main class="content">
    <div class="stack">
      {content}
    </div>
  </main>
  {actionbar}
  {MOBILENAV}
  {overlay}
</div>
"""


def vtabs(items, active):
    out = []
    for label in items:
        cls = "vtab is-active" if label == active else "vtab"
        out.append(f'<button class="{cls}">{label}</button>')
    return '<div class="vtabs">' + "".join(out) + "</div>"


SIDE = f"""
  <aside class="side">
    <div class="side__brand">
      <div class="side__mark">{ico(I["target"], 15)}</div>
      <div class="grow">
        <div class="side__name">Tornei Biliardo</div>
        <div class="side__role">direzione gara</div>
      </div>
      <button class="iconbtn" style="width:28px;height:28px;background:#2A3033;color:#B6BEC0"
              title="Nascondi la colonna">{ico(I["back"], 13)}</button>
    </div>
    <div class="side__group">
      <div class="side__grouplabel">Generale</div>
      <a class="is-active" href="#">{ico(I["home"], 14)}Dashboard</a>
      <a href="#">{ico(I["table"], 14)}Sale Biliardo</a>
      <a href="#">{ico(I["target"], 14)}Esercizi</a>
      <a href="#">{ico(I["list"], 14)}Esami</a>
      <a href="#">{ico(I["swords"], 14)}Sfide individuali</a>
    </div>
    <div class="side__user">
      <div class="avatar">PA</div>
      <div class="grow">
        <div style="font-size:13px;font-weight:800">pa</div>
        <div class="side__role">direttore &middot; Lv 17</div>
      </div>
      <div class="side__count">4</div>
    </div>
  </aside>
"""


def desktop(head_actions, content):
    return f"""
<div class="app">
  {SIDE}
  <div class="dmain">
    <header class="dhead">
      <div class="grow">
        <h1>Gara 3 &middot; Gioved&igrave;</h1>
        <div class="head__sub">Biliardo Mimmo &middot; Al 5 &middot; Palla 8 &middot;
          <span class="num">gio 3 set 2026, 20:00</span></div>
      </div>
      <div class="dhead__actions">{head_actions}</div>
    </header>
    <div class="dcontent">
      {content}
    </div>
  </div>
</div>
"""


def doc(body):
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <script src="./support.js"></script>
</head>
<body>
<x-dc>
<helmet>
  {FONTS}
  <style>{CSS}</style>
</helmet>
{body}
</x-dc>
</body>
</html>
"""


# --------------------------------------------------------------------------
# Pezzi di contenuto condivisi fra le direzioni
# --------------------------------------------------------------------------

def match_card(p1, s1, p2, s2, state, right_html, locked=False, winner=None):
    """Card partita come components/_match_card.html: pill di stato a sinistra,
    tavolo o comando a destra, poi giocatori e punteggio."""
    cls = "card card--locked" if locked else "card"
    dim1 = "color:var(--c7-ink-muted)" if winner == 2 else ""
    dim2 = "color:var(--c7-ink-muted)" if winner == 1 else ""
    return f"""
      <article class="{cls}">
        <div class="row" style="justify-content:space-between">
          {state}
          {right_html}
        </div>
        <div style="margin-top:14px;display:grid;grid-template-columns:1fr auto 1fr;
                    align-items:center;gap:10px">
          <div>
            <div style="font-size:13px;font-weight:800;{dim1}">{p1}</div>
            <div class="num-lg" style="{dim1}">{s1}</div>
          </div>
          <div class="faint" style="font-size:12px;font-weight:800">vs</div>
          <div style="text-align:right">
            <div style="font-size:13px;font-weight:800;{dim2}">{p2}</div>
            <div class="num-lg" style="{dim2}">{s2}</div>
          </div>
        </div>
      </article>
"""


def stepper_card(p1, s1, p2, s2, table, live=True):
    """Card partita della direzione Console: il punteggio si segna qui."""
    pill = (f'<span class="state state--accent">In corso</span>' if live
            else '<span class="state state--warn">Da giocare</span>')
    tbl = (f'<span class="pill" style="height:30px;padding:0 12px;font-size:12px">'
           f'{ico(I["table"], 13)} Tavolo <span class="num">{table}</span></span>'
           if table else
           f'<button class="btn btn--warn btn--sm">Assegna tavolo</button>')
    return f"""
      <article class="card">
        <div class="row" style="justify-content:space-between">
          {pill}
          {tbl}
        </div>
        <div style="margin-top:12px;display:grid;grid-template-columns:1fr 1fr;gap:10px">
          {score_side(p1, s1)}
          {score_side(p2, s2)}
        </div>
      </article>
"""


def pending_card(p1, p2):
    """Partita non ancora iniziata: niente segnapunti — non c'e' nulla da
    segnare finche' non si gioca. Il comando e' assegnare il tavolo."""
    return f"""
      <article class="card">
        <div class="row" style="justify-content:space-between">
          <span class="state state--warn">Da giocare</span>
          <button class="btn btn--warn btn--sm">Assegna tavolo</button>
        </div>
        <div class="row" style="margin-top:12px">
          <div class="grow" style="font-size:13px;font-weight:800">{p1}</div>
          <div class="faint" style="font-size:12px;font-weight:800">vs</div>
          <div class="grow" style="font-size:13px;font-weight:800;text-align:right">{p2}</div>
        </div>
      </article>
"""


R1 = [("m.rossi", "5", "d.bianchi", "2", "1"), ("a.galli", "5", "s.conti", "3", "2"),
      ("l.ferrari", "5", "f.costa", "1", "3"), ("g.verdi", "5", "p.marini", "4", "1"),
      ("r.neri", "5", "e.sala", "0", "2")]


def round1_rows():
    """Il turno concluso e' un elenco raggruppato, non cinque card."""
    rows = ""
    for p1, s1, p2, s2, tbl in R1:
        rows += f"""
        <div class="rows__row">
          <div class="grow">
            <div class="rows__title muted">{p1} <span class="faint">vs</span> {p2}</div>
          </div>
          <div class="num" style="font-size:14px;color:var(--c7-ink-soft)">{s1}&ndash;{s2}</div>
          <div class="rows__sub" style="width:58px;text-align:right">Tavolo {tbl}</div>
        </div>"""
    return f"""
          <div class="sechead" style="margin-top:4px">
            <h3 class="muted">Turno 1</h3>
            <span class="state state--muted" style="margin-left:auto">Concluso</span>
          </div>
          <div class="rows">{rows}</div>
"""


def score_side(name, score):
    return f"""
          <div class="card--sunk" style="border-radius:var(--c7-r-field);padding:10px 10px 12px">
            <div style="font-size:12px;font-weight:800;text-align:center;
                        white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{name}</div>
            <div class="row" style="margin-top:8px;gap:6px">
              <button class="iconbtn" style="width:38px;height:38px;background:var(--c7-card)"
                      >{ico(I["minus"], 15)}</button>
              <div class="num grow" style="text-align:center;font-size:26px;font-weight:800">{score}</div>
              <button class="iconbtn" style="width:38px;height:38px;background:var(--c7-ink);
                      color:#fff">{ico(I["plus"], 15)}</button>
            </div>
          </div>
"""


def todo_row(icon, title, sub, tone="warn"):
    tile = {"warn": "tile tile--warn", "ok": "tile tile--ok",
            "locked": "tile tile--locked", "neutral": "tile tile--neutral",
            "accent": "tile"}[tone]
    return f"""
        <div class="rows__row">
          <div class="{tile} tile--sm">{ico(icon, 16)}</div>
          <div class="grow">
            <div class="rows__title">{title}</div>
            <div class="rows__sub">{sub}</div>
          </div>
          <span class="faint">{ico(I["chevron"], 15)}</span>
        </div>
"""


def classifica_rows(n=4):
    data = [("1", "m.rossi", "4", "+11"), ("2", "a.galli", "3", "+6"),
            ("3", "d.bianchi", "3", "+2"), ("4", "l.ferrari", "2", "-1")]
    out = []
    for pos, name, w, diff in data[:n]:
        out.append(f"""
        <div class="rows__row">
          <div class="num" style="width:20px;font-size:15px;font-weight:800">{pos}</div>
          <div class="avatar">{name[0].upper()}{name[2].upper()}</div>
          <div class="grow"><div class="rows__title">{name}</div></div>
          <div class="num" style="font-size:15px;font-weight:800">{w}</div>
          <div class="num muted" style="width:34px;text-align:right;font-size:13px">{diff}</div>
        </div>""")
    return "".join(out)


# --------------------------------------------------------------------------
# A · REGIA — la pagina di oggi, piu' una fascia che dice il prossimo passo
# --------------------------------------------------------------------------

REGIA_BAND_MOBILE = f"""
      <section class="card card--accent">
        <div class="row">
          <div class="kicker grow">Turno 2 di 4 &middot; in corso</div>
          <span class="state state--onaccent">Amalfi</span>
        </div>
        <h3 style="margin-top:6px;font-size:19px">3 partite ancora aperte</h3>
        <div class="row" style="margin-top:12px;gap:10px">
          <div class="num" style="font-size:13px;color:var(--c7-accent-bright)">2/5</div>
          <div class="bar grow"><div class="bar__fill" style="width:40%"></div></div>
        </div>
        <div style="margin-top:14px;display:flex;gap:8px;flex-wrap:wrap">
          <span class="pill" style="height:34px;background:rgba(242,248,247,.14);
                color:var(--c7-accent-bright);font-size:12px">
            {ico(I["table"], 14)} 1 tavolo da assegnare</span>
          <span class="pill" style="height:34px;background:rgba(242,248,247,.14);
                color:var(--c7-accent-bright);font-size:12px">
            {ico(I["clock"], 14)} 2 risultati mancanti</span>
        </div>
        <div class="row" style="margin-top:12px;gap:10px">
          <div class="grow" style="font-size:12px;font-weight:700;color:var(--c7-accent-dim)">
            Si avvia a turno chiuso</div>
          <button class="btn btn--locked btn--sm">Avvia turno 3</button>
        </div>
      </section>
"""


def regia_mobile():
    content = f"""
      {REGIA_BAND_MOBILE}

      <div class="sechead" style="margin-top:4px">
        <h3>Turno 2</h3>
        <span class="state state--accent" style="margin-left:auto">In corso</span>
      </div>

      {match_card("m.rossi", "4", "g.verdi", "2",
                  '<span class="state state--accent">In corso</span>',
                  f'<span class="muted" style="font-size:12px">Tavolo '
                  f'<span class="num">1</span></span>')}
      {match_card("d.bianchi", "3", "l.ferrari", "3",
                  '<span class="state state--accent">In corso</span>',
                  f'<span class="muted" style="font-size:12px">Tavolo '
                  f'<span class="num">2</span></span>')}
      {match_card("s.conti", "0", "p.marini", "0",
                  '<span class="state state--warn">Da giocare</span>',
                  '<button class="btn btn--warn btn--sm">Assegna tavolo</button>')}

      <div class="sechead" style="margin-top:4px">
        <h3 class="muted">Turno 1</h3>
        <span class="state state--muted" style="margin-left:auto">Concluso</span>
      </div>
"""
    return doc(phone("Biliardo Mimmo &middot; Al 5",
                     vtabs(["Turni", "Classifica", "Iscritti", "Gestione"], "Turni"),
                     content))


def regia_desktop():
    band = f"""
      <section class="card card--accent" style="display:flex;align-items:center;
               gap:22px;flex-wrap:wrap;padding:20px 22px">
        <div style="min-width:230px">
          <div class="kicker">Turno 2 di 4 &middot; in corso</div>
          <h3 style="margin-top:4px;font-size:20px">3 partite ancora aperte</h3>
        </div>
        <div style="flex:1;min-width:200px">
          <div class="row" style="gap:10px">
            <div class="num" style="font-size:13px;color:var(--c7-accent-bright)">2/5</div>
            <div class="bar grow"><div class="bar__fill" style="width:40%"></div></div>
          </div>
          <div style="margin-top:10px;display:flex;gap:8px">
            <span class="pill" style="height:32px;background:rgba(242,248,247,.14);
                  color:var(--c7-accent-bright);font-size:12px">
              {ico(I["table"], 13)} 1 tavolo da assegnare</span>
            <span class="pill" style="height:32px;background:rgba(242,248,247,.14);
                  color:var(--c7-accent-bright);font-size:12px">
              {ico(I["clock"], 13)} 2 risultati mancanti</span>
          </div>
        </div>
        <button class="btn btn--locked">Avvia turno 3</button>
      </section>
"""
    table_rows = ""
    rows = [("m.rossi", "g.verdi", "4&ndash;2", "In corso", "accent", "1"),
            ("d.bianchi", "l.ferrari", "3&ndash;3", "In corso", "accent", "2"),
            ("s.conti", "p.marini", "&mdash;", "Da giocare", "warn", None),
            ("a.galli", "r.neri", "5&ndash;1", "Conclusa", "ok", "3"),
            ("f.costa", "X a tavolino", "&mdash;", "X", "info", "bye")]
    for p1, p2, sc, st, tone, tbl in rows:
        if tbl == "bye":
            tblcell = '<span class="faint">&mdash;</span>'
        elif tbl:
            tblcell = f'<span class="num">{tbl}</span>'
        else:
            tblcell = '<button class="btn btn--warn btn--sm">Assegna</button>' 
        table_rows += f"""
            <tr>
              <td style="padding:13px 0;font-weight:800">{p1} <span class="faint">vs</span> {p2}</td>
              <td class="num" style="padding:13px 0;font-size:15px">{sc}</td>
              <td style="padding:13px 0"><span class="state state--{tone}">{st}</span></td>
              <td style="padding:13px 0">{tblcell}</td>
              <td style="padding:13px 0;text-align:right">
                <span class="faint">{ico(I["chevron"], 15)}</span></td>
            </tr>"""

    left = f"""
        <div class="stack">
          <div class="sechead">
            <h3>Turno 2</h3>
            <span class="sechead__more">Palla 8 &middot; Al 5</span>
          </div>
          <section class="card">
            <table style="width:100%;border-collapse:collapse;font-size:13px">
              <thead>
                <tr class="label" style="text-align:left">
                  <th style="padding-bottom:10px">Giocatori</th>
                  <th style="padding-bottom:10px">Risultato</th>
                  <th style="padding-bottom:10px">Stato</th>
                  <th style="padding-bottom:10px">Tavolo</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>{table_rows}</tbody>
            </table>
          </section>
          {round1_rows()}
        </div>
"""
    right = f"""
        <div class="stack">
          <section class="card">
            <div class="row">
              <h3 class="grow">Gestione</h3>
              <span class="state state--accent">In gioco</span>
            </div>
            <div class="stack" style="margin-top:14px">
              <div class="flash flash--info">
                <span class="flash__ico">{ico(I["play"], 14)}</span>
                <div><div class="flash__title">Turno 2/4 in corso</div></div>
              </div>
              <button class="btn btn--secondary btn--w">{ico(I["rotate"], 16)} Annulla avvio turno 2</button>
              <button class="btn btn--secondary btn--w">{ico(I["users"], 16)} Direttori di gara</button>
              <button class="btn btn--secondary btn--w">{ico(I["table"], 16)} Tavoli</button>
            </div>
          </section>
          <section class="card">
            <div class="row"><h3 class="grow">Informazioni gara</h3></div>
            <div style="margin-top:12px;display:grid;grid-template-columns:auto 1fr;
                        gap:8px 16px;font-size:13px">
              <span class="muted">Sala</span><span style="font-weight:800">Biliardo Mimmo</span>
              <span class="muted">Turni</span><span class="num">4</span>
              <span class="muted">Accoppiamento</span><span style="font-weight:800">Amalfi</span>
              <span class="muted">Iscritti</span><span class="num">10</span>
            </div>
          </section>
        </div>
"""
    content = f"""
      <div class="stack">
        {band}
        <div class="cols">
          {left}
          {right}
        </div>
      </div>
"""
    actions = ('<button class="btn btn--secondary btn--sm">'
               f'{ico(I["share"], 15)} Link pubblico</button>'
               '<button class="btn btn--primary btn--sm">'
               f'{ico(I["gear"], 15)} Gestione</button>')
    return doc(desktop(actions, content))


# --------------------------------------------------------------------------
# B · CONSOLE — il turno in corso e' la pagina; a destra cosa manca
# --------------------------------------------------------------------------

# La card riassuntiva del turno: scura come la fascia di fase (scelta 1B
# del 12/09/2026), perche' e' lei a dire dove siamo.
CONSOLE_HEAD = f"""
      <section class="card card--accent" style="padding:14px 16px">
        <div class="row">
          <div class="grow">
            <div class="kicker">Turno 2 di 4</div>
            <div class="row" style="margin-top:4px;gap:8px">
              <div class="num" style="font-size:19px;font-weight:800">2/5</div>
              <div style="font-size:13px;font-weight:700;color:var(--c7-accent-dim)">partite chiuse</div>
            </div>
          </div>
          <div style="text-align:right">
            <div class="kicker">Tavoli</div>
            <div class="num" style="margin-top:4px;font-size:19px;font-weight:800">2/4</div>
          </div>
        </div>
        <div class="bar" style="margin-top:10px"><div class="bar__fill" style="width:40%"></div></div>
      </section>
"""


def console_mobile():
    content = f"""
      {CONSOLE_HEAD}

      {stepper_card("m.rossi", "4", "g.verdi", "2", "1")}
      {stepper_card("d.bianchi", "3", "l.ferrari", "3", "2")}
      {pending_card("s.conti", "p.marini")}
"""
    bar = f"""
  <div class="actionbar">
    <button class="btn btn--locked">{ico(I["play"], 16)} Avvia turno 3 &middot; 3 aperte</button>
  </div>
"""
    return doc(phone("Biliardo Mimmo &middot; Al 5",
                     vtabs(["Turni", "Classifica", "Iscritti", "Gestione"], "Turni"),
                     content, bar))


def console_desktop():
    strip = f"""
      <section class="card card--accent" style="display:flex;align-items:center;gap:24px;
               padding:18px 22px">
        <div>
          <div class="kicker">Turno in corso</div>
          <div class="num" style="margin-top:2px;font-size:28px;font-weight:800">2<span
             style="font-size:16px;color:var(--c7-accent-dim)">/4</span></div>
        </div>
        <div style="width:1px;height:44px;background:rgba(242,248,247,.18)"></div>
        <div>
          <div class="kicker">Partite chiuse</div>
          <div class="num" style="margin-top:2px;font-size:28px;font-weight:800">2<span
             style="font-size:16px;color:var(--c7-accent-dim)">/5</span></div>
        </div>
        <div style="width:1px;height:44px;background:rgba(242,248,247,.18)"></div>
        <div>
          <div class="kicker">Tavoli occupati</div>
          <div class="num" style="margin-top:2px;font-size:28px;font-weight:800">2<span
             style="font-size:16px;color:var(--c7-accent-dim)">/4</span></div>
        </div>
        <div class="grow"></div>
        <button class="btn btn--locked">{ico(I["play"], 16)} Avvia turno 3</button>
      </section>
"""
    board = f"""
        <div class="stack">
          <div class="sechead">
            <h3>Partite del turno 2</h3>
            <span class="sechead__more">Palla 8 &middot; Al 5</span>
          </div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
            {stepper_card("m.rossi", "4", "g.verdi", "2", "1")}
            {stepper_card("d.bianchi", "3", "l.ferrari", "3", "2")}
            {pending_card("s.conti", "p.marini")}
            <article class="card card--ok">
              <div class="row" style="justify-content:space-between">
                <span class="state state--ok">Da validare</span>
                <span style="font-size:12px;font-weight:700">Tavolo <span class="num">3</span></span>
              </div>
              <div style="margin-top:12px;display:grid;grid-template-columns:1fr 1fr;gap:10px">
                <div class="card--sunk" style="border-radius:var(--c7-r-field);padding:10px;text-align:center">
                  <div style="font-size:12px;font-weight:800">a.galli</div>
                  <div class="num" style="margin-top:6px;font-size:30px;font-weight:800;line-height:1">5</div>
                </div>
                <div class="card--sunk" style="border-radius:var(--c7-r-field);padding:10px;text-align:center;color:var(--c7-ink-muted)">
                  <div style="font-size:12px;font-weight:800">r.neri</div>
                  <div class="num" style="margin-top:6px;font-size:30px;font-weight:800;line-height:1">1</div>
                </div>
              </div>
              <div style="margin-top:12px"><button class="btn btn--success btn--sm btn--w">{ico(I["check"], 15)} Valida e libera il tavolo 3</button></div>
            </article>
          </div>
          {round1_rows()}
        </div>
"""
    rail = f"""
        <div class="stack">
          <div class="sechead"><h3>Da fare adesso</h3></div>
          <div class="rows">
            {todo_row(I["table"], "1 tavolo da assegnare", "s.conti vs p.marini")}
            {todo_row(I["clock"], "2 risultati aperti", "tavoli 1 e 2")}
            {todo_row(I["scale"], "Nessun parimerito", "ultimo controllo al turno 1", "locked")}
          </div>

          <div class="sechead" style="margin-top:4px"><h3>Tavoli</h3>
            <span class="sechead__more">Configura</span></div>
          <section class="card">
            <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px">
              <div class="card--sunk" style="border-radius:var(--c7-r-control);padding:10px;
                   text-align:center;background:var(--c7-accent);color:var(--c7-accent-ink)">
                <div class="num" style="font-size:17px;font-weight:800">1</div>
                <div style="font-size:10px;font-weight:700;color:var(--c7-accent-dim)">m.rossi</div>
              </div>
              <div class="card--sunk" style="border-radius:var(--c7-r-control);padding:10px;
                   text-align:center;background:var(--c7-accent);color:var(--c7-accent-ink)">
                <div class="num" style="font-size:17px;font-weight:800">2</div>
                <div style="font-size:10px;font-weight:700;color:var(--c7-accent-dim)">d.bianchi</div>
              </div>
              <div class="card--sunk" style="border-radius:var(--c7-r-control);padding:10px;
                   text-align:center">
                <div class="num" style="font-size:17px;font-weight:800">3</div>
                <div class="muted" style="font-size:10px;font-weight:700">libero</div>
              </div>
              <div class="card--sunk" style="border-radius:var(--c7-r-control);padding:10px;
                   text-align:center">
                <div class="num" style="font-size:17px;font-weight:800">4</div>
                <div class="muted" style="font-size:10px;font-weight:700">libero</div>
              </div>
            </div>
          </section>

          <div class="sechead" style="margin-top:4px"><h3>Impostazioni gara</h3></div>
          <div class="rows">
            {todo_row(I["users"], "Direttori di gara", "solo tu", "neutral")}
            {todo_row(I["share"], "Vetrina", "locandina caricata", "neutral")}
            {todo_row(I["table"], "Tavoli", "cambia fra un turno e l'altro", "neutral")}
          </div>
        </div>
"""
    content = f"""
      <div class="stack">
        {strip}
        <div class="cols">
          {board}
          {rail}
        </div>
      </div>
"""
    actions = ('<button class="btn btn--secondary btn--sm">'
               f'{ico(I["trophy"], 15)} Classifica</button>'
               '<button class="btn btn--secondary btn--sm">'
               f'{ico(I["users"], 15)} Iscritti <span class="num">10</span></button>')
    return doc(desktop(actions, content))


# --------------------------------------------------------------------------
# C · FASI — la pagina mostra la fase; il resto va in Impostazioni
# --------------------------------------------------------------------------

PHASE_STRIP = f"""
      <section style="display:flex;align-items:center;gap:8px">
        <div class="pill" style="height:34px;background:var(--c7-ok-bg);color:var(--c7-ok-ink);
             font-size:12px">{ico(I["check"], 14)} Iscrizione</div>
        <div style="height:2px;flex:1;background:var(--c7-line)"></div>
        <div class="pill is-active" style="height:34px;font-size:12px">
          {ico(I["play"], 13)} In gioco</div>
        <div style="height:2px;flex:1;background:var(--c7-line)"></div>
        <div class="pill" style="height:34px;font-size:12px;color:var(--c7-ink-faint)">
          {ico(I["flag"], 13)} Chiusura</div>
      </section>
"""


def fasi_mobile():
    content = f"""
      {PHASE_STRIP}

      <section class="card card--accent">
        <div class="kicker">Turno 2 di 4</div>
        <h3 style="margin-top:5px;font-size:19px">Mancano 3 partite</h3>
        <div class="row" style="margin-top:12px;gap:10px">
          <div class="num" style="font-size:13px;color:var(--c7-accent-bright)">2/5</div>
          <div class="bar grow"><div class="bar__fill" style="width:40%"></div></div>
        </div>
        <div class="stack" style="margin-top:14px;gap:8px">
          <div class="row" style="gap:10px">
            <span class="tile tile--sm" style="background:rgba(242,248,247,.14);
                  color:var(--c7-accent-bright)">{ico(I["table"], 15)}</span>
            <div class="grow" style="font-size:13px;font-weight:700">1 tavolo da assegnare</div>
            <span style="color:var(--c7-accent-bright)">{ico(I["chevron"], 15)}</span>
          </div>
          <div class="row" style="gap:10px">
            <span class="tile tile--sm" style="background:rgba(242,248,247,.14);
                  color:var(--c7-accent-bright)">{ico(I["clock"], 15)}</span>
            <div class="grow" style="font-size:13px;font-weight:700">2 risultati mancanti</div>
            <span style="color:var(--c7-accent-bright)">{ico(I["chevron"], 15)}</span>
          </div>
        </div>
      </section>

      <div style="display:flex;gap:6px">
        <button class="vtab is-active" style="flex:1">Partite</button>
        <button class="vtab" style="flex:1">Classifica</button>
      </div>

      {match_card("m.rossi", "4", "g.verdi", "2",
                  '<span class="state state--accent">In corso</span>',
                  '<span class="muted" style="font-size:12px">Tavolo '
                  '<span class="num">1</span></span>')}
      {pending_card("s.conti", "p.marini")}

      <div class="rows">
        {todo_row(I["users"], "Iscritti", "10 attivi, nessuna riserva", "neutral")}
        {todo_row(I["gear"], "Impostazioni gara", "direttori, tavoli, squadre, turni", "neutral")}
      </div>
"""
    return doc(phone("Biliardo Mimmo &middot; Al 5", "", content))


def fasi_desktop():
    left = f"""
        <div class="stack">
          <section class="card card--accent" style="display:flex;align-items:center;
                   gap:22px;padding:20px 22px">
            <div style="min-width:220px">
              <div class="kicker">Turno 2 di 4</div>
              <h3 style="margin-top:4px;font-size:20px">Mancano 3 partite</h3>
            </div>
            <div class="grow">
              <div class="row" style="gap:10px">
                <div class="num" style="font-size:13px;color:var(--c7-accent-bright)">2/5</div>
                <div class="bar grow"><div class="bar__fill" style="width:40%"></div></div>
              </div>
            </div>
            <button class="btn btn--locked">Avvia turno 3</button>
          </section>

          <div class="sechead"><h3>Partite del turno 2</h3>
            <span class="sechead__more">Palla 8 &middot; Al 5</span></div>
          {match_card("m.rossi", "4", "g.verdi", "2",
                      '<span class="state state--accent">In corso</span>',
                      '<span class="muted" style="font-size:12px">Tavolo '
                      '<span class="num">1</span></span>')}
          {match_card("d.bianchi", "3", "l.ferrari", "3",
                      '<span class="state state--accent">In corso</span>',
                      '<span class="muted" style="font-size:12px">Tavolo '
                      '<span class="num">2</span></span>')}
          {pending_card("s.conti", "p.marini")}
          {round1_rows()}
        </div>
"""
    right = f"""
        <div class="stack">
          <div class="sechead"><h3>Classifica</h3>
            <span class="sechead__more">Dopo il turno 1</span></div>
          <div class="rows">
            <div class="rows__row" style="padding-top:11px;padding-bottom:11px">
              <div class="grow label" style="margin:0">Giocatore</div>
              <div class="label" style="margin:0">Vinte</div>
              <div class="label" style="margin:0;width:34px;text-align:right">Diff</div>
            </div>
            {classifica_rows()}</div>

          <div class="sechead" style="margin-top:4px"><h3>Impostazioni gara</h3></div>
          <div class="rows">
            {todo_row(I["users"], "Direttori di gara", "solo tu", "neutral")}
            {todo_row(I["table"], "Tavoli", "4 disponibili", "neutral")}
            {todo_row(I["grid"], "Squadre e categorie", "non usate in questa gara", "neutral")}
            {todo_row(I["list"], "Configurazione turni", "4 turni, distanza al 5", "neutral")}
          </div>
        </div>
"""
    content = f"""
      <div class="stack">
        {PHASE_STRIP}
        <div class="cols">
          {left}
          {right}
        </div>
      </div>
"""
    actions = ('<button class="btn btn--secondary btn--sm">'
               f'{ico(I["share"], 15)} Link pubblico</button>')
    return doc(desktop(actions, content))


# --------------------------------------------------------------------------
# Scrittura
# --------------------------------------------------------------------------

FILES = {
    "Main.dc.html": console_mobile,          # candidata in testa: B telefono
    "ConsoleDesktop.dc.html": console_desktop,
    "RegiaMobile.dc.html": regia_mobile,
    "RegiaDesktop.dc.html": regia_desktop,
    "FasiMobile.dc.html": fasi_mobile,
    "FasiDesktop.dc.html": fasi_desktop,
}

CANVAS = {
    "artboards": [
        {"file": "RegiaMobile.dc.html", "title": "A · Regia — telefono",
         "x": 0, "y": 0, "w": 390, "h": 844},
        {"file": "Main.dc.html", "title": "B · Console — telefono",
         "x": 1600, "y": 0, "w": 390, "h": 844},
        {"file": "FasiMobile.dc.html", "title": "C · Fasi — telefono",
         "x": 3200, "y": 0, "w": 390, "h": 844},
        {"file": "RegiaDesktop.dc.html", "title": "A · Regia — desktop",
         "x": 0, "y": 1010, "w": 1440, "h": 900},
        {"file": "ConsoleDesktop.dc.html", "title": "B · Console — desktop",
         "x": 1600, "y": 1010, "w": 1440, "h": 900},
        {"file": "FasiDesktop.dc.html", "title": "C · Fasi — desktop",
         "x": 3200, "y": 1010, "w": 1440, "h": 900},
    ],
    "annotations": [
        {"id": "nota-a", "x": 0, "y": -230, "w": 460,
         "text": "A · REGIA\nLa pagina di oggi con una fascia in cima che dice a che "
                 "punto e' il turno e cosa lo tiene aperto: tavoli da assegnare e "
                 "risultati mancanti.\n\nPerche': il direttore non ha un comando da "
                 "premere mentre il turno gira — ha lavoro sparso. La fascia lo "
                 "raccoglie.\nCosto: aggiunge un blocco, non toglie niente. Le quattro "
                 "linguette e le sezioni restano dove sono."},
        {"id": "nota-b", "x": 1600, "y": -230, "w": 460,
         "text": "B · CONSOLE\nIl turno in corso diventa la pagina: punteggio "
                 "segnato sulla card (niente modale), tavolo sulla card, e a destra "
                 "«da fare adesso» con la mappa dei tavoli.\n\nPerche': e' la "
                 "pagina che si tiene aperta mentre si dirige.\nCosto: il piu' grosso "
                 "dei tre — tocca il segnapunti, non solo l'impaginazione."},
        {"id": "nota-c", "x": 3200, "y": -230, "w": 460,
         "text": "C · FASI\nNiente quattro linguette: una striscia mostra il ciclo "
                 "(iscrizione → gioco → chiusura) e la pagina e' la fase in "
                 "corso. Direttori, tavoli, squadre, categorie e configurazione turni "
                 "finiscono sotto «Impostazioni gara».\n\nPerche': in gioco il "
                 "90% di quelle sezioni non serve.\nCosto: aggiungere un co-direttore a "
                 "gara iniziata costa un tap in piu', e la striscia mangia spazio "
                 "verticale sul telefono."},
    ],
    "launch": {"view": "canvas"},
}


def main():
    for name, fn in FILES.items():
        (SRC / name).write_text(fn(), encoding="utf-8")
    (SRC / "canvas.json").write_text(
        json.dumps(CANVAS, ensure_ascii=False, indent=2), encoding="utf-8")
    print("scritti:", ", ".join(sorted(FILES)), "+ canvas.json")


if __name__ == "__main__":
    main()
