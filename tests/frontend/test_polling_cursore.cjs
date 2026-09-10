/**
 * Headless automation per static/js/polling.js — il protocollo col server.
 *
 * Tre proprietà, ognuna nata da un modo in cui gli aggiornamenti live si
 * perdevano:
 *
 * 1. il primo poll parte **senza** `since`: il client non ha più un orologio
 *    da confrontare con quello del server. Un telefono avanti di qualche
 *    secondo perdeva i primi eventi; uno indietro riceveva eventi vecchi,
 *    ricaricava, e li riceveva di nuovo — un ciclo di ricaricamenti;
 * 2. dal secondo poll in poi `since` è il cursore restituito dal server, e
 *    resta fermo quando non arriva niente;
 * 3. una scheda rimasta nascosta più a lungo di quanto il server conserva gli
 *    eventi non può recuperarli: al ritorno chiama `onGap` invece di fingere
 *    che non sia successo nulla.
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
  // jsdom non implementa location.reload(): lo segnala sulla console
  // virtuale, ed è così che contiamo i ricaricamenti.
  const { VirtualConsole } = require("jsdom");
  const consoleVirtuale = new VirtualConsole();
  let ricaricamenti = 0;
  consoleVirtuale.on("jsdomError", function (e) {
    if (String(e.message).includes("Not implemented: navigation")) {
      ricaricamenti += 1;
    } else {
      console.error(e);
    }
  });
  const dom = new JSDOM("<!doctype html><body></body>", {
    runScripts: "outside-only",
    pretendToBeVisual: true,
    virtualConsole: consoleVirtuale,
  });
  const finestra = dom.window;

  // fetch finto: registra gli URL e risponde con quello che il test decide.
  const richieste = [];
  let risposta = { events: [], cursor: 0, retention: 60 };
  finestra.fetch = function (url) {
    richieste.push(url);
    return Promise.resolve({
      ok: true,
      json: function () {
        return Promise.resolve(risposta);
      },
    });
  };

  // document.hidden pilotato dal test.
  let nascosta = false;
  Object.defineProperty(finestra.document, "hidden", {
    get: function () {
      return nascosta;
    },
  });
  function visibilita(h) {
    nascosta = h;
    finestra.document.dispatchEvent(new finestra.Event("visibilitychange"));
  }

  // Orologio pilotato dal test (per la durata del nascondimento).
  let adesso = 1_000_000;
  finestra.Date.now = function () {
    return adesso;
  };

  finestra.eval(SRC);
  return {
    finestra,
    richieste,
    visibilita,
    rispondi: function (r) {
      risposta = r;
    },
    avanza: function (ms) {
      adesso += ms;
    },
    ricaricamenti: function () {
      return ricaricamenti;
    },
  };
}

// Aspetta che le promise del fetch finto si risolvano.
function tick() {
  return new Promise(function (r) {
    setTimeout(r, 0);
  });
}

async function primo_poll_senza_since_poi_col_cursore() {
  const amb = ambiente();
  const eventi = [];
  const poller = amb.finestra.Polling.create({
    url: "/sse/poll/gara/8",
    onEvent: function (e) {
      eventi.push(e.type);
    },
    interval: 100000, // il timer non deve scattare da solo nel test
  });

  amb.rispondi({ events: [], cursor: 41, retention: 60 });
  poller.start();
  await new Promise(function (r) {
    setTimeout(r, 600); // il primo poll parte dopo 500 ms
  });
  assert.deepStrictEqual(amb.richieste, ["/sse/poll/gara/8"], "primo poll senza since");
  assert.deepStrictEqual(eventi, [], "il passato non si consegna");

  amb.rispondi({
    events: [{ id: 42, type: "match_updated", data: {} }],
    cursor: 42,
    retention: 60,
  });
  amb.visibilita(true);
  amb.visibilita(false); // ritorno in primo piano = poll immediato
  await tick();
  await tick();
  assert.strictEqual(amb.richieste[1], "/sse/poll/gara/8?since=41");
  assert.deepStrictEqual(eventi, ["match_updated"]);

  amb.rispondi({ events: [], cursor: 42, retention: 60 });
  amb.visibilita(true);
  amb.visibilita(false);
  await tick();
  await tick();
  assert.strictEqual(amb.richieste[2], "/sse/poll/gara/8?since=42", "il cursore avanza con l'ultimo evento");

  poller.stop();
  console.log("  ok  primo poll senza since, poi col cursore del server");
}

async function scheda_nascosta_oltre_la_conservazione_chiama_onGap() {
  const amb = ambiente();
  let buchi = 0;
  const poller = amb.finestra.Polling.create({
    url: "/sse/poll/gara/8",
    onEvent: function () {},
    onGap: function () {
      buchi += 1;
    },
    interval: 100000,
  });
  amb.rispondi({ events: [], cursor: 1, retention: 60 });
  poller.start();
  await new Promise(function (r) {
    setTimeout(r, 600);
  });

  // Nascosta per 30 s: dentro la conservazione, nessun buco.
  amb.visibilita(true);
  amb.avanza(30_000);
  amb.visibilita(false);
  await tick();
  assert.strictEqual(buchi, 0, "30 s non sono un buco");

  // Nascosta per 61 s: il server ha già buttato via quegli eventi.
  amb.visibilita(true);
  amb.avanza(61_000);
  amb.visibilita(false);
  await tick();
  assert.strictEqual(buchi, 1, "oltre la conservazione è un buco");

  poller.stop();
  console.log("  ok  scheda nascosta oltre la conservazione: onGap");
}

async function reloadOnEvents_ricarica_sul_buco() {
  const amb = ambiente();
  amb.rispondi({ events: [], cursor: 1, retention: 60 });
  const poller = amb.finestra.Polling.reloadOnEvents({
    url: "/sse/poll/gara/8",
    reloadOn: ["match_updated"],
    interval: 100000,
  });
  await new Promise(function (r) {
    setTimeout(r, 600);
  });
  amb.visibilita(true);
  amb.avanza(120_000);
  amb.visibilita(false);
  await tick();
  assert.strictEqual(amb.ricaricamenti(), 1, "chi torna dopo due minuti vede la pagina nuova");
  poller.stop();
  console.log("  ok  reloadOnEvents ricarica quando c'è un buco");
}

(async function () {
  console.log("polling.js — cursore e buchi");
  await primo_poll_senza_since_poi_col_cursore();
  await scheda_nascosta_oltre_la_conservazione_chiama_onGap();
  await reloadOnEvents_ricarica_sul_buco();
  console.log("tutti i test di polling.js passano");
})().catch(function (e) {
  console.error(e);
  process.exit(1);
});
