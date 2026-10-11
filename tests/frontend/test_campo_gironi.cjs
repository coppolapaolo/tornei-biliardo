/*
 * static/js/campo_gironi.js — la fase finale dopo i gironi nei moduli
 * (ADR-081): si vede solo con più gironi, qualificati/finalina/limite solo
 * col tabellone, i minuti solo con «Un limite diverso». Un campo nascosto è
 * spento, quindi non arriva al server.
 */
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const SORGENTE = fs.readFileSync(
  path.join(__dirname, "..", "..", "static", "js", "campo_gironi.js"),
  "utf8"
);

function pagina({ tetto = "2", fase = "nessuna", modo = "gironi" } = {}) {
  const html = `<!doctype html><body>
    <select id="strategia"><option value="amalfi">A</option><option value="round_robin" selected>R</option></select>
    <div data-gironi data-strategia-da="#strategia" data-girone="round_robin">
      <select name="max_groups" data-gironi-tetto>
        <option value="1" ${tetto === "1" ? "selected" : ""}>1</option>
        <option value="2" ${tetto === "2" ? "selected" : ""}>2</option>
      </select>
      <div data-gironi-se-piu>
        <div data-fase-finale>
          <label class="c7-choice"><input type="radio" name="final_phase_mode" value="nessuna" ${fase === "nessuna" ? "checked" : ""}></label>
          <label class="c7-choice"><input type="radio" name="final_phase_mode" value="tabellone" data-fase-tabellone ${fase === "tabellone" ? "checked" : ""}></label>
          <div data-fase-se-tabellone>
            <select name="qualifiers_per_group"><option value="2">2</option></select>
            <input type="checkbox" name="third_place_match">
            <div data-fase-regola>
              <select name="final_phase_time_limit" data-fase-regola-modo>
                <option value="gironi" ${modo === "gironi" ? "selected" : ""}>g</option>
                <option value="nessuno" ${modo === "nessuno" ? "selected" : ""}>n</option>
                <option value="minuti" data-fase-regola-valore ${modo === "minuti" ? "selected" : ""}>m</option>
              </select>
              <div data-fase-regola-campo><input name="final_phase_time_limit_minutes"></div>
            </div>
            <div data-fase-regola>
              <select name="final_distance_mode" data-fase-regola-modo>
                <option value="come" selected>c</option>
                <option value="altra" data-fase-regola-valore>a</option>
              </select>
              <div data-fase-regola-campo id="distanzaFinale"><input name="final_distance"></div>
            </div>
          </div>
        </div>
      </div>
    </div></body>`;
  const dom = new JSDOM(html, { runScripts: "outside-only" });
  const win = dom.window;
  const doc = win.document;
  const eventi = [];
  doc.addEventListener("gara:fase-finale", (e) => eventi.push(e.detail.tabellone));
  win.eval(SORGENTE);
  // Fuori dal browser DOMContentLoaded è già passato: si rilancia a mano.
  doc.dispatchEvent(new win.Event("DOMContentLoaded"));
  const campo = (nome) => doc.querySelector(`[name="${nome}"]`);
  const cambia = (el, valore) => {
    el.value = valore;
    el.dispatchEvent(new win.Event("change"));
  };
  return {
    win,
    eventi,
    campo,
    seTabellone: doc.querySelector("[data-fase-se-tabellone]"),
    minuti: doc.querySelector("[data-fase-regola-campo]"),
    tetto: (v) => cambia(campo("max_groups"), v),
    strategia: (v) => cambia(doc.getElementById("strategia"), v),
    modo: (v) => cambia(campo("final_phase_time_limit"), v),
    fase: (v) => {
      const radio = doc.querySelector(`[name="final_phase_mode"][value="${v}"]`);
      radio.checked = true;
      radio.dispatchEvent(new win.Event("change"));
    },
  };
}

let controlli = 0;
function check(nome, fn) {
  fn();
  controlli += 1;
  console.log("  ok -", nome);
}

console.log("campo_gironi.js — fase finale");

check("senza tabellone qualificati, finalina e limite sono nascosti e spenti", () => {
  const p = pagina();
  assert.strictEqual(p.seTabellone.hidden, true);
  assert.strictEqual(p.campo("qualifiers_per_group").disabled, true);
  assert.strictEqual(p.campo("third_place_match").disabled, true);
  assert.strictEqual(p.win.gironiConTabellone(), false);
});

check("col tabellone si accendono, e i minuti solo con un limite diverso", () => {
  const p = pagina();
  p.fase("tabellone");
  assert.strictEqual(p.seTabellone.hidden, false);
  assert.strictEqual(p.campo("qualifiers_per_group").disabled, false);
  assert.strictEqual(p.campo("third_place_match").disabled, false);
  assert.strictEqual(p.minuti.hidden, true);
  assert.strictEqual(p.campo("final_phase_time_limit_minutes").disabled, true);
  p.modo("minuti");
  assert.strictEqual(p.minuti.hidden, false);
  assert.strictEqual(p.campo("final_phase_time_limit_minutes").disabled, false);
  assert.strictEqual(p.win.gironiConTabellone(), true);
  assert.strictEqual(p.eventi[p.eventi.length - 1], true);
});

check("col girone unico la fase finale si spegne tutta", () => {
  const p = pagina({ fase: "tabellone", modo: "minuti" });
  assert.strictEqual(p.win.gironiConTabellone(), true);
  p.tetto("1");
  assert.strictEqual(p.campo("final_phase_mode").disabled, true);
  assert.strictEqual(p.seTabellone.hidden, true);
  assert.strictEqual(p.campo("final_phase_time_limit_minutes").disabled, true);
  assert.strictEqual(p.win.gironiConTabellone(), false);
  assert.strictEqual(p.eventi[p.eventi.length - 1], false);
});

check("fuori dal girone all'italiana non c'è tabellone dopo i gironi", () => {
  const p = pagina({ fase: "tabellone" });
  p.strategia("amalfi");
  assert.strictEqual(p.win.gironiConTabellone(), false);
  assert.strictEqual(p.campo("qualifiers_per_group").disabled, true);
});

check("la distanza della finale segue il tabellone e la sua voce", () => {
  const p = pagina();
  const doc = p.win.document;
  const cambia = (el, v) => { el.value = v; el.dispatchEvent(new p.win.Event("change")); };
  assert.strictEqual(p.campo("final_distance_mode").disabled, true);
  p.fase("tabellone");
  assert.strictEqual(p.campo("final_distance_mode").disabled, false);
  assert.strictEqual(doc.getElementById("distanzaFinale").hidden, true);
  assert.strictEqual(p.campo("final_distance").disabled, true);
  cambia(p.campo("final_distance_mode"), "altra");
  assert.strictEqual(doc.getElementById("distanzaFinale").hidden, false);
  assert.strictEqual(p.campo("final_distance").disabled, false);
  // Il limite della fase finale resta indipendente.
  assert.strictEqual(p.minuti.hidden, true);
  p.tetto("1");
  assert.strictEqual(p.campo("final_distance").disabled, true);
});

console.log(`${controlli} controlli superati`);
