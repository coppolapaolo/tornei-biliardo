/**
 * Il modulo dell'esercizio (templates/challenge/form.html).
 *
 * Il modulo funziona anche senza questo file: tutto quello che fa qui è
 * comodità, tranne una cosa — il foglio «ha già delle prove». Il server si
 * rifiuta di salvare (409) finché non arriva una decisione; qui la si chiede
 * sopra il modulo com'è, così la foto appena scelta non va persa, e si
 * rispedisce lo stesso modulo con la risposta.
 */
(function () {
  'use strict';

  var form = document.querySelector('[data-challenge-form]');
  if (!form) return;
  var messages = window.challengeFormMessages || {};

  // ── al più N abilità: le pillole in più si spengono, non spariscono ──────
  document.querySelectorAll('[data-pick-max]').forEach(function (group) {
    var max = parseInt(group.dataset.pickMax, 10);
    var boxes = Array.prototype.slice.call(group.querySelectorAll('input[type="checkbox"]'));
    function sync() {
      var full = boxes.filter(function (b) { return b.checked; }).length >= max;
      boxes.forEach(function (b) {
        var off = full && !b.checked;
        b.disabled = off;
        b.closest('label').classList.toggle('is-off', off);
      });
    }
    boxes.forEach(function (b) { b.addEventListener('change', sync); });
    sync();
  });

  // ── un gruppo di radio che si può anche spegnere (il livello) ────────────
  document.querySelectorAll('[data-radio-off]').forEach(function (group) {
    var none = group.querySelector('input[value=""]');
    group.querySelectorAll('input[type="radio"]').forEach(function (radio) {
      radio.addEventListener('click', function () {
        if (radio.dataset.wasChecked === '1' && none && radio !== none) {
          none.checked = true;
        }
        group.querySelectorAll('input[type="radio"]').forEach(function (r) {
          r.dataset.wasChecked = r.checked ? '1' : '';
        });
      });
      radio.dataset.wasChecked = radio.checked ? '1' : '';
    });
  });

  // ── il massimo riguarda solo gli esercizi a punteggio ────────────────────
  var maxRow = document.getElementById('maxScoreRow');
  var maxInput = document.getElementById('max_score');
  function syncMaxScore() {
    var chosen = form.querySelector('input[name="scoring_type"]:checked');
    var scored = !chosen || chosen.value === 'score';
    // `d-none` e non `hidden`: la riga è un `d-flex`, che vince su [hidden].
    maxRow.classList.toggle('d-none', !scored);
    // Si svuota: un 15 scritto prima di cambiare idea resterebbe nel modulo,
    // invisibile, e tornerebbe a galla cambiando idea di nuovo.
    if (!scored) maxInput.value = '';
  }
  form.querySelectorAll('input[name="scoring_type"]').forEach(function (radio) {
    radio.addEventListener('change', syncMaxScore);
  });
  if (maxRow) syncMaxScore();

  // ── varianti: aggiungere e togliere righe ────────────────────────────────
  var variants = form.querySelector('[data-variants]');
  if (variants) {
    var template = variants.querySelector('[data-variant-template]');
    var addButton = variants.querySelector('[data-variant-add]');
    addButton.addEventListener('click', function () {
      var row = template.content.firstElementChild.cloneNode(true);
      variants.insertBefore(row, template);
      row.querySelector('input[name="variant_label"]').focus();
    });
    variants.addEventListener('click', function (event) {
      var remove = event.target.closest('[data-variant-remove]');
      if (remove) remove.closest('[data-variant-row]').remove();
    });
  }

  // ── anteprima della foto: senza, l'immagine sbagliata si scopre dopo ─────
  var imageInput = document.getElementById('image');
  var preview = document.getElementById('imagePreview');
  var current = document.getElementById('currentImage');
  if (imageInput && preview) {
    imageInput.addEventListener('change', function () {
      var file = imageInput.files && imageInput.files[0];
      preview.hidden = !file;
      if (current) current.hidden = !!file;
      if (file) preview.querySelector('img').src = URL.createObjectURL(file);
    });
  }

  // ── passare al disegnatore senza perdere quello che si è scritto ─────────
  var toBuilder = document.getElementById('goToBuilder');
  if (toBuilder) {
    toBuilder.addEventListener('click', function (event) {
      var params = new URLSearchParams();
      var title = form.elements.title.value.trim();
      if (title) params.set('title', title);
      var description = form.elements.description.value.trim();
      if (description) params.set('description', description);
      var chosen = form.querySelector('input[name="scoring_type"]:checked');
      if (chosen && chosen.value === 'pass_fail') params.set('pass_fail_only', 'true');
      if (maxInput && maxInput.value.trim()) params.set('max_score', maxInput.value.trim());
      if (params.toString()) {
        event.preventDefault();
        window.location.href = toBuilder.href + '?' + params.toString();
      }
    });
  }

  // ── salvare, e la domanda quando ci sono già delle prove ─────────────────
  var sheetEl = document.getElementById('evidenceSheet');
  function openSheet(payload) {
    if (!sheetEl) return false;
    if (payload) {
      sheetEl.querySelector('[data-evidence-title]').textContent = payload.title || '';
      sheetEl.querySelector('[data-evidence-text]').textContent = payload.text || '';
    }
    if (window.bootstrap && window.bootstrap.Modal) {
      window.bootstrap.Modal.getOrCreateInstance(sheetEl).show();
    } else {
      sheetEl.classList.add('show');
      sheetEl.style.display = 'block';
    }
    return true;
  }

  function fail(text) {
    if (typeof window.showError === 'function') window.showError(text);
    else window.alert(text);
  }

  var sending = false;
  function send() {
    if (sending) return;
    sending = true;
    var headers = { 'X-Requested-With': 'XMLHttpRequest' };
    if (typeof window.csrfToken === 'function') headers['X-CSRFToken'] = window.csrfToken();
    return fetch(form.getAttribute('action') || window.location.href, {
      method: 'POST',
      headers: headers,
      body: new FormData(form)
    })
      .then(function (response) {
        return response.json().then(function (body) { return { status: response.status, body: body }; });
      })
      .then(function (result) {
        sending = false;
        if (result.body && result.body.success) {
          window.location.href = result.body.redirect_url;
        } else if (result.status === 409 && result.body && result.body.needs_decision) {
          if (!openSheet(result.body)) fail(result.body.title);
        } else {
          fail((result.body && result.body.error) || messages.saveFailed);
        }
      })
      .catch(function () {
        sending = false;
        fail(messages.saveFailed);
      });
  }

  form.addEventListener('submit', function (event) {
    event.preventDefault();
    var then = event.submitter && event.submitter.dataset ? event.submitter.dataset.then : '';
    form.elements.then.value = then || '';
    // Ogni invio dal pulsante riparte da «chiedi»: la decisione vale solo per
    // il salvataggio su cui è stata presa.
    form.elements.on_evidence.value = '';
    send();
  });

  if (sheetEl) {
    sheetEl.querySelectorAll('[data-evidence-choice]').forEach(function (button) {
      button.addEventListener('click', function () {
        form.elements.on_evidence.value = button.dataset.evidenceChoice;
        send();
      });
    });
    if (form.dataset.decisionOpen) openSheet(null);
  }
})();
