/**
 * Headless automation per l'editor della catena degli spareggi (ADR-078).
 *
 * Carica il vero static/js/catena_spareggi.js in jsdom, con una
 * configurazione nella forma di models/classification/editor_catena.py, e
 * verifica le regole che l'editor deve rispettare prima ancora del server:
 *
 * 1. il valore nel campo nascosto segue la lista (sposta, togli, aggiungi);
 * 2. il sorteggio resta in fondo, e nel turno non si toglie;
 * 3. un criterio nuovo entra prima dello spareggio SSR e del sorteggio;
 * 4. lo SSR ha il suo posto, che − e + cambiano;
 * 5. cambiando sistema, la catena di default diventa quella del nuovo, una
 *    catena scelta perde solo il criterio diventato principale;
 * 6. la frase del regolamento si ricompone a ogni modifica.
 *
 * Run:  cd tests/frontend && npm install && npm test
 */
const fs = require("fs");
const path = require("path");
const assert = require("assert");
const { JSDOM } = require("jsdom");

const SORGENTE = fs.readFileSync(
  path.join(__dirname, "..", "..", "static", "js", "catena_spareggi.js"),
  "utf8"
);

const NOMI = {
  vittorie: "Vittorie",
  rack_vinti: "Triangoli vinti",
  punti: "Punti",
  differenza_rack: "Differenza triangoli",
  scontri_diretti: "Scontri diretti",
  ssr: "Spareggio SSR",
  posizione_precedente: "Posizione precedente",
  sorteggio: "Sorteggio",
};
const FRASI = {
  vittorie: "le vittorie",
  rack_vinti: "i triangoli vinti",
  punti: "i punti",
  differenza_rack: "la differenza triangoli",
  scontri_diretti: "lo scontro diretto",
  ssr: "lo spareggio SSR",
  ssr_n: "lo spareggio SSR fino al {n}° posto",
  posizione_precedente: "la posizione al turno precedente",
  sorteggio: "il sorteggio",
};
const TESTI = {
  conta: "{a_pari} conta {elenco}.",
  poi: ", poi {x}",
  vuota: "{a_pari} i giocatori restano a pari merito.",
  finoAl: "fino al {n}°",
  su: "Sposta prima",
  giu: "Sposta dopo",
  togli: "Togli",
  meno: "Un posto in meno",
  piu: "Un posto in più",
  aggiungi: "Aggiungi un criterio",
  principaleNota: "criterio principale",
  sorteggioNota: "sempre ultimo",
  nessunAltro: "Non restano criteri da aggiungere.",
};

function config(livello, voci) {
  const gara = livello === "gara";
  const ammessi = (principale) =>
    ["scontri_diretti", "differenza_rack", "rack_vinti", "vittorie", "ssr",
      "posizione_precedente", "sorteggio"].filter(
      (c) => c !== principale && !(livello === "turno" && c === "ssr")
    );
  return {
    livello,
    sistema: "WINS",
    voci,
    completa: !gara,
    ssrConPosto: gara,
    ssrDefault: 3,
    ssrMassimo: 99,
    ammessi: { WINS: ammessi("vittorie"), RACK: ammessi("rack_vinti") },
    principale: { WINS: "Vittorie", RACK: "Triangoli vinti" },
    default: gara
      ? { WINS: ["differenza_rack", "ssr:3"], RACK: ["ssr:3"] }
      : {
          WINS: ["differenza_rack", "posizione_precedente", "sorteggio"],
          RACK: ["posizione_precedente", "sorteggio"],
        },
    nomi: NOMI,
    frasi: FRASI,
    aPari: { WINS: "A pari vittorie", RACK: "A pari triangoli vinti" },
    testi: TESTI,
  };
}

function editor(livello, voci) {
  const html = `<!doctype html><body>
    <select id="sistema"><option value="WINS" selected>W</option><option value="RACK">R</option></select>
    <div data-catena data-sistema-da="#sistema">
      <input type="hidden" name="catena" data-catena-valore>
      <ol data-catena-voci></ol><div data-catena-aggiungi></div><p data-catena-frase></p>
    </div></body>`;
  const dom = new JSDOM(html, { runScripts: "outside-only" });
  const radice = dom.window.document.querySelector("[data-catena]");
  radice.setAttribute("data-config", JSON.stringify(config(livello, voci)));
  dom.window.eval(SORGENTE);
  // Fuori dal browser DOMContentLoaded arriva dopo: si avvia a mano, come fa
  // chi aggiunge un editor dopo il caricamento.
  dom.window.c7CatenaSpareggi.avvia();
  const doc = dom.window.document;
  const q = (s) => radice.querySelector(s);
  return {
    valore: () => q("[data-catena-valore]").value,
    frase: () => q("[data-catena-frase]").textContent,
    clic: (s) => q(s).dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true })),
    c: (s) => q(s),
    sistema: (v) => {
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

console.log("catena_spareggi.js");

check("la frase e il valore iniziali", () => {
  const e = editor("gara", ["differenza_rack", "ssr:3"]);
  assert.strictEqual(e.valore(), "differenza_rack,ssr:3");
  assert.strictEqual(
    e.frase(),
    "A pari vittorie conta la differenza triangoli, poi lo spareggio SSR fino al 3° posto."
  );
});

check("un criterio nuovo entra prima dello SSR", () => {
  const e = editor("gara", ["differenza_rack", "ssr:3"]);
  e.clic('[data-aggiungi="scontri_diretti"]');
  assert.strictEqual(e.valore(), "differenza_rack,scontri_diretti,ssr:3");
});

check("si sposta e si toglie", () => {
  const e = editor("gara", ["differenza_rack", "scontri_diretti"]);
  e.clic('[data-indice="1"] [data-azione="su"]');
  assert.strictEqual(e.valore(), "scontri_diretti,differenza_rack");
  e.clic('[data-indice="0"] [data-azione="togli"]');
  assert.strictEqual(e.valore(), "differenza_rack");
  e.clic('[data-indice="0"] [data-azione="togli"]');
  assert.strictEqual(e.valore(), "");
  assert.strictEqual(e.frase(), "A pari vittorie i giocatori restano a pari merito.");
});

check("il posto dello SSR con − e +", () => {
  const e = editor("gara", ["ssr:1"]);
  assert.ok(e.c('[data-azione="meno"]').disabled, "sotto il primo posto non si scende");
  e.clic('[data-azione="piu"]');
  assert.strictEqual(e.valore(), "ssr:2");
});

check("nel turno il sorteggio c'è sempre e non si toglie", () => {
  const e = editor("turno", ["differenza_rack"]);
  assert.strictEqual(e.valore(), "differenza_rack,sorteggio");
  assert.strictEqual(e.c('[data-indice="1"] [data-azione="togli"]'), null);
  assert.strictEqual(e.c('[data-aggiungi="ssr"]'), null, "niente SSR nel turno");
  e.clic('[data-aggiungi="scontri_diretti"]');
  assert.strictEqual(e.valore(), "differenza_rack,scontri_diretti,sorteggio");
});

check("il principale non si offre", () => {
  const e = editor("gara", []);
  assert.strictEqual(e.c('[data-aggiungi="vittorie"]'), null);
  assert.ok(e.c('[data-aggiungi="rack_vinti"]'));
});

check("cambio di sistema: la catena di default segue", () => {
  const e = editor("turno", ["differenza_rack", "posizione_precedente", "sorteggio"]);
  e.sistema("RACK");
  assert.strictEqual(e.valore(), "posizione_precedente,sorteggio");
  assert.ok(e.frase().startsWith("A pari triangoli vinti"));
});

check("cambio di sistema: lo SSR della gara tiene il suo posto", () => {
  const e = editor("gara", ["differenza_rack", "ssr:5"]);
  e.sistema("RACK");
  assert.strictEqual(e.valore(), "ssr:5");
});

check("cambio di sistema: una catena scelta perde solo il nuovo principale", () => {
  const e = editor("gara", ["rack_vinti", "scontri_diretti"]);
  e.sistema("RACK");
  assert.strictEqual(e.valore(), "scontri_diretti");
});

console.log(`${controlli} controlli superati`);
