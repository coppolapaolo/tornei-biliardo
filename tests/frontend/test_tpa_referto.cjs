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
 * 1. il tastierino è uno, sempre tutto visibile: dieci numeri, nove lettere
 *    con la loro parola sotto, «Primo tiro di calcio?»; i tasti non ammessi
 *    si spengono, non spariscono;
 * 2. un tocco invia il comando all'indirizzo dei `data-*`, col token CSRF, e
 *    ridisegna con lo stato della risposta;
 * 3. toccare il riquadro dell'avversario passa il tavolo — o, prima della
 *    spaccata, sceglie chi spacca — e il riquadro lo dice;
 * 4. «cancella» toglie l'annotazione del turno in corso;
 * 5. mentre un invio è in corso i tocchi non contano;
 * 6. un rifiuto del server diventa un messaggio, e lo stato non cambia;
 * 7. chi guarda rilegge lo stato quando l'altro annota, non quando annota
 *    lui, e ricarica la pagina se il referto è stato chiuso;
 * 8. il TPA va da 0 a 1000, senza punto, e conta quanto i triangoli;
 * 9. la notazione è quella del referto: spaccata in apice, triangolo vinto
 *    cerchiato, calcio come numero del giocatore sopra la casella;
 * 10. nella card dell'avversario resta scritto il suo ultimo turno;
 * 11. «Indietro» e «Avanti» scorrono i turni **senza chiamare il server**:
 *     rileggere non scrive, e mentre si rilegge il tastierino è spento;
 * 12. «Riparti da questo turno…» apre un foglio che nomina i turni che
 *     escono, e solo la conferma chiama il server;
 * 13. uno stato nuovo dal server riporta al turno in corso;
 * 14. a referto chiuso i triangoli sono ripiegati, con chi li ha vinti
 *     nell'intestazione, e si aprono uno per uno o tutti insieme.
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
    can_clear: false,
    current_rack: 1,
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
      ' data-closed="' + (iniziale.closed ? "true" : "false") + '"' +
      ' data-et-spacca-chiude="spacca e chiude" data-et-apri-tutti="Apri tutti" data-et-chiudi-tutti="Chiudi tutti"' +
      ' data-clear-url="/m/7/tpa/clear" data-restart-url="/m/7/tpa/restart"' +
      ' data-et-posizione="turno {n} di {m}" data-et-rileggi="Rileggi il turno {n} di {m}"' +
      ' data-et-riparti="Riparti da questo turno…" data-et-riparti-titolo="Ripartire dal turno {n}?"' +
      ' data-et-riparti-conferma="Riparti dal turno {n}" data-et-si-riannota="si riannota"' +
      ' data-et-passa="Tocca: tavolo a {nome}" data-et-spacca-lui="Tocca: spacca {nome}"' +
      ' data-et-al-tavolo="al tavolo" data-et-spacca="spacca"' +
      ' data-et-triangoli="Triangoli" data-et-tpa="TPA"' +
      ' data-et-bilia="bilia" data-et-bilie="bilie" data-et-errore-uno="errore" data-et-errori="errori"' +
      ' data-et-senza-tpa="TPA ancora da calcolare" data-et-quante="bilie?"' +
      ' data-et-triangolo="Triangolo"' +
      ' data-et-errore="Non è stato possibile annotare."' +
      ' data-et-cancella="cancella" data-et-cancella-aria="Cancella il turno"' +
      ' data-et-cap-m="sbagliato" data-et-cap-k="di sponda" data-et-cap-s="difesa"' +
      ' data-et-cap-p="in buca" data-et-cap-g="triangolo" data-et-cap-n="non colpita"' +
      ' data-et-kick-in="Primo tiro di calcio?" data-et-kick-in-aria="calcio del giocatore {n}"' +
      ' data-et-runout-chiedi="Un solo turno?"' +
      ' data-et-runout-si="Chiusa in un solo turno">' +
      '<div id="tpaPlayers"></div>' +
      (scrive
        ? '<p id="tpaRileggi" hidden></p><div id="tpaNumbers"></div><div id="tpaLetters"></div>' +
          '<button id="tpaIndietro"></button><span id="tpaPosizione"></span><button id="tpaAvanti"></button>' +
          '<div id="tpaRipartiModal"><h3 id="tpaRipartiTitolo"></h3><div id="tpaRipartiElenco"></div>' +
          '<button id="tpaRipartiConferma"></button></div>'
        : "") +
      '<button id="tpaApriTutti"></button><div id="tpaSheet"></div>' +
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
  const foglio = { aperto: false };
  w.c7TpaReferto.avvia(w.document.getElementById("tpaReferto"), {
    ricarica: function () { ricariche += 1; },
    foglio: {
      apri: function () { foglio.aperto = true; },
      chiudi: function () { foglio.aperto = false; },
    },
  });

  const doc = w.document;
  return {
    doc: doc,
    chiamate: chiamate,
    errori: errori,
    foglio: foglio,
    risposte: risposte,
    ricariche: function () { return ricariche; },
    ascoltatore: function () { return ascoltatore; },
    tasto: function (comando) {
      return doc.querySelector('[data-command="' + comando + '"]');
    },
    casella: function (posto, quale) {
      return doc.getElementById("tpaPlayers").children[posto - 1]
        .querySelector(".c7-tpa-box--" + quale);
    },
    riquadri: function () { return doc.getElementById("tpaPlayers").children; },
    formatTpa: w.c7TpaReferto.formatTpa,
  };
}

function giro() {
  return new Promise(function (resolve) { setTimeout(resolve, 0); });
}

async function main() {
  // 1. Un tastierino solo, sempre tutto visibile; spento ciò che non è ammesso.
  {
    const a = ambiente(stato());
    const numeri = Array.prototype.map.call(
      a.doc.querySelectorAll("#tpaNumbers [data-command]"),
      function (b) { return b.getAttribute("data-command"); }
    );
    assert.deepStrictEqual(numeri, ["clear", "0", "1", "2", "3", "4", "5", "6", "7", "8", "9"]);
    assert.strictEqual(a.tasto("3").disabled, false);
    assert.strictEqual(a.tasto("4").disabled, true);
    const lettere = Array.prototype.map.call(
      a.doc.querySelectorAll("#tpaLetters [data-command]"),
      function (b) { return b.getAttribute("data-command"); }
    );
    assert.deepStrictEqual(lettere, ["M", "K", "S", "P", "G", "N", "n", "x", "p", "K-in"]);
    assert.strictEqual(a.tasto("M").disabled, true);
    assert.strictEqual(a.tasto("K-in").disabled, true, "il calcio c'è sempre, spento");
    assert.strictEqual(a.tasto("M").querySelector(".c7-tpa-key__cap").textContent, "sbagliato");
    assert.strictEqual(a.tasto("n").querySelector(".c7-tpa-key__cap"), null);
    assert.strictEqual(a.casella(1, "white").textContent, "bilie?");
  }

  // 1 bis. A numeri non ammessi il blocco resta: si spegne e basta.
  {
    const a = ambiente(stato({ buttons: ["M", "K-in", "runout"] }));
    assert.strictEqual(a.doc.querySelectorAll("#tpaNumbers [data-command]").length, 11);
    assert.strictEqual(a.tasto("0").disabled, true);
    assert.strictEqual(a.tasto("K-in").disabled, false);
    assert.strictEqual(a.tasto("runout").textContent, "Un solo turno?");
    assert.strictEqual(ambiente(stato()).tasto("runout"), null, "il run-out si chiede solo se ambiguo");
  }

  // 1 ter. A palla 10 c'è anche il 10; a palla 9 no.
  {
    assert.ok(ambiente(stato({ game_type: 10 })).tasto("10"));
    assert.strictEqual(ambiente(stato()).tasto("10"), null);
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
    assert.strictEqual(a.tasto("3").disabled, true);
    assert.strictEqual(a.casella(1, "white").textContent, "3", "dopo il numero parlano le lettere accese");
  }

  // 3. Il riquadro dell'avversario passa il tavolo, e lo dice; il proprio no.
  {
    const a = ambiente(stato());
    const r = a.riquadri();
    assert.strictEqual(r[0].tagName, "DIV");
    assert.ok(r[0].className.indexOf("c7-tpa-half--on") >= 0);
    assert.strictEqual(r[1].tagName, "BUTTON");
    assert.strictEqual(r[1].querySelector(".c7-tpa-half__tap").textContent, "Tocca: tavolo a Sara");
    r[1].click();
    assert.deepStrictEqual(JSON.parse(a.chiamate[0].init.body), { command: "end" });
  }

  // 3 bis. Prima della spaccata lo stesso tocco sceglie chi spacca.
  {
    const s = stato();
    s.current.can_choose_seat = true;
    s.current.is_break = true;
    const a = ambiente(s);
    assert.strictEqual(a.riquadri()[1].querySelector(".c7-tpa-half__tap").textContent, "Tocca: spacca Sara");
    a.riquadri()[1].click();
    assert.deepStrictEqual(JSON.parse(a.chiamate[0].init.body), { command: "seat:2" });
  }

  // 3 ter. Quando il motore non lo ammette, nessun riquadro è un pulsante.
  {
    const a = ambiente(stato({ can_switch_player: false }));
    assert.strictEqual(a.riquadri()[1].tagName, "DIV");
    assert.strictEqual(a.riquadri()[1].querySelector(".c7-tpa-half__tap"), null);
  }

  // 4. «Cancella» toglie l'annotazione del turno; a turno bianco è spento.
  {
    const a = ambiente(stato({ can_clear: true }));
    assert.strictEqual(a.tasto("clear").disabled, false);
    a.tasto("clear").click();
    assert.strictEqual(a.chiamate[0].url, "/m/7/tpa/clear");

    const vuoto = ambiente(stato({ commands: 0 }));
    assert.strictEqual(vuoto.tasto("clear").disabled, true, "a turno bianco non c'è niente da cancellare");
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
    assert.strictEqual(a.casella(1, "white").textContent, "", "a chi guarda non si chiede niente");
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
    assert.ok(a.riquadri()[1].className.indexOf("c7-tpa-half--on") >= 0);
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

  // 8. Il TPA da 0 a 1000, senza punto, grande quanto i triangoli.
  {
    const a = ambiente(stato());
    const f = a.formatTpa;
    assert.strictEqual(f(780), "780");
    assert.strictEqual(f(45), "45");
    assert.strictEqual(f(1000), "1000");
    assert.strictEqual(f(0), "0");
    assert.strictEqual(f(null), "—");
    assert.strictEqual(f(undefined), "—");

    const cifre = a.riquadri()[0].querySelectorAll(".c7-tpa-fig");
    assert.strictEqual(cifre.length, 2);
    assert.strictEqual(cifre[0].textContent, "Triangoli2");
    assert.strictEqual(cifre[1].textContent, "TPA780");
    assert.strictEqual(cifre[0].querySelector(".c7-tpa-fig__v").className,
      cifre[1].querySelector(".c7-tpa-fig__v").className, "stessa evidenza");
    assert.ok(a.riquadri()[0].querySelector(".c7-tpa-half__meta").textContent.indexOf("4 bilie · 1 errore") >= 0);
  }

  // 9. La notazione del referto.
  {
    const s = stato({ buttons: [] });
    s.current.is_break = true;
    s.current.winning = true;
    s.current.main_note = "M^n";
    s.current.secondary_note = "P";
    s.current.annotation = { break_potted: 1, total_potted: 3, first_shot_kick_in: true, run_out: null };
    const a = ambiente(s);
    const bianca = a.casella(1, "white");
    assert.strictEqual(bianca.querySelector(".c7-tpa-nt__break").textContent, "1", "spaccata in apice");
    assert.strictEqual(bianca.querySelector(".c7-tpa-nt__balls--won").textContent, "3", "triangolo vinto: cerchio");
    assert.strictEqual(bianca.querySelector(".c7-tpa-nt__main").textContent, "Mn");
    assert.strictEqual(bianca.querySelector(".c7-tpa-nt__main sup").textContent, "n");
    assert.ok(bianca.textContent.indexOf("/") < 0, "mai «1/3»");
    assert.strictEqual(a.casella(1, "shaded").textContent, "P");

    // Il calcio: il numero del giocatore, sopra la casella e fuori dal bianco.
    const calcio = a.riquadri()[0].querySelector(".c7-tpa-kickrow");
    assert.strictEqual(calcio.textContent, "1");
    assert.strictEqual(bianca.contains(calcio), false);
    // La riga c'è anche dall'altra parte, vuota: le caselle restano allineate.
    assert.strictEqual(a.riquadri()[1].querySelector(".c7-tpa-kickrow").textContent, "");
  }

  // 10. Nella card dell'avversario resta il suo ultimo turno di questo
  //     triangolo; a triangolo nuovo è bianca.
  {
    const turno = function (player, tot, main, extra) {
      return Object.assign({
        player: player, is_break: false, winning: false, main_note: main, secondary_note: "",
        annotation: { break_potted: null, total_potted: tot, first_shot_kick_in: false },
        score_snapshot: null,
      }, extra || {});
    };
    const racks = [
      { number: 1, turns: [turno(2, 5, "M")] },
      { number: 2, turns: [turno(1, 1, "M"), turno(2, 2, "S^x"), turno(1, null, "")] },
    ];
    const a = ambiente(stato({ racks: racks, current_rack: 2 }));
    assert.strictEqual(a.casella(2, "white").textContent, "2Sx");
    assert.strictEqual(a.casella(1, "white").textContent, "bilie?");

    const nuovo = ambiente(stato({ racks: [racks[0], { number: 2, turns: [turno(1, null, "")] }], current_rack: 2 }));
    assert.strictEqual(nuovo.casella(2, "white").textContent, "");
  }

  // 11-13. Rileggere il referto, e ripartire da un turno.
  {
    const foto = function (r1, t1, r2, t2) {
      return { 1: { racks_won: r1, tpa: t1, balls_potted: 3, total_errors: 1 },
               2: { racks_won: r2, tpa: t2, balls_potted: 2, total_errors: 0 } };
    };
    const turno = function (n, player, tot, main, snap, extra) {
      return Object.assign({
        turn: n, player: player, is_break: n === 1, winning: false, main_note: main, secondary_note: "",
        annotation: { break_potted: n === 1 ? 1 : null, total_potted: tot, first_shot_kick_in: false },
        score_snapshot: snap,
      }, extra || {});
    };
    const racks = [
      { number: 1, turns: [turno(1, 1, 3, "M", foto(0, 750, 0, null)), turno(2, 2, 6, "", foto(0, 750, 1, 1000), { winning: true })] },
      { number: 2, turns: [turno(1, 2, 2, "S", foto(0, 750, 1, 900)), turno(2, 1, null, "", null)] },
    ];
    const vivo = stato({ racks: racks, current_rack: 2, current_turn: 2, can_clear: false });
    const a = ambiente(vivo);
    const doc = a.doc;
    const indietro = doc.getElementById("tpaIndietro");
    const avanti = doc.getElementById("tpaAvanti");
    assert.strictEqual(doc.getElementById("tpaPosizione").textContent, "turno 4 di 4");
    assert.strictEqual(avanti.disabled, true);
    assert.strictEqual(indietro.disabled, false);
    assert.strictEqual(doc.getElementById("tpaRileggi").hidden, true);

    // Due passi indietro: il turno 2, quello che ha chiuso il primo triangolo.
    indietro.click();
    indietro.click();
    assert.strictEqual(a.chiamate.length, 0, "rileggere non chiama il server");
    assert.strictEqual(doc.getElementById("tpaPosizione").textContent, "turno 2 di 4");
    assert.strictEqual(doc.getElementById("tpaRileggi").hidden, false);
    assert.strictEqual(doc.getElementById("tpaRileggi").textContent, "Rileggi il turno 2 di 4");
    // Al tavolo c'è chi giocava quel turno, col punteggio di allora.
    assert.ok(a.riquadri()[1].className.indexOf("c7-tpa-half--on") >= 0);
    assert.strictEqual(a.riquadri()[1].querySelectorAll(".c7-tpa-fig__v")[0].textContent, "1");
    assert.strictEqual(a.riquadri()[1].querySelectorAll(".c7-tpa-fig__v")[1].textContent, "1000");
    assert.strictEqual(a.casella(2, "white").querySelector(".c7-tpa-nt__balls--won").textContent, "6");
    assert.strictEqual(a.casella(1, "white").textContent, "13M", "nell'altra card il suo turno di prima");
    // Qui non si scrive: tastierino spento, nessun riquadro da toccare.
    assert.strictEqual(a.tasto("3").disabled, true);
    assert.strictEqual(a.tasto("clear").disabled, true);
    assert.strictEqual(a.riquadri()[0].tagName, "DIV");
    assert.strictEqual(a.tasto("K-in"), null);
    assert.strictEqual(a.tasto("restart").disabled, false);
    assert.strictEqual(a.tasto("restart").textContent, "Riparti da questo turno…");

    // In fondo a sinistra non si va oltre il primo turno.
    indietro.click();
    assert.strictEqual(indietro.disabled, true);
    avanti.click();

    // 12. Il foglio nomina chi esce; solo la conferma chiama il server.
    a.tasto("restart").click();
    assert.strictEqual(a.foglio.aperto, true);
    assert.strictEqual(a.chiamate.length, 0);
    assert.strictEqual(doc.getElementById("tpaRipartiTitolo").textContent, "Ripartire dal turno 2?");
    const righe = doc.getElementById("tpaRipartiElenco").children;
    assert.strictEqual(righe.length, 2, "il turno che si riapre e l'unico scritto dopo; quello bianco in corso non conta");
    assert.ok(righe[0].textContent.indexOf("si riannota") >= 0);
    assert.ok(righe[1].className.indexOf("c7-tpa-out") >= 0);
    assert.ok(righe[1].textContent.indexOf("Sara") >= 0 && righe[1].textContent.indexOf("2S") >= 0);
    assert.strictEqual(doc.getElementById("tpaRipartiConferma").textContent, "Riparti dal turno 2");

    doc.getElementById("tpaRipartiConferma").click();
    assert.strictEqual(a.chiamate[0].url, "/m/7/tpa/restart");
    assert.deepStrictEqual(JSON.parse(a.chiamate[0].init.body), { rack: 1, turn: 2 });

    // 13. Lo stato nuovo riporta al turno in corso, e il foglio si chiude.
    const dopo = stato({ racks: [{ number: 1, turns: [racks[0].turns[0], turno(2, 2, null, "", null)] }],
      current_rack: 1, current_turn: 2, current_player: 2 });
    a.risposte[0].ok({ success: true, state: dopo });
    await giro();
    assert.strictEqual(a.foglio.aperto, false);
    assert.strictEqual(doc.getElementById("tpaPosizione").textContent, "turno 2 di 2");
    assert.strictEqual(doc.getElementById("tpaRileggi").hidden, true);
    assert.strictEqual(a.tasto("3").disabled, false);
    assert.strictEqual(a.tasto("restart"), null);
  }

  // 14. A referto chiuso il referto è un racconto: triangoli ripiegati.
  {
    const turno = function (player, tot, extra) {
      return Object.assign({
        player: player, is_break: false, winning: false, main_note: "M", secondary_note: "",
        annotation: { break_potted: null, total_potted: tot, first_shot_kick_in: false },
        score_snapshot: null,
      }, extra || {});
    };
    const racks = [
      { number: 1, turns: [turno(1, 9, { is_break: true, winning: true, main_note: "",
          annotation: { break_potted: 3, total_potted: 9, first_shot_kick_in: false },
          score_snapshot: { 1: { racks_won: 1 }, 2: { racks_won: 0 } } })] },
      { number: 2, turns: [turno(2, 4, { is_break: true }), turno(1, 5, { winning: true, main_note: "",
          score_snapshot: { 1: { racks_won: 2 }, 2: { racks_won: 0 } } })] },
    ];
    const a = ambiente(stato({ closed: true, racks: racks, current_player: 2 }), { scrive: false });
    const doc = a.doc;
    const foglio = doc.getElementById("tpaSheet");
    const teste = foglio.querySelectorAll(".c7-tpa-sheet__rack");
    assert.strictEqual(teste.length, 2);
    assert.strictEqual(teste[0].tagName, "BUTTON");
    assert.ok(teste[0].textContent.indexOf("Triangolo 1 · Marco") >= 0);
    assert.ok(teste[0].textContent.indexOf("spacca e chiude") >= 0);
    assert.ok(teste[1].textContent.indexOf("spacca e chiude") < 0, "ha vinto chi non spaccava");
    assert.ok(teste[1].textContent.indexOf("2–0") >= 0);
    const righe = function () {
      return Array.prototype.filter.call(foglio.querySelectorAll(".c7-tpa-sheet__turn"),
        function (r) { return !r.hidden; }).length;
    };
    assert.strictEqual(righe(), 0, "tutti ripiegati");
    teste[1].click();
    assert.strictEqual(righe(), 2);
    assert.strictEqual(foglio.querySelectorAll(".c7-tpa-sheet__rack")[1].getAttribute("aria-expanded"), "true");
    const tutti = doc.getElementById("tpaApriTutti");
    assert.strictEqual(tutti.textContent, "Apri tutti");
    tutti.click();
    assert.strictEqual(righe(), 3);
    assert.strictEqual(tutti.textContent, "Chiudi tutti");
    tutti.click();
    assert.strictEqual(righe(), 0);

    // Le card: nessuno è al tavolo, niente caselle, in evidenza chi ha vinto.
    assert.strictEqual(a.riquadri()[0].querySelector(".c7-tpa-slip"), null);
    assert.ok(a.riquadri()[0].className.indexOf("c7-tpa-half--on") >= 0);
    assert.ok(a.riquadri()[1].className.indexOf("c7-tpa-half--on") < 0);
    assert.ok(a.riquadri()[1].textContent.indexOf("al tavolo") < 0);
  }

  // A referto aperto i triangoli restano distesi, e le teste non sono pulsanti.
  {
    const a = ambiente(stato({ racks: [{ number: 1, turns: [{ player: 1, is_break: true, winning: false,
      main_note: "M", secondary_note: "", annotation: { break_potted: 1, total_potted: 3, first_shot_kick_in: false },
      score_snapshot: null }] }] }));
    const testa = a.doc.querySelector(".c7-tpa-sheet__rack");
    assert.strictEqual(testa.tagName, "DIV");
    assert.strictEqual(a.doc.querySelectorAll(".c7-tpa-sheet__turn")[0].hidden, false);
  }

  // Il referto sotto: stessa notazione delle caselle.
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
    const prima = foglio.children[1].querySelector(".c7-tpa-sheet__note");
    assert.strictEqual(prima.querySelector(".c7-tpa-nt__break").textContent, "1");
    assert.ok(prima.textContent.indexOf("/") < 0);
    assert.ok(prima.textContent.indexOf("P") >= 0);
    const seconda = foglio.children[2].querySelector(".c7-tpa-sheet__note");
    assert.strictEqual(seconda.querySelector(".c7-tpa-nt__balls--won").textContent, "6");
    assert.strictEqual(seconda.querySelector(".c7-tpa-kick").textContent, "2");
    assert.ok(seconda.textContent.indexOf("↺") < 0 && seconda.textContent.indexOf("●") < 0);
  }

  console.log("test_tpa_referto: ok");
}

main().catch(function (e) {
  console.error(e);
  process.exit(1);
});
