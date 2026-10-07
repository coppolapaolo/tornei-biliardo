/*
 * static/js/campo_punti.js — il campo «Punti in classifica» si vede solo col
 * sistema a punti, e nascosto non si manda né si valida (ADR-078).
 */
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const SORGENTE = fs.readFileSync(
  path.join(__dirname, "..", "..", "static", "js", "campo_punti.js"),
  "utf8"
);

function pagina(sistema) {
  const html = `<!doctype html><body>
    <select id="sistema"><option value="WINS">W</option><option value="POINTS">P</option></select>
    <fieldset data-punti data-sistema-da="#sistema">
      <input name="points_win" value="3" required>
    </fieldset></body>`;
  const dom = new JSDOM(html, { runScripts: "outside-only" });
  const doc = dom.window.document;
  doc.getElementById("sistema").value = sistema;
  dom.window.eval(SORGENTE);
  // Fuori dal browser DOMContentLoaded arriva dopo: si avvia a mano.
  dom.window.c7CampoPunti.avvia();
  return {
    campo: doc.querySelector("[data-punti]"),
    input: doc.querySelector("input"),
    scegli: (v) => {
      const sel = doc.getElementById("sistema");
      sel.value = v;
      sel.dispatchEvent(new dom.window.Event("change"));
    },
  };
}

let controlli = 0;
function check(nome, fn) {
  fn();
  controlli += 1;
  console.log("  ok -", nome);
}

console.log("campo_punti.js");

check("a vittorie il campo è nascosto e spento", () => {
  const p = pagina("WINS");
  assert.strictEqual(p.campo.hidden, true);
  assert.strictEqual(p.input.disabled, true);
});

check("a punti si vede, e segue il selettore", () => {
  const p = pagina("POINTS");
  assert.strictEqual(p.campo.hidden, false);
  assert.strictEqual(p.input.disabled, false);
  p.scegli("WINS");
  assert.strictEqual(p.campo.hidden, true);
  p.scegli("POINTS");
  assert.strictEqual(p.input.disabled, false);
});

console.log(`${controlli} controlli superati`);
