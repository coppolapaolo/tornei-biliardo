/**
 * Headless automation for the Gamification V3 frontend logic.
 *
 * Loads the REAL static/js/gamification.js inside a jsdom window and asserts the
 * deterministic, non-visual behaviours of the §11/§11-quater intensity scale and
 * anti-invasiveness cap. This covers the *automatable* subset of the manual test
 * report (docs/reference/GAMIFICATION_V3_MANUAL_TEST_REPORT.md). The purely
 * visual rows (animation smoothness, real rendering, cross-tab, OS-level reduced
 * motion, confetti visuals, notification center) remain a human gate.
 *
 * Covered report rows:
 *   2.1, 2.4  XP event -> NO toast (only badge)
 *   2.2, 2.3  XP -> count-up + pulse (motion on)
 *   3.1..3.4  level-up -> glow + level update + exactly one toast, exempt from cap
 *   5.1, 5.2  cap: max 1 capped toast / session
 *   5.3       level-up exempt from cap
 *   5.4       cap reset on new session (sessionStorage)
 *   5.5       privacy mode (sessionStorage throws) -> do not block
 *   6.1, 6.2  prefers-reduced-motion -> no pulse class, instant value
 *   6.4       motion on -> pulse class restored
 *   8.1       confetti only on strong events
 *   10.2,10.3 welcome / nudge / unlock still toast
 *
 * Run:  cd tests/frontend && npm install && npm test
 * (jsdom is the only dependency; see package.json)
 */
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const GAMI_JS = path.join(__dirname, "..", "..", "static", "js", "gamification.js");
const SRC = fs.readFileSync(GAMI_JS, "utf8");

// In-memory footer exposing internal class bindings for spying (does not touch
// the source file).
const FOOTER = `
;window.__GamificationToast = GamificationToast;
window.__GamificationBadge = GamificationBadge;
window.__GAMI_CAPPED_TOAST_KEY = GAMI_CAPPED_TOAST_KEY;
`;

const BADGE_HTML = `
<div id="gami-badge" class="gami-badge"
     data-level="3" data-current-xp="120" data-xp-next="300" data-progress="40">
  <span class="gami-badge-ring" style="--gami-progress: 40"><i class="fas fa-trophy"></i></span>
  <span id="gami-badge-level">3</span>
  <span><span id="gami-badge-xp">120</span> XP</span>
</div>
<script type="application/json" id="gamification-config">{"i18n":{}}</script>
`;

/**
 * Build an isolated environment with the real gamification.js loaded.
 * @param {{reducedMotion?: boolean, breakSessionStorage?: boolean, noSpy?: boolean}} opts
 */
function makeEnv(opts = {}) {
  const dom = new JSDOM(`<!DOCTYPE html><html><body>${BADGE_HTML}</body></html>`, {
    runScripts: "dangerously",
    pretendToBeVisual: true, // provides requestAnimationFrame
    url: "https://localhost/", // real origin so sessionStorage works (not about:blank)
  });
  const win = dom.window;

  // matchMedia (jsdom doesn't implement it) — controls reducedMotion.
  win.matchMedia = (q) => ({
    matches: !!opts.reducedMotion,
    media: q,
    onchange: null,
    addListener() {}, removeListener() {},
    addEventListener() {}, removeEventListener() {}, dispatchEvent() { return false; },
  });

  // Privacy mode: a sessionStorage that throws on every access.
  if (opts.breakSessionStorage) {
    Object.defineProperty(win, "sessionStorage", {
      configurable: true,
      value: {
        getItem() { throw new Error("blocked"); },
        setItem() { throw new Error("blocked"); },
        removeItem() { throw new Error("blocked"); },
        clear() { throw new Error("blocked"); },
      },
    });
  }

  // Confetti spy (the code guards on `typeof ConfettiEffect !== 'undefined'`).
  const confetti = [];
  win.ConfettiEffect = { fire: (t) => confetti.push(t) };

  // Load the real script + exposure footer in global scope.
  win.eval(SRC + FOOTER);

  // Spy on toast *requests* (independent of the async render queue). Skipped for
  // confetti tests (noSpy) so the real show* methods run and fire ConfettiEffect.
  const toasts = { xp: 0, levelup: 0, achievement: 0, streak: 0, quest: 0, welcome: 0, nudge: 0, unlock: 0, streakLost: 0 };
  if (!opts.noSpy) {
    const P = win.__GamificationToast.prototype;
    P.showXPGain = () => { toasts.xp++; };
    P.showLevelUp = () => { toasts.levelup++; };
    P.showAchievement = () => { toasts.achievement++; };
    P.showStreak = () => { toasts.streak++; };
    P.showQuest = () => { toasts.quest++; };
    P.showWelcome = () => { toasts.welcome++; };
    P.showNudge = () => { toasts.nudge++; };
    P.showUnlock = () => { toasts.unlock++; };
    P.showStreakLost = () => { toasts.streakLost++; };
  }

  return { win, dom, confetti, toasts };
}

// ---- tiny assertion harness ----
let passed = 0, failed = 0;
const failures = [];
function check(name, cond, detail) {
  if (cond) { passed++; console.log(`  PASS  ${name}`); }
  else { failed++; failures.push(name + (detail ? ` — ${detail}` : "")); console.log(`  FAIL  ${name}${detail ? " — " + detail : ""}`); }
}
function section(t) { console.log(`\n== ${t} ==`); }

// ============================================================
section("XP -> only badge, no toast (report 2.1 / 2.4)");
{
  const { win, toasts } = makeEnv();
  win.showGamificationEvent("xp", { amount: 50 });
  check("XP event produces NO toast", Object.values(toasts).every((v) => v === 0), JSON.stringify(toasts));
  check("badge dataset current-xp target preserved (120)", win.document.getElementById("gami-badge").dataset.currentXp === "120");
  check("xp element exists for count-up", !!win.document.getElementById("gami-badge-xp"));
}

// ============================================================
section("XP count-up + pulse (motion on) vs instant (reduced) (report 2.2 / 2.3 / 6.1 / 6.2 / 6.4)");
{
  const { win } = makeEnv({ reducedMotion: true });
  win.showGamificationEvent("xp", { amount: 30 }); // target 120, from 90
  const badge = win.document.getElementById("gami-badge");
  const xpEl = win.document.getElementById("gami-badge-xp");
  check("reduced-motion: no badge-pulse class", !badge.classList.contains("badge-pulse"));
  check("reduced-motion: XP value instant == target (120)", xpEl.textContent === "120", `got ${xpEl.textContent}`);
}
{
  const { win } = makeEnv({ reducedMotion: false });
  win.showGamificationEvent("xp", { amount: 30 });
  const badge = win.document.getElementById("gami-badge");
  check("motion on: badge-pulse class added", badge.classList.contains("badge-pulse"));
}

// ============================================================
section("level-up -> 1 toast, exempt from cap; updates badge (report 3.1..3.4 / 5.3)");
{
  const { win, toasts } = makeEnv({ reducedMotion: false });
  win.showGamificationEvent("achievement", { name: "A", description: "d", rarity: "common" }); // consumes cap
  win.showGamificationEvent("streak", { count: 4 }); // suppressed by cap
  win.showGamificationEvent("levelup", { level: 5, title: "T" }); // exempt

  check("achievement (1st capped) shows 1 toast", toasts.achievement === 1, JSON.stringify(toasts));
  check("streak (2nd capped) suppressed (0 toast)", toasts.streak === 0, JSON.stringify(toasts));
  check("level-up shows exactly 1 toast (exempt from cap)", toasts.levelup === 1, JSON.stringify(toasts));

  const badge = win.document.getElementById("gami-badge");
  check("level-up updates badge level number to 5", win.document.getElementById("gami-badge-level").textContent === "5");
  check("level-up updates data-level to 5", badge.dataset.level === "5");
  check("level-up adds glow class (badge-levelup)", badge.classList.contains("badge-levelup"));
}

// ============================================================
section("cap: max 1 capped toast / session (report 5.1 / 5.2)");
{
  const { win, toasts } = makeEnv();
  win.showGamificationEvent("achievement", { name: "A", description: "d" });
  win.showGamificationEvent("streak", { count: 4 });
  win.showGamificationEvent("quest", { name: "Q", description: "d" });
  check("only 1 capped toast across achievement+streak+quest", toasts.achievement + toasts.streak + toasts.quest === 1, JSON.stringify(toasts));
  check("first event (achievement) is the one shown", toasts.achievement === 1);
}

// ============================================================
section("cap reset on new session (report 5.4)");
{
  const { win, toasts } = makeEnv();
  win.showGamificationEvent("achievement", { name: "A", description: "d" }); // shown, slot consumed
  win.showGamificationEvent("quest", { name: "Q", description: "d" }); // suppressed
  check("session1: 1 achievement + 0 quest", toasts.achievement === 1 && toasts.quest === 0, JSON.stringify(toasts));
  win.sessionStorage.removeItem(win.__GAMI_CAPPED_TOAST_KEY); // simulate new tab/session
  win.showGamificationEvent("quest", { name: "Q2", description: "d" });
  check("session2 (cleared): quest toast shown again", toasts.quest === 1, JSON.stringify(toasts));
}

// ============================================================
section("privacy mode: sessionStorage throws -> do not block (report 5.5)");
{
  const { win, toasts } = makeEnv({ breakSessionStorage: true });
  win.showGamificationEvent("achievement", { name: "A", description: "d" });
  win.showGamificationEvent("streak", { count: 4 });
  check("privacy: both capped toasts shown (no blocking)", toasts.achievement === 1 && toasts.streak === 1, JSON.stringify(toasts));
}

// ============================================================
section("confetti only on strong events (report 8.1) — real show* methods (noSpy)");
{
  const { win, confetti } = makeEnv({ noSpy: true });
  win.showGamificationEvent("xp", { amount: 10 });
  check("XP fires NO confetti", confetti.length === 0, JSON.stringify(confetti));
}
{
  const { win, confetti } = makeEnv({ noSpy: true });
  win.showGamificationEvent("achievement", { name: "A", description: "d", rarity: "common" });
  check("common achievement fires NO confetti", confetti.length === 0, JSON.stringify(confetti));
}
{
  const { win, confetti } = makeEnv({ noSpy: true });
  win.showGamificationEvent("achievement", { name: "A", description: "d", rarity: "rare" });
  check("rare achievement fires confetti", confetti.includes("rare"), JSON.stringify(confetti));
}
{
  const { win, confetti } = makeEnv({ noSpy: true });
  win.showGamificationEvent("levelup", { level: 5, title: "T" });
  check("level-up fires confetti('level')", confetti.includes("level"), JSON.stringify(confetti));
}

// ============================================================
section("welcome / nudge / unlock still toast (report 10.2 / 10.3)");
{
  const { win, toasts } = makeEnv();
  win.showGamificationEvent("welcome", { username: "Paolo" });
  check("welcome shows toast", toasts.welcome === 1);
}
{
  const { win, toasts } = makeEnv();
  win.showGamificationEvent("nudge", { code: "c", name: "n", description: "d" });
  check("nudge shows toast (actionable, not capped)", toasts.nudge === 1);
}
{
  const { win, toasts } = makeEnv();
  win.showGamificationEvent("unlock", { code: "c", name: "n", description: "d" });
  check("unlock shows toast", toasts.unlock === 1);
}

// ============================================================
section("console helpers exposed (report intestazione)");
{
  const { win } = makeEnv();
  check("window.showGamificationEvent is a function", typeof win.showGamificationEvent === "function");
  check("window.testGamificationEffects is a function", typeof win.testGamificationEffects === "function");
}

// ---- summary ----
console.log(`\n==================== SUMMARY ====================`);
console.log(`PASS: ${passed}   FAIL: ${failed}`);
if (failed) {
  console.log(`\nFailures:`);
  failures.forEach((f) => console.log(`  - ${f}`));
  process.exit(1);
}
console.log(`All automatable checks green.`);
