/**
 * Headless automation per static/js/exercise-run.js — i comandi della cornice
 * di esecuzione di un esercizio (fase 5a).
 *
 * 1. più e meno muovono la cifra dentro 0…massimo, e le barrette la seguono;
 * 2. «Registra» spedisce il punteggio, con la variante accesa;
 * 3. la risposta porta il pezzo «come sta andando» già disegnato dal server:
 *    la pagina lo sostituisce, non lo ricompone;
 * 4. dopo una prova la cifra torna a zero e l'annulla si accende;
 * 5. sul superato/non superato il tasto dell'esito *è* la registrazione;
 * 6. l'annulla chiama la sua route e ridisegna lo stesso pezzo;
 * 7. un errore del server si mostra e non tocca la pagina;
 * 8. i due formati (verticale e tabellone) si aggiornano insieme;
 * 9. l'altezza dei comandi viene detta al CSS.
 *
 * Run:  cd tests/frontend && npm install && npm test
 */
const fs = require("fs");
const path = require("path");
const assert = require("assert");
const { JSDOM } = require("jsdom");

const SRC = fs.readFileSync(
  path.join(__dirname, "..", "..", "static", "js", "exercise-run.js"),
  "utf8"
);

function pagina({ passFail = false, max = 3, risposte = [] } = {}) {
  const comandi = passFail
    ? `<button data-outcome="true"></button><button data-outcome="false"></button>`
    : `<button data-score-step="-1"></button>
       <span data-score-display>0</span>
       <button data-score-step="1"></button>
       <div data-score-pips><span data-pip="0"></span><span data-pip="1"></span><span data-pip="2"></span></div>
       <button data-record><span data-record-label>Registra la prova</span></button>`;
  const dom = new JSDOM(
    `<div data-run data-pass-fail="${passFail}" data-max-score="${max}"
          data-record-url="/train" data-undo-url="/undo"
          data-msg-recording="Registro…" data-msg-error="errore"
          data-msg-network="rete" data-msg-undo-error="annulla-errore">
       <label><input type="radio" name="variant_id" value="" checked></label>
       <label><input type="radio" name="variant_id" value="7"></label>
       <div data-run-progress>prima</div>
       <span data-drill-count>0</span><span data-drill-count>0</span>
       <span data-drill-best>—</span>
       <aside data-run-dock>${comandi}<button data-undo disabled></button></aside>
     </div>`,
    { runScripts: "outside-only" }
  );
  const w = dom.window;
  const chiamate = [];
  const coda = risposte.slice();
  w.csrfToken = () => "tok";
  w.showError = (m) => { w.__errore = m; };
  w.fetch = (url, opt) => {
    chiamate.push({ url, body: opt.body ? JSON.parse(opt.body) : null, headers: opt.headers });
    const r = coda.shift();
    return r instanceof Error
      ? Promise.reject(r)
      : Promise.resolve({ json: () => Promise.resolve(r) });
  };
  w.eval(SRC);
  const $ = (s) => w.document.querySelector(s);
  const attesa = () => new Promise((ok) => setTimeout(ok, 0));
  return { w, $, chiamate, attesa };
}

const ok = (extra) => Object.assign(
  { success: true, progress_html: "<b>dopo</b>", attempts_count: 1, best_score: 2, passed_count: 1 },
  extra
);

(async () => {
  // 1. la cifra sta dentro 0…massimo, e le barrette la seguono
  {
    const p = pagina();
    p.$('[data-score-step="-1"]').click();
    assert.strictEqual(p.$("[data-score-display]").textContent, "0");
    for (let i = 0; i < 5; i++) p.$('[data-score-step="1"]').click();
    assert.strictEqual(p.$("[data-score-display]").textContent, "3");
    assert.strictEqual(p.w.document.querySelectorAll("[data-pip].is-on").length, 3);
  }

  // senza tetto (max 0) si sale quanto si vuole
  {
    const p = pagina({ max: 0 });
    for (let i = 0; i < 25; i++) p.$('[data-score-step="1"]').click();
    assert.strictEqual(p.$("[data-score-display]").textContent, "25");
  }

  // 2–4. registra: punteggio e variante, pezzo sostituito, cifra a zero
  {
    const p = pagina({ risposte: [ok()] });
    p.$('input[name="variant_id"][value="7"]').checked = true;
    p.$('[data-score-step="1"]').click();
    p.$('[data-score-step="1"]').click();
    p.$("[data-record]").click();
    assert.strictEqual(p.$("[data-record-label]").textContent, "Registro…");
    await p.attesa();
    assert.deepStrictEqual(p.chiamate[0].body, { score: 2, variant_id: "7" });
    assert.strictEqual(p.chiamate[0].headers["X-CSRFToken"], "tok");
    assert.strictEqual(p.$("[data-run-progress]").innerHTML, "<b>dopo</b>");
    assert.strictEqual(p.$("[data-score-display]").textContent, "0");
    assert.strictEqual(p.$("[data-undo]").disabled, false);
    assert.strictEqual(p.$("[data-record-label]").textContent, "Registra la prova");
    // 8. i due contatori del tabellone orizzontale salgono insieme
    const conti = [...p.w.document.querySelectorAll("[data-drill-count]")].map((e) => e.textContent);
    assert.deepStrictEqual(conti, ["1", "1"]);
    assert.strictEqual(p.$("[data-drill-best]").textContent, "2");
  }

  // 5. superato / non superato: un tocco, una prova
  {
    const p = pagina({ passFail: true, risposte: [ok({ best_score: null, passed_count: 4 })] });
    p.$('[data-outcome="false"]').click();
    await p.attesa();
    assert.deepStrictEqual(p.chiamate[0].body, { passed: false });
    assert.strictEqual(p.$("[data-drill-best]").textContent, "4");
  }

  // 6. l'annulla
  {
    const p = pagina({ risposte: [ok(), ok({ progress_html: "vuoto", attempts_count: 0, best_score: null })] });
    p.$("[data-record]").click();
    await p.attesa();
    p.$("[data-undo]").click();
    await p.attesa();
    assert.strictEqual(p.chiamate[1].url, "/undo");
    assert.strictEqual(p.$("[data-run-progress]").innerHTML, "vuoto");
    assert.strictEqual(p.$("[data-undo]").disabled, true);
    assert.strictEqual(p.$("[data-drill-best]").textContent, "—");
  }

  // 7. l'errore si mostra e la pagina resta com'era
  {
    const p = pagina({ risposte: [{ success: false, error: "troppo alto" }, new Error("giù")] });
    p.$("[data-record]").click();
    await p.attesa();
    assert.strictEqual(p.w.__errore, "troppo alto");
    assert.strictEqual(p.$("[data-run-progress]").innerHTML, "prima");
    p.$("[data-record]").click();
    await p.attesa();
    assert.strictEqual(p.w.__errore, "rete");
    assert.strictEqual(p.$("[data-record]").disabled, false, "dopo un errore si può riprovare");
  }

  // 9. l'altezza dei comandi arriva al CSS
  {
    const p = pagina();
    assert.ok(
      p.w.document.documentElement.style.getPropertyValue("--c7-run-dock-h").endsWith("px")
    );
  }

  console.log("test_exercise_run: ok");
})().catch((e) => { console.error(e); process.exit(1); });
