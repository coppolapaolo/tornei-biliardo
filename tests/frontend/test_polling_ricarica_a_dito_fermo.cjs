/**
 * Headless automation per static/js/polling.js — la pagina non si ricarica
 * sotto il dito.
 *
 * La pagina gara del direttore si ricarica a ogni triangolo segnato da
 * chiunque: durante una gara, ogni pochi secondi. Sull'iPhone un
 * ricaricamento arrivato mentre si scorre lasciava la barra di navigazione
 * in basso a metà schermo, sopra il contenuto (segnalazione del 12/11/2026).
 *
 * `Polling.ricaricaQuandoFermo` aspetta che il dito sia alzato e che lo
 * scorrimento sia fermo da un momento. Deve:
 *
 * 1. ricaricare subito se nessuno sta toccando o scorrendo;
 * 2. aspettare finché un dito è sullo schermo;
 * 3. aspettare la fine dell'inerzia dopo che il dito si è alzato;
 * 4. ricaricare una volta sola, anche se chiesta dieci volte;
 * 5. essere la strada di `reloadOnEvents`.
 *
 * Run:  cd tests/frontend && npm install && npm test
 */
const fs = require("fs");
const path = require("path");
const assert = require("assert");
const { JSDOM } = require("jsdom");

const SRC = fs.readFileSync(
  path.join(__dirname, "..", "..", "static", "js", "polling.js"),
  "utf8"
);

function ambiente() {
  const dom = new JSDOM("<!doctype html><body></body>", {
    url: "https://example.test/direttore/gara/54",
    runScripts: "outside-only",
    pretendToBeVisual: true,
  });
  const finestra = dom.window;
  finestra.eval(SRC);
  const ricariche = [];
  return {
    finestra,
    ricariche,
    ricarica: function () {
      ricariche.push(Date.now());
    },
    evento: function (tipo) {
      finestra.document.dispatchEvent(
        new finestra.Event(tipo, { bubbles: true })
      );
    },
  };
}

function aspetta(ms) {
  return new Promise(function (r) {
    setTimeout(r, ms);
  });
}

async function a_riposo_ricarica_subito() {
  const amb = ambiente();
  amb.finestra.Polling.ricaricaQuandoFermo(amb.ricarica);
  await aspetta(250);
  assert.strictEqual(amb.ricariche.length, 1);
}

async function col_dito_sullo_schermo_aspetta() {
  const amb = ambiente();
  amb.evento("touchstart");
  amb.finestra.Polling.ricaricaQuandoFermo(amb.ricarica);
  await aspetta(900);
  assert.strictEqual(amb.ricariche.length, 0, "ricaricata sotto il dito");
  amb.evento("touchend");
  await aspetta(900);
  assert.strictEqual(amb.ricariche.length, 1);
}

async function aspetta_la_fine_dell_inerzia() {
  const amb = ambiente();
  amb.evento("touchstart");
  amb.evento("touchend");
  amb.finestra.Polling.ricaricaQuandoFermo(amb.ricarica);
  // La pagina continua a scorrere da sola dopo che il dito si è alzato.
  for (let i = 0; i < 8; i++) {
    amb.evento("scroll");
    await aspetta(100);
  }
  assert.strictEqual(amb.ricariche.length, 0, "ricaricata durante l'inerzia");
  await aspetta(900);
  assert.strictEqual(amb.ricariche.length, 1);
}

async function una_volta_sola() {
  const amb = ambiente();
  for (let i = 0; i < 10; i++) {
    amb.finestra.Polling.ricaricaQuandoFermo(amb.ricarica);
  }
  await aspetta(600);
  assert.strictEqual(amb.ricariche.length, 1);
}

async function reload_on_events_passa_da_qui() {
  const amb = ambiente();
  let giro = 0;
  amb.finestra.fetch = function () {
    giro += 1;
    const corpo =
      giro === 1
        ? { cursor: 1, events: [] }
        : { cursor: 2, events: [{ type: "match_updated" }] };
    return Promise.resolve({
      status: 200,
      ok: true,
      redirected: false,
      json: function () {
        return Promise.resolve(corpo);
      },
    });
  };
  amb.evento("touchstart");
  const poller = amb.finestra.Polling.reloadOnEvents({
    url: "/sse/poll/gara/54",
    reloadOn: ["match_updated"],
    interval: 100,
    ricarica: amb.ricarica,
  });
  await aspetta(1200);
  assert.ok(giro >= 2, "il poller non ha girato");
  assert.strictEqual(amb.ricariche.length, 0, "ricaricata sotto il dito");
  amb.evento("touchend");
  await aspetta(900);
  poller.stop();
  assert.strictEqual(amb.ricariche.length, 1);
}

(async function () {
  const prove = [
    a_riposo_ricarica_subito,
    col_dito_sullo_schermo_aspetta,
    aspetta_la_fine_dell_inerzia,
    una_volta_sola,
    reload_on_events_passa_da_qui,
  ];
  for (const prova of prove) {
    await prova();
    console.log("ok  " + prova.name);
  }
  console.log("polling, ricarica a dito fermo: " + prove.length + " prove");
  process.exit(0);
})().catch(function (e) {
  console.error(e);
  process.exit(1);
});
