/**
 * Headless automation per static/js/notifications.js — i toast di errore.
 *
 * Il difetto (2026-11-10): `clearErrorToasts` cercava `.text-bg-danger`, ma
 * `showToast` crea il toast con `bg-danger text-white` (compatibilità con
 * Bootstrap 5.1). Gli errori sono persistenti — non si chiudono da soli — e
 * il selettore non ne trovava mai nessuno: a ogni errore se ne impilava uno
 * in più.
 *
 * 1. un secondo errore toglie il primo: ne resta uno solo, l'ultimo;
 * 2. i toast che non sono errori restano dove sono;
 * 3. regge anche un toast di errore senza istanza Bootstrap (si rimuove).
 *
 * Run:  cd tests/frontend && npm install && npm test
 */
const fs = require("fs");
const path = require("path");
const assert = require("assert");
const { JSDOM } = require("jsdom");

const SRC = fs.readFileSync(
  path.join(__dirname, "..", "..", "static", "js", "notifications.js"),
  "utf8"
);

function pagina() {
  const dom = new JSDOM('<!doctype html><body><div id="toast-container"></div></body>', {
    runScripts: "outside-only",
  });
  const w = dom.window;
  const istanze = new w.WeakMap();
  // Il minimo di bootstrap.Toast che il modulo usa: `hide()` porta a
  // `hidden.bs.toast`, che è l'evento su cui il toast si toglie dal DOM.
  w.bootstrap = {
    Toast: class {
      constructor(el) {
        this.el = el;
        istanze.set(el, this);
      }
      show() {}
      hide() {
        this.el.dispatchEvent(new w.Event("hidden.bs.toast"));
      }
      static getInstance(el) {
        return istanze.get(el) || null;
      }
    },
  };
  w.eval(SRC);
  const testi = (selettore) =>
    [...w.document.querySelectorAll(selettore)].map((t) => t.textContent);
  return { w, testi };
}

// 1. un secondo errore toglie il primo
{
  const p = pagina();
  p.w.showError("primo");
  p.w.showError("secondo");
  p.w.showError("terzo");
  assert.deepStrictEqual(p.testi("#toast-container .toast"), ["terzo"]);
}

// 2. gli altri toast non si toccano
{
  const p = pagina();
  p.w.showSuccess("fatto");
  p.w.showWarning("occhio");
  p.w.showError("errore");
  p.w.showError("errore di nuovo");
  assert.deepStrictEqual(p.testi("#toast-container .toast"), [
    "fatto",
    "occhio",
    "errore di nuovo",
  ]);
}

// 3. un errore senza istanza Bootstrap si rimuove comunque
{
  const p = pagina();
  const orfano = p.w.document.createElement("div");
  orfano.className = "toast align-items-center bg-danger text-white border-0";
  orfano.textContent = "orfano";
  p.w.document.getElementById("toast-container").appendChild(orfano);
  p.w.clearErrorToasts();
  assert.deepStrictEqual(p.testi("#toast-container .toast"), []);
}

console.log("notifications.js (toast di errore): 3 scenari OK");
