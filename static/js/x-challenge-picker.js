/* Ricarica l'elenco degli esercizi offribili per la X (issue #267).
 *
 * Perché serve. Il direttore che non trova l'esercizio giusto lo crea nel
 * builder, che si apre in un'altra scheda. Al ritorno, senza questo, l'unico
 * modo di vedere il nuovo esercizio nell'elenco sarebbe ricaricare la pagina —
 * cioè perdere tutto quello che ha già compilato nel modulo della gara. Il
 * ricaricamento mirato è ciò che rende la creazione «dentro la procedura»
 * invece che una deviazione da cui si torna indietro a mani vuote.
 *
 * La selezione corrente si conserva: se l'esercizio scelto c'è ancora dopo il
 * ricaricamento, resta selezionato.
 */
(function () {
  'use strict';

  function elencoUrl(bottone) {
    // L'indirizzo lo mette il template (url_for), non questo file: un percorso
    // scritto a mano qui sopravviverebbe a una rinomina della route senza che
    // nessuno se ne accorga.
    return bottone.dataset.url;
  }

  window.ricaricaEserciziX = function (bottone) {
    var select = document.getElementById(bottone.dataset.target);
    if (!select) return;

    var testoOriginale = bottone.textContent;
    bottone.disabled = true;

    fetch(elencoUrl(bottone), { credentials: 'same-origin' })
      .then(function (r) { return r.json(); })
      .then(function (dati) {
        if (!dati || !dati.success) return;

        var scelto = select.value;
        // La prima opzione è «scelto dall'applicazione» e non arriva dal
        // server: si conserva invece di ricrearla, così il suo testo resta
        // quello tradotto dal template.
        var primaOpzione = select.options[0];
        // Svuotamento per rimozione e non con `innerHTML = ''`: il risultato è
        // identico, ma non lascia in giro una riga che ogni revisione di
        // sicurezza dovrà riesaminare per concludere che era innocua.
        while (select.firstChild) select.removeChild(select.firstChild);
        if (primaOpzione) select.appendChild(primaOpzione);

        dati.challenges.forEach(function (c) {
          var opt = document.createElement('option');
          opt.value = c.id;
          opt.textContent = c.name;
          select.appendChild(opt);
        });

        select.value = scelto;
        if (select.value !== scelto) select.selectedIndex = 0;
      })
      .finally(function () {
        bottone.disabled = false;
        bottone.textContent = testoOriginale;
      });
  };
})();
