#!/usr/bin/env python3
"""Kit del canvas «TPA ed esercizi»: gusci, icone, tavolo, grafici.

I token e le classi di base vengono dal kit del canvas della gara del
direttore (copiati alla lettera da tokens-7c.css / theme-7c.css): qui si
aggiungono solo le classi del referto TPA — copiate da theme-7c.css — e i
pezzi nuovi che il redesign propone.
"""

import importlib.util
import math
import pathlib

# Il kit di base sta nel canvas accanto: sorgenti/ -> canvas-tpa-esercizi/ ->
# redesign-7c/. Relativo a questo file, cosi' il generatore gira da qualunque
# copia del repo (worktree compresi) e non solo dalla macchina di chi l'ha scritto.
REDESIGN = pathlib.Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "kit_gara", REDESIGN / "canvas-gara-direttore/sorgenti/gen_gara_direttore.py"
)
_kit = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_kit)

BASE_CSS = _kit.CSS
FONTS = _kit.FONTS
ico = _kit.ico
I = dict(_kit.I)  # noqa: E741 - il nome viene dal kit di base
I.update(
    {
        "heart": '<path d="M12 20s-7-4.4-7-10a4 4 0 0 1 7-2.5A4 4 0 0 1 19 10c0 5.6-7 10-7 10z"/>',
        "search": '<circle cx="11" cy="11" r="6.5"/><path d="M16 16l4 4"/>',
        "dots": '<circle cx="5" cy="12" r="1.2"/><circle cx="12" cy="12" r="1.2"/><circle cx="19" cy="12" r="1.2"/>',
        "pencil": '<path d="M4 20l4-1 11-11-3-3L5 16l-1 4z"/>',
        "copy": '<rect x="8" y="8" width="12" height="12" rx="2.5"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/>',
        "chart": '<path d="M4 19h16"/><path d="M6 15l4-5 4 3 5-7"/>',
        "dice": '<rect x="4" y="4" width="16" height="16" rx="3.5"/><circle cx="9" cy="9" r=".9"/><circle cx="15" cy="15" r=".9"/><circle cx="15" cy="9" r=".9"/><circle cx="9" cy="15" r=".9"/>',
        "x": '<path d="M6 6l12 12M18 6L6 18"/>',
        "up": '<path d="M12 19V6"/><path d="M6 12l6-6 6 6"/>',
        "down": '<path d="M12 5v13"/><path d="M6 12l6 6 6-6"/>',
        "eye": '<path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z"/><circle cx="12" cy="12" r="2.6"/>',
        "lock": '<rect x="5" y="11" width="14" height="9" rx="2.5"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>',
        "sheet": '<path d="M7 3h8l4 4v14H7z"/><path d="M10 12h6M10 16h6"/>',
        "camera": '<path d="M4 8h3l2-3h6l2 3h3v11H4z"/><circle cx="12" cy="13" r="3.2"/>',
        "rect": '<rect x="4" y="7" width="16" height="10" rx="1.5"/>',
        "ring": '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3"/>',
        "hash": '<path d="M9 4L7 20M17 4l-2 16M4 9h16M3 15h16"/>',
        "callout": '<path d="M4 5h16v10H11l-4 4v-4H4z"/>',
        "donut": '<circle cx="12" cy="12" r="6" stroke-dasharray="3 3"/>',
        "move": '<path d="M12 3v18M3 12h18M12 3l-3 3M12 3l3 3M12 21l-3-3M12 21l3-3M3 12l3-3M3 12l3 3M21 12l-3-3M21 12l-3 3"/>',
        "cue": '<path d="M4 20L20 4"/><circle cx="18" cy="6" r="1.4"/>',
        "pen": '<path d="M4 18c4-8 6 2 10-6s4-4 6-6"/>',
        "type": '<path d="M5 6h14M12 6v13"/>',
        "cal": '<rect x="4" y="5" width="16" height="15" rx="2.5"/><path d="M4 10h16M9 3v4M15 3v4"/>',
        "cert": '<circle cx="12" cy="9" r="5.5"/><path d="M8.5 13.5L7 21l5-2.5 5 2.5-1.5-7.5"/>',
        "user": '<circle cx="12" cy="8" r="4"/><path d="M4 20c1.5-4 5-6 8-6s6.5 2 8 6"/>',
        "star": '<path d="M12 3.5l2.6 5.4 5.9.8-4.3 4.1 1 5.9L12 16.9l-5.2 2.8 1-5.9-4.3-4.1 5.9-.8z"/>',
        "swap": '<path d="M6 8h13l-3.5-3.5"/><path d="M18 16H5l3.5 3.5"/>',
        "info": '<circle cx="12" cy="12" r="8.5"/><path d="M12 11v5"/><circle cx="12" cy="8" r=".6"/>',
    }
)

EXTRA_CSS = """
/* --- referto TPA: copiato da theme-7c.css ------------------------------ */
.tpa{display:grid;gap:var(--c7-gap)}
.tpa-player{display:grid;grid-template-columns:1fr auto auto;gap:var(--c7-gap);
  align-items:center;padding:14px var(--c7-pad-card);border-radius:var(--c7-r-card);
  background:var(--c7-card);color:var(--c7-ink);border:1.5px solid transparent;width:100%;
  text-align:left;font-family:inherit}
.tpa-player--active{background:var(--c7-accent);color:var(--c7-accent-ink)}
.tpa-player--tap{border-color:var(--c7-line)}
.tpa-player__name{display:block;font-size:15px;font-weight:800;letter-spacing:-.01em}
.tpa-player__meta{display:block;margin-top:2px;font-size:12px;font-weight:700;
  color:var(--c7-ink-muted)}
.tpa-player__meta--mono{font-family:var(--c7-font-mono);font-size:11px;font-weight:600}
.tpa-player--active .tpa-player__meta{color:var(--c7-accent-dim)}
.tpa-player__tpa{font-size:26px;font-weight:800;letter-spacing:-.03em;
  font-variant-numeric:tabular-nums;line-height:1}
.tpa-player__racks{min-width:34px;height:34px;border-radius:50%;background:var(--c7-bg);
  color:var(--c7-ink);display:grid;place-items:center;font-size:14px;font-weight:800}
.tpa-player--active .tpa-player__racks{background:var(--c7-accent-bright);color:var(--c7-ink)}
.tpa-boxes{display:grid;grid-template-columns:1fr 74px;gap:8px}
.tpa-box{min-height:62px;border-radius:var(--c7-r-control);padding:8px;display:flex;
  align-items:baseline;justify-content:center;gap:6px;font-size:22px;font-weight:800;
  letter-spacing:-.02em;font-variant-numeric:tabular-nums}
.tpa-box--white{background:var(--c7-card);color:var(--c7-ink)}
.tpa-box--shaded{background:var(--c7-sunken);color:var(--c7-ink-soft)}
.tpa-box__hint{font-size:12px;font-weight:700;color:var(--c7-ink-muted)}
.pad{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}
.key{height:var(--c7-touch);border:0;border-radius:var(--c7-r-control);background:var(--c7-card);
  color:var(--c7-ink);font-family:inherit;font-size:17px;font-weight:800}
.key--tall{height:58px;font-size:19px}
.key--off{background:var(--c7-sunken);color:var(--c7-ink-faint)}
.key--foul{background:var(--c7-sunken)}
.key--game{background:var(--c7-ok-bg);color:var(--c7-ok-ink)}
.key--small{font-size:15px;color:var(--c7-ink-muted)}
.key--wide{grid-column:1 / -1;height:var(--c7-touch);font-size:14px;display:flex;
  align-items:center;justify-content:center;gap:8px}
.key__cap{display:block;font-size:9px;font-weight:800;letter-spacing:.06em;
  text-transform:uppercase;color:var(--c7-ink-muted);margin-top:1px}
.key--game .key__cap{color:var(--c7-ok-body)}
.undo{height:var(--c7-touch);border:1.5px solid var(--c7-line);border-radius:var(--c7-r-pill);
  background:transparent;color:var(--c7-ink-soft);font-family:inherit;font-size:14px;
  font-weight:700;width:100%;display:flex;align-items:center;justify-content:center;gap:8px}
.sheet{border-radius:var(--c7-r-card);background:var(--c7-card);overflow:hidden}
.sheet__rack{padding:8px var(--c7-pad-card);background:var(--c7-sunken);font-size:11px;
  font-weight:800;letter-spacing:.06em;text-transform:uppercase;color:var(--c7-ink-muted);
  display:flex;justify-content:space-between;gap:10px}
.sheet__turn{padding:10px var(--c7-pad-card);display:grid;grid-template-columns:22px 1fr auto;
  gap:10px;align-items:center;border-bottom:1px solid var(--c7-line-soft)}
.sheet__seat{width:22px;height:22px;border-radius:50%;background:var(--c7-bg);display:grid;
  place-items:center;font-size:10px;font-weight:800;color:var(--c7-ink-muted)}
.sheet__who{font-size:13px;font-weight:700}
.sheet__note{font-family:var(--c7-font-mono);font-size:13px;font-weight:700;
  color:var(--c7-ink-soft)}
.sheet__turn--won .sheet__note{color:var(--c7-ok)}
.sheet__turn--now{background:var(--c7-accent-tint);border-bottom:0}

/* --- pezzi nuovi -------------------------------------------------------- */
.phone--tall{height:auto;min-height:844px;overflow:visible;padding-bottom:28px}
.head__act{width:46px;height:46px;border:0;border-radius:50%;background:var(--c7-card);
  color:var(--c7-ink-soft);display:grid;place-items:center;flex-shrink:0}
.dock{position:absolute;left:0;right:0;bottom:0;padding:14px var(--c7-gutter) 22px;
  background:var(--c7-bg);border-top:1px solid var(--c7-line);display:grid;gap:8px}
.duo{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.half{border-radius:var(--c7-r-control);padding:14px 12px;background:rgba(242,248,247,.08);
  border:0;color:inherit;font-family:inherit;text-align:left;display:block;width:100%}
.half--on{background:var(--c7-accent-bright);color:#0D2A36}
.half__name{font-size:13px;font-weight:800;display:block}
.half__rack{font-size:48px;font-weight:800;letter-spacing:-.04em;line-height:1.05;
  display:block;font-variant-numeric:tabular-nums}
.half__tpa{font-family:var(--c7-font-mono);font-size:15px;font-weight:800;display:block}
.half__meta{font-size:11px;font-weight:700;opacity:.75;display:block;margin-top:2px}
.field{height:var(--c7-field-h);border-radius:var(--c7-r-field);background:var(--c7-card);
  display:flex;align-items:center;gap:10px;padding:0 18px;color:var(--c7-ink-faint);
  font-size:15px;font-weight:600}
.field--area{height:auto;min-height:96px;align-items:flex-start;padding:16px 18px;
  color:var(--c7-ink-soft);line-height:1.45}
.field--filled{color:var(--c7-ink)}
.hscroll{display:flex;gap:6px;overflow:hidden;margin:0 calc(var(--c7-gutter) * -1);
  padding:0 var(--c7-gutter)}
.chip{height:26px;padding:0 10px;border-radius:var(--c7-r-pill);font-size:11px;font-weight:800;
  display:inline-flex;align-items:center;background:var(--c7-bg);color:var(--c7-ink-soft);
  white-space:nowrap}
.chip--lvl{background:var(--c7-ink);color:#fff;font-family:var(--c7-font-mono)}
.chip--cat{background:var(--c7-accent-tint);color:var(--c7-accent-tint-ink)}
.chip--gesto{background:transparent;box-shadow:inset 0 0 0 1.5px var(--c7-line);color:var(--c7-ink-soft)}
.voto{display:inline-flex;align-items:center;gap:3px;font-family:var(--c7-font-mono);font-size:12px;font-weight:800;color:var(--c7-ink)}
.voto svg{color:var(--c7-oro);fill:var(--c7-oro)}
.card--accent .chip{background:rgba(242,248,247,.14);color:var(--c7-accent-ink)}
.ex{display:grid;grid-template-columns:112px 1fr;gap:12px;align-items:center}
.ex__thumb{border-radius:var(--c7-r-chip);overflow:hidden;background:var(--c7-ink)}
.ex__title{font-size:15px;font-weight:800;letter-spacing:-.01em}
.ex__line{font-size:12px;font-weight:700;color:var(--c7-ink-muted);margin-top:4px}
.kpis{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}
.kpi{background:var(--c7-card);border-radius:var(--c7-r-control);padding:12px}
.kpi__v{font-family:var(--c7-font-mono);font-size:22px;font-weight:800;letter-spacing:-.03em;
  display:flex;align-items:center;gap:4px}
.kpi__l{font-size:11px;font-weight:700;color:var(--c7-ink-muted)}
.kpi__band{font-size:11px;font-weight:800;color:var(--c7-ok-ink)}
.card--sunk .kpi{background:var(--c7-card)}
.choice{display:flex;align-items:center;gap:12px;min-height:56px;padding:10px 16px;border:0;
  border-radius:var(--c7-r-field);background:var(--c7-card);font-family:inherit;width:100%;
  text-align:left;color:var(--c7-ink)}
.choice.is-on{background:var(--c7-accent);color:var(--c7-accent-ink)}
.choice__t{font-size:14px;font-weight:800;display:block}
.choice__s{font-size:11px;font-weight:700;color:var(--c7-ink-muted);display:block}
.choice.is-on .choice__s{color:var(--c7-accent-dim)}
.choice__v{margin-left:auto;font-family:var(--c7-font-mono);font-size:20px;font-weight:800}
.big{height:96px;border:0;border-radius:var(--c7-r-card);font-family:inherit;font-size:18px;
  font-weight:800;display:flex;flex-direction:column;align-items:center;justify-content:center;
  gap:4px}
.big--no{background:var(--c7-err-bg);color:var(--c7-err-ink)}
.big--yes{background:var(--c7-ink);color:#fff}
.big__s{font-size:11px;font-weight:700;opacity:.75}
.scorepad{display:flex;align-items:center;justify-content:center;gap:22px}
.scorepad__btn{width:64px;height:64px;border-radius:50%;border:0;background:var(--c7-card);
  color:var(--c7-ink);display:grid;place-items:center}
.scorepad__v{font-size:64px;font-weight:800;letter-spacing:-.04em;line-height:1;
  font-variant-numeric:tabular-nums}
.scorepad__max{font-family:var(--c7-font-mono);font-size:18px;font-weight:700;
  color:var(--c7-ink-muted)}
.pips{display:flex;gap:5px;justify-content:center}
.pip{width:22px;height:8px;border-radius:999px;background:var(--c7-line)}
.pip.is-on{background:var(--c7-accent)}
.pip.is-miss{background:var(--c7-err)}
.stepper{display:inline-flex;align-items:center;gap:6px;background:var(--c7-bg);
  border-radius:var(--c7-r-pill);padding:4px}
.stepper button{width:40px;height:40px;border-radius:50%;border:0;background:var(--c7-card);
  color:var(--c7-ink);display:grid;place-items:center}
.stepper span{min-width:34px;text-align:center;font-family:var(--c7-font-mono);font-size:17px;
  font-weight:800}
.lvl{display:grid;grid-template-columns:repeat(5,1fr);gap:6px}
.lvl button{height:var(--c7-touch);border:0;border-radius:var(--c7-r-control);
  background:var(--c7-card);font-family:var(--c7-font-mono);font-size:16px;font-weight:800;
  color:var(--c7-ink-soft)}
.lvl button.is-on{background:var(--c7-ink);color:#fff}
.veil{position:absolute;inset:0;background:rgba(27,33,36,.45)}
.bottomsheet{position:absolute;left:0;right:0;bottom:0;background:var(--c7-bg);
  border-radius:var(--c7-r-card-lg) var(--c7-r-card-lg) 0 0;padding:22px var(--c7-gutter) 26px;
  display:grid;gap:12px;box-shadow:var(--c7-shadow-pop)}
.grab{width:44px;height:5px;border-radius:999px;background:var(--c7-line);margin:0 auto 4px}
.goal__top{display:flex;align-items:baseline;gap:8px}
.goal__t{font-size:14px;font-weight:800}
.goal__v{margin-left:auto;font-family:var(--c7-font-mono);font-size:13px;font-weight:800}
.legend{display:flex;gap:14px;font-size:11px;font-weight:700;color:var(--c7-ink-muted)}
.legend i{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:5px}
.errtab{display:grid;grid-template-columns:1fr 48px 48px;gap:0;font-size:13px;font-weight:700}
.errtab > div{padding:9px 0;border-bottom:1px solid var(--c7-line-soft)}
.errtab .n{font-family:var(--c7-font-mono);font-weight:800;text-align:right}
.seq{display:flex;gap:4px}
.seq__step{flex:1;min-width:0;display:flex;flex-direction:column;align-items:center;gap:5px}
.seq__dot{width:28px;height:28px;border-radius:50%;background:var(--c7-card);color:var(--c7-ink-muted);
  display:grid;place-items:center;font-family:var(--c7-font-mono);font-size:12px;font-weight:800}
.seq__step.is-done .seq__dot{background:var(--c7-ok-bg);color:var(--c7-ok-ink)}
.seq__step.is-now .seq__dot{background:var(--c7-accent);color:var(--c7-accent-ink)}
.seq__lab{font-size:10px;font-weight:700;color:var(--c7-ink-faint);text-align:center;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:100%}
.seq__step.is-now .seq__lab{color:var(--c7-ink);font-weight:800}
.item{display:grid;grid-template-columns:20px 64px 1fr auto;gap:10px;align-items:center;
  padding:10px 12px;background:var(--c7-card);border-radius:var(--c7-r-field)}
.item__grip{color:var(--c7-ink-faint);display:grid;gap:3px;justify-items:center}
.item__grip i{display:block;width:14px;height:2px;border-radius:2px;background:currentColor}
.item__thumb{border-radius:8px;overflow:hidden;background:var(--c7-ink)}
.item__t{font-size:13px;font-weight:800;letter-spacing:-.01em}
.item__s{font-size:11px;font-weight:700;color:var(--c7-ink-muted)}
.stepper--sm button{width:32px;height:32px}
.stepper--sm span{min-width:26px;font-size:14px}
.tool{width:100%;border:0;border-radius:var(--c7-r-control);background:transparent;color:var(--c7-ink-soft);
  font-family:inherit;font-size:11px;font-weight:700;display:flex;flex-direction:column;align-items:center;
  justify-content:center;gap:4px;height:58px}
.tool.is-on{background:var(--c7-accent);color:var(--c7-accent-ink)}
.tool--new{position:relative}
.tool--new::after{content:"";position:absolute;top:8px;right:14px;width:7px;height:7px;border-radius:50%;
  background:var(--c7-warn)}
.toolstrip{display:flex;gap:4px;background:var(--c7-card);border-radius:var(--c7-r-field);padding:4px}
.toolstrip .tool{min-width:62px;flex:1}
.stage{background:var(--c7-ink);border-radius:var(--c7-r-card);padding:14px;display:grid;place-items:center}
.toggle{width:50px;height:30px;border-radius:999px;background:var(--c7-line);position:relative;flex-shrink:0}
.toggle::after{content:"";position:absolute;top:3px;left:3px;width:24px;height:24px;border-radius:50%;
  background:var(--c7-card)}
.toggle.is-on{background:var(--c7-ok)}
.toggle.is-on::after{left:23px}
.tl{display:grid;grid-template-columns:14px 1fr;gap:0 12px}
.tl__dot{width:10px;height:10px;border-radius:50%;background:var(--c7-line);margin-top:6px;justify-self:center}
.tl__dot.is-now{background:var(--c7-accent)}
.tl__body{padding-bottom:14px}
.reg{display:grid;grid-template-columns:46px repeat(10,1fr) 38px;font-family:var(--c7-font-mono);
  font-size:13px;font-weight:800;text-align:center;background:var(--c7-card);
  border-radius:var(--c7-r-control);overflow:hidden}
.reg > *{padding:9px 0;border-bottom:1px solid var(--c7-line-soft)}
.reg .hd{background:var(--c7-ink);color:#fff;font-size:11px;padding:8px 0;border:0}
.reg .hd small{display:block;font-size:8px;font-weight:700;opacity:.7;letter-spacing:.04em}
.reg .dt{font-size:11px;color:var(--c7-ink-muted);font-weight:700}
.reg .tot{background:var(--c7-sunken)}
.reg .hi{background:var(--c7-ok-bg);color:var(--c7-ok-ink)}
.reg .lo{background:var(--c7-err-bg);color:var(--c7-err-ink)}
.reg .mt{color:var(--c7-line)}
.six{display:grid;grid-template-columns:repeat(6,1fr);gap:6px}
.six button{height:56px;border:0;border-radius:var(--c7-r-control);background:var(--c7-card);
  font-family:var(--c7-font-mono);font-size:20px;font-weight:800;color:var(--c7-ink)}
.six button.is-on{background:var(--c7-accent);color:var(--c7-accent-ink)}
.key--clear{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:1px;
  background:transparent;border:1.5px solid var(--c7-line);color:var(--c7-ink-soft)}
.key--clear.key--off{background:transparent;color:var(--c7-ink-faint);border-style:dashed}
.key--off .key__cap{color:var(--c7-ink-faint)}
.key--game.key--off,.key--foul.key--off{background:var(--c7-sunken);color:var(--c7-ink-faint)}
.hist{display:grid;grid-template-columns:1fr auto 1fr;gap:8px;align-items:center}
.hist__btn{height:var(--c7-touch);border:1.5px solid var(--c7-line);border-radius:var(--c7-r-pill);
  background:transparent;color:var(--c7-ink-soft);font-family:inherit;font-size:13px;font-weight:800;
  display:flex;align-items:center;justify-content:center;gap:6px}
.hist__btn--off{color:var(--c7-ink-faint);border-style:dashed}
.hist__pos{font-family:var(--c7-font-mono);font-size:11px;font-weight:700;color:var(--c7-ink-muted);
  padding:0 4px;white-space:nowrap}
.figs{display:flex;align-items:flex-end;gap:12px;margin-top:4px}
.fig{display:block}
.fig__k{display:block;font-size:9px;font-weight:800;letter-spacing:.08em;text-transform:uppercase;opacity:.7}
.fig__v{display:block;font-weight:800;letter-spacing:-.04em;line-height:1.05;font-variant-numeric:tabular-nums}
.half__now{margin-left:6px;font-size:9px;font-weight:800;letter-spacing:.06em;text-transform:uppercase;
  padding:2px 6px;border-radius:999px;background:rgba(13,42,54,.14)}
.half--tap{box-shadow:inset 0 0 0 1.5px rgba(242,248,247,.28);cursor:pointer}
.half__tap{display:flex;align-items:center;gap:6px;margin-top:8px;font-size:11px;font-weight:800;
  color:var(--c7-accent-bright)}
.shots{display:grid;grid-template-columns:repeat(10,1fr);gap:5px}
.shot{height:26px;border-radius:8px;display:grid;place-items:center;font-family:var(--c7-font-mono);
  font-size:12px;font-weight:800;background:var(--c7-card);color:var(--c7-ink)}
.shot--todo{background:transparent;box-shadow:inset 0 0 0 1.5px var(--c7-line)}
.shot--miss{background:var(--c7-sunken);color:var(--c7-ink-faint)}
.shot--v1{background:rgba(201,168,76,.22)}
.shot--v2{background:rgba(201,168,76,.50)}
.shot--v3{background:var(--c7-oro);color:var(--c7-oro-ink)}
.nt{display:inline-flex;align-items:baseline;gap:1px;white-space:nowrap}
.nt sup{font-size:.62em;font-weight:800;line-height:0;position:relative;top:-.55em;vertical-align:baseline;margin-right:1px}
.nt__won{display:inline-grid;place-items:center;min-width:1.7em;height:1.7em;padding:0 .2em;border-radius:999px;
  box-shadow:inset 0 0 0 2px currentColor;align-self:center}
.nt__won sup{top:-.35em}
.kickrow{min-height:13px;display:flex;justify-content:center;align-items:flex-end;line-height:1}
.ntk{display:inline-flex;flex-direction:column;align-items:center;gap:2px;line-height:1;vertical-align:middle}
.ntk__n{display:inline-grid;place-items:center;width:1.25em;height:1.25em;border-radius:50%;font-size:.58em;
  font-weight:800;box-shadow:inset 0 0 0 1.5px currentColor;line-height:1}
.nt__foul{margin-left:6px;padding:0 5px;border-radius:5px;background:var(--c7-sunken);color:var(--c7-ink-soft);
  font-size:.85em;align-self:center}
.errtab .h{font-size:10px;font-weight:800;letter-spacing:.08em;text-transform:uppercase;
  color:var(--c7-ink-muted)}
"""

CSS = BASE_CSS + EXTRA_CSS


# --------------------------------------------------------------------------
# Gusci
# --------------------------------------------------------------------------


def _nav(active):
    voci = [
        ("home", "Dashboard"),
        ("table", "Sale"),
        ("swords", "Sfide"),
        ("target", "Esercizi"),
        ("bell", "Notifiche"),
    ]
    out = []
    for icon, label in voci:
        cls = ' class="is-active"' if label == active else ""
        out.append(f'<a{cls} href="#">{ico(I[icon], 16)}{label}</a>')
    return '<nav class="mobilenav">' + "".join(out) + "</nav>"


def area_tabs(active):
    """Le quattro stanze dell'allenamento: oggi «Esami» non e' nemmeno nella
    nav mobile, e schede e andamento non esistono."""
    voci = ["Esercizi", "Schede", "Esami", "Andamento"]
    return (
        '<div class="vtabs">'
        + "".join(
            f'<button class="vtab{" is-active" if v == active else ""}">{v}</button>'
            for v in voci
        )
        + "</div>"
    )


def seqstrip(steps, current):
    """Striscia della sequenza: fatto, in corso, da fare. La stessa per una
    scheda di allenamento e per un esame."""
    out = []
    for i, label in enumerate(steps):
        cls = "is-done" if i < current else ("is-now" if i == current else "")
        mark = ico(I["check"], 12, 3) if i < current else str(i + 1)
        out.append(
            f'<div class="seq__step {cls}"><span class="seq__dot">{mark}</span>'
            f'<span class="seq__lab">{label}</span></div>'
        )
    return '<div class="seq">' + "".join(out) + "</div>"


def phone(
    title,
    sub,
    content,
    *,
    nav="Esercizi",
    actionbar="",
    dock="",
    overlay="",
    action="",
    h=844,
    avatar="MA",
    tabs="",
):
    """Guscio telefono. `nav=None` = schermata a fuoco, senza nav flottante
    (come il tabellone della partita). `h` oltre 844 = pagina che scorre,
    disegnata per intero."""
    tall = h > 844
    cls = "phone phone--tall" if tall else "phone"
    right = action or f'<div class="avatar avatar--lg">{avatar}</div>'
    navhtml = "" if (nav is None or tall) else _nav(nav)
    return f"""
<div class="{cls}" style="width: 390px; height: {h}px;">
  <header class="head">
    <button class="head__back" aria-label="Indietro">{ico(I["back"], 17)}</button>
    <div class="head__title">
      <h1>{title}</h1>
      <div class="head__sub">{sub}</div>
    </div>
    {right}
  </header>
  {tabs}
  <main class="content">
    <div class="stack">
      {content}
    </div>
  </main>
  {actionbar}
  {dock}
  {navhtml}
  {overlay}
</div>
"""


def desktop(
    title,
    sub,
    actions,
    content,
    active="Sfide individuali",
    who=("MA", "Marco Rossi", "giocatore &middot; Lv 4", "giocatore"),
):
    voci = [
        ("home", "Dashboard"),
        ("table", "Sale Biliardo"),
        ("target", "Esercizi"),
        ("list", "Esami"),
        ("swords", "Sfide individuali"),
    ]
    on = ' class="is-active"'
    links = "".join(
        f'<a{on if label == active else ""} href="#">' f"{ico(I[icon], 14)}{label}</a>"
        for icon, label in voci
    )
    return f"""
<div class="app" style="width: 1440px; height: 900px;">
  <aside class="side">
    <div class="side__brand">
      <div class="side__mark">{ico(I["target"], 15)}</div>
      <div class="grow">
        <div class="side__name">Tornei Biliardo</div>
        <div class="side__role">{who[3]}</div>
      </div>
    </div>
    <div class="side__group">
      <div class="side__grouplabel">Generale</div>
      {links}
    </div>
    <div class="side__user">
      <div class="avatar">{who[0]}</div>
      <div class="grow">
        <div style="font-size:13px;font-weight:800">{who[1]}</div>
        <div class="side__role">{who[2]}</div>
      </div>
    </div>
  </aside>
  <div class="dmain">
    <header class="dhead">
      <div class="grow">
        <h1>{title}</h1>
        <div class="head__sub">{sub}</div>
      </div>
      <div class="dhead__actions">{actions}</div>
    </header>
    <div class="dcontent">
      {content}
    </div>
  </div>
</div>
"""


def doc(title, body, w, h):
    return f"""<!doctype html>
<html lang="it">
<head>
<meta charset="utf-8">
<title>{title}</title>
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
<script type="text/x-dc" data-dc-script data-props='{{"$preview":{{"width":{w},"height":{h}}}}}'>
class Component extends DCLogic {{
  renderVals() {{ return {{}}; }}
}}
</script>
</body>
</html>
"""


# --------------------------------------------------------------------------
# Il tavolo — stessa geometria del disegnatore: 1 diamante = 100 unita',
# piano di gioco 800x400. I colori sono quelli del disegnatore, smorzati.
# --------------------------------------------------------------------------

PANNO = "#3F7F9B"
SPONDA = "#2A3033"
BALLS = {
    1: "#E0B437",
    2: "#2F5FA8",
    3: "#B23B3B",
    4: "#6A4C93",
    5: "#D9772E",
    6: "#2C8A6B",
    7: "#7A3B2E",
    8: "#1B2124",
    9: "#E0B437",
}


def ball(x, y, n=None, r=11):
    if n is None:
        return (
            f'<circle cx="{x}" cy="{y}" r="{r}" fill="#F5F7F6" stroke="#1B2124" '
            f'stroke-width="1.5"/>'
        )
    col = BALLS.get(n, "#6B7679")
    return (
        f'<circle cx="{x}" cy="{y}" r="{r}" fill="{col}"/>'
        f'<circle cx="{x}" cy="{y}" r="{r * .5}" fill="#F5F7F6"/>'
        f'<text x="{x}" y="{y + 3.2}" text-anchor="middle" font-size="9" '
        f'font-weight="800" fill="#1B2124" font-family="Manrope,sans-serif">{n}</text>'
    )


def ghost(x, y, r=11):
    return (
        f'<circle cx="{x}" cy="{y}" r="{r}" fill="none" stroke="#F5F7F6" '
        f'stroke-width="1.6" stroke-dasharray="4 3"/>'
    )


def line(x1, y1, x2, y2, dashed=True, color="#F5F7F6"):
    dash = ' stroke-dasharray="7 6"' if dashed else ""
    return (
        f'<path d="M{x1} {y1}L{x2} {y2}" stroke="{color}" stroke-width="2.2" '
        f'fill="none"{dash} stroke-linecap="round"/>'
    )


ORO = "#C9A84C"


def bullseye(x, y, r=90, numeri=None):
    """Il bersaglio: anelli che valgono PUNTI (3 al centro, poi 2, poi 1), una
    sola tinta a opacita' crescente e il valore scritto sull'anello. Niente
    anelli «verde» e «rosso»: il colore non e' nel dato (D14)."""
    out = (
        f'<circle cx="{x}" cy="{y}" r="{r}" fill="{ORO}" fill-opacity=".20" stroke="{ORO}" '
        f'stroke-width="2" stroke-dasharray="2 5" stroke-linecap="round"/>'
        f'<circle cx="{x}" cy="{y}" r="{r * .62}" fill="{ORO}" fill-opacity=".34" stroke="{ORO}" stroke-width="1.6"/>'
        f'<circle cx="{x}" cy="{y}" r="{r * .27}" fill="{ORO}" fill-opacity=".92"/>'
    )
    if numeri is None:
        numeri = r >= 100  # su un tavolo intero i numeri non si leggono
    if numeri:
        fs = max(11, r * 0.2)
        for val, k, col in (
            ("3", 0, "#2A2208"),
            ("2", 0.445, "#F5F7F6"),
            ("1", 0.81, "#F5F7F6"),
        ):
            out += (
                f'<text x="{x}" y="{y - r * k + fs * .36:.1f}" text-anchor="middle" font-size="{fs:.0f}" '
                f'font-weight="800" fill="{col}" font-family="Manrope,sans-serif">{val}</text>'
            )
    return out


def livechart(values, total, ref, top, ref_label, w=330, h=74, bars=False, pace=False):
    """Avanzamento DAL VIVO: quello fatto finora (linea o barre), i posti ancora
    vuoti, e una linea tratteggiata di confronto con se stessi."""
    x0, x1, yb, yt = 8, w - 8, h - 12, 8
    step = (x1 - x0) / (total - 1 if not bars else total)

    def y(v):
        return yb - v / top * (yb - yt)

    ry = y(ref)
    out = f'<svg viewBox="0 0 {w} {h}" width="100%" style="display:block">'
    out += f'<path d="M{x0} {yb}H{x1}" stroke="#D3D8D7" stroke-width="1"/>'
    # `pace`: il confronto e' una corsa (da zero al totale solito), non una quota
    ref_d = f"M{x0} {yb}L{x1} {ry:.1f}" if pace else f"M{x0} {ry:.1f}H{x1}"
    out += (
        f'<path d="{ref_d}" stroke="#8A9497" stroke-width="1.4" stroke-dasharray="4 4" fill="none"/>'
        f'<text x="{x1}" y="{ry - 5:.1f}" text-anchor="end" font-size="9" font-weight="800" '
        f'fill="#6B7679" font-family="Manrope,sans-serif">{ref_label}</text>'
    )
    if bars:
        bw = step * 0.62
        for i in range(total):
            cx = x0 + step * i + step / 2
            if i < len(values):
                now = i == len(values) - 1
                fill = "#8FCDE8" if now else "#2C4A52"
                edge = ' stroke="#2C4A52" stroke-width="2"' if now else ""
                out += (
                    f'<rect x="{cx - bw / 2:.1f}" y="{y(values[i]):.1f}" width="{bw:.1f}" '
                    f'height="{yb - y(values[i]):.1f}" rx="4" fill="{fill}"{edge}/>'
                )
            else:
                out += f'<rect x="{cx - bw / 2:.1f}" y="{yb - 3}" width="{bw:.1f}" height="3" rx="1.5" fill="#D3D8D7"/>'
    else:
        pts = [(x0 + step * i, y(v)) for i, v in enumerate(values)]
        for i in range(len(values), total):
            out += (
                f'<circle cx="{x0 + step * i:.1f}" cy="{yb}" r="1.6" fill="#B9C1C2"/>'
            )
        path = " ".join(
            f"{'M' if i == 0 else 'L'}{px:.1f} {py:.1f}"
            for i, (px, py) in enumerate(pts)
        )
        out += (
            f'<path d="{path}" fill="none" stroke="#2C4A52" stroke-width="2.4" stroke-linecap="round" '
            f'stroke-linejoin="round"/>'
        )
        lx, ly = pts[-1]
        out += f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="5" fill="#8FCDE8" stroke="#2C4A52" stroke-width="2"/>'
    return out + "</svg>"


def ob(x, y, r=12):
    """Bilia bersaglio senza numero, come nei diagrammi delle schede Ronin."""
    return f'<circle cx="{x}" cy="{y}" r="{r}" fill="#1B2124"/>'


def freccia(x1, y1, x2, y2, color="#1B2124"):
    import math as _m

    a = _m.atan2(y2 - y1, x2 - x1)
    hx, hy = x2 - _m.cos(a) * 16, y2 - _m.sin(a) * 16
    px, py = -_m.sin(a) * 8, _m.cos(a) * 8
    return (
        f'<path d="M{x1} {y1}L{hx:.1f} {hy:.1f}" stroke="{color}" stroke-width="3.2" '
        f'stroke-dasharray="9 7" fill="none"/>'
        f'<polygon points="{x2},{y2} {hx + px:.1f},{hy + py:.1f} {hx - px:.1f},{hy - py:.1f}" '
        f'fill="{color}"/>'
    )


def mezzo(items="", specchiato=False, width="100%"):
    """Inquadratura su mezzo tavolo (angolo in alto a sinistra), come nei
    diagrammi di Ronin. `specchiato` = la variante a sinistra."""
    flip = ";transform:scaleX(-1)" if specchiato else ""
    return (
        table(items, width=width)
        .replace('viewBox="-40 -40 880 480"', 'viewBox="-40 -40 470 470"')
        .replace(
            'style="display:block;overflow:visible"', f'style="display:block{flip}"'
        )
    )


def table(items="", vertical=False, width="100%"):
    pockets = [(0, 0), (400, 0), (800, 0), (0, 400), (400, 400), (800, 400)]
    dia = (
        [(x, -20) for x in range(100, 800, 100) if x != 400]
        + [(x, 420) for x in range(100, 800, 100) if x != 400]
        + [(-20, y) for y in (100, 200, 300)]
        + [(820, y) for y in (100, 200, 300)]
    )
    inner = (
        f'<rect x="-40" y="-40" width="880" height="480" rx="26" fill="{SPONDA}"/>'
        f'<rect x="0" y="0" width="800" height="400" fill="{PANNO}"/>'
        + "".join(
            f'<circle cx="{x}" cy="{y}" r="17" fill="#14181A"/>' for x, y in pockets
        )
        + "".join(f'<circle cx="{x}" cy="{y}" r="3" fill="#9AA6A9"/>' for x, y in dia)
        + items
    )
    if vertical:
        return (
            f'<svg viewBox="0 0 480 880" width="{width}" style="display:block">'
            f'<g transform="translate(440 40) rotate(90)">{inner}</g></svg>'
        )
    return (
        f'<svg viewBox="-40 -40 880 480" width="{width}" style="display:block;overflow:visible">'
        f"{inner}</svg>"
    )


def sparkline(values, w=320, h=84, top=100):
    n = len(values)
    pts = [
        (12 + i * (w - 24) / (n - 1), h - 10 - v / top * (h - 20))
        for i, v in enumerate(values)
    ]
    path = " ".join(
        f"{'M' if i == 0 else 'L'}{x:.1f} {y:.1f}" for i, (x, y) in enumerate(pts)
    )
    dots = "".join(
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.2" fill="#2C4A52"/>' for x, y in pts
    )
    lx, ly = pts[-1]
    return (
        f'<svg viewBox="0 0 {w} {h}" width="100%" style="display:block">'
        f'<path d="M12 {h - 10}H{w - 12}" stroke="#D3D8D7" stroke-width="1"/>'
        f'<path d="{path}" fill="none" stroke="#2C4A52" stroke-width="2.4" '
        f'stroke-linecap="round" stroke-linejoin="round"/>{dots}'
        f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="5.5" fill="#8FCDE8" stroke="#2C4A52" '
        f'stroke-width="2"/></svg>'
    )


def radar(labels, recent, prev, size=300):
    c = size / 2
    rmax = size / 2 - 46
    n = len(labels)

    def pt(i, v):
        a = -math.pi / 2 + i * 2 * math.pi / n
        return c + math.cos(a) * rmax * v / 100, c + math.sin(a) * rmax * v / 100

    def poly(vals):
        return " ".join(
            f"{x:.1f},{y:.1f}" for x, y in (pt(i, v) for i, v in enumerate(vals))
        )

    rings = "".join(
        f'<polygon points="{poly([k] * n)}" fill="none" stroke="#D3D8D7" stroke-width="1"/>'
        for k in (25, 50, 75, 100)
    )
    axes = "".join(
        f'<path d="M{c} {c}L{pt(i, 100)[0]:.1f} {pt(i, 100)[1]:.1f}" stroke="#D3D8D7" '
        f'stroke-width="1"/>'
        for i in range(n)
    )
    labs = ""
    for i, lab in enumerate(labels):
        x, y = pt(i, 128)
        labs += (
            f'<text x="{x:.1f}" y="{y + 4:.1f}" text-anchor="middle" font-size="11" '
            f'font-weight="800" fill="#3D474A" font-family="Manrope,sans-serif">{lab}</text>'
        )
    return (
        f'<svg viewBox="0 0 {size} {size}" width="100%" style="display:block">'
        f"{rings}{axes}"
        f'<polygon points="{poly(prev)}" fill="#9AA3A6" fill-opacity=".22" stroke="#9AA3A6" '
        f'stroke-width="1.6" stroke-dasharray="5 4"/>'
        f'<polygon points="{poly(recent)}" fill="#2C4A52" fill-opacity=".28" stroke="#2C4A52" '
        f'stroke-width="2.4" stroke-linejoin="round"/>{labs}</svg>'
    )
