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
    proponiCreazione(contenitore, campo.value, trovati);
  }

  // ── Crea dalla ricerca (ADR-085, emendamento del 2026-10-19) ──────────
  //
  // Chi non ha un account non si trova: il testo cercato diventa la
  // proposta «Crea «Mario Rossi» come non registrato e iscrivilo». Prima
  // parola il nome, il resto il cognome — come si dice un nome a voce —, e
  // i due campi restano modificabili. Toccati a mano, la ricerca non li
  // riscrive più finché non la si svuota.

  /** «mario de luca» → «Mario De Luca»: la maiuscola che si scrive a mano. */
  function maiuscole(testo) {
    return testo.replace(/(^|[\s'-])(\S)/g, function (_t, prima, lettera) {
      return prima + lettera.toUpperCase();
    });
  }

  function aggiornaPulsante(modulo) {
    var invia = modulo.querySelector(".js-iscritti-crea-invia");
    var testo = modulo.querySelector(".js-iscritti-crea-testo");
    if (!invia || !testo) return;
    if (!invia.dataset.iniziale) invia.dataset.iniziale = testo.textContent;
    var nome = [
      modulo.querySelector(".js-iscritti-crea-nome").value,
      modulo.querySelector(".js-iscritti-crea-cognome").value,
    ].join(" ").replace(/\s+/g, " ").trim();
    testo.textContent = nome
      ? invia.dataset.formato.replace("{nome}", nome)
      : invia.dataset.iniziale;
  }

  function proponiCreazione(contenitore, scritto, trovati) {
    var modulo = contenitore.querySelector(".js-iscritti-crea");
    if (!modulo) return;
    var parole = (scritto || "").trim().split(/\s+/).filter(Boolean);
    var nome = modulo.querySelector(".js-iscritti-crea-nome");
    var cognome = modulo.querySelector(".js-iscritti-crea-cognome");

    modulo.hidden = parole.length === 0;
    if (parole.length === 0) {
      delete modulo.dataset.toccato;
      nome.value = "";
      cognome.value = "";
    } else if (!modulo.dataset.toccato) {
      nome.value = maiuscole(parole[0]);
      cognome.value = maiuscole(parole.slice(1).join(" "));
    }
    // Con dei risultati il gesto principale resta «Iscrivi» sulla riga: la
    // creazione passa in secondo piano. Senza, è lei la proposta.
    var invia = modulo.querySelector(".js-iscritti-crea-invia");
    if (invia) {
      invia.classList.toggle("btn-primary", trovati === 0);
      invia.classList.toggle("btn-secondary", trovati > 0);
    }
    aggiornaPulsante(modulo);
  }

  document.addEventListener("input", function (evento) {
    var modulo = evento.target.closest && evento.target.closest(".js-iscritti-crea");
    if (!modulo) return;
    modulo.dataset.toccato = "1";
    aggiornaPulsante(modulo);
  });

  // All'apertura le righe sono nascoste: si scrive, e compaiono. Con lo
  // script spento restano visibili, quindi il nascondere lo fa lo script.
  function nascondiTutte() {
    Array.prototype.forEach.call(document.querySelectorAll("[data-iscrivibili]"), function (contenitore) {
      righe(contenitore).forEach(function (riga) { riga.hidden = true; });
      // Anche la proposta di creare: compare quando si scrive un nome.
      var campo = contenitore.querySelector(".js-iscritti-cerca");
      if (campo) proponiCreazione(contenitore, campo.value, 0);
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
