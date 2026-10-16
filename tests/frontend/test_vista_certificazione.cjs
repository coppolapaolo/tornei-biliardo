/*
 * static/js/vista_certificazione.js — il selettore Tornei · Confermate · Tutte
 * del profilo (ADR-083, UC6).
 *
 * Il server rende i numeri delle tre viste; lo script sceglie quale si vede
 * mettendo `data-vista-attiva` su <html>, e ricorda la scelta nel browser.
 * Qui: la predefinita, il cambio di vista, la persistenza fra due pagine, la
 * migrazione della chiave del vecchio toggle ELO, e lo storage che lancia.
 */
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const SORGENTE = fs.readFileSync(
  path.join(__dirname, "..", "..", "static", "js", "vista_certificazione.js"),
  "utf8"
);

const CORPO = `
  <div class="c7-seg">
    <button type="button" data-vista-scelta="tornei" aria-pressed="false">Tornei</button>
    <button type="button" data-vista-scelta="confermate" aria-pressed="true">Confermate</button>
    <button type="button" data-vista-scelta="tutte" aria-pressed="false">Tutte</button>
  </div>
  <div data-vista="tornei">1510</div>
  <div data-vista="confermate">1530</div>
  <div data-vista="tutte">1545</div>`;

/* Uno storage in memoria condiviso fra due «pagine», come il localStorage
   vero fra un caricamento e il successivo. */
function memoria(iniziale) {
  const dati = Object.assign({}, iniziale || {});
  return {
    dati,
    getItem: (k) => (k in dati ? dati[k] : null),
    setItem: (k, v) => { dati[k] = String(v); },
    removeItem: (k) => { delete dati[k]; },
  };
}

function storageCheLancia() {
  const errore = () => { throw new Error("SecurityError: storage negato"); };
  return { getItem: errore, setItem: errore, removeItem: errore };
}

/* Carica una pagina col selettore. Lo script gira come nel head: il corpo c'è
   già qui, quindi lo stato dei pulsanti si allinea subito. */
function pagina(storage) {
  const dom = new JSDOM(`<!doctype html><html><head></head><body>${CORPO}</body></html>`, {
    runScripts: "outside-only",
  });
  Object.defineProperty(dom.window, "localStorage", {
    configurable: true,
    get: () => storage,
  });
  dom.window.eval(SORGENTE);
  const doc = dom.window.document;
  return {
    window: dom.window,
    attiva: () => doc.documentElement.getAttribute("data-vista-attiva"),
    premuto: () =>
      Array.from(doc.querySelectorAll("[data-vista-scelta]"))
        .filter((b) => b.getAttribute("aria-pressed") === "true")
        .map((b) => b.getAttribute("data-vista-scelta")),
    acceso: () =>
      Array.from(doc.querySelectorAll("[data-vista-scelta].is-on")).map((b) =>
        b.getAttribute("data-vista-scelta")
      ),
    tocca: (vista) =>
      doc
        .querySelector(`[data-vista-scelta="${vista}"]`)
        .dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true })),
  };
}

let controlli = 0;
function check(nome, fn) {
  fn();
  controlli += 1;
  console.log("  ok -", nome);
}

console.log("vista_certificazione.js");

check("la prima volta la vista è Confermate", () => {
  const p = pagina(memoria());
  assert.strictEqual(p.attiva(), "confermate");
  assert.deepStrictEqual(p.premuto(), ["confermate"]);
  assert.deepStrictEqual(p.acceso(), ["confermate"]);
});

check("toccare Tutte cambia la vista e il pulsante acceso", () => {
  const p = pagina(memoria());
  p.tocca("tutte");
  assert.strictEqual(p.attiva(), "tutte");
  assert.deepStrictEqual(p.premuto(), ["tutte"]);
  assert.deepStrictEqual(p.acceso(), ["tutte"]);
});

check("la scelta resta dopo il ricaricamento, e vale su un altro profilo", () => {
  const storage = memoria();
  pagina(storage).tocca("tornei");
  // Ricarica, o apre il profilo di Gianni: stesso browser, stessa scelta.
  const dopo = pagina(storage);
  assert.strictEqual(dopo.attiva(), "tornei");
  assert.deepStrictEqual(dopo.premuto(), ["tornei"]);
});

check("un valore sconosciuto nello storage torna alla predefinita", () => {
  const p = pagina(memoria({ vistaCertificazione: "boh" }));
  assert.strictEqual(p.attiva(), "confermate");
});

check("il vecchio toggle ELO sul globale diventa Confermate, e la chiave sparisce", () => {
  const storage = memoria({ eloMode: "global" });
  const p = pagina(storage);
  assert.strictEqual(p.attiva(), "confermate");
  assert.strictEqual(storage.dati.vistaCertificazione, "confermate");
  assert.ok(!("eloMode" in storage.dati));
});

check("il vecchio toggle ELO sul competitivo diventa Tornei", () => {
  const storage = memoria({ eloMode: "competitive" });
  assert.strictEqual(pagina(storage).attiva(), "tornei");
  assert.strictEqual(storage.dati.vistaCertificazione, "tornei");
});

check("con lo storage che lancia il selettore funziona ma non ricorda", () => {
  const p = pagina(storageCheLancia());
  assert.strictEqual(p.attiva(), "confermate");
  p.tocca("tutte");
  assert.strictEqual(p.attiva(), "tutte");
  assert.deepStrictEqual(p.premuto(), ["tutte"]);
  // Pagina nuova: niente è stato ricordato.
  assert.strictEqual(pagina(storageCheLancia()).attiva(), "confermate");
});

check("senza localStorage del tutto si parte da Confermate", () => {
  const p = pagina(undefined);
  assert.strictEqual(p.attiva(), "confermate");
  p.tocca("tornei");
  assert.strictEqual(p.attiva(), "tornei");
});

check("il CSS nasconde i blocchi delle viste non scelte", () => {
  // jsdom applica i selettori d'attributo di un foglio in linea: si prova la
  // regola vera di theme-7c.css, non una sua copia.
  const css = fs.readFileSync(
    path.join(__dirname, "..", "..", "static", "css", "theme-7c.css"),
    "utf8"
  );
  const inizio = css.indexOf("html:not([data-vista-attiva]) [data-vista]");
  const fine = css.indexOf("}", inizio) + 1;
  const regola = css.slice(inizio, fine);
  assert.ok(inizio > 0, "regola delle viste non trovata in theme-7c.css");

  const p = pagina(memoria());
  const doc = p.window.document;
  const stile = doc.createElement("style");
  stile.textContent = regola;
  doc.head.appendChild(stile);
  const visibili = () =>
    Array.from(doc.querySelectorAll("[data-vista]"))
      .filter((el) => p.window.getComputedStyle(el).display !== "none")
      .map((el) => el.textContent);

  assert.deepStrictEqual(visibili(), ["1530"]);
  p.tocca("tornei");
  assert.deepStrictEqual(visibili(), ["1510"]);
  p.tocca("tutte");
  assert.deepStrictEqual(visibili(), ["1545"]);
});

console.log(`${controlli} controlli superati`);
