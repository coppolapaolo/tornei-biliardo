/* Il conto alla rovescia del limite di tempo (ADR-077).
 *
 * Il server scrive sull'elemento quando e' partito (`data-timer-inizio`, ISO
 * in UTC), quanti minuti ci sono (`data-timer-minuti`) e che ore erano per
 * lui quando ha disegnato la pagina (`data-timer-adesso`). La differenza fra
 * quest'ultimo e l'orologio del dispositivo corregge un telefono che va
 * avanti o indietro: segnapunti, card del direttore e schermo sala mostrano
 * lo stesso numero senza chiedere niente a nessuno.
 *
 * Solo visivo: allo scadere l'elemento prende `is-scaduto` (e la card che lo
 * contiene `c7-card--warn`), e il testo diventa «Tempo scaduto +2'». Non
 * succede nient'altro: e' il direttore che decide se interrompere.
 */
(function () {
  'use strict';

  function due(n) { return n < 10 ? '0' + n : String(n); }

  function testo(restanti, etichettaScaduto) {
    if (restanti > 0) {
      var s = Math.ceil(restanti / 1000);
      return Math.floor(s / 60) + ':' + due(s % 60);
    }
    var oltre = Math.floor(-restanti / 60000);
    return etichettaScaduto + (oltre > 0 ? " +" + oltre + "'" : '');
  }

  function aggiorna(el, adesso) {
    var inizio = Date.parse(el.getAttribute('data-timer-inizio'));
    var minuti = parseInt(el.getAttribute('data-timer-minuti'), 10);
    if (isNaN(inizio) || isNaN(minuti)) return;
    var restanti = inizio + minuti * 60000 - adesso;
    var scritta = el.querySelector('[data-timer-testo]');
    if (scritta) scritta.textContent = testo(restanti, el.getAttribute('data-et-scaduto') || '');
    var scaduto = restanti <= 0;
    el.classList.toggle('is-scaduto', scaduto);
    var card = el.closest('[data-timer-card]');
    if (card && scaduto) card.classList.add('c7-card--warn');
  }

  function avvia() {
    var timer = Array.prototype.slice.call(document.querySelectorAll('[data-timer-inizio]'));
    if (!timer.length) return;
    // Lo scarto fra l'orologio del server e quello del dispositivo, misurato
    // una volta sola al caricamento.
    var scarto = 0;
    var server = Date.parse(timer[0].getAttribute('data-timer-adesso') || '');
    if (!isNaN(server)) scarto = server - Date.now();
    function giro() {
      var adesso = Date.now() + scarto;
      timer.forEach(function (el) { aggiorna(el, adesso); });
    }
    giro();
    setInterval(giro, 1000);
  }

  window.c7ContoAllaRovescia = { testo: testo, aggiorna: aggiorna };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', avvia);
  } else {
    avvia();
  }
})();
