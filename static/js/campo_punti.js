/*
 * Il campo «Punti in classifica» (templates/components/_campo_punti.html)
 * si vede solo col sistema a punti (ADR-078, emendamento).
 *
 * Ogni `[data-punti][data-sistema-da]` segue il <select> indicato: nascosto,
 * i suoi input sono disabilitati, così il browser non li valida e il modulo
 * non li manda (il server con un altro sistema non li leggerebbe comunque).
 */
(function () {
  'use strict';

  function segui(campo) {
    var sorgente = document.querySelector(campo.getAttribute('data-sistema-da'));
    if (!sorgente) return;
    function aggiorna() {
      var aPunti = sorgente.value === 'POINTS';
      campo.hidden = !aPunti;
      campo.querySelectorAll('input').forEach(function (input) {
        input.disabled = !aPunti;
      });
    }
    sorgente.addEventListener('change', aggiorna);
    aggiorna();
  }

  function avvia() {
    document.querySelectorAll('[data-punti][data-sistema-da]').forEach(segui);
  }

  // Per chi aggiunge un campo dopo il caricamento, e per i test.
  window.c7CampoPunti = { avvia: avvia };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', avvia);
  } else {
    avvia();
  }
})();
