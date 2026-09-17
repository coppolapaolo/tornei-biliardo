/**
 * Headless automation per static/js/board_acchito.js — le due domande
 * dell'acchito sul tabellone orizzontale (ADR-056, emendamento 2026-09-17).
 *
 * Gara 3 della Ronin Cup: segnato chi aveva vinto l'acchito, il tabellone
 * «non andava avanti». Per proseguire serviva «Comincia», un pulsante nella
 * fascia in basso — l'unico stato del tabellone in cui il bersaglio non era
 * la mezza schermata, e proprio la fascia che su iPhone in orizzontale può
 * finire sotto la barra del browser.
 *
 * Quattro proprietà:
 *
 * 1. il primo tocco risponde «chi ha vinto» e cambia la domanda, senza
 *    inviare niente;
 * 2. il secondo tocco risponde «chi apre» e **invia subito**: si prosegue
 *    toccando i nomi, senza passare da un pulsante;
 * 3. chi ha vinto può mandare al tavolo l'avversario («Regole generali pool»
 *    1.2): i due valori sono indipendenti;
 * 4. «Ricomincia» torna alla prima domanda, e durante l'invio i tocchi non
 *    contano.
 *
 * Run:  cd tests/frontend && npm install && npm test
 */
const fs = require("fs");
const path = require("path");
const assert = require("assert");
const { JSDOM } = require("jsdom");

const SRC = fs.readFileSync(
  path.join(__dirname, "..", "..", "static", "js", "board_acchito.js"),
  "utf8"
);

function ambiente() {
  const dom = new JSDOM(
    '<!doctype html><body><div id="boardLag"' +
      ' data-domanda-uno="uno?" data-domanda-due="due?"' +
      ' data-nota-uno="nota uno" data-nota-due="nota due"' +
      ' data-et-acchito="acchito" data-et-apre="apre" data-et-entrambi="acchito · apre">' +
      "<div data-lag-title></div>" +
      [7, 9].map(function (id) {
        return '<button data-lag-player="' + id + '"><span class="c7-board__lagq-pill" hidden></span></button>';
      }).join("") +
      "<span data-lag-note></span><button data-lag-reset disabled></button>" +
      "</div></body>",
    { runScripts: "outside-only" }
  );
  const w = dom.window;
  w.eval(SRC);
  const lag = w.document.getElementById("boardLag");
  const inviati = [];
  w.c7BoardAcchito.avvia(lag, function (vinto, apre, btn) {
    inviati.push({ vinto: vinto, apre: apre, btn: btn });
  });
  return {
    inviati: inviati,
    lato: function (id) { return lag.querySelector('[data-lag-player="' + id + '"]'); },
    pill: function (id) { return lag.querySelector('[data-lag-player="' + id + '"] .c7-board__lagq-pill'); },
    titolo: lag.querySelector("[data-lag-title]"),
    nota: lag.querySelector("[data-lag-note]"),
    ricomincia: lag.querySelector("[data-lag-reset]"),
  };
}

// 1. Il primo tocco cambia la domanda e non invia.
(function () {
  const a = ambiente();
  assert.strictEqual(a.titolo.textContent, "uno?");
  assert.strictEqual(a.ricomincia.disabled, true);
  a.lato(7).click();
  assert.strictEqual(a.titolo.textContent, "due?");
  assert.strictEqual(a.nota.textContent, "nota due");
  assert.strictEqual(a.pill(7).hidden, false);
  assert.strictEqual(a.pill(7).textContent, "acchito");
  assert.strictEqual(a.ricomincia.disabled, false);
  assert.strictEqual(a.inviati.length, 0);
})();

// 2. Il secondo tocco invia subito: caso comune, apre chi ha vinto.
(function () {
  const a = ambiente();
  a.lato(7).click();
  a.lato(7).click();
  assert.deepStrictEqual(
    a.inviati.map(function (i) { return [i.vinto, i.apre]; }), [[7, 7]]);
  assert.strictEqual(a.inviati[0].btn, a.lato(7));
  assert.strictEqual(a.pill(7).textContent, "acchito · apre");
})();

// 3. Chi ha vinto manda al tavolo l'avversario.
(function () {
  const a = ambiente();
  a.lato(7).click();
  a.lato(9).click();
  assert.deepStrictEqual(
    a.inviati.map(function (i) { return [i.vinto, i.apre]; }), [[7, 9]]);
  assert.strictEqual(a.pill(7).textContent, "acchito");
  assert.strictEqual(a.pill(9).textContent, "apre");
})();

// 4a. «Ricomincia» torna alla prima domanda.
(function () {
  const a = ambiente();
  a.lato(7).click();
  a.ricomincia.click();
  assert.strictEqual(a.titolo.textContent, "uno?");
  assert.strictEqual(a.pill(7).hidden, true);
  assert.strictEqual(a.ricomincia.disabled, true);
  a.lato(9).click();
  a.lato(9).click();
  assert.deepStrictEqual(
    a.inviati.map(function (i) { return [i.vinto, i.apre]; }), [[9, 9]]);
})();

// 4b. Durante l'invio (il lato toccato è spento, come fa `withLoading`) i
//     tocchi non contano; a invio fallito e lato riacceso si riprova.
(function () {
  const a = ambiente();
  a.lato(7).click();
  a.lato(9).click();
  a.lato(9).disabled = true;
  a.lato(7).click();
  assert.strictEqual(a.inviati.length, 1);
  a.lato(9).disabled = false;
  a.lato(7).click();
  assert.deepStrictEqual(
    a.inviati.map(function (i) { return [i.vinto, i.apre]; }), [[7, 9], [7, 7]]);
})();

console.log("test_board_acchito: ok");
