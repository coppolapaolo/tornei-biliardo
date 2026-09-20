/* La cornice di esecuzione di un esercizio: i comandi (fase 5a).
 *
 * La pagina ha tre posti — il disegno, «come sta andando», i comandi — e
 * questo modulo muove solo il terzo. Il secondo **non lo disegna lui**: ogni
 * risposta del server porta `progress_html`, lo stesso pezzo già pronto, e qui
 * lo si sostituisce. Grafico e frasi hanno così un disegnatore solo, e nessun
 * testo tradotto viene composto nel browser.
 *
 * I due formati (verticale e tabellone orizzontale) mostrano gli **stessi**
 * comandi e gli **stessi** numeri: si lavora per selettore e non per id. Un id
 * si scrive una volta sola, e duplicarlo avrebbe fatto aggiornare un contatore
 * su due, in silenzio, a seconda dell'orientamento.
 *
 * Dati e testi arrivano dai `data-*` di `[data-run]`; `csrfToken()` e
 * `showError()` sono quelli di `base.html`.
 */
(function () {
  'use strict';

  var root = document.querySelector('[data-run]');
  if (!root) return;

  var isPassFail = root.dataset.passFail === 'true';
  var maxScore = parseInt(root.dataset.maxScore, 10) || 0;
  var msg = {
    recording: root.dataset.msgRecording,
    error: root.dataset.msgError,
    network: root.dataset.msgNetwork,
    undoError: root.dataset.msgUndoError
  };

  function all(selector) {
    return Array.prototype.slice.call(document.querySelectorAll(selector));
  }
  function setText(selector, value) {
    all(selector).forEach(function (el) { el.textContent = value; });
  }
  function fail(message) {
    if (typeof window.showError === 'function') window.showError(message);
  }

  /* ---- La cifra ---------------------------------------------------------- */
  var score = 0;
  function showScore() {
    all('[data-score-display]').forEach(function (el) {
      // La cifra che cambia sotto gli occhi salta; `c7ScorePop` anima solo se
      // il valore è cambiato davvero.
      if (window.c7ScorePop) window.c7ScorePop.segna(el, String(score));
      else el.textContent = String(score);
    });
    all('[data-score-pips] [data-pip]').forEach(function (pip) {
      pip.classList.toggle('is-on', parseInt(pip.dataset.pip, 10) < score);
    });
  }

  all('[data-score-step]').forEach(function (button) {
    button.addEventListener('click', function () {
      var next = score + parseInt(button.dataset.scoreStep, 10);
      if (next < 0) return;
      // Il tetto ferma il tastierino: è la stessa regola che il server
      // applica, portata dove l'errore si sta per fare.
      if (maxScore && next > maxScore) return;
      score = next;
      showScore();
    });
  });

  /* ---- Dopo ogni risposta ------------------------------------------------ */
  function redraw(data) {
    // `innerHTML` è voluto: il pezzo lo rende Jinja sul nostro server, con
    // l'autoescape acceso, quindi ciò che scrivono gli utenti (l'etichetta di
    // una variante) arriva già neutralizzato. Non ci passa altro.
    if (typeof data.progress_html === 'string') {
      all('[data-run-progress]').forEach(function (el) { el.innerHTML = data.progress_html; });
    }
    setText('[data-drill-count]', data.attempts_count);
    // Sui superato/non superato il secondo contatore mostra le riuscite, non
    // il record: «il tuo record è 1» non vuol dire niente.
    if (isPassFail) {
      if (data.passed_count !== undefined) setText('[data-drill-best]', data.passed_count);
    } else {
      var best = data.best_score;
      setText('[data-drill-best]', best === null || best === undefined ? '—' : best);
    }
    all('[data-undo]').forEach(function (b) { b.disabled = !data.attempts_count; });
  }

  var busy = false;
  function lock(locked) {
    busy = locked;
    // L'annulla lo governa `redraw`: spento finché non c'è niente da disfare.
    all('[data-outcome], [data-record], [data-score-step]').forEach(function (b) {
      b.disabled = locked;
    });
  }

  function post(url, payload) {
    var options = {
      method: 'POST',
      headers: { 'X-CSRFToken': window.csrfToken(), 'X-Requested-With': 'XMLHttpRequest' }
    };
    if (payload) {
      options.headers['Content-Type'] = 'application/json';
      options.body = JSON.stringify(payload);
    }
    return window.fetch(url, options).then(function (r) { return r.json(); });
  }

  function record(payload) {
    if (busy) return;
    lock(true);
    // L'etichetta torna com'era alla fine, comunque vada: lasciarla su
    // «Registro…» dopo un errore di rete direbbe che sta ancora salvando.
    var labels = all('[data-record-label]').map(function (el) { return [el, el.textContent]; });
    labels.forEach(function (pair) { pair[0].textContent = msg.recording; });

    // La variante scelta viaggia con ogni prova: resta accesa fra una e
    // l'altra, perché chi tira da destra ne fa dieci di fila da destra.
    var variant = document.querySelector('input[name="variant_id"]:checked');
    if (variant && variant.value) payload.variant_id = variant.value;

    function done() {
      lock(false);
      labels.forEach(function (pair) { pair[0].textContent = pair[1]; });
    }
    post(root.dataset.recordUrl, payload).then(function (data) {
      if (!data.success) { fail(data.error || msg.error); return; }
      redraw(data);
      score = 0;
      showScore();
    }).catch(function () { fail(msg.network); }).then(done);
  }

  // Superato / non superato: un tocco, una prova. Niente conferma: la via
  // d'uscita è l'annulla, che sta accanto e costa un tocco anche lui.
  all('[data-outcome]').forEach(function (button) {
    button.addEventListener('click', function () {
      record({ passed: button.dataset.outcome === 'true' });
    });
  });
  all('[data-record]').forEach(function (button) {
    button.addEventListener('click', function () { record({ score: score }); });
  });

  all('[data-undo]').forEach(function (button) {
    button.addEventListener('click', function () {
      if (busy) return;
      lock(true);
      post(root.dataset.undoUrl, null).then(function (data) {
        if (!data.success) { fail(data.error || msg.undoError); return; }
        redraw(data);
      }).catch(function () { fail(msg.undoError); }).then(function () { lock(false); });
    });
  });

  /* ---- I comandi agganciati in basso ------------------------------------- */
  // Sotto lg i comandi stanno fissi al posto della nav: la loro altezza vera
  // va detta al CSS, perché il contenuto possa scorrere fin sopra.
  var dock = document.querySelector('[data-run-dock]');
  if (dock) {
    var tell = function () {
      document.documentElement.style.setProperty('--c7-run-dock-h', dock.offsetHeight + 'px');
    };
    tell();
    window.addEventListener('resize', tell);
  }

  showScore();
})();
