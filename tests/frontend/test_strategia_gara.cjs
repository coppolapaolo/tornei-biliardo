/*
 * static/js/strategia_gara.js — i menu della gara seguono il formato scelto
 * (modifica della gara e modale «Nuova gara» del campionato a piazzamenti,
 * ADR-080).
 */
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const SORGENTE = fs.readFileSync(
  path.join(__dirname, "..", "..", "static", "js", "strategia_gara.js"),
  "utf8"
);

const VINCOLI = {
  amalfi: { constraints: { first_round_policies: ["random", "rating", "classification"], odd_policies: ["no", "bye", "bye_with_challenge", "trio"], anti_rematch: true, anti_rematch_required: true } },
  random: { constraints: { first_round_policies: ["random"], odd_policies: ["no", "bye", "bye_with_challenge", "trio"], anti_rematch: true, anti_rematch_required: false } },
  round_robin: { constraints: { first_round_policies: ["random"], odd_policies: ["bye"], anti_rematch: false, anti_rematch_required: false } },
};

function pagina(strategia, sistema) {
  const html = `<!doctype html><body><form>
    <select id="create_matchmaking_strategy" data-strategia-gara data-prefisso="create_"
            data-vincoli='${JSON.stringify(VINCOLI)}' data-girone="round_robin">
      <option value="amalfi">A</option><option value="random">R</option><option value="round_robin">G</option>
    </select>
    <select id="create_classification_system">
      <option value="WINS">W</option><option value="RACK">T</option><option value="POINTS">P</option>
    </select>
    <select id="create_first_round_policy">
      <option value="random">c</option><option value="rating">r</option><option value="classification">k</option>
    </select>
    <select id="create_odd_number_policy">
      <option value="no">no</option>
      <option value="bye" data-label="X a tavolino" data-label-girone="Riposo">X a tavolino</option>
      <option value="bye_with_challenge">X con prova</option>
      <option value="trio">trio</option>
    </select>
    <div id="create_anti_rematch_section" data-nascondi-se-imposto>
      <input type="checkbox" id="create_anti_rematch_enabled" name="anti_rematch_enabled">
    </div>
  </form></body>`;
  const dom = new JSDOM(html, { runScripts: "outside-only" });
  const doc = dom.window.document;
  doc.getElementById("create_matchmaking_strategy").value = strategia;
  doc.getElementById("create_classification_system").value = sistema || "WINS";
  dom.window.eval(SORGENTE);
  if (doc.readyState === "loading") {
    doc.dispatchEvent(new dom.window.Event("DOMContentLoaded"));
  }
  const $ = (id) => doc.getElementById(id);
  const scegli = (id, v) => {
    $(id).value = v;
    $(id).dispatchEvent(new dom.window.Event("change"));
  };
  return { $, scegli };
}

let controlli = 0;
function check(nome, fn) {
  fn();
  controlli += 1;
  console.log("  ok -", nome);
}

console.log("strategia_gara.js");

check("Amalfi: anti-reincontro acceso, casella nascosta ma nel modulo", () => {
  const p = pagina("amalfi");
  const anti = p.$("create_anti_rematch_enabled");
  assert.strictEqual(anti.checked, true);
  assert.strictEqual(anti.disabled, false);
  assert.strictEqual(p.$("create_anti_rematch_section").hidden, true);
});

check("casuale: l'anti-reincontro è una scelta", () => {
  const p = pagina("random");
  assert.strictEqual(p.$("create_anti_rematch_section").hidden, false);
  assert.strictEqual(p.$("create_anti_rematch_enabled").disabled, false);
});

check("girone: solo il riposo, col suo nome, e primo abbinamento casuale", () => {
  const p = pagina("amalfi");
  p.scegli("create_first_round_policy", "rating");
  p.scegli("create_odd_number_policy", "trio");
  p.scegli("create_matchmaking_strategy", "round_robin");
  assert.strictEqual(p.$("create_odd_number_policy").value, "bye");
  assert.strictEqual(p.$("create_first_round_policy").value, "random");
  const bye = p.$("create_odd_number_policy").querySelector('option[value="bye"]');
  assert.strictEqual(bye.textContent, "Riposo");
  assert.strictEqual(p.$("create_anti_rematch_enabled").disabled, true);
  assert.strictEqual(p.$("create_anti_rematch_section").hidden, true);
});

check("coi triangoli totali la X a tavolino semplice sparisce", () => {
  const p = pagina("random", "WINS");
  assert.strictEqual(p.$("create_odd_number_policy").value, "no");
  p.scegli("create_odd_number_policy", "bye");
  p.scegli("create_classification_system", "RACK");
  const bye = p.$("create_odd_number_policy").querySelector('option[value="bye"]');
  assert.strictEqual(bye.disabled, true);
  assert.notStrictEqual(p.$("create_odd_number_policy").value, "bye");
});

check("il cambio dei dispari emette change", () => {
  const p = pagina("random");
  p.scegli("create_odd_number_policy", "trio");
  let visto = null;
  p.$("create_odd_number_policy").addEventListener("change", (e) => { visto = e.target.value; });
  p.scegli("create_matchmaking_strategy", "round_robin");
  assert.strictEqual(visto, "bye");
});

console.log(`${controlli} controlli superati`);
