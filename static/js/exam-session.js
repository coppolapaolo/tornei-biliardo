/* La sessione d'esame, dal lato di chi scrive i punteggi.
 *
 * Due cose sole, e nessuna richiesta di rete: la prova si manda con un modulo
 * normale.
 *
 *  1. I due tasti muovono la cifra di uno, dentro 0…massimo. La cifra è il
 *     campo stesso: chi la tocca la scrive dal tastierino numerico.
 *  2. Sotto lg il tastierino è agganciato in basso: la sua altezza vera va
 *     detta al CSS, perché il contenuto possa scorrere fin sopra.
 */
(function () {
  'use strict';

  function clamp(value, max) {
    if (Number.isNaN(value) || value < 0) return 0;
    return value > max ? max : value;
  }

  document.querySelectorAll('[data-exam-pad]').forEach(function (pad) {
    var max = parseInt(pad.dataset.max, 10) || 0;
    var field = pad.querySelector('input[name="score"]');
    if (!field) return;

    function write(value) {
      var next = String(clamp(value, max));
      if (next === field.value) return;
      field.value = next;
      // La cifra che cambia sotto gli occhi salta (`c7-pop`). `c7ScorePop`
      // scrive `textContent`, e qui la cifra è un campo: il salto si rigioca
      // a mano, togliendo e rimettendo la classe.
      field.classList.remove('is-pop');
      void field.offsetWidth;
      field.classList.add('is-pop');
    }

    pad.querySelectorAll('[data-step]').forEach(function (button) {
      button.addEventListener('click', function () {
        write((parseInt(field.value, 10) || 0) + parseInt(button.dataset.step, 10));
      });
    });
    field.addEventListener('focus', function () { field.select(); });
    field.addEventListener('blur', function () {
      field.value = String(clamp(parseInt(field.value, 10), max));
    });
  });

  var dock = document.getElementById('examDock');
  if (dock) {
    var tell = function () {
      document.documentElement.style.setProperty('--c7-exam-dock-h', dock.offsetHeight + 'px');
    };
    tell();
    window.addEventListener('resize', tell);
  }
})();
