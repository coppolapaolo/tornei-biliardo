/**
 * Headless automation per static/js/challenge-form.js — il modulo
 * dell'esercizio.
 *
 * 1. scelte tre abilità, le altre si spengono; tolta una, si riaccendono;
 * 2. il livello si può spegnere toccando di nuovo la cifra accesa;
 * 3. «riuscito o no» nasconde e svuota il punteggio massimo;
 * 4. le varianti si aggiungono e si tolgono;
 * 5. un 409 con `needs_decision` apre il foglio, e la scelta rispedisce lo
 *    stesso modulo con `on_evidence`; un invio nuovo riparte da «chiedi».
 *
 * Run:  cd tests/frontend && npm install && npm test
 */
const fs = require("fs");
const path = require("path");
const assert = require("assert");
const { JSDOM } = require("jsdom");

const SRC = fs.readFileSync(
  path.join(__dirname, "..", "..", "static", "js", "challenge-form.js"),
  "utf8"
);

const HTML = `
<form data-challenge-form action="/challenges/1/edit">
  <input type="hidden" name="on_evidence" value="">
  <input type="hidden" name="then" value="">
  <input name="title" value="Spot"><textarea name="description">x</textarea>
  <div data-pick-max="3">
    ${["a", "b", "c", "d"].map((v) => `<label class="c7-pill"><input type="checkbox" name="abilita" value="${v}"></label>`).join("")}
  </div>
  <div data-radio-off>
    <label><input type="radio" name="declared_level" value="" checked></label>
    <label><input type="radio" name="declared_level" value="2"></label>
  </div>
  <label><input type="radio" name="scoring_type" value="pass_fail"></label>
  <label><input type="radio" name="scoring_type" value="score" checked></label>
  <div id="maxScoreRow"><input id="max_score" name="max_score" value="10"></div>
  <div data-variants>
    <template data-variant-template><div data-variant-row>
      <input type="hidden" name="variant_id" value=""><input name="variant_label">
      <button type="button" data-variant-remove></button></div></template>
    <button type="button" data-variant-add></button>
  </div>
  <button type="submit" id="save"></button>
</form>
<div id="evidenceSheet">
  <h3 data-evidence-title></h3><div data-evidence-text></div>
  <button data-evidence-choice="copy"></button>
  <button data-evidence-choice="overwrite"></button>
</div>`;

function pagina(risposte) {
  const dom = new JSDOM(HTML, { runScripts: "outside-only", url: "http://x/challenges/1/edit" });
  const w = dom.window;
  const inviati = [];
  w.fetch = (url, opts) => {
    inviati.push({ url, on_evidence: opts.body.get("on_evidence") });
    const r = risposte.shift();
    return Promise.resolve({ status: r.status, json: () => Promise.resolve(r.body) });
  };
  w.showError = (t) => (w.__errore = t);
  w.eval(SRC);
  return { w, doc: w.document, inviati };
}
const tick = () => new Promise((r) => setTimeout(r, 0));

(async () => {
  // 1. al più tre abilità
  {
    const { doc, w } = pagina([]);
    const box = [...doc.querySelectorAll('input[name="abilita"]')];
    box.slice(0, 3).forEach((b) => { b.checked = true; b.dispatchEvent(new w.Event("change", { bubbles: true })); });
    assert.strictEqual(box[3].disabled, true);
    assert.ok(box[3].closest("label").classList.contains("is-off"));
    box[0].checked = false;
    box[0].dispatchEvent(new w.Event("change", { bubbles: true }));
    assert.strictEqual(box[3].disabled, false);
  }

  // 2. il livello si spegne
  {
    const { doc } = pagina([]);
    const due = doc.querySelector('input[name="declared_level"][value="2"]');
    due.click();
    assert.ok(due.checked);
    due.click();
    assert.ok(doc.querySelector('input[name="declared_level"][value=""]').checked);
  }

  // 3. riuscito o no: il massimo sparisce e si svuota
  {
    const { doc } = pagina([]);
    doc.querySelector('input[value="pass_fail"]').click();
    assert.ok(doc.getElementById("maxScoreRow").classList.contains("d-none"));
    assert.strictEqual(doc.getElementById("max_score").value, "");
  }

  // 4. varianti
  {
    const { doc } = pagina([]);
    doc.querySelector("[data-variant-add]").click();
    doc.querySelector("[data-variant-add]").click();
    assert.strictEqual(doc.querySelectorAll("[data-variant-row]").length, 2);
    doc.querySelector("[data-variant-remove]").click();
    assert.strictEqual(doc.querySelectorAll("[data-variant-row]").length, 1);
  }

  // 5. la domanda, la risposta, e il nuovo invio che riparte da «chiedi»
  {
    const { doc, w, inviati } = pagina([
      { status: 409, body: { success: false, needs_decision: true, title: "Ha già 9 prove", text: "…" } },
      { status: 200, body: { success: true, redirect_url: "http://x/challenges/1/edit#fatto" } },
      { status: 422, body: { success: false, error: "no" } },
    ]);
    doc.getElementById("save").click();
    await tick(); await tick(); await tick();
    assert.strictEqual(doc.querySelector("[data-evidence-title]").textContent, "Ha già 9 prove");
    assert.ok(doc.getElementById("evidenceSheet").classList.contains("show"));

    doc.querySelector('[data-evidence-choice="copy"]').click();
    await tick(); await tick(); await tick();
    assert.deepStrictEqual(inviati.map((i) => i.on_evidence), ["", "copy"]);
    assert.ok(w.location.href.endsWith("#fatto"));

    doc.getElementById("save").click();
    await tick(); await tick(); await tick();
    assert.strictEqual(inviati[2].on_evidence, "");
    assert.strictEqual(w.__errore, "no");
  }

  console.log("test_challenge_form.cjs: ok");
})().catch((e) => { console.error(e); process.exit(1); });
