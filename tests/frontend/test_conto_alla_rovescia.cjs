/**
 * Headless automation per static/js/conto_alla_rovescia.js (ADR-077).
 *
 * 1. il testo: minuti:secondi prima dello scadere, «Tempo scaduto +N'» dopo;
 * 2. allo scadere la pastiglia prende `is-scaduto` e la card che la contiene
 *    `c7-card--warn` — solo visivo, nient'altro;
 * 3. lo scarto fra l'orologio del server e quello del dispositivo si corregge:
 *    un telefono avanti di dieci minuti mostra lo stesso tempo degli altri.
 *
 * Run:  cd tests/frontend && npm install && npm test
 */
const fs = require("fs");
const path = require("path");
const assert = require("assert");
const { JSDOM } = require("jsdom");

const SRC = fs.readFileSync(
  path.join(__dirname, "..", "..", "static", "js", "conto_alla_rovescia.js"),
  "utf8"
);

function pagina(inizio, adessoServer) {
  const html =
    '<article class="c7-card" data-timer-card>' +
    '<span class="c7-timer" data-timer-minuti="30" data-timer-inizio="' + inizio + '"' +
    ' data-timer-adesso="' + adessoServer + '" data-et-scaduto="Tempo scaduto">' +
    '<span data-timer-testo></span></span></article>';
  const dom = new JSDOM("<!doctype html><body>" + html + "</body>", {
    runScripts: "outside-only",
  });
  return dom.window;
}

// Lo script parte a DOMContentLoaded se il documento sta ancora caricando:
// qui lo si fa partire subito, come nella pagina vera dopo il parsing.
function esegui(w) {
  w.eval(SRC);
  if (w.document.readyState === "loading") {
    w.document.dispatchEvent(new w.Event("DOMContentLoaded"));
  }
}

// 1. Il testo
{
  const w = pagina("2026-10-06T20:00:00Z", "2026-10-06T20:00:00Z");
  w.eval(SRC);
  const t = w.c7ContoAllaRovescia.testo;
  assert.strictEqual(t(6 * 60 * 1000, "Tempo scaduto"), "6:00");
  assert.strictEqual(t(65 * 1000, "Tempo scaduto"), "1:05");
  assert.strictEqual(t(0, "Tempo scaduto"), "Tempo scaduto");
  assert.strictEqual(t(-2 * 60 * 1000 - 5000, "Tempo scaduto"), "Tempo scaduto +2'");
  console.log("ok  testo prima e dopo lo scadere");
}

// 2 e 3. Lo scadere, con l'orologio del dispositivo avanti di dieci minuti
{
  const adessoVero = Date.parse("2026-10-06T20:31:00Z");
  const w = pagina("2026-10-06T20:00:00Z", "2026-10-06T20:31:00Z");
  // Il dispositivo segna dieci minuti in più del server.
  const realeNow = w.Date.now;
  w.Date.now = () => adessoVero + 10 * 60 * 1000;
  esegui(w);
  const el = w.document.querySelector(".c7-timer");
  assert.strictEqual(el.querySelector("[data-timer-testo]").textContent, "Tempo scaduto +1'");
  assert.ok(el.classList.contains("is-scaduto"));
  assert.ok(w.document.querySelector("article").classList.contains("c7-card--warn"));
  w.Date.now = realeNow;
  console.log("ok  scaduto, card in avviso, scarto dell'orologio corretto");
}

// Prima dello scadere niente avviso
{
  const w = pagina("2026-10-06T20:00:00Z", "2026-10-06T20:24:00Z");
  w.Date.now = () => Date.parse("2026-10-06T20:24:00Z");
  esegui(w);
  const el = w.document.querySelector(".c7-timer");
  assert.strictEqual(el.querySelector("[data-timer-testo]").textContent, "6:00");
  assert.ok(!el.classList.contains("is-scaduto"));
  assert.ok(!w.document.querySelector("article").classList.contains("c7-card--warn"));
  console.log("ok  prima dello scadere nessun avviso");
}
console.log("test_conto_alla_rovescia: tutto ok");
process.exit(0);
