/**
 * Le bilie del voto nella scheda di un esercizio: da 1 a 5, si tocca quella
 * del voto e si accendono tutte fino a lei.
 *
 * Il voto parte al tocco; le bilie si accendono subito e tornano com'erano se
 * il server rifiuta. Toccare di nuovo la bilia del proprio voto lo toglie. La testata — «4,5 · 12 giocatori» — si aggiorna al ricaricamento:
 * riscriverla da qui vorrebbe dire rifare in JS la frase che il server sa già
 * dire in due lingue.
 */
(function () {
  'use strict';

  var box = document.querySelector('[data-rating]');
  if (!box) return;
  var messages = window.challengeRatingMessages || {};
  var balls = Array.prototype.slice.call(box.querySelectorAll('[data-ball]'));
  var note = box.querySelector('[data-rating-note]');
  var current = parseInt(box.dataset.ratingValue, 10) || 0;
  var sending = false;

  function paint(value) {
    balls.forEach(function (ball) {
      var n = parseInt(ball.dataset.ball, 10);
      ball.classList.toggle('is-on', n <= value);
      ball.setAttribute('aria-checked', n === value ? 'true' : 'false');
    });
    if (note) note.textContent = value ? messages.removeHint : messages.helpHint;
  }

  balls.forEach(function (ball) {
    ball.addEventListener('click', function () {
      if (sending) return;
      var chosen = parseInt(ball.dataset.ball, 10);
      var next = chosen === current ? 0 : chosen;
      var before = current;
      sending = true;
      paint(next);
      var headers = { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' };
      if (typeof window.csrfToken === 'function') headers['X-CSRFToken'] = window.csrfToken();
      fetch(box.dataset.rateUrl, {
        method: 'POST',
        headers: headers,
        body: JSON.stringify({ rating: next || null })
      })
        .then(function (response) { return response.json(); })
        .then(function (data) {
          sending = false;
          if (!data || !data.success) throw new Error((data && data.error) || '');
          current = data.rating || 0;
          box.dataset.ratingValue = String(current);
          paint(current);
        })
        .catch(function (error) {
          sending = false;
          current = before;
          paint(before);
          if (typeof window.showError === 'function') {
            window.showError(error && error.message ? error.message : messages.failed);
          }
        });
    });
  });
})();
