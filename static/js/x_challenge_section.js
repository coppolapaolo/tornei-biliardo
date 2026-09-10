/* La domanda «quale esercizio si gioca al posto della X» (issue #267).
 *
 * Esiste solo con la politica `bye_with_challenge`: altrove e' una domanda
 * senza oggetto, e il parser non legge nemmeno il campo
 * (`GaraFormParser._parse_x_challenge`).
 *
 * PERCHE' STA QUI e non in due `<script>` inline, com'era fino al 2026-09-04.
 * La regola era copiata nel modulo di modifica e nel modal di creazione, e in
 * nessuna delle due copie il `required` seguiva la visibilita'. Ne uscivano due
 * guasti, entrambi visti in produzione:
 *
 * 1. **Salva non faceva niente, in silenzio.** Un controllo `required` e vuoto
 *    dentro un contenitore `display:none` rende il modulo invalido, ma il
 *    browser non puo' mostrare il messaggio accanto a un elemento che non puo'
 *    ricevere il focus: blocca l'invio e basta. Con qualunque politica diversa
 *    da «X con esercizio» — cioe' quasi sempre — nessuna gara si poteva ne'
 *    creare dal modal ne' modificare.
 * 2. **La sezione riappariva da sola.** `bracket_options.js` nasconde e mostra
 *    ogni `[data-bracket-hide]` scrivendo `node.style.display`, e la sezione
 *    portava quell'attributo: al primo `sync()` con una strategia a girone
 *    rimetteva `display: ''`, cancellando il `display:none` deciso dalla
 *    politica. Il campo tornava visibile anche con «X vinta a tavolino».
 *
 * Da qui la regola del file: **un nodo, un padrone**. La sezione non e' piu'
 * `data-bracket-hide`; a decidere se mostrarla e se il suo campo e'
 * obbligatorio e' solo questo file, che tiene conto anche del formato a
 * tabellone — dove la politica dei dispari non viene proprio letta, perche' i
 * bye sono strutturali (`_bracket_derived_fields`).
 *
 * Il formato non lo deduce da un elenco di strategie scritto qui: lo ascolta
 * da `bracket_options.js`, che e' l'unico a saperlo. Nelle pagine senza quel
 * file l'evento non arriva mai e il formato resta «non a tabellone», che e' il
 * caso giusto per il modal dentro un campionato.
 *
 * Aggancio nel template: sul contenitore
 *
 *     data-x-challenge-section="<id del select della politica>"
 *
 * cosi' lo stesso file serve i due moduli, che hanno id diversi.
 */
(function () {
  'use strict';

  var aTabellone = false;

  function sezioni() {
    return document.querySelectorAll('[data-x-challenge-section]');
  }

  function aggiornaUna(sezione) {
    var policy = document.getElementById(sezione.dataset.xChallengeSection);
    if (!policy) { return; }

    var attiva = policy.value === 'bye_with_challenge' && !aTabellone;
    sezione.style.display = attiva ? '' : 'none';

    /* L'obbligo vive con la visibilita': su un campo nascosto bloccherebbe
     * l'invio senza poter dire dove. Quando la sezione si vede, invece, il
     * fumetto del browser compare accanto al campo — ed e' comunque la
     * seconda difesa: la prima e' il server, che rifiuta la gara senza
     * esercizio con un messaggio scritto per il direttore. */
    Array.prototype.forEach.call(
      sezione.querySelectorAll('select, input'),
      function (campo) { campo.required = attiva; }
    );
  }

  function aggiorna() {
    Array.prototype.forEach.call(sezioni(), aggiornaUna);
  }

  document.addEventListener('gara:formato', function (e) {
    aTabellone = !!(e.detail && e.detail.isBracket);
    aggiorna();
  });

  document.addEventListener('DOMContentLoaded', function () {
    Array.prototype.forEach.call(sezioni(), function (sezione) {
      var policy = document.getElementById(sezione.dataset.xChallengeSection);
      if (policy) { policy.addEventListener('change', aggiorna); }
    });
    aggiorna();
  });
})();
