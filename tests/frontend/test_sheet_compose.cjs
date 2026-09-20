/**
 * Headless automation per static/js/sheet-compose.js — comporre una scheda di
 * allenamento (ADR-067).
 *
 * Il modulo non parla col server: quello che conta è **cosa finisce nel
 * modulo**, cioè le sette liste parallele che il server legge per posizione.
 * Qui si prova che dopo ogni gesto siano allineate e dicano quello che
 * l'utente ha appena scelto.
 *
 * 1. il foglio si apre sulla voce da cui è partito, e mostra i suoi valori;
 * 2. cambiare misura riscrive il campo della voce, e la pillola lo dice;
 * 3. col punteggio il «quanto farne» sparisce dal foglio — il massimo lo dice
 *    l'esercizio — e la voce non manda più un numero nel totale;
 * 4. il totale somma **solo** le voci a riusciti, e conta due volte quelle
 *    segnate da due lati;
 * 5. dove l'unità e la misura sono la stessa parola non si ripete;
 * 6. «da che parte» compare solo se l'esercizio ha delle varianti, e toglierlo
 *    dimezza il totale;
 * 7. il titoletto di sezione sta sulla prima voce che lo apre;
 * 8. gli interruttori della scheda scoprono le righe che dipendono da loro, e
 *    il giorno si chiede solo se la scheda è a giorni;
 * 9. una voce appena pescata dal foglio nasce già leggibile.
 *
 * Run:  cd tests/frontend && npm install && npm test
 */
const fs = require("fs");
const path = require("path");
const assert = require("assert");
const { JSDOM } = require("jsdom");

const SEQ = fs.readFileSync(
  path.join(__dirname, "..", "..", "static", "js", "sequence-editor.js"),
  "utf8"
);
const SRC = fs.readFileSync(
  path.join(__dirname, "..", "..", "static", "js", "sheet-compose.js"),
  "utf8"
);

function voce(id, titolo, { measure = "made", amount = 5, variant = "0", section = "", varianti = 0 } = {}) {
  return `<li data-seq-item data-seq-key="${id}">
    <div class="c7-seq__section" data-seq-slot="section"></div>
    <button type="button" data-seq-grip></button>
    <span data-seq-fill="title">${titolo}</span>
    <input type="hidden" name="challenge_id" value="${id}" data-seq-from="key">
    <input type="hidden" name="item_id" value="">
    <input type="hidden" name="measure" value="${measure}" data-sheet-measure>
    <input type="hidden" name="amount" value="${amount}" data-sheet-amount>
    <input type="hidden" name="per_variant" value="${variant}" data-sheet-variant>
    <input type="hidden" name="section" value="${section}" data-sheet-section>
    <input type="hidden" name="day" value="" data-sheet-day>
    <input type="hidden" data-seq-from="variants" data-sheet-variants value="${varianti}">
    <span hidden data-seq-weight="0" data-sheet-weight></span>
    <button type="button" data-sheet-open><span data-sheet-dose></span></button>
    <button type="button" data-seq-remove></button>
  </li>`;
}

const PAGINA = `
<form data-seq-editor data-sheet-compose data-seq-picker-id="foglio">
  <span data-seq-total data-seq-total-text="{n} tiri a riusciti"></span>
  <ol data-seq-list>
    ${voce(1, "Stop shot", { varianti: 2, variant: "1", section: "Tecnica" })}
    ${voce(2, "Giro di tavolo", { measure: "minutes", amount: 10, section: "Riscaldamento" })}
  </ol>
  <div data-seq-empty hidden>vuota</div>
  <div data-seq-live data-seq-live-text="{title}: {n}/{total}"></div>
  <template data-seq-template>${voce("", "")}</template>

  <label><input type="checkbox" data-sheet-toggle="has_threshold" name="has_threshold" value="1"></label>
  <div data-sheet-when="has_threshold"><input name="threshold" value="8"></div>
  <label><input type="checkbox" data-sheet-toggle="uses_days" name="uses_days" value="1"></label>
</form>

<div data-sheet-dialog
     data-sheet-msg-shots="Quanti tiri" data-sheet-msg-games="Quante partite"
     data-sheet-msg-minutes="Quanti minuti"
     data-sheet-unit-shots="tiri" data-sheet-unit-games="partite" data-sheet-unit-minutes="minuti"
     data-sheet-msg-threshold="Entra nella soglia." data-sheet-msg-out="Fuori dalla soglia.">
  <h3 data-sheet-dialog-title></h3>
  <button type="button" data-sheet-pick="done">Fatto</button>
  <button type="button" data-sheet-pick="made">Riusciti</button>
  <button type="button" data-sheet-pick="score">Punteggio</button>
  <button type="button" data-sheet-pick="wins">Vinte</button>
  <button type="button" data-sheet-pick="minutes">Minuti</button>
  <div data-sheet-amount-row>
    <span data-sheet-amount-label></span>
    <button type="button" data-sheet-step="-1"></button>
    <input type="number" min="1" max="999" data-sheet-dialog-amount>
    <button type="button" data-sheet-step="1"></button>
  </div>
  <label data-sheet-variant-row hidden><input type="checkbox" data-sheet-dialog-variant></label>
  <input type="text" data-sheet-dialog-section>
  <div data-sheet-day-row hidden><input type="text" data-sheet-dialog-day></div>
  <div data-sheet-note></div>
</div>

<div id="foglio" data-seq-picker>
  <button data-seq-option data-seq-key="9" data-seq-title="Draw shot" data-seq-variants="0"></button>
</div>`;

function pagina() {
  const dom = new JSDOM(`<!doctype html><body>${PAGINA}</body>`, { runScripts: "outside-only" });
  const w = dom.window;
  w.eval(SEQ);
  w.eval(SRC);
  const form = w.document.querySelector("[data-sheet-compose]");
  const dialog = w.document.querySelector("[data-sheet-dialog]");
  /* Avvio esplicito, come in test_sequence_editor.cjs: in jsdom il documento
     è già pronto quando lo script viene valutato, e l'auto-avvio dipende da
     un evento che non arriverà più. */
  form.c7Seq = w.c7SequenceEditor.avvia(form, w.document.getElementById("foglio"));
  form.c7Sheet = w.c7SheetCompose.avvia(form, dialog);
  return { w, form, dialog };
}

/* Ciò che il server leggerebbe: le liste parallele. */
function inviato(w, form) {
  const data = new w.FormData(form);
  return {
    ids: data.getAll("challenge_id"),
    measure: data.getAll("measure"),
    amount: data.getAll("amount"),
    variant: data.getAll("per_variant"),
    section: data.getAll("section"),
  };
}

function apri(w, form, dialog, indice) {
  const voci = form.querySelectorAll("[data-seq-item]");
  const bottone = voci[indice].querySelector("[data-sheet-open]");
  const evento = new w.Event("show.bs.modal");
  evento.relatedTarget = bottone;
  dialog.dispatchEvent(evento);
}

function click(w, nodo) {
  nodo.dispatchEvent(new w.MouseEvent("click", { bubbles: true }));
}

function il_foglio_si_apre_sulla_voce_giusta() {
  const { w, form, dialog } = pagina();
  apri(w, form, dialog, 1);
  assert.strictEqual(dialog.querySelector("[data-sheet-dialog-title]").textContent, "Giro di tavolo");
  assert.strictEqual(dialog.querySelector("[data-sheet-dialog-amount]").value, "10");
  assert.strictEqual(dialog.querySelector("[data-sheet-amount-label]").textContent, "Quanti minuti");
  assert.strictEqual(dialog.querySelector("[data-sheet-note]").textContent, "Fuori dalla soglia.");
}

function cambiare_misura_riscrive_la_voce() {
  const { w, form, dialog } = pagina();
  apri(w, form, dialog, 1);
  click(w, dialog.querySelector('[data-sheet-pick="made"]'));

  assert.deepStrictEqual(inviato(w, form).measure, ["made", "made"]);
  const dose = form.querySelectorAll("[data-sheet-dose]")[1].textContent;
  assert.ok(dose.includes("10 tiri"), dose);
  assert.ok(dose.includes("riusciti"), dose);
  assert.strictEqual(dialog.querySelector("[data-sheet-note]").textContent, "Entra nella soglia.");
  /* La pillola scelta si accende con la classe del tema: una classe sbagliata
     non dà errore, lascia solo la scelta senza riscontro. */
  assert.ok(dialog.querySelector('[data-sheet-pick="made"]').classList.contains("is-active"));
  assert.ok(!dialog.querySelector('[data-sheet-pick="minutes"]').classList.contains("is-active"));
}

function col_punteggio_il_quanto_farne_sparisce() {
  const { w, form, dialog } = pagina();
  apri(w, form, dialog, 0);
  click(w, dialog.querySelector('[data-sheet-pick="score"]'));

  assert.strictEqual(dialog.querySelector("[data-sheet-amount-row]").hidden, true);
  const dose = form.querySelector("[data-sheet-dose]").textContent;
  assert.ok(!dose.includes("5"), dose);
  assert.strictEqual(form.querySelector("[data-seq-total]").textContent, "0 tiri a riusciti");
}

function il_totale_conta_solo_i_riusciti_e_i_due_lati() {
  const { w, form } = pagina();
  /* Stop shot: 5 tiri × 2 lati. Il giro di tavolo è a minuti: fuori. */
  assert.strictEqual(form.querySelector("[data-seq-total]").textContent, "10 tiri a riusciti");
  assert.strictEqual(form.querySelector("[data-sheet-dose]").textContent, "5 tiri · ×2 · riusciti");
}

function l_unita_non_si_ripete_quando_e_la_misura() {
  const { w, form } = pagina();
  /* La seconda voce è a minuti: «10 minuti», non «10 minuti · minuti». */
  assert.strictEqual(form.querySelectorAll("[data-sheet-dose]")[1].textContent, "10 minuti");
}

function da_che_parte_solo_dove_ci_sono_le_varianti() {
  const { w, form, dialog } = pagina();
  apri(w, form, dialog, 0);
  assert.strictEqual(dialog.querySelector("[data-sheet-variant-row]").hidden, false);
  apri(w, form, dialog, 1);
  assert.strictEqual(dialog.querySelector("[data-sheet-variant-row]").hidden, true);
}

function togliere_i_due_lati_dimezza_il_totale() {
  const { w, form, dialog } = pagina();
  apri(w, form, dialog, 0);
  const spunta = dialog.querySelector("[data-sheet-dialog-variant]");
  spunta.checked = false;
  spunta.dispatchEvent(new w.Event("change", { bubbles: true }));

  assert.deepStrictEqual(inviato(w, form).variant, ["0", "0"]);
  assert.strictEqual(form.querySelector("[data-seq-total]").textContent, "5 tiri a riusciti");
}

function il_titoletto_sta_sulla_prima_voce_del_gruppo() {
  const { w, form } = pagina();
  const titoli = form.querySelectorAll('[data-seq-slot="section"]');
  assert.strictEqual(titoli[0].textContent, "Tecnica");
  assert.strictEqual(titoli[1].textContent, "Riscaldamento");

  /* Due voci nello stesso gruppo: il titoletto lo apre solo la prima. */
  const dialog = w.document.querySelector("[data-sheet-dialog]");
  apri(w, form, dialog, 1);
  const campo = dialog.querySelector("[data-sheet-dialog-section]");
  campo.value = "Tecnica";
  campo.dispatchEvent(new w.Event("input", { bubbles: true }));

  assert.strictEqual(titoli[0].textContent, "Tecnica");
  assert.strictEqual(titoli[1].textContent, "");
}

function gli_interruttori_scoprono_le_loro_righe() {
  const { w, form } = pagina();
  const riga = form.querySelector('[data-sheet-when="has_threshold"]');
  assert.strictEqual(riga.hidden, true);

  const spunta = form.querySelector('[data-sheet-toggle="has_threshold"]');
  spunta.checked = true;
  spunta.dispatchEvent(new w.Event("change", { bubbles: true }));
  assert.strictEqual(riga.hidden, false);
}

function il_giorno_si_chiede_solo_se_la_scheda_ne_ha() {
  const { w, form, dialog } = pagina();
  apri(w, form, dialog, 0);
  assert.strictEqual(dialog.querySelector("[data-sheet-day-row]").hidden, true);

  const spunta = form.querySelector('[data-sheet-toggle="uses_days"]');
  spunta.checked = true;
  spunta.dispatchEvent(new w.Event("change", { bubbles: true }));
  apri(w, form, dialog, 0);
  assert.strictEqual(dialog.querySelector("[data-sheet-day-row]").hidden, false);
}

function una_voce_nuova_nasce_gia_leggibile() {
  const { w, form } = pagina();
  const opzione = w.document.querySelector("[data-seq-option]");
  click(w, opzione);

  const voci = form.querySelectorAll("[data-seq-item]");
  assert.strictEqual(voci.length, 3);
  /* Il componente aggiunge la voce; il riscontro di questo modulo arriva col
     ridisegno differito, come nella pagina vera. */
  return new Promise(function (risolvi) {
    w.setTimeout(function () {
      assert.strictEqual(voci[2].querySelector("[data-sheet-dose]").textContent, "5 tiri · riusciti");
      assert.strictEqual(form.querySelector("[data-seq-total]").textContent, "15 tiri a riusciti");
      risolvi();
    }, 0);
  });
}

async function main() {
  const prove = [
    il_foglio_si_apre_sulla_voce_giusta,
    cambiare_misura_riscrive_la_voce,
    col_punteggio_il_quanto_farne_sparisce,
    il_totale_conta_solo_i_riusciti_e_i_due_lati,
    l_unita_non_si_ripete_quando_e_la_misura,
    da_che_parte_solo_dove_ci_sono_le_varianti,
    togliere_i_due_lati_dimezza_il_totale,
    il_titoletto_sta_sulla_prima_voce_del_gruppo,
    gli_interruttori_scoprono_le_loro_righe,
    il_giorno_si_chiede_solo_se_la_scheda_ne_ha,
    una_voce_nuova_nasce_gia_leggibile,
  ];
  for (const prova of prove) {
    await prova();
    console.log("  ✓", prova.name.replace(/_/g, " "));
  }
  console.log(`${prove.length}/${prove.length} sheet-compose`);
}

main().catch(function (errore) {
  console.error(errore);
  process.exit(1);
});
