# Frontend headless tests (jsdom)

Headless automation for the deterministic client-side JavaScript: the
gamification badge (`test_gamification_badge.cjs`), the entrants search
(`test_iscritti_ricerca.cjs`), the live-polling cursor
(`test_polling_cursore.cjs`), the X-challenge section of the competition form
(`test_x_challenge_section.cjs`), the help mode of `static/js/help-hints.js`
(`test_help_hints.cjs`: activator, «?» placement, bubble, once-per-screen
introduction as a real modal dialog, switch, no localStorage) and the score
digit that pops when it changes (`test_score_pop.cjs`: `segna` animates only
on a real change and replays, `pagehide` saves, only changed digits pop after
a reload of the same page, other page / stale save / denied storage stay
still).

The first and oldest file covers the **gamification frontend logic** — the
*automatable* subset of the Gamification V3 manual test report
(`docs/reference/GAMIFICATION_V3_MANUAL_TEST_REPORT.md`).

These tests load the real `static/js/gamification.js` inside a
[jsdom](https://github.com/jsdom/jsdom) window and assert the deterministic,
non-visual behaviour of the §11 / §11-quater intensity scale and the
anti-invasiveness toast cap:

- XP events produce **no** toast (badge-only: count-up + pulse);
- level-up shows **exactly one** toast, **exempt** from the session cap, and
  updates the badge level + glow;
- the cap allows **at most one** capped toast (achievement/streak/quest) per
  browser session, resets on a new session, and **degrades gracefully** when
  `sessionStorage` is unavailable (privacy mode);
- `prefers-reduced-motion` disables the pulse and makes the XP value update
  instantly;
- confetti fires **only** on strong events (level-up, rare+ achievement);
- welcome / nudge / unlock toasts still fire.

## What this does NOT cover (human gate)

Animation smoothness, real browser rendering, cross-tab session reset, the OS-level
reduced-motion toggle, confetti visuals, responsive layout and the notification
center remain a **manual browser gate** — see
`docs/reference/GAMIFICATION_V3_MANUAL_TESTS.md`.

## Run

```bash
cd tests/frontend
npm install      # installs jsdom locally (node_modules is gitignored)
npm test         # runs every suite listed in package.json, in order
```

Exit code is non-zero if any check fails; the summary lists every check.

> Note: this is a standalone Node toolchain, intentionally decoupled from the
> Python `pytest` suite (no Node in CI yet). Run it manually after touching
> `static/js/gamification.js` or the badge markup in `templates/base.html`.
