/**
 * Headless automation per static/js/score_pop.js — la cifra che cambia salta.
 *
 * Tre proprietà:
 *
 * 1. `segna(el, valore)` scrive il valore e mette `.is-pop` **solo** se è
 *    cambiato, e lo rimette anche la seconda volta (il riflusso fra togliere
 *    e rimettere la classe è ciò che fa ripartire l'animazione);
 * 2. dopo un ricaricamento della stessa pagina, entro la finestra, le cifre
 *    diverse da quelle salvate a `pagehide` saltano, le uguali no;
 * 3. un'altra pagina, un salvataggio vecchio o un numero diverso di cifre
 *    non fanno saltare niente — sarebbe un movimento che non spiega nessun
 *    cambiamento.
 *
 * Run:  cd tests/frontend && npm install && npm test
 */
const fs = require("fs");
const path = require("path");
const assert = require("assert");
const { JSDOM } = require("jsdom");

const SRC = fs.readFileSync(
  path.join(__dirname, "..", "..", "static", "js", "score_pop.js"),
  "utf8"
);

const CARD =
  '<div class="c7-score"><span class="c7-score__num">3</span>' +
  '<span class="c7-score__num">2</span></div>';

async function pagina(url, html, storagePrima) {
  const dom = new JSDOM("<!doctype html><body>" + html + "</body>", {
    url: url,
    runScripts: "outside-only",
    pretendToBeVisual: true,
  });
  const w = dom.window;
  if (storagePrima) {
    w.sessionStorage.setItem("c7-score-prima", JSON.stringify(storagePrima));
  }
  w.eval(SRC);
  // Come nel browser: `ripristina` gira a DOMContentLoaded, che jsdom
  // spedisce al giro successivo dell'event loop.
  await new Promise(function (r) {
    if (w.document.readyState !== "loading") r();
    else w.addEventListener("DOMContentLoaded", r);
  });
  return w;
}

function cifre(w) {
  return Array.from(w.document.querySelectorAll(".c7-score__num"));
}

async function segna_salta_solo_se_cambia() {
  const w = await pagina("http://localhost/match/1", CARD);
  const [a] = cifre(w);
  assert.strictEqual(w.c7ScorePop.segna(a, 3), false, "stesso valore: niente salto");
  assert.ok(!a.classList.contains("is-pop"));
  assert.strictEqual(w.c7ScorePop.segna(a, 4), true);
  assert.strictEqual(a.textContent, "4");
  assert.ok(a.classList.contains("is-pop"), "valore nuovo: salta");
  // La seconda cifra della stessa partita deve saltare di nuovo: la classe
  // viene tolta e rimessa, non lasciata lì.
  let tolta = false;
  const remove = a.classList.remove.bind(a.classList);
  a.classList.remove = function (c) {
    if (c === "is-pop") tolta = true;
    return remove(c);
  };
  assert.strictEqual(w.c7ScorePop.segna(a, 5), true);
  assert.ok(tolta, "la classe è stata tolta prima di essere rimessa");
  assert.ok(a.classList.contains("is-pop"));
  console.log("  ok  segna: salta solo se il valore cambia, e rigioca");
}

async function pagehide_salva_le_cifre() {
  const w = await pagina("http://localhost/match/1", CARD);
  w.dispatchEvent(new w.Event("pagehide"));
  const salvato = JSON.parse(w.sessionStorage.getItem("c7-score-prima"));
  assert.strictEqual(salvato.pagina, "/match/1");
  assert.deepStrictEqual(salvato.valori, ["3", "2"]);
  assert.ok(Date.now() - salvato.quando < 2000);
  console.log("  ok  pagehide salva pagina, orario e cifre");
}

async function dopo_il_ricaricamento_saltano_solo_le_cifre_cambiate() {
  const w = await pagina("http://localhost/match/1", CARD.replace(">3<", ">4<"), {
    pagina: "/match/1",
    quando: Date.now() - 500,
    valori: ["3", "2"],
  });
  const [a, b] = cifre(w);
  assert.ok(a.classList.contains("is-pop"), "3 → 4 salta");
  assert.ok(!b.classList.contains("is-pop"), "2 → 2 sta fermo");
  assert.strictEqual(
    w.sessionStorage.getItem("c7-score-prima"),
    null,
    "il confronto si consuma: un secondo caricamento non rigioca"
  );
  console.log("  ok  dopo il ricaricamento salta solo la cifra cambiata");
}

async function altra_pagina_o_salvataggio_vecchio_non_fanno_niente() {
  const casi = [
    ["altra pagina", { pagina: "/match/2", quando: Date.now(), valori: ["3", "2"] }],
    ["troppo tempo", { pagina: "/match/1", quando: Date.now() - 60000, valori: ["3", "2"] }],
    ["numero di cifre diverso", { pagina: "/match/1", quando: Date.now(), valori: ["3"] }],
  ];
  for (const [nome, prima] of casi) {
    const w = await pagina("http://localhost/match/1", CARD.replace(">3<", ">4<"), prima);
    assert.ok(
      cifre(w).every((c) => !c.classList.contains("is-pop")),
      nome + ": nessun salto"
    );
  }
  console.log("  ok  altra pagina, salvataggio vecchio, cifre diverse: fermo");
}

async function senza_sessionstorage_non_esplode() {
  const w = await pagina("http://localhost/match/1", CARD);
  Object.defineProperty(w, "sessionStorage", {
    get() {
      throw new Error("negato");
    },
  });
  assert.doesNotThrow(() => w.c7ScorePop.salva());
  assert.strictEqual(w.c7ScorePop.ripristina(), 0);
  console.log("  ok  sessionStorage negato: la pagina resta ferma, senza errori");
}

(async function () {
  console.log("score_pop.js — la cifra che cambia salta");
  await segna_salta_solo_se_cambia();
  await pagehide_salva_le_cifre();
  await dopo_il_ricaricamento_saltano_solo_le_cifre_cambiate();
  await altra_pagina_o_salvataggio_vecchio_non_fanno_niente();
  await senza_sessionstorage_non_esplode();
  console.log("tutti i test di score_pop.js passano");
})().catch(function (e) {
  console.error(e);
  process.exit(1);
});
