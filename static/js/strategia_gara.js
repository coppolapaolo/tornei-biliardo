/* I vincoli della strategia di abbinamento nei moduli della gara.
 *
 * Scelto il formato (Amalfi, casuale, girone, tabellone), alcune scelte non
 * hanno piu' senso: il primo abbinamento per classifica nel girone, la X con
 * prova nel girone, la X a tavolino coi triangoli totali, l'anti-reincontro
 * spento con Amalfi. Qui si adattano i menu a ciò che la strategia ammette
 * (`STRATEGY_CONSTRAINTS`, passati dal server). Il server riapplica tutto
 * (`StrategyConfiguration.validate`, `odd_policy_for_strategy`).
 *
 * Fino al 2026-10-11 la regola stava in un `<script>` inline della modifica
 * della gara; ora serve anche il modale «Nuova gara» del campionato a
 * piazzamenti, che sceglie il formato della serata (ADR-080).
 *
 * Aggancio nel template, sul <select> della strategia:
 *
 *     data-strategia-gara
 *     data-vincoli='{{ available_strategies|tojson }}'
 *     data-girone="round_robin"
 *     data-prefisso="create_"            (facoltativo: prefisso degli id)
 *
 * Gli altri campi si trovano per id col prefisso: `first_round_policy`,
 * `odd_number_policy`, `anti_rematch_enabled`, `anti_rematch_section`,
 * `classification_system`, `strategy_description`. Mancano? Si saltano.
 *
 * Quando cambia la scelta dei dispari si emette `change` sul suo menu: chi
 * lo ascolta (la sezione dell'esercizio della X, l'avviso della partita a
 * tre) non resta fermo alla scelta di prima.
 */
(function () {
  'use strict';

  /* Le formule dei dispari che reggono con ogni sistema: col sistema RACK la
   * X a tavolino semplice darebbe zero triangoli a chi riposa
   * (`validators._validate_rack_system`). Nel girone decide la sola
   * strategia: li' il riposo non vale niente per nessuno. */
  var DISPARI_PER_SISTEMA = {
    WINS: ['no', 'bye', 'bye_with_challenge', 'trio'],
    RACK: ['no', 'bye_with_challenge', 'trio'],
    POINTS: ['no', 'bye', 'bye_with_challenge', 'trio'],
    POSITION: []
  };

  function cambia(menu, valore) {
    if (menu.value === valore) { return; }
    menu.value = valore;
    menu.dispatchEvent(new Event('change'));
  }

  function prepara(strategia) {
    var prefisso = strategia.dataset.prefisso || '';
    function perId(id) { return document.getElementById(prefisso + id); }

    var vincoli = {};
    try {
      vincoli = JSON.parse(strategia.dataset.vincoli || '{}');
    } catch (e) {
      vincoli = {};
    }
    var girone = strategia.dataset.girone;
    var primo = perId('first_round_policy');
    var dispari = perId('odd_number_policy');
    var anti = perId('anti_rematch_enabled');
    var sezioneAnti = perId('anti_rematch_section');
    var descrizione = perId('strategy_description');
    var sistema = perId('classification_system');

    function vincoliScelti() {
      return (vincoli[strategia.value] || {}).constraints || {};
    }

    function syncPrimo(c) {
      if (!primo) { return; }
      var ammesse = c.first_round_policies || ['random'];
      Array.prototype.forEach.call(primo.options, function (opzione) {
        if (!opzione.value) { return; }
        opzione.disabled = ammesse.indexOf(opzione.value) < 0;
      });
      if (ammesse.indexOf(primo.value) < 0) { cambia(primo, ammesse[0]); }
    }

    function syncDispari(c) {
      if (!dispari) { return; }
      var eGirone = strategia.value === girone;
      var perStrategia = c.odd_policies;
      var ammesse = DISPARI_PER_SISTEMA[sistema ? sistema.value : 'WINS'] || ['bye'];
      if (eGirone) {
        ammesse = perStrategia || ['bye'];
      } else if (perStrategia) {
        ammesse = ammesse.filter(function (p) { return perStrategia.indexOf(p) >= 0; });
      }
      Array.prototype.forEach.call(dispari.options, function (opzione) {
        if (!opzione.value) { return; }
        var valida = ammesse.indexOf(opzione.value) >= 0;
        opzione.disabled = !valida;
        opzione.hidden = !valida;
        // Nel girone il riposo ha un nome suo: non vale punti.
        if (opzione.dataset.labelGirone) {
          opzione.textContent = eGirone ? opzione.dataset.labelGirone : opzione.dataset.label;
        }
      });
      if (ammesse.length && ammesse.indexOf(dispari.value) < 0) {
        cambia(dispari, ammesse.indexOf('bye') >= 0 ? 'bye' : ammesse[0]);
      }
    }

    function syncAnti(c) {
      if (!anti) { return; }
      if (c.anti_rematch === false) {
        anti.checked = false;
        anti.disabled = true;
      } else {
        anti.disabled = false;
        if (c.anti_rematch_required) { anti.checked = true; }
      }
      /* Nel modale la casella non si mostra quando non e' una scelta: Amalfi
       * la impone, il girone non la usa. Resta nel modulo, accesa, e arriva
       * al server. Con `hidden`, non con `style.display`: quello e' di
       * `bracket_options.js`, e un nodo ha un padrone per meccanismo. */
      if (sezioneAnti && sezioneAnti.hasAttribute('data-nascondi-se-imposto')) {
        sezioneAnti.hidden = c.anti_rematch === false || !!c.anti_rematch_required;
      }
    }

    function sync() {
      var c = vincoliScelti();
      if (descrizione) {
        var scelta = strategia.options[strategia.selectedIndex];
        descrizione.textContent = (scelta && scelta.dataset.description) || '';
      }
      syncPrimo(c);
      syncDispari(c);
      syncAnti(c);
    }

    strategia.addEventListener('change', sync);
    if (sistema) {
      sistema.addEventListener('change', function () { syncDispari(vincoliScelti()); });
    }
    sync();
  }

  function avvia() {
    Array.prototype.forEach.call(
      document.querySelectorAll('select[data-strategia-gara]'),
      prepara
    );
  }

  // Per i test.
  window.c7StrategiaGara = { avvia: avvia };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', avvia);
  } else {
    avvia();
  }
})();
