/**
 * Headless automation per static/js/polling.js — la sessione scaduta.
 *
 * Il poll di chi ha perso la sessione riceveva un 302 verso la pagina di
 * login; `fetch` lo seguiva e consegnava il 200 di quella pagina, il JSON
 * falliva e il poller ripartiva ogni tre secondi, per sempre. Oggi il server
 * risponde 401, e il client deve:
 *
 * 1. fermarsi — nessun fetch ai tick successivi — sia col 401 sia con una
 *    risposta `redirected` (un server vecchio, un proxy);
 * 2. mostrare l'avviso «la sessione è scaduta» **una volta sola**, anche se
 *    sulla pagina girano più poller;
 * 3. offrire l'accesso con `next` sulla pagina corrente, così chi rientra
 *    torna dov'era.
 *
 * Run:  cd tests/frontend && npm install && npm test
 */
const fs = require("fs");
const path = require("path");
const assert = require("assert");
const { JSDOM } = require("jsdom");

const SRC = fs.readFileSync(
  path.join(__dirname, "..", "..", "static", "js", "polling.js"),
  "utf8"
);

const CONFIG = {
  login_url: "/auth/login",
  i18n: {
    title: "La sessione è scaduta",
    text: "Gli aggiornamenti in tempo reale si sono fermati.",
    action: "Accedi di nuovo",
  },
};

function ambiente(risposta) {
  const dom = new JSDOM(
    '<!doctype html><body><script type="application/json" id="polling-config">' +
      JSON.stringify(CONFIG) +
      "</script></body>",
    {
      url: "https://example.test/gara/8?tab=turni",
      runScripts: "outside-only",
      pretendToBeVisual: true,
    }
  );
  const finestra = dom.window;
  const richieste = [];
  finestra.fetch = function (url) {
    richieste.push(url);
    return Promise.resolve(risposta);
  };
  finestra.eval(SRC);
  return { finestra, richieste };
}

function aspetta(ms) {
  return new Promise(function (r) {
    setTimeout(r, ms);
  });
}

function avvisi(finestra) {
  return finestra.document.querySelectorAll(".c7-session-expired");
}

async function si_ferma(nome, risposta) {
  const amb = ambiente(risposta);
  const errori = [];
  const poller = amb.finestra.Polling.create({
    url: "/sse/poll/gara/8",
    onEvent: function () {},
    onError: function (e) {
      errori.push(e);
    },
    interval: 50,
  });
  poller.start();
  await aspetta(900); // primo poll a 500 ms, poi otto tick da 50 ms

  assert.strictEqual(amb.richieste.length, 1, nome + ": dopo la prima risposta nessun altro poll");
  assert.strictEqual(avvisi(amb.finestra).length, 1, nome + ": l'avviso compare");
  assert.deepStrictEqual(errori, [], nome + ": non è un errore da riprovare");
  poller.stop();
  console.log("  ok  " + nome + ": il poller si ferma e avvisa");
  return amb;
}

async function col_401_si_ferma_e_avvisa() {
  const amb = await si_ferma("401", {
    ok: false,
    status: 401,
    redirected: false,
    json: function () {
      return Promise.resolve({ error: "unauthenticated" });
    },
  });
  const avviso = avvisi(amb.finestra)[0];
  assert.ok(avviso.textContent.includes(CONFIG.i18n.title));
  assert.ok(avviso.textContent.includes(CONFIG.i18n.text));
  const link = avviso.querySelector("a");
  assert.strictEqual(link.textContent, CONFIG.i18n.action);
  assert.strictEqual(
    link.getAttribute("href"),
    "/auth/login?next=" + encodeURIComponent("/gara/8?tab=turni"),
    "si rientra tornando sulla pagina corrente"
  );
  assert.strictEqual(avviso.getAttribute("role"), "alert");
}

async function col_redirect_seguito_si_ferma_e_avvisa() {
  await si_ferma("redirect", {
    ok: true,
    status: 200,
    redirected: true,
    json: function () {
      return Promise.reject(new SyntaxError("Unexpected token <"));
    },
  });
}

async function due_poller_un_avviso_solo() {
  const amb = ambiente({
    ok: false,
    status: 401,
    redirected: false,
    json: function () {
      return Promise.resolve({});
    },
  });
  ["/sse/poll/gara/8", "/sse/poll/user/3"].forEach(function (url) {
    amb.finestra.Polling.create({ url: url, onEvent: function () {}, interval: 50 }).start();
  });
  await aspetta(900);
  assert.strictEqual(amb.richieste.length, 2, "ognuno si ferma dopo la sua risposta");
  assert.strictEqual(avvisi(amb.finestra).length, 1, "un avviso solo per pagina");
  console.log("  ok  due poller sulla stessa pagina: un avviso solo");
}

async function un_errore_di_rete_non_e_una_sessione_scaduta() {
  const amb = ambiente({
    ok: false,
    status: 502,
    redirected: false,
    json: function () {
      return Promise.resolve({});
    },
  });
  const poller = amb.finestra.Polling.create({
    url: "/sse/poll/gara/8",
    onEvent: function () {},
    onError: function () {},
    interval: 50,
  });
  poller.start();
  await aspetta(900);
  assert.ok(amb.richieste.length > 1, "un 502 durante un riavvio si riprova");
  assert.strictEqual(avvisi(amb.finestra).length, 0, "e non parla di sessione");
  poller.stop();
  console.log("  ok  un 502 si riprova senza avviso");
}

(async function () {
  console.log("polling.js — sessione scaduta");
  await col_401_si_ferma_e_avvisa();
  await col_redirect_seguito_si_ferma_e_avvisa();
  await due_poller_un_avviso_solo();
  await un_errore_di_rete_non_e_una_sessione_scaduta();
  console.log("tutti i test sulla sessione scaduta passano");
})().catch(function (e) {
  console.error(e);
  process.exit(1);
});
