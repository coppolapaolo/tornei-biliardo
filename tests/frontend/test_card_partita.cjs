/**
 * Headless automation per static/js/card_partita.js — gli stepper della card
 * del direttore, nelle quattro forme (due, set, trio, X con esercizio).
 *
 * Quattro proprietà:
 *
 * 1. i + si spengono alla regola della forma: «al N» e «esattamente N» per la
 *    partita a due e il set, quello che dice il server per il trio (l'ordine
 *    del girone), il massimo del turno per la X;
 * 2. un tocco invia i campi della forma all'indirizzo della card, e la card si
 *    aggiorna col punteggio che torna — anche i + del trio;
 * 3. alla chiusura (partita finita, set chiuso, card che cambia stato) la
 *    pagina si ricarica;
 * 4. la X non salva al tocco: il punteggio parte con «Convalida».
 * 5. il numero cambia **al tocco**, non alla risposta: due tocchi veloci si
 *    accodano e parte l'ultimo punteggio, un rifiuto rimette quello
 *    confermato (Ronin Cup, 16/09/2026: «tap e non succede niente»);
 * 6. il tocco che chiude **aspetta** prima di partire: la card dice che si sta
 *    chiudendo e offre «Annulla»; se la pagina se ne va, parte lo stesso.
 * 7. «Valida il risultato» aspetta come il tocco che chiude (`attendi`),
 *    con la stessa striscia e lo stesso «Annulla» (gara del 23/09/2026).
 *
 * Run:  cd tests/frontend && npm install && npm test
 */
const fs = require("fs");
const path = require("path");
const assert = require("assert");
const { JSDOM } = require("jsdom");

const SRC = fs.readFileSync(
  path.join(__dirname, "..", "..", "static", "js", "card_partita.js"),
  "utf8"
);

const ATTESA = 30;

function dopo(ms) {
  return new Promise(function (fatto) { setTimeout(fatto, ms); });
}

function differita() {
  let sblocca;
  const quando = new Promise(function (fatto) { sblocca = fatto; });
  return { quando: quando, sblocca: sblocca };
}

function lato(n) {
  return (
    '<button class="c7-partita__meno" data-lato="' + n + '"></button>' +
    '<span data-num="' + n + '"></span>' +
    '<button class="c7-partita__piu" data-lato="' + n + '"></button>'
  );
}

function ambiente(attributi, lati, risposte) {
  const dom = new JSDOM(
    "<!doctype html><body><article id=\"c\" " + attributi + ">" +
      [1, 2, 3].slice(0, lati).map(lato).join("") +
      "</article></body>",
    { runScripts: "outside-only" }
  );
  const w = dom.window;
  const inviati = [];
  let ricariche = 0;
  w.fetch = function (url, init) {
    const campi = {};
    init.body.forEach(function (v, k) { campi[k] = v; });
    inviati.push({ url: url, campi: campi, headers: init.headers });
    inviati[inviati.length - 1].keepalive = init.keepalive === true;
    const r = risposte.shift() || { ok: true, json: { success: true } };
    const pronta = { ok: r.ok, json: function () { return Promise.resolve(r.json); } };
    // `quando`: una promessa che il test risolve a mano, per guardare la
    // card mentre la richiesta e' ancora in volo.
    return r.quando ? r.quando.then(function () { return pronta; }) : Promise.resolve(pronta);
  };
  w.eval(SRC);
  const card = w.document.getElementById("c");
  const opzioni = {
    csrf: "tok",
    ricarica: function () { ricariche += 1; },
    attesaChiusura: ATTESA,
    attesaRicarica: 1,
    testi: { chiusura: "si chiude fra {n}", annulla: "annulla", chiusa: "chiusa" },
  };
  w.CardPartita.aggiorna(card);
  return {
    w: w,
    card: card,
    inviati: inviati,
    ricariche: function () { return ricariche; },
    piu: function (n) { return card.querySelector('.c7-partita__piu[data-lato="' + n + '"]'); },
    meno: function (n) { return card.querySelector('.c7-partita__meno[data-lato="' + n + '"]'); },
    num: function (n) { return card.querySelector('[data-num="' + n + '"]').textContent; },
    striscia: function () { return card.querySelector(".c7-partita__chiusura"); },
    tocca: function (n, delta) {
      const b = delta > 0 ? this.piu(n) : this.meno(n);
      return w.CardPartita.passo(b, delta, opzioni);
    },
  };
}

async function la_partita_a_due_si_ferma_alla_distanza() {
  const a = ambiente('data-tipo="due" data-punti="4,1" data-max="5" data-race-to="1" ' +
    'data-url="/admin/match/9/punteggio" data-campi="player1_score,player2_score" data-stato="in_corso"', 2,
    [{ ok: true, json: { success: true, player1_score: 4, player2_score: 2, finished: false, at_distance: false } }]);
  assert.strictEqual(a.piu(1).disabled, false);
  assert.strictEqual(a.num(1), "4");
  await a.tocca(2, 1);
  assert.deepStrictEqual(a.inviati[0].campi, { player1_score: "4", player2_score: "2" });
  assert.strictEqual(a.inviati[0].headers["X-CSRFToken"], "tok");
  assert.strictEqual(a.card.dataset.punti, "4,2");
  assert.strictEqual(a.num(2), "2");

  const esatto = ambiente('data-tipo="due" data-punti="2,1" data-max="3" data-race-to="0"', 2, []);
  assert.strictEqual(esatto.piu(1).disabled, true, "esattamente 3: a somma 3 il + si spegne");
  assert.strictEqual(esatto.piu(2).disabled, true);
}

async function il_trio_segue_i_piu_del_server() {
  const a = ambiente('data-tipo="trio" data-punti="0,0,0" data-piu="1,1,0" ' +
    'data-url="/admin/gara/trio/7/punteggio" data-campi="player1_racks,player2_racks,player3_racks" data-stato="in_corso"', 3,
    [{ ok: true, json: { success: true, punti: [1, 0, 0], piu: [true, true, true], finished: false, at_distance: false } }]);
  assert.strictEqual(a.piu(3).disabled, true, "il terzo aspetta il secondo triangolo");
  assert.strictEqual(a.meno(1).disabled, true);
  // Un tocco su un + spento non parte.
  assert.strictEqual(await a.tocca(3, 1), false);
  assert.strictEqual(a.inviati.length, 0);
  await a.tocca(1, 1);
  assert.deepStrictEqual(a.inviati[0].campi, { player1_racks: "1", player2_racks: "0", player3_racks: "0" });
  assert.strictEqual(a.card.dataset.piu, "1,1,1");
  assert.strictEqual(a.piu(3).disabled, false);
  assert.strictEqual(a.meno(1).disabled, false);
}

async function alla_chiusura_la_pagina_si_ricarica() {
  const set = ambiente('data-tipo="set" data-punti="3,1" data-max="4" data-race-to="1" ' +
    'data-url="/admin/match/9/set/punteggio" data-campi="player1_racks,player2_racks" data-stato="in_corso"', 2,
    [{ ok: true, json: { success: true, punti: [4, 1], set_chiuso: true, finished: false } }]);
  await set.tocca(1, 1);
  assert.strictEqual(set.inviati.length, 0, "il tocco che chiude aspetta");
  await dopo(ATTESA + 20);
  assert.deepStrictEqual(set.inviati[0].campi, { player1_racks: "4", player2_racks: "1" });
  assert.strictEqual(set.ricariche(), 1);

  const due = ambiente('data-tipo="due" data-punti="5,1" data-max="5" data-race-to="1" ' +
    'data-url="/u" data-campi="player1_score,player2_score" data-stato="da_validare"', 2,
    [{ ok: true, json: { success: true, player1_score: 4, player2_score: 1, finished: false, at_distance: false } }]);
  await due.tocca(1, -1);
  assert.strictEqual(due.ricariche(), 1, "la card da validare scesa sotto la distanza cambia forma");
}

async function un_rifiuto_rimette_la_card_com_era() {
  const a = ambiente('data-tipo="due" data-punti="1,1" data-max="5" data-race-to="1" ' +
    'data-url="/u" data-campi="player1_score,player2_score" data-stato="in_corso"', 2,
    [{ ok: false, json: { success: false, error: "Il turno è bloccato" } }]);
  let messaggio = null;
  await a.w.CardPartita.passo(a.piu(1), 1, { errore: function (m) { messaggio = m; } });
  assert.strictEqual(messaggio, "Il turno è bloccato");
  assert.strictEqual(a.card.dataset.punti, "1,1");
  assert.strictEqual(a.piu(1).disabled, false);
}

async function il_foglio_del_trio_si_ferma_ai_triangoli_del_trio() {
  // Il foglio della correzione: nessun indirizzo e nessun `data-piu` dal
  // server. Il limite è quello del trio finito: quattro a testa, sei in tutto.
  const a = ambiente('data-tipo="trio" data-punti="4,1,0" data-massimo="4" data-totale="6"', 3, []);
  assert.strictEqual(a.piu(1).disabled, true, "nessuno vince più dei triangoli che gioca");
  assert.strictEqual(a.piu(2).disabled, false);
  await a.tocca(2, 1);
  assert.strictEqual(a.card.dataset.punti, "4,2,0");
  assert.strictEqual(a.inviati.length, 0, "il foglio non salva al tocco");
  assert.strictEqual(a.piu(2).disabled, true, "a somma piena i + si spengono");
  assert.strictEqual(a.piu(3).disabled, true);
  assert.strictEqual(a.meno(3).disabled, true);
}

async function la_x_non_salva_al_tocco() {
  const a = ambiente('data-tipo="x" data-punti="2" data-max="3"', 1, []);
  await a.tocca(1, 1);
  assert.strictEqual(a.card.dataset.punti, "3");
  assert.strictEqual(a.piu(1).disabled, true, "al massimo del turno il + si spegne");
  assert.strictEqual(a.inviati.length, 0);
  await a.tocca(1, -1);
  assert.strictEqual(a.num(1), "2");
}


async function il_numero_cambia_al_tocco() {
  const volo = differita();
  const a = ambiente('data-tipo="due" data-punti="1,1" data-max="5" data-race-to="1" ' +
    'data-url="/u" data-campi="player1_score,player2_score" data-stato="in_corso"', 2,
    [{ ok: true, json: { success: true, player1_score: 2, player2_score: 1 }, quando: volo.quando }]);
  const fatto = a.tocca(1, 1);
  assert.strictEqual(a.num(1), "2", "il numero non aspetta il server");
  assert.strictEqual(a.piu(1).disabled, false, "e i tasti restano vivi");
  volo.sblocca();
  await fatto;
  assert.strictEqual(a.card.dataset.punti, "2,1");
}

async function due_tocchi_veloci_si_accodano() {
  const volo = differita();
  const a = ambiente('data-tipo="due" data-punti="1,1" data-max="5" data-race-to="1" ' +
    'data-url="/u" data-campi="player1_score,player2_score" data-stato="in_corso"', 2,
    [{ ok: true, json: { success: true, player1_score: 2, player2_score: 1 }, quando: volo.quando },
     { ok: true, json: { success: true, player1_score: 3, player2_score: 1 } }]);
  const primo = a.tocca(1, 1);
  a.tocca(1, 1);
  assert.strictEqual(a.num(1), "3");
  assert.strictEqual(a.inviati.length, 1, "una richiesta alla volta");
  volo.sblocca();
  await primo;
  await dopo(5);
  assert.deepStrictEqual(a.inviati.map(function (i) { return i.campi.player1_score; }), ["2", "3"]);
  assert.strictEqual(a.card.dataset.punti, "3,1", "la risposta vecchia non riscrive il numero nuovo");
}

async function un_rifiuto_torna_al_punteggio_confermato() {
  const volo = differita();
  const a = ambiente('data-tipo="due" data-punti="1,1" data-max="5" data-race-to="1" ' +
    'data-url="/u" data-campi="player1_score,player2_score" data-stato="in_corso"', 2,
    [{ ok: false, json: { success: false, error: "no" }, quando: volo.quando }]);
  const primo = a.tocca(1, 1);
  a.tocca(1, 1);
  assert.strictEqual(a.num(1), "3");
  volo.sblocca();
  await primo;
  assert.strictEqual(a.card.dataset.punti, "1,1");
  assert.strictEqual(a.num(1), "1");
  assert.strictEqual(a.inviati.length, 1, "dopo un rifiuto la coda si butta");
}

async function il_tocco_che_chiude_aspetta() {
  const a = ambiente('data-tipo="due" data-punti="4,1" data-max="5" data-race-to="1" ' +
    'data-url="/u" data-campi="player1_score,player2_score" data-stato="in_corso"', 2,
    [{ ok: true, json: { success: true, player1_score: 5, player2_score: 1, finished: true } }]);
  await a.tocca(1, 1);
  assert.strictEqual(a.num(1), "5", "il numero finale si vede subito");
  assert.strictEqual(a.inviati.length, 0, "ma la chiusura non e' ancora partita");
  assert.ok(a.striscia(), "la card dice che si sta chiudendo");
  assert.ok(a.striscia().textContent.indexOf("si chiude fra") !== -1);
  await dopo(ATTESA + 20);
  assert.deepStrictEqual(a.inviati[0].campi, { player1_score: "5", player2_score: "1" });
  assert.strictEqual(a.ricariche(), 1);
}

async function annulla_ferma_la_chiusura() {
  const a = ambiente('data-tipo="due" data-punti="4,1" data-max="5" data-race-to="1" ' +
    'data-url="/u" data-campi="player1_score,player2_score" data-stato="in_corso"', 2, []);
  await a.tocca(1, 1);
  a.striscia().querySelector("button").click();
  assert.strictEqual(a.num(1), "4");
  assert.strictEqual(a.striscia(), null);
  assert.strictEqual(a.piu(1).disabled, false);
  await dopo(ATTESA + 20);
  assert.strictEqual(a.inviati.length, 0, "il server ha gia' il 4 a 1: niente da inviare");
  assert.strictEqual(a.ricariche(), 0);
}

async function il_meno_durante_l_attesa_annulla() {
  const a = ambiente('data-tipo="due" data-punti="4,1" data-max="5" data-race-to="1" ' +
    'data-url="/u" data-campi="player1_score,player2_score" data-stato="in_corso"', 2, []);
  await a.tocca(1, 1);
  await a.tocca(1, -1);
  assert.strictEqual(a.num(1), "4");
  assert.strictEqual(a.striscia(), null);
  await dopo(ATTESA + 20);
  assert.strictEqual(a.inviati.length, 0);
  assert.strictEqual(a.ricariche(), 0);
}

async function se_la_pagina_se_ne_va_la_chiusura_parte_lo_stesso() {
  const a = ambiente('data-tipo="due" data-punti="4,1" data-max="5" data-race-to="1" ' +
    'data-url="/u" data-campi="player1_score,player2_score" data-stato="in_corso"', 2,
    [{ ok: true, json: { success: true, finished: true } }]);
  await a.tocca(1, 1);
  a.w.dispatchEvent(new a.w.Event("pagehide"));
  assert.strictEqual(a.inviati.length, 1);
  assert.deepStrictEqual(a.inviati[0].campi, { player1_score: "5", player2_score: "1" });
  assert.strictEqual(a.inviati[0].keepalive, true);
  await dopo(ATTESA + 20);
  assert.strictEqual(a.inviati.length, 1, "e non parte una seconda volta");
}

function ambienteValida() {
  const dom = new JSDOM(
    '<!doctype html><body><article class="c7-partita" id="c">' +
      '<div class="c7-partita__lati"></div>' +
      '<button id="v">Valida il risultato</button></article></body>',
    { runScripts: "outside-only" }
  );
  const w = dom.window;
  w.eval(SRC);
  const chiamate = [];
  const btn = w.document.getElementById("v");
  const card = w.document.getElementById("c");
  const opzioni = { attesaChiusura: ATTESA, testi: { chiusura: "si chiude fra {n}", annulla: "annulla" } };
  return {
    w: w,
    btn: btn,
    chiamate: chiamate,
    striscia: function () { return card.querySelector(".c7-partita__chiusura"); },
    valida: function () {
      return w.CardPartita.attendi(btn, function (keepalive) { chiamate.push(keepalive); }, opzioni);
    },
  };
}

async function valida_aspetta_prima_di_partire() {
  const a = ambienteValida();
  assert.strictEqual(a.valida(), true);
  assert.strictEqual(a.chiamate.length, 0, "la validazione non parte subito");
  assert.ok(a.striscia(), "la card dice che si sta chiudendo");
  assert.ok(a.striscia().textContent.indexOf("si chiude fra") !== -1);
  assert.strictEqual(a.btn.disabled, true, "un secondo tocco non accoda niente");
  assert.strictEqual(a.valida(), false);
  await dopo(ATTESA + 20);
  assert.deepStrictEqual(a.chiamate, [false], "parte una volta sola");
  assert.strictEqual(a.striscia(), null);
}

async function annulla_ferma_la_validazione() {
  const a = ambienteValida();
  a.valida();
  a.striscia().querySelector("button").click();
  assert.strictEqual(a.striscia(), null);
  assert.strictEqual(a.btn.disabled, false, "il pulsante torna disponibile");
  await dopo(ATTESA + 20);
  assert.strictEqual(a.chiamate.length, 0);
}

async function se_la_pagina_se_ne_va_la_validazione_parte_lo_stesso() {
  const a = ambienteValida();
  a.valida();
  a.w.dispatchEvent(new a.w.Event("pagehide"));
  assert.deepStrictEqual(a.chiamate, [true], "con keepalive");
  await dopo(ATTESA + 20);
  assert.strictEqual(a.chiamate.length, 1, "e non parte una seconda volta");
}

(async function () {
  const prove = [
    la_partita_a_due_si_ferma_alla_distanza,
    il_trio_segue_i_piu_del_server,
    alla_chiusura_la_pagina_si_ricarica,
    un_rifiuto_rimette_la_card_com_era,
    il_foglio_del_trio_si_ferma_ai_triangoli_del_trio,
    la_x_non_salva_al_tocco,
    il_numero_cambia_al_tocco,
    due_tocchi_veloci_si_accodano,
    un_rifiuto_torna_al_punteggio_confermato,
    il_tocco_che_chiude_aspetta,
    annulla_ferma_la_chiusura,
    il_meno_durante_l_attesa_annulla,
    se_la_pagina_se_ne_va_la_chiusura_parte_lo_stesso,
    valida_aspetta_prima_di_partire,
    annulla_ferma_la_validazione,
    se_la_pagina_se_ne_va_la_validazione_parte_lo_stesso,
  ];
  for (const prova of prove) {
    await prova();
    console.log("ok -", prova.name);
  }
  console.log("card_partita: " + prove.length + " prove superate");
})().catch(function (e) {
  console.error(e);
  process.exit(1);
});
