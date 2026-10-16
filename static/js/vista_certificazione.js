/*
 * La vista di certificazione scelta da chi guarda (ADR-083, UC6).
 *
 * Tre viste cumulative — Tornei, Confermate, Tutte — decidono quali partite
 * entrano nei numeri del profilo: ELO, vittorie, sconfitte, pareggi, TPA,
 * runout, partite recenti. Il server rende i numeri di tutte e tre in blocchi
 * `[data-vista]`; qui si sceglie quale si vede, senza ricaricare.
 *
 * La vista sta su `<html data-vista-attiva="…">`, e il CSS (theme-7c.css,
 * «Viste di certificazione») nasconde i blocchi delle altre. Questo file si
 * carica **nel head**, in modo sincrono: l'attributo c'è prima che il corpo
 * esista, e chi ha scelto Tornei non vede lampeggiare Confermate.
 *
 * La scelta la ricorda il browser (`localStorage`), la stessa su ogni pagina
 * che mostra numeri per vista: profilo proprio, profilo altrui. Ogni accesso
 * allo storage è in try/catch: in navigazione privata, o con i dati del sito
 * bloccati, il selettore funziona lo stesso e semplicemente non ricorda.
 *
 * Sostituisce `window.EloToggle`, che alternava due pool ELO cliccando sul
 * numero e salvava la scelta sotto `eloMode`: la chiave vecchia si migra alla
 * prima lettura, così non restano due meccanismi né due preferenze.
 */
(function () {
  'use strict';

  var CHIAVE = 'vistaCertificazione';
  var CHIAVE_VECCHIA = 'eloMode';
  var VISTE = ['tornei', 'confermate', 'tutte'];
  var PREDEFINITA = 'confermate';
  // Il toggle a due stati mostrava il competitivo (solo tornei) o il globale
  // (tornei + sfide confermate): sono le viste Tornei e Confermate.
  var DAL_TOGGLE_ELO = { competitive: 'tornei', global: 'confermate' };

  function valida(vista) {
    return VISTE.indexOf(vista) !== -1;
  }

  /* La vista ricordata, o la predefinita. Migra la chiave del vecchio toggle. */
  function ricordata() {
    try {
      var vista = window.localStorage.getItem(CHIAVE);
      if (valida(vista)) return vista;
      var vecchia = window.localStorage.getItem(CHIAVE_VECCHIA);
      if (vecchia !== null) {
        window.localStorage.removeItem(CHIAVE_VECCHIA);
        var migrata = DAL_TOGGLE_ELO[vecchia];
        if (migrata) {
          window.localStorage.setItem(CHIAVE, migrata);
          return migrata;
        }
      }
    } catch (e) { /* storage negato: si parte dalla predefinita */ }
    return PREDEFINITA;
  }

  function ricorda(vista) {
    try {
      window.localStorage.setItem(CHIAVE, vista);
    } catch (e) { /* storage negato: la scelta vale per questa pagina */ }
  }

  function attiva() {
    var vista = document.documentElement.getAttribute('data-vista-attiva');
    return valida(vista) ? vista : PREDEFINITA;
  }

  /* Mostra `vista`: attributo su <html>, e stato dei pulsanti del selettore. */
  function applica(vista) {
    if (!valida(vista)) vista = PREDEFINITA;
    document.documentElement.setAttribute('data-vista-attiva', vista);
    var pulsanti = document.querySelectorAll('[data-vista-scelta]');
    Array.prototype.forEach.call(pulsanti, function (pulsante) {
      var acceso = pulsante.getAttribute('data-vista-scelta') === vista;
      pulsante.classList.toggle('is-on', acceso);
      pulsante.setAttribute('aria-pressed', acceso ? 'true' : 'false');
    });
  }

  function scegli(vista) {
    if (!valida(vista)) return;
    ricorda(vista);
    applica(vista);
  }

  window.c7VistaCertificazione = {
    CHIAVE: CHIAVE,
    PREDEFINITA: PREDEFINITA,
    ricordata: ricordata,
    attiva: attiva,
    applica: applica,
    scegli: scegli,
    // Per i test e per chi aggiunge un selettore dopo il caricamento.
    avvia: function () { applica(attiva()); }
  };

  applica(ricordata());

  document.addEventListener('click', function (ev) {
    var pulsante = ev.target && ev.target.closest && ev.target.closest('[data-vista-scelta]');
    if (!pulsante) return;
    ev.preventDefault();
    scegli(pulsante.getAttribute('data-vista-scelta'));
  });

  // Nel head i pulsanti non esistono ancora: il loro stato si allinea quando
  // il corpo è pronto. L'attributo su <html> c'è già, e col CSS basta.
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', window.c7VistaCertificazione.avvia);
  } else {
    window.c7VistaCertificazione.avvia();
  }
})();
