/**
 * Headless automation per static/js/tpa-referto.js — la pagina del referto
 * TPA (ADR-044).
 *
 * Fino al 19/09/2026 questo codice stava dentro
 * `templates/individual_match/tpa_referto.html`, circa 345 righe di JavaScript
 * inline con gli indirizzi scritti a mano: non si poteva provare senza far
 * rendere la pagina a Flask, e infatti nessuno lo provava. Ora è un modulo che
 * legge tutto dagli attributi `data-*` dell'involucro.
 *
 * Il modulo **non conosce le regole**: disegna lo stato che il server gli dà e
 * rimanda ogni tocco al server. Quello che si prova qui è questo contratto.
 *
 * 1. il tastierino ha caselle fisse: i tasti non ammessi si spengono, non
 *    spariscono;
 * 2. un tocco invia il comando all'indirizzo dei `data-*`, col token CSRF, e
 *    ridisegna con lo stato della risposta;
 * 3. toccare il riquadro dell'avversario passa il tavolo — o, prima della
 *    spaccata, sceglie chi spacca;
 * 4. «annulla» va all'altro indirizzo, ed è spento a referto vuoto;
 * 5. mentre un invio è in corso i tocchi non contano;
 * 6. un rifiuto del server diventa un messaggio, e lo stato non cambia;
 * 7. chi guarda rilegge lo stato quando l'altro annota, non quando annota
 *    lui, e ricarica la pagina se il referto è stato chiuso;
 * 8. il TPA si scrive .780, e mille millesimi sono 1.000.
 *
 * Run:  cd tests/frontend && npm install && npm test
 */
const fs = require("fs");
const path = require("path");
const assert = require("assert");
const { JSDOM } = require("jsdom");

const SRC = fs.readFileSync(
  path.join(__dirname, "..", "..", "static", "js", "tpa-referto.js"),
  "utf8"
);

function stato(extra) {
  const base = {
    game_type: 9,
    closed: false,
    commands: 3,
    current_player: 1,
    can_switch_player: true,
    players: { 1: { name: "Marco" }, 2: { name: "Sara" } },
    score: {
      1: { balls_potted: 4, total_errors: 1, tpa: 780, racks_won: 2 },
      2: { balls_potted: 2, total_errors: 1, tpa: null, racks_won: 1 },
    },
    current: {
      is_break: false,
      can_choose_seat: false,
      winning: false,
      main_note: null,
      secondary_note: null,
      annotation: { total_potted: null, break_potted: null, first_shot_kick_in: false, run_out: null },
    },
    buttons: ["0", "1", "2", "3"],
    racks: [],
  };
  return Object.assign(base, extra || {});
}

function ambiente(iniziale, opzioni) {
  opzioni = opzioni || {};
  const scrive = opzioni.scrive !== false;
  const dom = new JSDOM(
    '<!doctype html><body><div id="tpaReferto"' +
      ' data-press-url="/m/7/tpa/press" data-undo-url="/m/7/tpa/undo"' +
      ' data-state-url="/m/7/tpa/state" data-poll-url="/sse/poll/individual_match/7"' +
      ' data-current-user-id="42" data-can-write="' + (scrive ? "true" : "false") + '"' +
      ' data-et-passa="passa il tavolo" data-et-al-tavolo="al tavolo"' +
      ' data-et-spacca="spacca" data-et-spacca-lui="spacca lui"' +
      ' data-et-senza-tpa="TPA ancora da calcolare" data-et-bilie="quante bilie?"' +
      ' data-et-perche="perché finisce il turno?" data-et-triangolo="Triangolo"' +
      ' data-et-errore="Non è stato possibile annotare."' +
      ' data-et-kick-in="di sponda" data-et-runout-chiedi="Una sola visita?"' +
      ' data-et-runout-si="Chiusa in una sola visita">' +
      '<div id="tpaPlayers"></div>' +
      '<div id="tpaWhiteBox"></div><div id="tpaShadedBox"></div>' +
      (scrive
        ? '<div id="tpaNumbers"></div><div id="tpaLetters"></div><button id="tpaUndo"></button>'
        : "") +
      '<div id="tpaSheet"></div>' +
      '<script type="application/json" id="tpaStato">' + JSON.stringify(iniziale) + "</script>" +
      "</div></body>",
    { runScripts: "outside-only" }
  );
  const w = dom.window;
  const chiamate = [];
  const errori = [];
  const risposte = [];
  let ricariche = 0;
  let ascoltatore = null;

  w.csrfToken = function () { return "tok"; };
  w.showError = function (m) { errori.push(m); };
  w.fetch = function (url, init) {
    chiamate.push({ url: url, init: init || null });
    return new Promise(function (resolve, reject) {
      risposte.push({
        ok: function (dati) { resolve({ json: function () { return Promise.resolve(dati); } }); },
        ko: function () { reject(new Error("rete")); },
      });
    });
  };
  w.Polling = {
    create: function (cfg) {
      ascoltatore = cfg;
      return { start: function () { ascoltatore.avviato = true; } };
    },
  };
  w.eval(SRC);
  w.c7TpaReferto.avvia(w.document.getElementById("tpaReferto"), {
    ricarica: function () { ricariche += 1; },
  });

  const doc = w.document;
  return {
    doc: doc,
    chiamate: chiamate,
    errori: errori,
    risposte: risposte,
    ricariche: function () { return ricariche; },
    ascoltatore: function () { return ascoltatore; },
    tasto: function (etichetta) {
      return Array.prototype.slice
        .call(doc.querySelectorAll("#tpaNumbers button, #tpaLetters button"))
        .filter(function (b) { return b.textContent === etichetta; })[0];
    },
    riquadri: function () { return doc.getElementById("tpaPlayers").children; },
    formatTpa: w.c7TpaReferto.formatTpa,
  };
}

function giro() {
  return new Promise(function (resolve) { setTimeout(resolve, 0); });
}

async function main() {
  // 1. Caselle fisse: tutti i numeri della disciplina e le nove lettere, gli
  //    ammessi accesi e gli altri spenti.
  {
    const a = ambiente(stato());
    const numeri = a.doc.querySelectorAll("#tpaNumbers button");
    assert.strictEqual(numeri.length, 10, "palla 9: da 0 a 9");
    assert.strictEqual(a.tasto("3").disabled, false);
    assert.strictEqual(a.tasto("4").disabled, true);
    const lettere = Array.prototype.map.call(
      a.doc.querySelectorAll("#tpaLetters button"),
      function (b) { return b.textContent; }
    );
    assert.deepStrictEqual(lettere, ["M", "K", "S", "P", "G", "N", "n", "x", "p"]);
    assert.strictEqual(a.tasto("M").disabled, true);
    assert.strictEqual(a.doc.getElementById("tpaWhiteBox").textContent, "quante bilie?");
  }

  // 1 bis. I due tasti larghi compaiono solo quando il motore li ammette.
  {
    const a = ambiente(stato({ buttons: ["M", "K-in", "runout"] }));
    const lettere = a.doc.querySelectorAll("#tpaLetters button");
    assert.strictEqual(lettere.length, 11);
    assert.strictEqual(lettere[9].textContent, "↺ di sponda");
    assert.strictEqual(lettere[10].textContent, "Una sola visita?");
    assert.strictEqual(a.doc.getElementById("tpaNumbers").style.display, "none");
  }

  // 2. Un tocco invia il comando e ridisegna con lo stato della risposta.
  {
    const a = ambiente(stato());
    a.tasto("3").click();
    assert.strictEqual(a.chiamate.length, 1);
    assert.strictEqual(a.chiamate[0].url, "/m/7/tpa/press");
    assert.strictEqual(a.chiamate[0].init.method, "POST");
    assert.strictEqual(a.chiamate[0].init.headers["X-CSRFToken"], "tok");
    assert.deepStrictEqual(JSON.parse(a.chiamate[0].init.body), { command: "3" });

    const dopo = stato({ buttons: ["M", "K", "S"] });
    dopo.current.annotation.total_potted = 3;
    a.risposte[0].ok({ success: true, state: dopo });
    await giro();
    assert.strictEqual(a.tasto("M").disabled, false);
    assert.strictEqual(a.tasto("3"), undefined, "senza numeri ammessi il blocco è vuoto");
    assert.ok(a.doc.getElementById("tpaWhiteBox").textContent.indexOf("3") === 0);
  }

  // 3. Il riquadro dell'avversario passa il tavolo; il proprio non si tocca.
  {
    const a = ambiente(stato());
    const r = a.riquadri();
    assert.strictEqual(r[0].tagName, "DIV");
    assert.ok(r[0].className.indexOf("c7-tpa-player--active") >= 0);
    assert.strictEqual(r[1].tagName, "BUTTON");
    assert.ok(r[1].textContent.indexOf("passa il tavolo") >= 0);
    r[1].click();
    assert.deepStrictEqual(JSON.parse(a.chiamate[0].init.body), { command: "end" });
  }

  // 3 bis. Prima della spaccata lo stesso tocco sceglie chi spacca.
  {
    const s = stato();
    s.current.can_choose_seat = true;
    s.current.is_break = true;
    const a = ambiente(s);
    assert.ok(a.riquadri()[1].textContent.indexOf("spacca lui") >= 0);
    a.riquadri()[1].click();
    assert.deepStrictEqual(JSON.parse(a.chiamate[0].init.body), { command: "seat:2" });
  }

  // 3 ter. Quando il motore non lo ammette, nessun riquadro è un pulsante.
  {
    const a = ambiente(stato({ can_switch_player: false }));
    assert.strictEqual(a.riquadri()[1].tagName, "DIV");
  }

  // 4. «Annulla» va all'altro indirizzo, ed è spento a referto vuoto.
  {
    const a = ambiente(stato());
    const annulla = a.doc.getElementById("tpaUndo");
    assert.strictEqual(annulla.disabled, false);
    annulla.click();
    assert.strictEqual(a.chiamate[0].url, "/m/7/tpa/undo");

    const vuoto = ambiente(stato({ commands: 0 }));
    assert.strictEqual(vuoto.doc.getElementById("tpaUndo").disabled, true);
  }

  // 5. Mentre un invio è in corso i tocchi non contano; dopo sì.
  {
    const a = ambiente(stato());
    a.tasto("1").click();
    a.tasto("2").click();
    assert.strictEqual(a.chiamate.length, 1);
    a.risposte[0].ok({ success: true, state: stato() });
    await giro();
    a.tasto("2").click();
    assert.strictEqual(a.chiamate.length, 2);
  }

  // 6. Un rifiuto diventa un messaggio e lo stato resta quello di prima; la
  //    rete che cade dice la frase generica.
  {
    const a = ambiente(stato());
    a.tasto("1").click();
    a.risposte[0].ok({ success: false, message: "Non tocca a te" });
    await giro();
    assert.deepStrictEqual(a.errori, ["Non tocca a te"]);
    assert.strictEqual(a.tasto("3").disabled, false);

    a.tasto("1").click();
    a.risposte[1].ko();
    await giro();
    assert.strictEqual(a.errori[1], "Non è stato possibile annotare.");
    a.tasto("1").click();
    assert.strictEqual(a.chiamate.length, 3, "dopo un errore si può riprovare");
  }

  // 7. Chi guarda: niente tastierino, ascolta il canale del match.
  {
    const a = ambiente(stato(), { scrive: false });
    assert.strictEqual(a.riquadri()[1].tagName, "DIV");
    const canale = a.ascoltatore();
    assert.strictEqual(canale.url, "/sse/poll/individual_match/7");
    assert.strictEqual(canale.avviato, true);

    canale.onEvent({ type: "rack_updated", data: {} });
    canale.onEvent({ type: "tpa_updated", data: { by: 42 } });
    assert.strictEqual(a.chiamate.length, 0, "i propri tocchi e gli altri eventi non rileggono");

    canale.onEvent({ type: "tpa_updated", data: { by: 9 } });
    assert.strictEqual(a.chiamate[0].url, "/m/7/tpa/state");
    const dopo = stato({ current_player: 2 });
    a.risposte[0].ok({ success: true, state: dopo });
    await giro();
    assert.ok(a.riquadri()[1].className.indexOf("c7-tpa-player--active") >= 0);
    assert.strictEqual(a.ricariche(), 0);

    canale.onEvent({ type: "tpa_updated", data: { by: 9 } });
    a.risposte[1].ok({ success: true, state: stato({ closed: true }) });
    await giro();
    assert.strictEqual(a.ricariche(), 1, "referto chiuso mentre lo guardavi: si riprende dal server");
  }

  // 7 bis. Chi compila non ascolta; e nemmeno chi guarda un referto chiuso.
  {
    assert.strictEqual(ambiente(stato()).ascoltatore(), null);
    assert.strictEqual(ambiente(stato({ closed: true }), { scrive: false }).ascoltatore(), null);
  }

  // 8. Il TPA come sul referto.
  {
    const f = ambiente(stato()).formatTpa;
    assert.strictEqual(f(780), ".780");
    assert.strictEqual(f(45), ".045");
    assert.strictEqual(f(1000), "1.000");
    assert.strictEqual(f(null), "—");
    assert.strictEqual(f(undefined), "—");
  }

  // Il foglio: spaccata, nota, triangolo vinto.
  {
    const racks = [{
      number: 1,
      turns: [
        { player: 1, is_break: true, winning: false, main_note: "M^n", secondary_note: "P",
          annotation: { break_potted: 1, total_potted: 3, first_shot_kick_in: false },
          score_snapshot: { 1: { racks_won: 0 }, 2: { racks_won: 0 } } },
        { player: 2, is_break: false, winning: true, main_note: null, secondary_note: null,
          annotation: { break_potted: null, total_potted: 6, first_shot_kick_in: true },
          score_snapshot: { 1: { racks_won: 0 }, 2: { racks_won: 1 } } },
      ],
    }];
    const a = ambiente(stato({ racks: racks }));
    const foglio = a.doc.getElementById("tpaSheet");
    assert.strictEqual(foglio.children.length, 3);
    assert.strictEqual(foglio.children[0].textContent, "Triangolo 10–1");
    assert.ok(foglio.children[1].textContent.indexOf("1/3 Mn P") >= 0);
    assert.ok(foglio.children[2].className.indexOf("c7-tpa-sheet__turn--won") >= 0);
    assert.ok(foglio.children[2].textContent.indexOf("6 ↺ ●") >= 0);
  }

  console.log("test_tpa_referto: ok");
}

main().catch(function (e) {
  console.error(e);
  process.exit(1);
});
