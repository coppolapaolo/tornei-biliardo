/* Opzioni dei formati a tabellone nei form della gara (Step 10).
 *
 * Creazione e modifica sono due schermate diverse — una vecchia a card
 * Bootstrap, una nel design system 7c — ma la regola su cosa mostrare e' una
 * sola, quindi vive qui invece che copiata in due `<script>` inline.
 *
 * Il file agisce solo se trova gli id che si aspetta: nelle pagine che non
 * includono `_bracket_options.html` esce subito.
 */
(function () {
  'use strict';

  var BRACKET_STRATEGIES = ['direct_elimination', 'double_knockout'];

  document.addEventListener('DOMContentLoaded', function () {
    var strategy = document.getElementById('matchmaking_strategy');
    var section = document.getElementById('bracket_options_section');
    if (!strategy || !section) { return; }

    var thirdPlaceRow = document.getElementById('third_place_row');
    var doubleKoRow = document.getElementById('double_ko_rounds_row');
    var maxParticipants = document.getElementById('max_participants');
    var classification = document.getElementById('classification_system');

    /* Il sistema di classifica sul tabellone non e' una scelta: e' POSITION e
     * basta, e il server lo impone comunque. Il select resta visibile ma
     * spento, con l'etichetta che dice cosa sara' — invece di lasciar credere
     * che si possa scegliere e poi ignorare la risposta. */
    var note = document.createElement('div');
    note.className = 'form-text';
    note.id = 'bracket_classification_note';
    note.style.display = 'none';
    note.textContent = section.dataset.classificationNote || '';
    if (classification && classification.parentNode) {
      classification.parentNode.appendChild(note);
    }

    function sync() {
      var value = strategy.value;
      var isBracket = BRACKET_STRATEGIES.indexOf(value) >= 0;

      section.style.display = isBracket ? '' : 'none';
      if (thirdPlaceRow) {
        thirdPlaceRow.style.display = value === 'direct_elimination' ? '' : 'none';
      }
      if (doubleKoRow) {
        doubleKoRow.style.display = value === 'double_knockout' ? '' : 'none';
      }

      /* US-4: sul tabellone il massimo iscritti dichiara la capienza, quindi
       * e' obbligatorio. Fuori dal tabellone resta facoltativo. */
      if (maxParticipants) {
        maxParticipants.required = isBracket;
      }

      if (classification) {
        classification.disabled = isBracket;
        note.style.display = isBracket ? '' : 'none';
      }

      /* Il configuratore della distanza si accorge del formato scelto: sul
       * tabellone un numero esatto pari puo' finire in parita' e il nodo
       * resterebbe senza vincitore (vedi `_distance_configurator.html`). */
      if (typeof window.updateDistancePreview === 'function') {
        window.updateDistancePreview();
      }
    }

    strategy.addEventListener('change', sync);
    sync();
  });
})();
