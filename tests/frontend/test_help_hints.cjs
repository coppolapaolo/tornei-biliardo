/**
 * Headless automation per static/js/help-hints.js — la «modalità aiuto».
 *
 * Il componente non sa cos'è una competizione di prova (ADR-058): sa che una
 * pagina può dichiarare un attivatore (`[data-help-toggle]`), che l'utente
 * può spegnere la modalità per il suo browser, e che l'API di aiuto gli dà i
 * testi della schermata. Le proprietà verificate qui:
 *
 * 1. senza attivatore in pagina non chiama nemmeno l'API;
 * 2. con l'attivatore, ogni `[data-help]` con un suggerimento riceve una «?»
 *    — una sola, anche dopo un secondo giro — e le ancore senza elemento non
 *    rompono niente;
 * 3. la «?» apre un fumetto con titolo, testo e collegamento alla guida;
 * 4. la presentazione compare alla prima visita della schermata e mai più
 *    (memoria in localStorage);
 * 5. l'interruttore spegne tutto e lo riaccende, e la scelta resta;
 * 6. un 404 dell'API (schermata senza aiuto) è silenzioso per l'utente;
 * 7. senza localStorage (navigazione privata) funziona lo stesso;
 * 8. la presentazione e' un dialogo modale davvero: prende il fuoco, Tab
 *    gira fra i suoi pulsanti, un clic sul velo non la chiude ne' passa
 *    dietro, e alla chiusura il fuoco torna dov'era.
 *
 * Run:  cd tests/frontend && npm install && npm test
 */
const fs = require("fs");
const path = require("path");
const assert = require("assert");
const { JSDOM } = require("jsdom");

const SRC = fs.readFileSync(
  path.join(__dirname, "..", "..", "static", "js", "help-hints.js"),
  "utf8"
);

const PAYLOAD = {
  screen: "admin.competition.gara_detail",
  locale: "it",
  tour: {
    title: "La pagina della gara",
    intro: "Tutto quello che riguarda una gara sta qui.",
    audience: ["direttore"],
    steps: [
      { title: "Turni", text: "Chi gioca contro chi.", anchor: "gara-turni", hint: "gara.turni" },
      { title: "Fittizi", text: "I tre pulsanti.", anchor: "prova-fittizi", hint: "prova.fittizi" },
    ],
  },
  hints: [
    {
      id: "gara.turni",
      label: "Turni",
      short: "Chi gioca contro chi, turno per turno.",
      anchor: "gara-turni",
      url: "/aiuto/giocare/seguire_la_gara#turni",
    },
    {
      id: "prova.fittizi",
      label: "Giocatori fittizi",
      short: "Tre pulsanti per riempire la prova.",
      anchor: "prova-fittizi",
      url: "/aiuto/organizzare/fare_una_prova#iscrivere",
    },
    {
      id: "gara.assente",
      label: "Non in pagina",
      short: "Un'ancora che questa schermata non espone.",
      anchor: "gara-assente",
      url: null,
    },
  ],
};

const I18N = {
  help: "Aiuto",
  read_more: "Leggi nella guida",
  close: "Chiudi",
  next: "Avanti",
  done: "Ho capito",
  skip: "Salta",
  step_of: "{n} di {total}",
  presentation: "Presentazione",
};

function ambiente(opzioni) {
  opzioni = opzioni || {};
  const attivatore = opzioni.attivatore === undefined ? true : opzioni.attivatore;
  const html =
    "<!doctype html><body>" +
    '<script type="application/json" id="help-hints-config">' +
    JSON.stringify({
      screen: "admin.competition.gara_detail",
      api: "/aiuto/api/schermata/admin.competition.gara_detail",
      debug: !!opzioni.debug,
      i18n: I18N,
    }) +
    "</script>" +
    (attivatore
      ? '<div class="banner"><input type="checkbox" role="switch" data-help-toggle></div>'
      : "") +
    '<h2 data-help="gara-turni">Turni</h2>' +
    '<div class="c7-label" data-help="prova-fittizi">Giocatori fittizi</div>' +
    '<button type="button" data-help="prova-fittizi">Iscrivi il minimo</button>' +
    "</body>";
  const dom = new JSDOM(html, {
    url: "http://localhost/",
    runScripts: "outside-only",
    pretendToBeVisual: true,
  });
  const finestra = dom.window;

  const richieste = [];
  finestra.fetch = function (url) {
    richieste.push(url);
    if (opzioni.status === 404) {
      return Promise.resolve({ ok: false, status: 404, json: () => Promise.resolve({}) });
    }
    return Promise.resolve({
      ok: true,
      status: 200,
      json: () => Promise.resolve(JSON.parse(JSON.stringify(PAYLOAD))),
    });
  };

  const avvisi = [];
  finestra.console.warn = function () {
    avvisi.push(Array.prototype.join.call(arguments, " "));
  };

  if (opzioni.senzaStorage) {
    Object.defineProperty(finestra, "localStorage", {
      get: function () {
        throw new Error("SecurityError: localStorage negato");
      },
    });
  } else if (opzioni.storage) {
    Object.keys(opzioni.storage).forEach(function (k) {
      finestra.localStorage.setItem(k, opzioni.storage[k]);
    });
  }

  finestra.eval(SRC);
  return { finestra, richieste, avvisi, document: finestra.document };
}

function q(doc) {
  return doc.querySelectorAll(".c7-help-q");
}

const esiti = [];
function check(nome, fn) {
  return Promise.resolve()
    .then(fn)
    .then(
      () => esiti.push({ nome, ok: true }),
      (e) => esiti.push({ nome, ok: false, errore: e })
    );
}

(async function () {
  await check("senza attivatore non chiama l'API e non mostra niente", async () => {
    const a = ambiente({ attivatore: false });
    await a.finestra.HelpHints.refresh();
    assert.strictEqual(a.richieste.length, 0);
    assert.strictEqual(q(a.document).length, 0);
    assert.strictEqual(a.finestra.HelpHints.isActive(), false);
  });

  await check("con l'attivatore chiama l'API e mette una «?» per ogni elemento", async () => {
    const a = ambiente({ debug: true });
    await a.finestra.HelpHints.refresh();
    assert.deepStrictEqual(a.richieste, ["/aiuto/api/schermata/admin.competition.gara_detail"]);
    // Tre elementi con data-help, due ancore note: tre «?».
    assert.strictEqual(q(a.document).length, 3);
    // La «?» di un titolo sta dentro il titolo; quella di un pulsante subito dopo.
    const titolo = a.document.querySelector('h2[data-help="gara-turni"]');
    assert.ok(titolo.querySelector(".c7-help-q"), "dentro il titolo");
    const bottone = a.document.querySelector('button[data-help="prova-fittizi"]');
    assert.ok(!bottone.querySelector(".c7-help-q"), "mai dentro un pulsante");
    assert.ok(bottone.nextElementSibling.classList.contains("c7-help-q"), "dopo il pulsante");
    // Un secondo giro non raddoppia.
    await a.finestra.HelpHints.refresh();
    assert.strictEqual(q(a.document).length, 3);
    // In sviluppo l'ancora senza elemento si segnala in console.
    assert.ok(a.avvisi.some((m) => m.includes("gara-assente")), a.avvisi.join("|"));
  });

  await check("la «?» apre un fumetto con titolo, testo e collegamento", async () => {
    const a = ambiente();
    await a.finestra.HelpHints.refresh();
    a.document.querySelector('.c7-help-tour [data-help-action="skip"]').click();
    const pulsante = a.document.querySelector('.c7-help-q[data-help-for="prova-fittizi"]');
    pulsante.click();
    const pop = a.document.querySelector(".c7-help-pop");
    assert.ok(pop, "fumetto aperto");
    assert.ok(pop.textContent.includes("Giocatori fittizi"));
    assert.ok(pop.textContent.includes("Tre pulsanti per riempire la prova."));
    const link = pop.querySelector("a");
    assert.strictEqual(link.getAttribute("href"), "/aiuto/organizzare/fare_una_prova#iscrivere");
    assert.strictEqual(link.textContent.trim(), "Leggi nella guida");
    // Un altro clic sulla stessa «?» lo chiude; Esc pure.
    pulsante.click();
    assert.strictEqual(a.document.querySelector(".c7-help-pop"), null);
    pulsante.click();
    a.document.dispatchEvent(new a.finestra.KeyboardEvent("keydown", { key: "Escape" }));
    assert.strictEqual(a.document.querySelector(".c7-help-pop"), null);
  });

  await check("la presentazione compare alla prima visita e poi mai più", async () => {
    const a = ambiente();
    await a.finestra.HelpHints.refresh();
    const tour = a.document.querySelector(".c7-help-tour");
    assert.ok(tour, "presentazione alla prima visita");
    assert.ok(tour.textContent.includes("La pagina della gara"));
    assert.ok(tour.textContent.includes("Tutto quello che riguarda una gara sta qui."));
    // Avanti sul primo passo: evidenzia l'elemento del secondo.
    tour.querySelector('[data-help-action="next"]').click();
    assert.ok(tour.textContent.includes("I tre pulsanti."));
    const evidenziati = a.document.querySelectorAll(".c7-help-target");
    assert.ok(evidenziati.length >= 1, "elemento del passo evidenziato");
    // Ultimo passo: il pulsante dice «Ho capito» e chiude.
    const fine = tour.querySelector('[data-help-action="next"]');
    assert.strictEqual(fine.textContent.trim(), "Ho capito");
    fine.click();
    assert.strictEqual(a.document.querySelector(".c7-help-tour"), null);
    assert.strictEqual(a.document.querySelectorAll(".c7-help-target").length, 0);
    assert.strictEqual(
      a.finestra.localStorage.getItem("tb-help-seen:admin.competition.gara_detail"),
      "1"
    );
    await a.finestra.HelpHints.refresh();
    assert.strictEqual(a.document.querySelector(".c7-help-tour"), null, "seconda visita: niente");
    // Le «?» restano anche senza presentazione.
    assert.strictEqual(q(a.document).length, 3);
  });

  await check("la presentazione e' modale: fuoco dentro, Tab in cerchio, velo che assorbe", async () => {
    const a = ambiente();
    const interruttore = a.document.querySelector("[data-help-toggle]");
    interruttore.focus();
    await a.finestra.HelpHints.refresh();
    const tour = a.document.querySelector(".c7-help-tour");
    const avanti = tour.querySelector('[data-help-action="next"]');
    const salta = tour.querySelector('[data-help-action="skip"]');
    assert.strictEqual(a.document.activeElement, avanti, "il fuoco entra sul pulsante principale");
    const tab = (shift) =>
      a.document.dispatchEvent(
        new a.finestra.KeyboardEvent("keydown", { key: "Tab", shiftKey: !!shift, cancelable: true })
      );
    tab(false);
    assert.strictEqual(a.document.activeElement, salta, "Tab dall'ultimo torna al primo");
    tab(false);
    assert.strictEqual(a.document.activeElement, avanti);
    tab(true);
    assert.strictEqual(a.document.activeElement, salta, "Shift+Tab va indietro");
    // Un clic sul velo non chiude la presentazione.
    tour.click();
    assert.ok(a.document.querySelector(".c7-help-tour"), "velo cliccato: resta aperta");
    // Alla chiusura il fuoco torna dov'era.
    salta.click();
    assert.strictEqual(a.document.querySelector(".c7-help-tour"), null);
    assert.strictEqual(a.document.activeElement, interruttore, "fuoco ripristinato");
  });

  await check("l'interruttore spegne tutto, riaccende, e la scelta resta", async () => {
    const a = ambiente();
    await a.finestra.HelpHints.refresh();
    const interruttore = a.document.querySelector("[data-help-toggle]");
    assert.strictEqual(interruttore.checked, true, "acceso per default nella pagina che lo offre");
    interruttore.checked = false;
    interruttore.dispatchEvent(new a.finestra.Event("change", { bubbles: true }));
    await a.finestra.HelpHints.ready;
    assert.strictEqual(q(a.document).length, 0);
    assert.strictEqual(a.document.querySelector(".c7-help-tour"), null);
    assert.strictEqual(a.finestra.localStorage.getItem("tb-help-mode"), "0");
    assert.strictEqual(a.finestra.HelpHints.isActive(), false);
    interruttore.checked = true;
    interruttore.dispatchEvent(new a.finestra.Event("change", { bubbles: true }));
    await a.finestra.HelpHints.ready;
    assert.strictEqual(q(a.document).length, 3);
    assert.strictEqual(a.finestra.localStorage.getItem("tb-help-mode"), "1");
  });

  await check("spenta in un'altra visita: niente API, interruttore su off", async () => {
    const a = ambiente({ storage: { "tb-help-mode": "0" } });
    await a.finestra.HelpHints.refresh();
    assert.strictEqual(a.richieste.length, 0);
    assert.strictEqual(q(a.document).length, 0);
    assert.strictEqual(a.document.querySelector("[data-help-toggle]").checked, false);
  });

  await check("schermata senza aiuto (404): silenzio per l'utente, avviso in sviluppo", async () => {
    const a = ambiente({ status: 404, debug: true });
    await a.finestra.HelpHints.refresh();
    assert.strictEqual(q(a.document).length, 0);
    assert.strictEqual(a.document.querySelector(".c7-help-tour"), null);
    assert.ok(a.avvisi.length >= 1, "avviso in console");
    // Fuori sviluppo nemmeno l'avviso.
    const b = ambiente({ status: 404, debug: false });
    await b.finestra.HelpHints.refresh();
    assert.strictEqual(b.avvisi.length, 0);
  });

  await check("senza localStorage funziona lo stesso", async () => {
    const a = ambiente({ senzaStorage: true });
    await a.finestra.HelpHints.refresh();
    assert.strictEqual(q(a.document).length, 3);
    assert.ok(a.document.querySelector(".c7-help-tour"), "presentazione (non puo' ricordarla)");
    const interruttore = a.document.querySelector("[data-help-toggle]");
    interruttore.checked = false;
    interruttore.dispatchEvent(new a.finestra.Event("change", { bubbles: true }));
    await a.finestra.HelpHints.ready;
    assert.strictEqual(q(a.document).length, 0, "spegne almeno per questa pagina");
  });

  let falliti = 0;
  esiti.forEach((e) => {
    if (e.ok) {
      console.log("  ✓ " + e.nome);
    } else {
      falliti += 1;
      console.log("  ✗ " + e.nome);
      console.log("    " + (e.errore && e.errore.stack ? e.errore.stack : e.errore));
    }
  });
  console.log(`\nhelp-hints: ${esiti.length - falliti}/${esiti.length} ok`);
  process.exit(falliti ? 1 : 0);
})();
