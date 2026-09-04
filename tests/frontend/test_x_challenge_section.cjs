/**
 * Headless automation per la sezione «esercizio per la X».
 *
 * Carica i veri static/js/x_challenge_section.js e static/js/bracket_options.js
 * dentro jsdom e presidia i due guasti visti in produzione il 2026-09-04, dopo
 * la PR #269:
 *
 * 1. il campo dell'esercizio era `required` anche quando la sezione era
 *    nascosta. Un controllo invalido che non puo' ricevere il focus rende il
 *    modulo invalido senza che il browser possa dire dove: il pulsante Salva
 *    diventava inerte e muto. Con la politica di default («X vinta a
 *    tavolino») nessuna gara si poteva creare dal modal ne' modificare;
 * 2. `bracket_options.js` riscriveva il `display` della sezione — che portava
 *    `data-bracket-hide` — rimettendola visibile anche con una politica che
 *    non prevede l'esercizio.
 *
 * Il test guarda `checkValidity()`, che e' esattamente cio' che decide se il
 * browser invia il modulo: e' la differenza fra «Salva funziona» e «Salva non
 * fa niente».
 *
 * Run:  cd tests/frontend && npm install && npm test
 */
const fs = require("fs");
const path = require("path");
const assert = require("assert");
const { JSDOM } = require("jsdom");

function sorgente(nome) {
  return fs.readFileSync(
    path.join(__dirname, "..", "..", "static", "js", nome),
    "utf8"
  );
}

const X_SECTION = sorgente("x_challenge_section.js");
const BRACKET = sorgente("bracket_options.js");

/* La forma del modulo di modifica (templates/components/_gara_edit_form.html):
 * il select della strategia e le opzioni del tabellone ci sono, quindi
 * bracket_options.js si attiva davvero — che e' la condizione del guasto 2. */
function pagina(policyIniziale, strategiaIniziale) {
  return `<!doctype html><body>
    <form id="f">
      <select id="matchmaking_strategy" name="matchmaking_strategy">
        <option value="amalfi" ${strategiaIniziale === "amalfi" ? "selected" : ""}>Amalfi</option>
        <option value="direct_elimination" ${strategiaIniziale === "direct_elimination" ? "selected" : ""}>Eliminazione diretta</option>
      </select>
      <div id="bracket_options_section" data-minimum-players="{}"></div>
      <input id="max_participants" value="16">
      <input id="min_participants" value="4">

      <select id="odd_number_policy" name="odd_number_policy">
        <option value="bye" ${policyIniziale === "bye" ? "selected" : ""}>X — vinto a tavolino</option>
        <option value="bye_with_challenge" ${policyIniziale === "bye_with_challenge" ? "selected" : ""}>X con esercizio</option>
        <option value="trio" ${policyIniziale === "trio" ? "selected" : ""}>Match a 3</option>
      </select>

      <div id="x_challenge_section" data-x-challenge-section="odd_number_policy"
           ${policyIniziale === "bye_with_challenge" ? "" : 'style="display:none"'}>
        <select id="x_challenge_id" name="x_challenge_id">
          <option value="" disabled selected>Scegli un esercizio…</option>
          <option value="7">Esercizio 7</option>
        </select>
      </div>
      <button type="submit">Salva</button>
    </form>
  </body>`;
}

function ambiente(policy, strategia) {
  const dom = new JSDOM(pagina(policy, strategia || "amalfi"), {
    runScripts: "outside-only",
  });
  const w = dom.window;
  // L'ordine e' quello dei template: le opzioni del tabellone sono incluse
  // prima, la sezione della X in fondo al modulo.
  w.eval(BRACKET);
  w.eval(X_SECTION);
  w.document.dispatchEvent(new w.Event("DOMContentLoaded"));
  return w;
}

function stato(w) {
  const sezione = w.document.getElementById("x_challenge_section");
  const campo = w.document.getElementById("x_challenge_id");
  return {
    display: sezione.style.display,
    required: campo.required,
    modulo_valido: w.document.getElementById("f").checkValidity(),
  };
}

function cambiaPolicy(w, valore) {
  const policy = w.document.getElementById("odd_number_policy");
  policy.value = valore;
  policy.dispatchEvent(new w.Event("change"));
}

function cambiaStrategia(w, valore) {
  const s = w.document.getElementById("matchmaking_strategy");
  s.value = valore;
  s.dispatchEvent(new w.Event("change"));
}

const prove = [];
function prova(nome, fn) {
  prove.push([nome, fn]);
}

prova("con «X vinta a tavolino» il modulo si puo' salvare", function () {
  const s = stato(ambiente("bye"));
  assert.strictEqual(s.display, "none", "la sezione deve restare nascosta");
  assert.strictEqual(s.required, false, "il campo nascosto non puo' essere obbligatorio");
  assert.strictEqual(s.modulo_valido, true, "il guasto: Salva non faceva niente");
});

prova("bracket_options non riapre la sezione", function () {
  // Il guasto 2: al primo sync() con una strategia a girone, setHidden()
  // rimetteva `display: ''` su ogni [data-bracket-hide]. La sezione non porta
  // piu' quell'attributo, quindi il suo display lo decide solo la politica.
  const w = ambiente("bye");
  assert.strictEqual(
    w.document.getElementById("x_challenge_section").style.display,
    "none"
  );
});

prova("con «X con esercizio» l'esercizio e' obbligatorio", function () {
  const w = ambiente("bye_with_challenge");
  const s = stato(w);
  assert.strictEqual(s.display, "", "la sezione deve vedersi");
  assert.strictEqual(s.required, true, "senza esercizio la gara non sta in piedi");
  assert.strictEqual(s.modulo_valido, false, "il browser deve chiedere l'esercizio");

  // …e scegliendolo il modulo torna valido.
  w.document.getElementById("x_challenge_id").value = "7";
  assert.strictEqual(stato(w).modulo_valido, true);
});

prova("cambiare politica muove insieme visibilita' e obbligo", function () {
  const w = ambiente("bye");
  cambiaPolicy(w, "bye_with_challenge");
  assert.deepStrictEqual(
    { display: stato(w).display, required: stato(w).required },
    { display: "", required: true }
  );
  cambiaPolicy(w, "trio");
  assert.deepStrictEqual(
    { display: stato(w).display, required: stato(w).required },
    { display: "none", required: false }
  );
  assert.strictEqual(stato(w).modulo_valido, true);
});

prova("sul tabellone la domanda non si pone", function () {
  // I bye sono strutturali e `odd_number_policy` non viene nemmeno letta
  // (`_bracket_derived_fields`): chiedere l'esercizio bloccherebbe il modulo
  // per una scelta che il server scarta.
  const w = ambiente("bye_with_challenge");
  cambiaStrategia(w, "direct_elimination");
  const s = stato(w);
  assert.strictEqual(s.display, "none");
  assert.strictEqual(s.required, false);
  assert.strictEqual(s.modulo_valido, true);

  // E tornando a un girone la domanda torna, obbligo compreso.
  cambiaStrategia(w, "amalfi");
  assert.strictEqual(stato(w).display, "");
  assert.strictEqual(stato(w).required, true);
});

prova("il modal di creazione usa gli stessi id del suo modulo", function () {
  // Nel modal gli id sono prefissati `create_` e non c'e' il select della
  // strategia: il file deve reggere entrambe le forme.
  const dom = new JSDOM(
    `<!doctype html><body><form id="f">
       <select id="create_odd_number_policy"><option value="bye" selected>a tavolino</option>
       <option value="bye_with_challenge">con esercizio</option></select>
       <div id="create_x_challenge_section"
            data-x-challenge-section="create_odd_number_policy" style="display:none">
         <select id="create_x_challenge_id" name="x_challenge_id">
           <option value="" disabled selected>Scegli…</option>
           <option value="3">Esercizio 3</option>
         </select>
       </div>
     </form></body>`,
    { runScripts: "outside-only" }
  );
  const w = dom.window;
  w.eval(X_SECTION);
  w.document.dispatchEvent(new w.Event("DOMContentLoaded"));

  const campo = w.document.getElementById("create_x_challenge_id");
  assert.strictEqual(campo.required, false);
  assert.strictEqual(w.document.getElementById("f").checkValidity(), true);

  const policy = w.document.getElementById("create_odd_number_policy");
  policy.value = "bye_with_challenge";
  policy.dispatchEvent(new w.Event("change"));
  assert.strictEqual(campo.required, true);
  assert.strictEqual(
    w.document.getElementById("create_x_challenge_section").style.display,
    ""
  );
});

let falliti = 0;
prove.forEach(function (p) {
  try {
    p[1]();
    console.log("  ok  " + p[0]);
  } catch (e) {
    falliti += 1;
    console.error("FAIL  " + p[0] + "\n      " + e.message);
  }
});
console.log(
  (falliti ? "✗ " : "✓ ") + (prove.length - falliti) + "/" + prove.length + " prove"
);
process.exit(falliti ? 1 : 0);
