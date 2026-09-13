/**
 * Headless automation per la ricerca fra i giocatori da iscrivere.
 *
 * Carica il vero static/js/iscritti_ricerca.js dentro jsdom e verifica che la
 * stringa cercata peschi in username, nome e cognome — il caso che ha motivato
 * la funzione: il direttore conosce la persona, non il suo soprannome.
 *
 * Dal 2026-09-13 i candidati sono righe con «Iscrivi» (canvas 2.2/2.3), non
 * una tendina: nascoste finché non si scrive, compaiono quelle che
 * corrispondono, con il conteggio. Due copie del componente nella stessa
 * pagina filtrano in modo indipendente: il codice non usa `id`.
 *
 * Run:  cd tests/frontend && npm install && npm test
 */
const fs = require("fs");
const path = require("path");
const assert = require("assert");
const { JSDOM } = require("jsdom");

const SRC = fs.readFileSync(
  path.join(__dirname, "..", "..", "static", "js", "iscritti_ricerca.js"),
  "utf8"
);

const GIOCATORI = [
  { id: "1", username: "marco_b", nome: "Marco Bianchi" },
  { id: "2", username: "marcob", nome: "Marco Rossi" },
  { id: "3", username: "nick", nome: "Nicolò Verdi" },
  { id: "4", username: "solitario", nome: "" },
];

function righe(giocatori) {
  return giocatori
    .map(function (g) {
      const chiave = (g.username + " " + g.nome).trim().toLowerCase();
      const etichetta = g.nome ? g.nome + " · " + g.username : g.username;
      return `<form class="js-iscrivibile" data-cerca="${chiave}" data-username="${g.username}">
        <span>${etichetta}</span><button type="submit">Iscrivi</button></form>`;
    })
    .join("\n");
}

function blocco(massimo) {
  return `
  <div data-iscrivibili${massimo ? ` data-massimo="${massimo}"` : ""}>
    <input type="search" class="js-iscritti-cerca">
    <div class="js-iscritti-esito" data-formato="{n} giocatori trovati"></div>
    <div class="js-iscritti-nessuno" hidden>Nessuno</div>
    ${righe(GIOCATORI)}
  </div>`;
}

function ambiente(massimo) {
  // Due copie del componente, come nella pagina della gara.
  const dom = new JSDOM(`<!doctype html><body>${blocco(massimo)}${blocco(massimo)}</body>`, {
    runScripts: "outside-only",
  });
  dom.window.eval(SRC);
  return dom.window;
}

function cerca(window, indiceCopia, testo) {
  const contenitore = window.document.querySelectorAll("[data-iscrivibili]")[indiceCopia];
  const campo = contenitore.querySelector(".js-iscritti-cerca");
  campo.value = testo;
  campo.dispatchEvent(new window.Event("input", { bubbles: true }));
  return contenitore;
}

function visibili(contenitore) {
  return Array.from(contenitore.querySelectorAll(".js-iscrivibile"))
    .filter(function (r) { return !r.hidden; })
    .map(function (r) { return r.dataset.username; });
}

const prove = [];
function prova(nome, corpo) { prove.push({ nome, corpo }); }

prova("all'apertura le righe sono nascoste", function () {
  const window = ambiente();
  assert.deepStrictEqual(visibili(window.document.querySelector("[data-iscrivibili]")), []);
});

prova("cerca per cognome", function () {
  const window = ambiente();
  assert.deepStrictEqual(visibili(cerca(window, 0, "rossi")), ["marcob"]);
});

prova("cerca per username", function () {
  const window = ambiente();
  assert.deepStrictEqual(visibili(cerca(window, 0, "marco_b")), ["marco_b"]);
});

prova("cerca senza accenti", function () {
  const window = ambiente();
  assert.deepStrictEqual(visibili(cerca(window, 0, "nicolo")), ["nick"]);
});

prova("nessun risultato: nessuna riga e il messaggio", function () {
  const window = ambiente();
  const contenitore = cerca(window, 0, "inesistente");
  assert.deepStrictEqual(visibili(contenitore), []);
  assert.strictEqual(contenitore.querySelector(".js-iscritti-nessuno").hidden, false);
});

prova("svuotare il campo nasconde di nuovo tutto", function () {
  const window = ambiente();
  cerca(window, 0, "rossi");
  const contenitore = cerca(window, 0, "");
  assert.deepStrictEqual(visibili(contenitore), []);
  assert.strictEqual(contenitore.querySelector(".js-iscritti-esito").textContent, "");
});

prova("le due copie del componente non si disturbano", function () {
  const window = ambiente();
  const prima = cerca(window, 0, "rossi");
  const seconda = window.document.querySelectorAll("[data-iscrivibili]")[1];
  assert.deepStrictEqual(visibili(prima), ["marcob"]);
  assert.deepStrictEqual(visibili(seconda), []);
});

prova("il conteggio dice quanti ne restano", function () {
  const window = ambiente();
  const contenitore = cerca(window, 0, "marco");
  assert.strictEqual(contenitore.querySelector(".js-iscritti-esito").textContent, "2 giocatori trovati");
});

prova("oltre il massimo le righe in piu' restano nascoste ma contate", function () {
  const window = ambiente(1);
  const contenitore = cerca(window, 0, "marco");
  assert.deepStrictEqual(visibili(contenitore), ["marco_b"]);
  assert.strictEqual(contenitore.querySelector(".js-iscritti-esito").textContent, "2 giocatori trovati");
});

prova("senza data-cerca si ripiega sul testo della riga", function () {
  const window = ambiente();
  window.document.querySelectorAll(".js-iscrivibile").forEach(function (r) {
    r.removeAttribute("data-cerca");
  });
  assert.deepStrictEqual(visibili(cerca(window, 0, "rossi")), ["marcob"]);
});

prova("Invio nel campo non manda il form a metà", function () {
  const window = ambiente();
  const campo = window.document.querySelector(".js-iscritti-cerca");
  const evento = new window.KeyboardEvent("keydown", {
    key: "Enter",
    bubbles: true,
    cancelable: true,
  });
  campo.dispatchEvent(evento);
  assert.strictEqual(evento.defaultPrevented, true);
});

let falliti = 0;
prove.forEach(function ({ nome, corpo }) {
  try {
    corpo();
    console.log("  ok   " + nome);
  } catch (errore) {
    falliti += 1;
    console.log("  FAIL " + nome + "\n       " + (errore && errore.message));
  }
});
console.log(`\n${prove.length - falliti} passed, ${falliti} failed (iscritti_ricerca)`);
if (falliti) process.exit(1);
