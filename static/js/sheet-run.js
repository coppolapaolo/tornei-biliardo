/* La seduta di una scheda: i comandi (ADR-067).
 *
 * Un tocco, una richiesta, e la risposta porta i **due pezzi già disegnati dal
 * server** — «come sta andando» e i comandi. Qui non si compone niente: si
 * manda il gesto e si sostituisce l'HTML. È la stessa scelta della prova a
 * colpi (ADR-066), e la ragione è che due copie dello stato, una qui e una
 * nel server, prima o poi divergono — e qui divergerebbero davanti a chi ha
 * appena segnato dieci caselle col telefono sulla sponda.
 *
 * Si lavora per **delega sul contenitore**: i comandi vengono sostituiti a
 * ogni risposta, quindi un ascoltatore attaccato a un tasto non sopravvivrebbe
 * al primo tocco.
 *
 * `csrfToken()` e `showError()` sono quelli di `base.html`.
 */
(function () {
  'use strict';

  var root = document.querySelector('[data-sheet-run]');
  if (!root) return;

  var urls = {
    record: root.dataset.recordUrl,
    shot: root.dataset.shotUrl,
    undo: root.dataset.undoUrl
  };
  var msgError = root.dataset.msgError;
  var at = parseInt(root.dataset.at, 10) || 0;
  var inCorso = false;

  function fail(message) {
    if (typeof window.showError === 'function') window.showError(message || msgError);
  }

  function cella(nodo) {
    var box = nodo.closest('[data-cell]');
    if (!box) return null;
    return {
      item_id: parseInt(box.dataset.item, 10),
      variant_id: box.dataset.variant ? parseInt(box.dataset.variant, 10) : null
    };
  }

  function ridisegna(dati) {
    /* `innerHTML` è voluto: il pezzo lo rende Jinja sul nostro server, con
       l'autoescape acceso — l'etichetta di una variante scritta da un utente
       arriva già neutralizzata. */
    if (typeof dati.progress_html === 'string') {
      root.querySelectorAll('[data-run-progress]').forEach(function (el) {
        el.innerHTML = dati.progress_html;
      });
    }
    if (typeof dati.dock_html === 'string') {
      root.querySelectorAll('[data-run-dock]').forEach(function (el) {
        el.innerHTML = dati.dock_html;
      });
    }
  }

  function manda(url, corpo) {
    if (inCorso) return;
    inCorso = true;
    corpo.at = at;
    fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': window.csrfToken() },
      body: JSON.stringify(corpo)
    })
      .then(function (risposta) {
        return risposta.json().then(function (dati) {
          if (!risposta.ok || !dati.success) throw new Error(dati.error || msgError);
          return dati;
        });
      })
      .then(ridisegna)
      .catch(function (errore) { fail(errore.message); })
      .finally(function () { inCorso = false; });
  }

  /* ── I gesti sulle caselle ─────────────────────────────────────────── */
  root.addEventListener('click', function (event) {
    var tasto = event.target.closest('[data-value],[data-shot],[data-done],[data-undo],[data-clear],[data-pad-save]');
    if (!tasto || tasto.disabled) return;
    var dove = cella(tasto);
    if (!dove) return;

    if (tasto.hasAttribute('data-value')) {
      manda(urls.record, Object.assign({}, dove, { value: parseInt(tasto.dataset.value, 10) }));
      return;
    }
    if (tasto.hasAttribute('data-shot')) {
      manda(urls.shot, Object.assign({}, dove, { made: tasto.dataset.shot === '1' }));
      return;
    }
    if (tasto.hasAttribute('data-done')) {
      manda(urls.record, Object.assign({}, dove, { done: tasto.dataset.done === '1' }));
      return;
    }
    if (tasto.hasAttribute('data-undo')) {
      manda(urls.undo, dove);
      return;
    }
    if (tasto.hasAttribute('data-clear')) {
      manda(urls.undo, Object.assign({}, dove, { clear: true }));
      return;
    }
    if (tasto.hasAttribute('data-pad-save')) {
      var campo = tasto.closest('[data-cell]').querySelector('[data-pad-value]');
      manda(urls.record, Object.assign({}, dove, { value: parseInt(campo.value, 10) || 0 }));
    }
  });

  /* ── Il tastierino meno · cifra · più ──────────────────────────────── */
  root.addEventListener('click', function (event) {
    var passo = event.target.closest('[data-step]');
    if (!passo) return;
    var pad = passo.closest('[data-pad]');
    if (!pad) return;
    var campo = pad.querySelector('[data-pad-value]');
    var massimo = parseInt(pad.dataset.max, 10);
    var valore = (parseInt(campo.value, 10) || 0) + parseInt(passo.dataset.step, 10);
    if (valore < 0) valore = 0;
    if (!isNaN(massimo) && valore > massimo) valore = massimo;
    campo.value = String(valore);
  });

  /* ── Il foglio «scrivi il totale» ──────────────────────────────────── */
  var foglio = document.getElementById('sheetTotale');
  if (foglio) {
    var corrente = null;

    foglio.addEventListener('show.bs.modal', function (event) {
      var apri = event.relatedTarget;
      corrente = apri ? apri.closest('[data-cell]') : null;
      var campo = foglio.querySelector('[data-total-value]');
      var massimo = foglio.querySelector('[data-total-max]');
      if (apri && campo) {
        campo.value = apri.dataset.current || '0';
        campo.max = apri.dataset.max || '';
        if (massimo) massimo.textContent = apri.dataset.max ? '/ ' + apri.dataset.max : '';
      }
    });

    foglio.addEventListener('click', function (event) {
      var campo = foglio.querySelector('[data-total-value]');
      var passo = event.target.closest('[data-total-step]');
      if (passo) {
        var massimo = parseInt(campo.max, 10);
        var valore = (parseInt(campo.value, 10) || 0) + parseInt(passo.dataset.totalStep, 10);
        if (valore < 0) valore = 0;
        if (!isNaN(massimo) && valore > massimo) valore = massimo;
        campo.value = String(valore);
        return;
      }
      if (event.target.closest('[data-total-save]') && corrente) {
        manda(urls.record, {
          item_id: parseInt(corrente.dataset.item, 10),
          variant_id: corrente.dataset.variant ? parseInt(corrente.dataset.variant, 10) : null,
          value: parseInt(campo.value, 10) || 0
        });
      }
    });
  }
})();
