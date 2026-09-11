/**
 * Headless automation per la ricerca fra i giocatori da iscrivere.
 *
 * Carica il vero static/js/iscritti_ricerca.js dentro jsdom e verifica che la
 * stringa cercata peschi in username, nome e cognome — il caso che ha motivato
 * la funzione: il direttore conosce la persona, non il suo soprannome.
 *
 * Il componente degli iscritti è incluso due volte nella pagina della gara
 * (mobile e desktop): le due copie devono filtrare in modo indipendente, ed è
 * la ragione per cui il codice non usa `id` né `getElementById`.
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

function opzioni(giocatori) {
  return giocatori
    .map(function (g) {
      const chiave = (g.username + " " + g.nome).trim().toLowerCase();
      const etichetta = g.nome ? g.nome + " · " + g.username : g.username;
      return `<option value="${g.id}" data-cerca="${chiave}">${etichetta}</option>`;
    })
    .join("\n");
}

function form() {
  return `
  <form>
    <input type="search" class="js-iscritti-cerca">
    <select name="user_id">
      <option value="">Seleziona giocatore…</option>
      ${opzioni(GIOCATORI)}
    </select>
    <div class="js-iscritti-esito" data-formato="{n} giocatori trovati"></div>
  </form>`;
}

function ambiente() {
  // Due copie del componente, come nella pagina della gara.
  const dom = new JSDOM(`<!doctype html><body>${form()}${form()}</body>`, {
    runScripts: "outside-only",
  });
  dom.window.eval(SRC);
  return dom.window;
}

function cerca(window, indiceCopia, testo) {
  const modulo = window.document.querySelectorAll("form")[indiceCopia];
  const campo = modulo.querySelector(".js-iscritti-cerca");
  campo.value = testo;
  campo.dispatchEvent(new window.Event("input", { bubbles: true }));
  return modulo.querySelector('select[name="user_id"]');
}

function username(tendina) {
  return Array.from(tendina.options)
    .filter(function (o) {
      return o.value;
    })
    .map(function (o) {
      return GIOCATORI[Number(o.value) - 1].username;
    });
}

const prove = [];
function prova(nome, fn) {
  prove.push([nome, fn]);
}

prova("cerca per username", function () {
  const window = ambiente();
  assert.deepStrictEqual(username(cerca(window, 0, "marco_b")), ["marco_b"]);
});

prova("cerca per nome", function () {
  const window = ambiente();
  assert.deepStrictEqual(username(cerca(window, 0, "marco")), [
    "marco_b",
    "marcob",
  ]);
});

prova("cerca per cognome — il caso di chi non conosce lo username", function () {
  const window = ambiente();
  assert.deepStrictEqual(username(cerca(window, 0, "rossi")), ["marcob"]);
});

prova("nome e cognome insieme", function () {
  const window = ambiente();
  assert.deepStrictEqual(username(cerca(window, 0, "marco bianchi")), ["marco_b"]);
});

prova("gli accenti non contano: «nicolo» trova «Nicolò»", function () {
  const window = ambiente();
  assert.deepStrictEqual(username(cerca(window, 0, "nicolo")), ["nick"]);
});

prova("chi non ha anagrafica si trova per username", function () {
  const window = ambiente();
  assert.deepStrictEqual(username(cerca(window, 0, "solit")), ["solitario"]);
});

prova("un solo superstite viene preselezionato", function () {
  const window = ambiente();
  const tendina = cerca(window, 0, "rossi");
  assert.strictEqual(tendina.value, "2");
});

prova("nessun risultato: tendina vuota e niente selezione", function () {
  const window = ambiente();
  const tendina = cerca(window, 0, "inesistente");
  assert.deepStrictEqual(username(tendina), []);
  assert.strictEqual(tendina.value, "");
});

prova("il segnaposto resta sempre", function () {
  const window = ambiente();
  const tendina = cerca(window, 0, "inesistente");
  assert.strictEqual(tendina.options.length, 1);
  assert.strictEqual(tendina.options[0].value, "");
});

prova("svuotare il campo rimette tutti", function () {
  const window = ambiente();
  cerca(window, 0, "rossi");
  assert.strictEqual(username(cerca(window, 0, "")).length, GIOCATORI.length);
});

prova("le due copie del componente non si disturbano", function () {
  const window = ambiente();
  const prima = cerca(window, 0, "rossi");
  const seconda = window.document.querySelectorAll("form")[1].querySelector("select");
  assert.deepStrictEqual(username(prima), ["marcob"]);
  assert.strictEqual(username(seconda).length, GIOCATORI.length);
});

prova("il conteggio dice quanti ne restano", function () {
  const window = ambiente();
  cerca(window, 0, "marco");
  const esito = window.document.querySelectorAll(".js-iscritti-esito")[0];
  assert.strictEqual(esito.textContent, "2 giocatori trovati");
});

prova("senza data-cerca si ripiega sull'etichetta, non si esclude tutto", function () {
  const window = ambiente();
  const tendina = window.document.querySelector('select[name="user_id"]');
  Array.from(tendina.options).forEach(function (o) {
    o.removeAttribute("data-cerca");
  });
  assert.deepStrictEqual(username(cerca(window, 0, "rossi")), ["marcob"]);
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
prove.forEach(function ([nome, fn]) {
  try {
    fn();
    console.log("  ok   " + nome);
  } catch (errore) {
    falliti += 1;
    console.log("  FAIL " + nome + "\n       " + errore.message);
  }
});
console.log(
  `\n${prove.length - falliti} passed, ${falliti} failed (iscritti_ricerca)`
);
process.exit(falliti ? 1 : 0);
