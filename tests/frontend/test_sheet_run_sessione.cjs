/**
 * Headless automation per static/js/sheet-run.js — la sessione scaduta mentre
 * si segna una seduta di scheda.
 *
 * Il difetto (2026-11-10): a sessione scaduta `fetch` segue il 302 verso il
 * login e consegna il 200 di quella pagina; `risposta.json()` solleva, e il
 * toast mostrava il messaggio grezzo del parser — «Unexpected token '<'…».
 * Il criterio per riconoscerla è quello di `polling.js`: 401, risposta
 * `redirected`, o un 200 che non è JSON.
 *
 * 1. a sessione scaduta il toast dice di rientrare, col testo del template;
 * 2. lo stesso con un 401 pulito;
 * 3. un errore del server continua a mostrare il suo messaggio;
 * 4. una risposta buona ridisegna, e dopo un errore si può riprovare.
 *
 * Run:  cd tests/frontend && npm install && npm test
 */
const fs = require("fs");
const path = require("path");
const assert = require("assert");
const { JSDOM } = require("jsdom");

const SRC = fs.readFileSync(
  path.join(__dirname, "..", "..", "static", "js", "sheet-run.js"),
  "utf8"
);

const json = (dati, stato = 200) => ({
  status: stato,
  ok: stato < 400,
  redirected: false,
  headers: { get: () => "application/json" },
  json: () => Promise.resolve(dati),
});
const LOGIN = {
  status: 200,
  ok: true,
  redirected: true,
  headers: { get: () => "text/html; charset=utf-8" },
  json: () => Promise.reject(new SyntaxError("Unexpected token '<'")),
};
const NON_AUTORIZZATO = {
  status: 401,
  ok: false,
  redirected: false,
  headers: { get: () => "application/json" },
  json: () => Promise.resolve({ success: false, error: "unauthorized" }),
};

function pagina(risposte) {
  const dom = new JSDOM(
    `<div data-sheet-run data-at="0" data-record-url="/record"
          data-msg-error="errore" data-msg-session="sessione scaduta">
       <div data-run-progress>prima</div>
       <div data-cell data-item="3"><button data-done="1"></button></div>
     </div>`,
    { runScripts: "outside-only" }
  );
  const w = dom.window;
  const coda = risposte.slice();
  let chiamate = 0;
  w.csrfToken = () => "tok";
  w.showError = (m) => { w.__errore = m; };
  w.fetch = () => {
    chiamate += 1;
    return Promise.resolve(coda.shift());
  };
  w.eval(SRC);
  const segna = async () => {
    w.document.querySelector("[data-done]").click();
    await new Promise((ok) => setTimeout(ok, 0));
  };
  const avanzamento = () => w.document.querySelector("[data-run-progress]").innerHTML;
  return { w, segna, avanzamento, chiamate: () => chiamate };
}

(async () => {
  // 1. il 302 verso il login, seguito da fetch
  {
    const p = pagina([LOGIN]);
    await p.segna();
    assert.strictEqual(p.w.__errore, "sessione scaduta");
    assert.strictEqual(p.avanzamento(), "prima");
  }

  // 2. il 401
  {
    const p = pagina([NON_AUTORIZZATO]);
    await p.segna();
    assert.strictEqual(p.w.__errore, "sessione scaduta");
  }

  // 3. un rifiuto del server mostra il suo messaggio
  {
    const p = pagina([json({ success: false, error: "troppo tardi" }, 409)]);
    await p.segna();
    assert.strictEqual(p.w.__errore, "troppo tardi");
  }

  // 4. dopo l'errore si riprova, e la risposta buona ridisegna
  {
    const p = pagina([LOGIN, json({ success: true, progress_html: "<b>dopo</b>" })]);
    await p.segna();
    await p.segna();
    assert.strictEqual(p.chiamate(), 2);
    assert.strictEqual(p.avanzamento(), "<b>dopo</b>");
  }

  console.log("test_sheet_run_sessione: ok");
})().catch((e) => { console.error(e); process.exit(1); });
