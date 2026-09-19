/**
 * Headless automation per static/js/exam-session.js — il tastierino della
 * sessione d'esame.
 *
 * Il modulo non parla col server: la prova la spedisce un modulo HTML, quindi
 * ciò che conta è il valore che resta nel campo `score`.
 *
 * 1. più e meno muovono la cifra di uno;
 * 2. la cifra non scende sotto zero e non supera il massimo dell'esercizio;
 * 3. una cifra scritta a mano fuori scala, o non numerica, rientra all'uscita
 *    dal campo;
 * 4. l'altezza del tastierino viene detta al CSS.
 *
 * Run:  cd tests/frontend && npm install && npm test
 */
const fs = require("fs");
const path = require("path");
const assert = require("assert");
const { JSDOM } = require("jsdom");

const SRC = fs.readFileSync(
  path.join(__dirname, "..", "..", "static", "js", "exam-session.js"),
  "utf8"
);

function pagina(valore, massimo) {
  const dom = new JSDOM(
    `<aside id="examDock">
       <div data-exam-pad data-max="${massimo}">
         <button type="button" data-step="-1"></button>
         <input name="score" value="${valore}">
         <button type="button" data-step="1"></button>
       </div>
     </aside>`,
    { runScripts: "outside-only" }
  );
  dom.window.eval(SRC);
  const doc = dom.window.document;
  return {
    dom,
    campo: doc.querySelector('input[name="score"]'),
    meno: doc.querySelector('[data-step="-1"]'),
    piu: doc.querySelector('[data-step="1"]'),
  };
}

// 1. più e meno muovono la cifra di uno
{
  const p = pagina(3, 10);
  p.piu.click();
  p.piu.click();
  assert.strictEqual(p.campo.value, "5");
  p.meno.click();
  assert.strictEqual(p.campo.value, "4");
  assert.ok(p.campo.classList.contains("is-pop"), "la cifra che cambia salta");
}

// 2. dentro 0…massimo
{
  const p = pagina(0, 2);
  p.meno.click();
  assert.strictEqual(p.campo.value, "0");
  for (let i = 0; i < 5; i++) p.piu.click();
  assert.strictEqual(p.campo.value, "2");
}

// 3. una cifra scritta a mano rientra all'uscita dal campo
{
  const p = pagina(0, 10);
  const esci = () => p.campo.dispatchEvent(new p.dom.window.Event("blur"));
  p.campo.value = "37";
  esci();
  assert.strictEqual(p.campo.value, "10");
  p.campo.value = "abc";
  esci();
  assert.strictEqual(p.campo.value, "0");
  p.campo.value = "-4";
  esci();
  assert.strictEqual(p.campo.value, "0");
}

// 4. l'altezza del tastierino viene detta al CSS
{
  const p = pagina(0, 10);
  const h = p.dom.window.document.documentElement.style.getPropertyValue("--c7-exam-dock-h");
  assert.ok(/^\d+px$/.test(h), `attesa un'altezza in px, trovato «${h}»`);
}

console.log("exam-session.js: 4 gruppi di verifiche passati");
