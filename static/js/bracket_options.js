/* Opzioni dei formati a tabellone nei form della gara.
 *
 * Creazione e modifica sono due schermate diverse — una vecchia a card
 * Bootstrap, una nel design system 7c — ma la regola su cosa mostrare e' una
 * sola, quindi vive qui invece che copiata in due `<script>` inline.
 *
 * Il file agisce solo se trova gli id che si aspetta: nelle pagine che non
 * includono `_bracket_options.html` esce subito.
 *
 * NOTA sulle responsabilita': qui si decide solo cosa **mostrare**. I valori
 * derivati (forfait, giocatori dispari, spareggio, turni, minimo iscritti) li
 * impone il server in `_bracket_derived_fields`, perche' una gara deve restare
 * coerente anche se arriva da una schermata vecchia o col JavaScript spento.
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
    var doubleKoRounds = document.getElementById('double_ko_rounds');
    var maxParticipants = document.getElementById('max_participants');
    var minParticipants = document.getElementById('min_participants');
    var roundsNote = document.getElementById('bracket_rounds_note');

    /* I minimi di formato arrivano dal server (`minimum_players_for`): sono
     * gli stessi che il sorteggio usa come pavimento del tabellone, e
     * riscriverli qui vorrebbe dire avere due verita' che possono divergere. */
    var floors = {};
    try {
      floors = JSON.parse(section.dataset.minimumPlayers || '{}');
    } catch (e) {
      floors = {};
    }

    /* I blocchi che sul tabellone non hanno alcun effetto: forfait (il ritiro
     * e' sempre walkover), giocatori dispari (i bye sono strutturali),
     * sistema di classifica (e' POSITION e basta), spareggio SSR (le
     * strategie POSITION dichiarano `requires_tiebreaker=False`) e numero di
     * turni (lo riscrive il sorteggio sugli iscritti effettivi). */
    var hideable = document.querySelectorAll('[data-bracket-hide]');

    function setHidden(node, hidden) {
      node.style.display = hidden ? 'none' : '';
      /* Un campo nascosto ma ancora `required` bloccherebbe il passo del
       * wizard senza che si veda dove: il browser non puo' dare il focus a un
       * elemento invisibile. Si toglie l'obbligo e lo si rimette uscendo. */
      Array.prototype.forEach.call(
        node.querySelectorAll('[required]'),
        function (field) { field.dataset.bracketWasRequired = '1'; }
      );
      Array.prototype.forEach.call(
        node.querySelectorAll('[data-bracket-was-required]'),
        function (field) { field.required = !hidden; }
      );
    }

    function estimatedRounds(value, capienza) {
      var floor = floors[value] || 2;
      var size = Math.max(floor, Math.pow(2, Math.ceil(Math.log2(capienza))));
      var levels = Math.round(Math.log2(size));
      // Doppio KO: winners + losers + finale + bella (ADR-038).
      return value === 'double_knockout' ? 2 * levels + 1 : levels;
    }

    function syncRoundsNote(value, isBracket) {
      if (!roundsNote) { return; }
      var capienza = parseInt(maxParticipants && maxParticipants.value, 10);
      if (!isBracket || !capienza) {
        roundsNote.style.display = 'none';
        return;
      }
      roundsNote.style.display = '';
      roundsNote.textContent = (roundsNote.dataset.template || '')
        .replace('{n}', estimatedRounds(value, capienza));
    }

    function sync() {
      var value = strategy.value;
      var isBracket = BRACKET_STRATEGIES.indexOf(value) >= 0;

      section.style.display = isBracket ? '' : 'none';
      Array.prototype.forEach.call(hideable, function (node) {
        setHidden(node, isBracket);
      });

      /* La finalina serve dove il terzo posto e' un pari merito: sempre a
       * eliminazione diretta, e nel doppio KO **solo con la fase a gironi**,
       * perche' li' il tabellone finale e' eliminazione diretta pura. Nel
       * doppio KO pieno il terzo lo decide il losers bracket. */
      if (thirdPlaceRow) {
        var conGironi = doubleKoRounds && doubleKoRounds.value;
        var applies = value === 'direct_elimination'
          || (value === 'double_knockout' && !!conGironi);
        thirdPlaceRow.style.display = applies ? '' : 'none';
      }
      if (doubleKoRow) {
        doubleKoRow.style.display = value === 'double_knockout' ? '' : 'none';
      }

      /* US-4: sul tabellone il massimo iscritti dichiara la capienza, quindi
       * e' obbligatorio. Fuori dal tabellone resta facoltativo. */
      if (maxParticipants) {
        maxParticipants.required = isBracket;
      }

      /* Il default del form e' 6, che per il doppio KO (che ne vuole 8) darebbe
       * una gara impossibile da avviare. */
      if (minParticipants) {
        var floor = isBracket ? (floors[value] || 2) : 2;
        minParticipants.min = floor;
        if (parseInt(minParticipants.value, 10) < floor) {
          minParticipants.value = floor;
        }
      }

      syncRoundsNote(value, isBracket);

      /* Il configuratore della distanza si accorge del formato scelto: sul
       * tabellone un numero esatto pari puo' finire in parita' e il nodo
       * resterebbe senza vincitore (vedi `_distance_configurator.html`). */
      if (typeof window.updateDistancePreview === 'function') {
        window.updateDistancePreview();
      }

      /* Quali strategie siano «a tabellone» lo sa solo questo file. Chi ha
       * bisogno di reagire al formato si abbona invece di tenersi una copia
       * dell'elenco, che prima o poi divergerebbe: vedi
       * `x_challenge_section.js`. */
      document.dispatchEvent(new CustomEvent('gara:formato', {
        detail: { isBracket: isBracket }
      }));
    }

    strategy.addEventListener('change', sync);
    if (doubleKoRounds) { doubleKoRounds.addEventListener('change', sync); }
    if (maxParticipants) { maxParticipants.addEventListener('input', sync); }
    sync();
  });
})();
