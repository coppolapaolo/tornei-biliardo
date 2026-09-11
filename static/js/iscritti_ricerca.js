/* static/js/iscritti_ricerca.js — filtra la tendina «chi iscrivere».
 *
 * Il direttore che aggiunge un iscritto spesso conosce la persona per nome e
 * cognome, non per username: la stringa cercata deve pescare in tutti e tre i
 * campi. Il filtro vive qui e non in una query perché `first_name`/`last_name`
 * sono cifrati in modo non deterministico — in chiaro esistono solo nella
 * pagina già resa, dove peraltro l'elenco completo c'è già tutto.
 *
 * Il componente degli iscritti è incluso **due volte** (mobile e desktop):
 * niente `id`, niente `getElementById`. Un solo ascoltatore delegato sul
 * documento serve entrambe le copie, e ogni copia lavora sulla propria
 * tendina risalendo con `closest`.
 *
 * Senza JavaScript resta la tendina completa di prima: il campo di ricerca è
 * un miglioramento, non un prerequisito.
 */
(function () {
  "use strict";

  /** Minuscolo e senza accenti: «Nicolò» si trova digitando «nicolo». */
  function normalizza(testo) {
    return (testo || "")
      .toLowerCase()
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "");
  }

  /* Le `option` si conservano al primo filtro e si ricostruiscono ogni volta.
     Nasconderle con `hidden` sarebbe più corto, ma su Safari le option
     nascoste restano visibili: la tendina mostrerebbe risultati che il campo
     dice di aver escluso. */
  function opzioniOriginali(tendina) {
    if (!tendina._opzioniIscritti) {
      tendina._opzioniIscritti = Array.prototype.slice.call(tendina.options);
    }
    return tendina._opzioniIscritti;
  }

  function filtra(campo) {
    var contenitore = campo.closest("form");
    if (!contenitore) return;
    var tendina = contenitore.querySelector('select[name="user_id"]');
    if (!tendina) return;

    var cercato = normalizza(campo.value).trim();
    var opzioni = opzioniOriginali(tendina);
    var selezionato = tendina.value;

    var superstiti = opzioni.filter(function (opzione) {
      // Il segnaposto («Seleziona giocatore…») non ha valore e resta sempre.
      if (!opzione.value) return true;
      if (!cercato) return true;
      return normalizza(opzione.dataset.cerca || opzione.text).indexOf(cercato) !== -1;
    });

    tendina.replaceChildren.apply(tendina, superstiti);

    var giocatori = superstiti.filter(function (opzione) {
      return opzione.value;
    });

    // Un solo superstite: è quello che si voleva. Preselezionarlo risparmia il
    // passaggio dalla tendina, che è il gesto che si stava cercando di evitare.
    if (giocatori.length === 1) {
      tendina.value = giocatori[0].value;
    } else if (
      giocatori.some(function (opzione) {
        return opzione.value === selezionato;
      })
    ) {
      tendina.value = selezionato;
    } else {
      tendina.value = "";
    }

    var stato = contenitore.querySelector(".js-iscritti-esito");
    if (stato) {
      stato.textContent = cercato ? stato.dataset.formato.replace("{n}", giocatori.length) : "";
    }
  }

  document.addEventListener("input", function (evento) {
    var campo = evento.target.closest && evento.target.closest(".js-iscritti-cerca");
    if (campo) filtra(campo);
  });

  // Invio nel campo di ricerca: si cerca, non si manda il form a metà.
  document.addEventListener("keydown", function (evento) {
    var campo = evento.target.closest && evento.target.closest(".js-iscritti-cerca");
    if (campo && evento.key === "Enter") evento.preventDefault();
  });
})();
