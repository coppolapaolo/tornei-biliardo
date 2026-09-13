/* static/js/iscritti_ricerca.js — la ricerca di chi iscrivere.
 *
 * Il direttore che aggiunge un iscritto spesso conosce la persona per nome e
 * cognome, non per username: la stringa cercata deve pescare in tutti e tre i
 * campi. Il filtro vive qui e non in una query perché `first_name`/`last_name`
 * sono cifrati in modo non deterministico — in chiaro esistono solo nella
 * pagina già resa, dove peraltro l'elenco completo c'è già tutto.
 *
 * Dal 2026-09-13 (canvas «Pagina gara del direttore», 2.2 e 2.3) i candidati
 * non stanno in una tendina ma in righe con «Iscrivi», dentro un contenitore
 * `[data-iscrivibili]`: le righe restano nascoste finché non si scrive, e
 * compaiono quelle che corrispondono, con il conteggio sotto al campo. Si
 * lavora per contenitore, risalendo con `closest`, così più copie del
 * componente nella stessa pagina non si disturbano; niente `id`.
 *
 * Senza JavaScript le righe restano tutte visibili: il campo di ricerca è un
 * miglioramento, non un prerequisito.
 */
(function () {
  "use strict";

  /** Minuscolo e senza accenti: «Nicolò» si trova digitando «nicolo». */
  function normalizza(testo) {
    return (testo || "")
      .toLowerCase()
      .normalize("NFD")
      .replace(/[̀-ͯ]/g, "");
  }

  function righe(contenitore) {
    return Array.prototype.slice.call(contenitore.querySelectorAll(".js-iscrivibile"));
  }

  function filtra(campo) {
    var contenitore = campo.closest("[data-iscrivibili]");
    if (!contenitore) return;

    var cercato = normalizza(campo.value).trim();
    var massimo = parseInt(contenitore.dataset.massimo || "8", 10);
    var trovati = 0;

    righe(contenitore).forEach(function (riga) {
      var chiave = normalizza(riga.dataset.cerca || riga.textContent);
      var corrisponde = cercato !== "" && chiave.indexOf(cercato) !== -1;
      if (corrisponde) trovati += 1;
      // Le prime `massimo` corrispondenze: una lista di trenta righe sotto il
      // campo non aiuta nessuno, e il conteggio dice quante ce ne sono.
      riga.hidden = !corrisponde || trovati > massimo;
    });

    var stato = contenitore.querySelector(".js-iscritti-esito");
    if (stato) {
      stato.textContent = cercato ? stato.dataset.formato.replace("{n}", trovati) : "";
    }
    var vuoto = contenitore.querySelector(".js-iscritti-nessuno");
    if (vuoto) {
      vuoto.hidden = !(cercato && trovati === 0);
    }
  }

  // All'apertura le righe sono nascoste: si scrive, e compaiono. Con lo
  // script spento restano visibili, quindi il nascondere lo fa lo script.
  function nascondiTutte() {
    Array.prototype.forEach.call(document.querySelectorAll("[data-iscrivibili]"), function (contenitore) {
      righe(contenitore).forEach(function (riga) { riga.hidden = true; });
    });
  }
  // Subito, per i contenitori gia' nel DOM, e di nuovo a documento pronto
  // per quelli che lo script precede: nascondere due volte non costa niente.
  nascondiTutte();
  document.addEventListener("DOMContentLoaded", nascondiTutte);

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
