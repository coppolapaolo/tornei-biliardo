/**
 * Headless automation per static/js/exercise-shots.js — l'esecuzione colpo per
 * colpo di un esercizio (fase 5b).
 *
 * 1. il tocco sul panno apre l'ingrandimento con la battente dove si è toccato;
 * 2. le coordinate sono quelle del disegnatore, non pixel: il conto tiene conto
 *    del viewBox e del riquadro, comprese le bande di «xMidYMid meet»;
 * 3. trascinare la battente sposta il punto, e non lo fa uscire dal panno;
 * 4. «Conferma» manda l'ultimo punto, non quello del primo tocco;
 * 5. «Tavolo intero» richiude senza mandare niente;
 * 6. «Non è entrata» manda subito un colpo senza posizione;
 * 7. la risposta ridisegna sia «come sta andando» sia i comandi;
 * 8. annulla e chiudi chiamano le loro route; un errore si mostra e la pagina
 *    resta com'era.
 *
 * Run:  cd tests/frontend && npm install && npm test
 */
const fs = require("fs");
const path = require("path");
const assert = require("assert");
const { JSDOM } = require("jsdom");

const SRC = fs.readFileSync(
  path.join(__dirname, "..", "..", "static", "js", "exercise-shots.js"),
  "utf8"
);

// Il panno: viewBox -30 -30 860 460, riquadro 860x460 a partire da (0, 0), quindi
// una unità del disegnatore = un pixel e l'origine del panno sta a (30, 30).
const VB = "-30 -30 860 460";

function pagina({ risposte = [] } = {}) {
  const dom = new JSDOM(
    `<div data-run data-shot-url="/shot" data-shot-undo-url="/shot/undo"
          data-shot-close-url="/shot/close" data-shot-restart-url="/shot/restart"
          data-msg-error="errore" data-msg-network="rete">
       <div data-run-progress>
         <div class="c7-cloth" data-cloth>
           <svg data-cloth-full data-vb="${VB}"></svg>
           <div data-cloth-zoom hidden>
             <svg data-cloth-zoomsvg data-vb="450 50 300 300">
               <line data-cross-x></line><line data-cross-y></line>
               <circle data-cloth-marker cx="600" cy="200" r="18"></circle>
             </svg>
             <button data-cloth-cancel></button>
             <button data-cloth-confirm></button>
           </div>
         </div>
       </div>
       <aside data-run-dock>
         <button data-shot-miss></button>
         <button data-shot-undo></button>
         <button data-shot-close></button>
         <button data-shot-restart></button>
       </aside>
     </div>`,
    { runScripts: "outside-only" }
  );
  const w = dom.window;
  const doc = w.document;
  const chiamate = [];
  const coda = risposte.slice();
  w.csrfToken = () => "tok";
  w.showError = (m) => { w.__errore = m; };
  w.fetch = (url, opt) => {
    chiamate.push({ url, body: opt.body ? JSON.parse(opt.body) : null });
    const r = coda.shift();
    return r instanceof Error
      ? Promise.reject(r)
      : Promise.resolve({ json: () => Promise.resolve(r) });
  };
  // jsdom non calcola i riquadri: li dichiariamo noi, uno a uno.
  const riquadro = (el, box) => { el.getBoundingClientRect = () => box; };
  riquadro(doc.querySelector("[data-cloth-full]"), { left: 0, top: 0, width: 860, height: 460 });
  riquadro(doc.querySelector("[data-cloth-zoomsvg]"), { left: 0, top: 0, width: 300, height: 300 });
  w.eval(SRC);
  const $ = (s) => doc.querySelector(s);
  const tocca = (el, clientX, clientY) => {
    const ev = new w.MouseEvent("pointerdown", { clientX, clientY, bubbles: true });
    el.dispatchEvent(ev);
  };
  return { w, doc, $, chiamate, tocca, riquadro, attesa: () => new Promise((ok) => setTimeout(ok, 0)) };
}

const ok = () => ({
  success: true,
  progress_html: "<b>dopo</b>",
  dock_html: "<i>comandi</i>",
});

(async () => {
  // 1–2. il tocco apre l'ingrandimento nel punto giusto
  {
    const p = pagina();
    // (330, 230) sullo schermo → (300, 200) sul panno: l'origine sta a (30, 30).
    p.tocca(p.$("[data-cloth-full]"), 330, 230);
    assert.strictEqual(p.$("[data-cloth-zoom]").hidden, false);
    const m = p.$("[data-cloth-marker]");
    assert.strictEqual(m.getAttribute("cx"), "300");
    assert.strictEqual(m.getAttribute("cy"), "200");
    assert.strictEqual(p.chiamate.length, 0, "il tocco non registra niente da solo");
  }

  // il riquadro più largo del viewBox lascia due bande ai lati: il conto le toglie
  {
    const p = pagina();
    // Scala 1 (la altezza è il lato stretto) e due bande da 430px ai lati:
    // l'origine del panno finisce a 460px dal bordo del riquadro.
    p.riquadro(p.$("[data-cloth-full]"), { left: 0, top: 0, width: 1720, height: 460 });
    p.tocca(p.$("[data-cloth-full]"), 460 + 300, 230);
    assert.strictEqual(p.$("[data-cloth-marker]").getAttribute("cx"), "300");
  }

  // 3–4. trascinare sposta il punto, e «Conferma» manda l'ultimo
  {
    const p = pagina({ risposte: [ok()] });
    p.tocca(p.$("[data-cloth-full]"), 330, 230);
    const zoom = p.$("[data-cloth-zoomsvg]");
    // viewBox 450 50 300 300 su un riquadro 300x300: una unità = un pixel.
    zoom.dispatchEvent(new p.w.MouseEvent("pointermove", { clientX: 200, clientY: 150, bubbles: true }));
    assert.strictEqual(p.$("[data-cloth-marker]").getAttribute("cx"), "650");
    assert.strictEqual(p.$("[data-cross-x]").getAttribute("x1"), "650");
    p.$("[data-cloth-confirm]").click();
    await p.attesa();
    assert.deepStrictEqual(p.chiamate[0], {
      url: "/shot",
      body: { made: true, x: 650, y: 200 },
    });
    // 7. la risposta ridisegna i due pezzi
    assert.strictEqual(p.$("[data-run-progress]").innerHTML, "<b>dopo</b>");
    assert.strictEqual(p.$("[data-run-dock]").innerHTML, "<i>comandi</i>");
  }

  // il punto non esce dal panno
  {
    const p = pagina();
    p.tocca(p.$("[data-cloth-full]"), 330, 230);
    p.$("[data-cloth-zoomsvg]").dispatchEvent(
      new p.w.MouseEvent("pointermove", { clientX: 5000, clientY: -5000, bubbles: true })
    );
    assert.strictEqual(p.$("[data-cloth-marker]").getAttribute("cx"), "800");
    assert.strictEqual(p.$("[data-cloth-marker]").getAttribute("cy"), "0");
  }

  // 5. «Tavolo intero» richiude e non manda niente
  {
    const p = pagina();
    p.tocca(p.$("[data-cloth-full]"), 330, 230);
    p.$("[data-cloth-cancel]").click();
    assert.strictEqual(p.$("[data-cloth-zoom]").hidden, true);
    assert.strictEqual(p.chiamate.length, 0);
  }

  // 6. «Non è entrata»: un colpo senza posizione
  {
    const p = pagina({ risposte: [ok()] });
    p.$("[data-shot-miss]").click();
    await p.attesa();
    assert.deepStrictEqual(p.chiamate[0], { url: "/shot", body: { made: false } });
  }

  // 8. annulla, chiudi, ricomincia
  {
    // Risposte senza `dock_html`: qui interessa che ogni comando chiami la sua
    // route, e ridisegnare i comandi toglierebbe di mezzo i pulsanti seguenti.
    const soloProgresso = { success: true, progress_html: "<b>dopo</b>" };
    const p = pagina({ risposte: [soloProgresso, soloProgresso, { success: true, redirect_url: "/fine" }] });
    p.$("[data-shot-undo]").click();
    await p.attesa();
    p.$("[data-shot-restart]").click();
    await p.attesa();
    p.$("[data-shot-close]").click();
    await p.attesa();
    assert.deepStrictEqual(p.chiamate.map((c) => c.url), ["/shot/undo", "/shot/restart", "/shot/close"]);
  }

  // l'errore si mostra e la pagina resta com'era
  {
    const p = pagina({ risposte: [{ success: false, error: "troppo tardi" }, new Error("giù")] });
    p.$("[data-shot-miss]").click();
    await p.attesa();
    assert.strictEqual(p.w.__errore, "troppo tardi");
    assert.ok(p.$("[data-run-progress]").innerHTML.includes("c7-cloth"));
    p.$("[data-shot-miss]").click();
    await p.attesa();
    assert.strictEqual(p.w.__errore, "rete");
  }

  console.log("test_exercise_shots: ok");
})().catch((e) => { console.error(e); process.exit(1); });
