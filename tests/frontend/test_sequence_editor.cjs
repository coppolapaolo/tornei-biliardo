/**
 * Headless automation per static/js/sequence-editor.js — la sequenza di
 * esercizi che si compone (esami oggi, schede di allenamento domani).
 *
 * Il modulo non parla col server: l'ordine che conta è quello del DOM, e lo
 * spedisce il modulo HTML. Quindi qui si prova che il DOM, dopo ogni gesto,
 * sia **quello che il server si aspetta di leggere**: tre liste parallele per
 * posizione, ogni voce con tutti i suoi campi.
 *
 * 1. le frecce sulla presa spostano la voce, e i campi la seguono;
 * 2. ai bordi non succede niente;
 * 3. il trascinamento cambia posto quando il dito supera la metà della vicina;
 * 4. «togli» leva la voce e i suoi campi, e a lista vuota compare l'avviso;
 * 5. meno e più ritoccano la cifra dentro i limiti, e anche una cifra scritta
 *    a mano viene riportata nei limiti;
 * 6. il totale somma i «vale» e conta 1 per ogni esercizio riuscito o no;
 * 7. scegliere dal foglio crea la voce dallo stampo: tiene la variante del
 *    tipo giusto, propone il valore del catalogo, e un esercizio riuscito o no
 *    manda comunque un `max_score` vuoto;
 * 8. un esercizio già in sequenza sparisce dal foglio, e torna se lo si toglie;
 * 9. la ricerca ignora maiuscole e accenti.
 *
 * Run:  cd tests/frontend && npm install && npm test
 */
const fs = require("fs");
const path = require("path");
const assert = require("assert");
const { JSDOM } = require("jsdom");

const SRC = fs.readFileSync(
  path.join(__dirname, "..", "..", "static", "js", "sequence-editor.js"),
  "utf8"
);

function voce(id, titolo, vale, prove) {
  const quanto =
    vale === null
      ? `<div data-seq-weight="1"><input type="hidden" name="max_score" value=""></div>`
      : `<div data-seq-stepper>
           <button type="button" data-seq-step="-1"></button>
           <input type="number" name="max_score" value="${vale}" min="1" max="999" data-seq-weight>
           <button type="button" data-seq-step="1"></button>
         </div>`;
  return `<li data-seq-item data-seq-key="${id}">
    <button type="button" data-seq-grip></button>
    <span data-seq-fill="title">${titolo}</span>
    <input type="hidden" name="challenge_id" value="${id}">
    ${quanto}
    <div data-seq-stepper>
      <button type="button" data-seq-step="-1"></button>
      <input type="number" name="max_attempts" value="${prove}" min="1" max="20">
      <button type="button" data-seq-step="1"></button>
    </div>
    <button type="button" data-seq-remove></button>
  </li>`;
}

const PAGINA = `
<form data-seq-editor>
  <span data-seq-total data-seq-total-text="fino a {n} punti"></span>
  <ol data-seq-list>
    ${voce(1, "Spot Shot Rally", 10, 3)}
    ${voce(2, "Serie da otto", null, 1)}
    ${voce(3, "Ferma nel cerchio", 12, 2)}
  </ol>
  <div data-seq-empty hidden>vuota</div>
  <div data-seq-live data-seq-live-text="{title}: posizione {n} di {total}"></div>
  <template data-seq-template>
    <li data-seq-item data-seq-key="">
      <button type="button" data-seq-grip></button>
      <span data-seq-slot="thumb"></span>
      <span data-seq-fill="title"></span><span data-seq-fill="sub"></span>
      <input type="hidden" name="challenge_id" data-seq-from="key">
      <div data-seq-if="score" data-seq-stepper>
        <input type="number" name="max_score" value="10" min="1" max="999" data-seq-from="vale" data-seq-weight>
      </div>
      <div data-seq-if="passfail" data-seq-weight="1"><input type="hidden" name="max_score" value=""></div>
      <div data-seq-stepper><input type="number" name="max_attempts" value="1" min="1" max="20"></div>
      <button type="button" data-seq-remove></button>
    </li>
  </template>
</form>
<div id="foglio" data-seq-picker>
  <input type="search" data-seq-search>
  <button data-seq-option data-seq-key="1" data-seq-title="Spot Shot Rally" data-seq-kind="score" data-seq-vale="10"></button>
  <button data-seq-option data-seq-key="7" data-seq-title="Linea tangente" data-seq-kind="score" data-seq-vale="15" data-seq-sub="nel catalogo vale 15"><span data-seq-slot="thumb"><img src="/t.png"></span></button>
  <button data-seq-option data-seq-key="8" data-seq-title="Colpo più difficile" data-seq-kind="passfail" data-seq-sub="riuscito o no"></button>
  <div data-seq-noresult hidden>niente</div>
</div>`;

function pagina() {
  const dom = new JSDOM(`<!doctype html><body>${PAGINA}</body>`, { runScripts: "outside-only" });
  const w = dom.window;
  w.eval(SRC);
  const editor = w.document.querySelector("[data-seq-editor]");
  const seq = w.c7SequenceEditor.avvia(editor, w.document.getElementById("foglio"));
  return { w, editor, seq };
}

/* Ciò che il server leggerebbe: le tre liste parallele. */
function inviato(w, editor) {
  const data = new w.FormData(editor);
  return {
    ids: data.getAll("challenge_id"),
    vale: data.getAll("max_score"),
    prove: data.getAll("max_attempts"),
  };
}

function tasto(w, nodo, key) {
  nodo.dispatchEvent(new w.KeyboardEvent("keydown", { key, bubbles: true, cancelable: true }));
}

function le_frecce_spostano_la_voce_con_i_suoi_campi() {
  const { w, editor, seq } = pagina();
  const terza = seq.items()[2];
  tasto(w, terza.querySelector("[data-seq-grip]"), "ArrowUp");
  tasto(w, terza.querySelector("[data-seq-grip]"), "ArrowUp");
  assert.deepStrictEqual(inviato(w, editor), {
    ids: ["3", "1", "2"],
    vale: ["12", "10", ""],
    prove: ["2", "3", "1"],
  });
  assert.strictEqual(
    editor.querySelector("[data-seq-live]").textContent,
    "Ferma nel cerchio: posizione 1 di 3"
  );
  console.log("  ok  le frecce spostano la voce, e i campi la seguono");
}

function ai_bordi_non_succede_niente() {
  const { w, editor, seq } = pagina();
  tasto(w, seq.items()[0].querySelector("[data-seq-grip]"), "ArrowUp");
  tasto(w, seq.items()[2].querySelector("[data-seq-grip]"), "ArrowDown");
  assert.deepStrictEqual(inviato(w, editor).ids, ["1", "2", "3"]);
  assert.strictEqual(seq.sposta(seq.items()[0], -1), false);
  console.log("  ok  ai bordi la voce resta dov'è");
}

function il_trascinamento_cambia_posto_oltre_la_meta_della_vicina() {
  const { w, editor, seq } = pagina();
  // jsdom non impagina: ogni voce è alta 100, una sotto l'altra, nell'ordine
  // in cui sta nel DOM in quel momento.
  seq.items().forEach((item) => {
    item.getBoundingClientRect = () => {
      const i = seq.items().indexOf(item);
      return { top: i * 100, height: 100 };
    };
  });
  const prima = seq.items()[0];
  const grip = prima.querySelector("[data-seq-grip]");
  const punta = (tipo, y) => {
    const e = new w.Event(tipo, { bubbles: true, cancelable: true });
    e.clientY = y;
    grip.dispatchEvent(e);
  };

  punta("pointerdown", 50);
  assert.ok(prima.classList.contains("is-dragging"));
  punta("pointermove", 140); // non ancora oltre la metà della seconda (150)
  assert.deepStrictEqual(inviato(w, editor).ids, ["1", "2", "3"]);
  punta("pointermove", 160);
  assert.deepStrictEqual(inviato(w, editor).ids, ["2", "1", "3"]);
  punta("pointerup", 160);
  assert.ok(!prima.classList.contains("is-dragging"));
  punta("pointermove", 290); // a dito alzato non si sposta più niente
  assert.deepStrictEqual(inviato(w, editor).ids, ["2", "1", "3"]);
  console.log("  ok  il trascinamento cambia posto oltre la metà della vicina");
}

function togli_leva_la_voce_e_a_lista_vuota_lo_dice() {
  const { w, editor, seq } = pagina();
  const vuota = editor.querySelector("[data-seq-empty]");
  seq.items()[1].querySelector("[data-seq-remove]").click();
  assert.deepStrictEqual(inviato(w, editor), { ids: ["1", "3"], vale: ["10", "12"], prove: ["3", "2"] });
  assert.strictEqual(vuota.hidden, true);
  seq.items().forEach((item) => item.querySelector("[data-seq-remove]").click());
  assert.strictEqual(vuota.hidden, false);
  assert.strictEqual(editor.querySelector("[data-seq-total]").hidden, true);
  console.log("  ok  togli leva voce e campi; a lista vuota compare l'avviso");
}

function meno_e_piu_restano_nei_limiti() {
  const { w, seq } = pagina();
  const prove = seq.items()[1].querySelector('[name="max_attempts"]');
  const [meno, piu] = prove.parentNode.querySelectorAll("[data-seq-step]");
  meno.click();
  assert.strictEqual(prove.value, "1", "sotto il minimo non si scende");
  piu.click();
  piu.click();
  assert.strictEqual(prove.value, "3");
  prove.value = "50";
  prove.dispatchEvent(new w.Event("change", { bubbles: true }));
  assert.strictEqual(prove.value, "20", "scritto a mano oltre il massimo: riportato al massimo");
  console.log("  ok  meno e più restano nei limiti, anche scrivendo a mano");
}

function il_totale_somma_i_vale_e_conta_uno_per_riuscito_o_no() {
  const { editor, seq } = pagina();
  const totale = editor.querySelector("[data-seq-total]");
  assert.strictEqual(totale.textContent, "fino a 23 punti"); // 10 + 1 + 12
  seq.items()[0].querySelector("[data-seq-step='1']").click();
  assert.strictEqual(totale.textContent, "fino a 24 punti");
  console.log("  ok  il totale: i «vale», più 1 per ogni riuscito o no");
}

function scegliere_dal_foglio_crea_la_voce_dallo_stampo() {
  const { w, editor } = pagina();
  const foglio = w.document.getElementById("foglio");

  foglio.querySelector('[data-seq-key="7"]').click();
  let nuova = editor.querySelector('[data-seq-item][data-seq-key="7"]');
  assert.strictEqual(nuova.querySelector('[data-seq-fill="title"]').textContent, "Linea tangente");
  assert.strictEqual(nuova.querySelector('[data-seq-fill="sub"]').textContent, "nel catalogo vale 15");
  assert.ok(nuova.querySelector('[data-seq-slot="thumb"] img'), "la miniatura è copiata");
  assert.strictEqual(nuova.querySelectorAll('[name="max_score"]').length, 1, "una sola variante");

  foglio.querySelector('[data-seq-key="8"]').click();
  nuova = editor.querySelector('[data-seq-item][data-seq-key="8"]');
  assert.strictEqual(nuova.querySelectorAll('[name="max_score"]').length, 1);

  assert.deepStrictEqual(inviato(w, editor), {
    ids: ["1", "2", "3", "7", "8"],
    vale: ["10", "", "12", "15", ""],
    prove: ["3", "1", "2", "1", "1"],
  });
  assert.strictEqual(editor.querySelector("[data-seq-total]").textContent, "fino a 39 punti");
  console.log("  ok  dal foglio: variante giusta, valore del catalogo, max_score vuoto se riuscito o no");
}

function chi_e_gia_in_sequenza_non_sta_nel_foglio() {
  const { w, seq } = pagina();
  const foglio = w.document.getElementById("foglio");
  const spot = foglio.querySelector('[data-seq-key="1"]');
  assert.strictEqual(spot.hidden, true, "già nell'esame: nascosto");
  spot.click();
  assert.strictEqual(seq.items().length, 3, "un'opzione nascosta non si aggiunge");
  seq.items()[0].querySelector("[data-seq-remove]").click();
  assert.strictEqual(spot.hidden, false, "tolto dall'esame: torna nel foglio");

  foglio.querySelector('[data-seq-key="7"]').click();
  foglio.querySelector('[data-seq-key="8"]').click();
  spot.click();
  assert.strictEqual(foglio.querySelector("[data-seq-noresult]").hidden, false);
  console.log("  ok  il foglio mostra solo chi non è in sequenza");
}

function la_ricerca_ignora_maiuscole_e_accenti() {
  const { w } = pagina();
  const foglio = w.document.getElementById("foglio");
  const cerca = foglio.querySelector("[data-seq-search]");
  cerca.value = "PIU DIFF";
  cerca.dispatchEvent(new w.Event("input", { bubbles: true }));
  assert.strictEqual(foglio.querySelector('[data-seq-key="8"]').hidden, false);
  assert.strictEqual(foglio.querySelector('[data-seq-key="7"]').hidden, true);
  console.log("  ok  la ricerca ignora maiuscole e accenti");
}

console.log("sequence-editor.js");
le_frecce_spostano_la_voce_con_i_suoi_campi();
ai_bordi_non_succede_niente();
il_trascinamento_cambia_posto_oltre_la_meta_della_vicina();
togli_leva_la_voce_e_a_lista_vuota_lo_dice();
meno_e_piu_restano_nei_limiti();
il_totale_somma_i_vale_e_conta_uno_per_riuscito_o_no();
scegliere_dal_foglio_crea_la_voce_dallo_stampo();
chi_e_gia_in_sequenza_non_sta_nel_foglio();
la_ricerca_ignora_maiuscole_e_accenti();
console.log("tutto ok");
