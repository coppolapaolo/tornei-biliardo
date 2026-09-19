/**
 * «Oggi» e il catalogo degli esercizi (templates/challenge/today.html,
 * catalog.html).
 *
 * Le pagine funzionano senza questo file: i filtri sono collegamenti. Qui si
 * aggiungono tre comodità — il cuore che non ricarica la pagina, una riga di
 * pillole per volta, e la ricerca nel testo delle card già a schermo.
 */
(function () {
  'use strict';

  var list = document.querySelector('[data-exercise-list]');
  if (!list) return;
  var messages = window.challengeCatalogMessages || {};

  // ── il cuore ─────────────────────────────────────────────────────────────
  list.addEventListener('click', function (event) {
    var button = event.target.closest('[data-favorite]');
    if (!button) return;
    event.preventDefault();
    var headers = { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' };
    if (typeof window.csrfToken === 'function') headers['X-CSRFToken'] = window.csrfToken();
    fetch(button.dataset.favoriteUrl, { method: 'POST', headers: headers })
      .then(function (response) { return response.json(); })
      .then(function (data) {
        if (!data || !data.success) throw new Error('favorite');
        var on = !!data.is_favorite;
        button.classList.toggle('is-on', on);
        button.setAttribute('aria-pressed', on ? 'true' : 'false');
        button.setAttribute('aria-label', on ? messages.favRemove : messages.favAdd);
        button.querySelector('i').className = (on ? 'fas' : 'far') + ' fa-heart';
      })
      .catch(function () {
        if (typeof window.showError === 'function') window.showError(messages.favError);
      });
  });

  // ── una riga di pillole per volta ────────────────────────────────────────
  var axes = list.querySelector('[data-axes]');
  if (axes) {
    var showAxis = function (key) {
      axes.querySelectorAll('[data-axis]').forEach(function (row) {
        row.classList.toggle('d-none', row.dataset.axis !== key);
      });
      axes.querySelectorAll('[data-axis-tab]').forEach(function (tab) {
        var on = tab.dataset.axisTab === key;
        tab.classList.toggle('is-on', on);
        tab.setAttribute('aria-selected', on ? 'true' : 'false');
      });
    };
    axes.querySelectorAll('[data-axis-tab]').forEach(function (tab) {
      tab.addEventListener('click', function () { showAxis(tab.dataset.axisTab); });
    });
    showAxis(axes.dataset.open || 'abilita');
  }

  // ── cercare nel testo delle card a schermo ───────────────────────────────
  var search = list.querySelector('[data-exercise-search]');
  if (search) {
    var counter = list.querySelector('[data-exercise-count]');
    var empty = list.querySelector('[data-exercise-empty]');
    var cards = Array.prototype.slice.call(list.querySelectorAll('[data-exercise]'));
    search.addEventListener('input', function () {
      var term = (search.value || '').trim().toLowerCase();
      var visible = 0;
      cards.forEach(function (card) {
        var show = !term || (card.dataset.search || '').indexOf(term) !== -1;
        card.classList.toggle('d-none', !show);
        if (show) visible++;
      });
      if (counter) {
        counter.textContent = visible === 1
          ? counter.dataset.templateOne
          : counter.dataset.templateMany.replace('{n}', visible);
      }
      if (empty && cards.length) empty.classList.toggle('d-none', visible > 0);
    });
  }
})();
