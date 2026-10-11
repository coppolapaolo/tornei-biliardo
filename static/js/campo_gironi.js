/* I gironi del girone all'italiana nei moduli (ADR-076).
 *
 * Il blocco `components/_campo_gironi.html` esiste solo col girone
 * all'italiana: qui si decide soltanto cosa **mostrare**. Un campo nascosto
 * resta spento, quindi non arriva al server, e il parser non tocca ciò che
 * non riceve (`GaraFormParser._parse_gironi`).
 *
 * - Il blocco segue il menu della strategia (`data-strategia-da`), quando la
 *   strategia si sceglie nella stessa pagina.
 * - Nel modulo del campionato segue anche il menu del sistema
 *   (`data-piazzamenti-da`): solo un campionato a piazzamenti propone i
 *   gironi, chi somma i totali resta a girone unico (ADR-080).
 * - Composizione e compagni compaiono solo con un tetto di almeno 2 gironi.
 * - Così la fase finale (ADR-081): col girone unico la gara non ha fase
 *   finale. «Finali per piazzamento» compare solo con «Gironi: fino a 2»
 *   (`data-fase-se-due`): con un altro tetto la voce si nasconde e, se era
 *   scelta, si torna a «Nessuna». Limite e distanza della fase finale e le
 *   regole della sola finale compaiono col tabellone e con le finali;
 *   qualificati e finalina solo col tabellone; il valore solo con «Un limite
 *   diverso» o «Un'altra distanza». Ogni cambio avvisa la distanza
 *   (`window.updateDistancePreview`) e chi ascolta `gara:fase-finale`: con
 *   una fase finale «esattamente N» non si offre.
 *   `window.gironiConFaseFinale()` risponde se nel modulo è scelta una fase
 *   finale (tabellone o finali per piazzamento).
 * - Le voci di un menu che cambiano nome col girone (`data-label-girone`, per
 *   esempio «Escludi» nella gestione dei ritiri) seguono la stessa strategia:
 *   il menu porta `data-segue-strategia` col selettore della strategia.
 */
(function () {
  'use strict';

  function spegni(nodo, spento) {
    Array.prototype.forEach.call(
      nodo.querySelectorAll('input, select'),
      function (campo) { campo.disabled = spento; }
    );
  }

  /* Un campo delle regole del tabellone (limite di tempo o distanza, della
   * fase finale o della sola finale): il valore solo con la voce che lo
   * chiede («Un limite diverso», «Un'altra distanza»), e tutto spento quando
   * il campo non vale (`acceso` falso). */
  function syncTempo(contenitore, acceso) {
    if (!contenitore) { return; }
    var modo = contenitore.querySelector('[data-fase-regola-modo]');
    var campo = contenitore.querySelector('[data-fase-regola-campo]');
    if (modo) { modo.disabled = !acceso; }
    if (campo) {
      var minuti = acceso && modo && modo.selectedOptions[0]
        && modo.selectedOptions[0].hasAttribute('data-fase-regola-valore');
      campo.hidden = !minuti;
      spegni(campo, !minuti);
    }
  }

  function preparaBlocco(blocco) {
    var tetto = blocco.querySelector('[data-gironi-tetto]');
    var sePiu = blocco.querySelector('[data-gironi-se-piu]');
    var strategia = blocco.dataset.strategiaDa
      ? document.querySelector(blocco.dataset.strategiaDa)
      : null;
    var sistema = blocco.dataset.piazzamentiDa
      ? document.querySelector(blocco.dataset.piazzamentiDa)
      : null;

    var fase = blocco.querySelector('[data-fase-finale]');
    var seFinale = blocco.querySelector('[data-fase-se-finale]');
    var seTabellone = blocco.querySelector('[data-fase-se-tabellone]');
    var regole = blocco.querySelectorAll('[data-fase-regola]');

    function selezionate() {
      Array.prototype.forEach.call(
        fase.querySelectorAll('.c7-choice input[type="radio"]'),
        function (r) { r.closest('.c7-choice').classList.toggle('is-selected', r.checked); }
      );
    }

    function syncFase(acceso, dueGironi) {
      if (!fase) { return; }
      var tabellone = fase.querySelector('[data-fase-tabellone]');
      var piazzamento = fase.querySelector('[data-fase-piazzamento]');
      var vocePiazzamento = fase.querySelector('[data-fase-se-due]');
      /* Le finali per piazzamento, solo con «Gironi: fino a 2». */
      if (piazzamento) {
        if (vocePiazzamento) { vocePiazzamento.hidden = !dueGironi; }
        if (!dueGironi && piazzamento.checked) {
          var nessuna = fase.querySelector('[data-fase-nessuna]');
          if (nessuna) { nessuna.checked = true; }
          selezionate();
        }
        piazzamento.disabled = !acceso || !dueGironi;
      }
      var conTabellone = !!(acceso && tabellone && tabellone.checked);
      var conFinali = !!(acceso && dueGironi && piazzamento && piazzamento.checked);
      var conFase = conTabellone || conFinali;
      if (seFinale) { seFinale.hidden = !conFase; }
      if (seTabellone) {
        seTabellone.hidden = !conTabellone;
        spegni(seTabellone, !conTabellone);
      }
      Array.prototype.forEach.call(
        blocco.querySelectorAll('[data-fase-solo-tabellone]'),
        function (n) { n.hidden = !conTabellone; }
      );
      Array.prototype.forEach.call(
        blocco.querySelectorAll('[data-fase-solo-piazzamento]'),
        function (n) { n.hidden = !conFinali; }
      );
      Array.prototype.forEach.call(regole, function (r) { syncTempo(r, conFase); });
      if (typeof window.updateDistancePreview === 'function') {
        window.updateDistancePreview();
      }
      document.dispatchEvent(new CustomEvent('gara:fase-finale', {
        detail: { tabellone: conTabellone, piazzamento: conFinali, faseFinale: conFase }
      }));
    }

    function sync() {
      var visibile = strategia
        ? strategia.value === blocco.dataset.girone
        : !blocco.hidden;
      if (sistema && sistema.value !== 'POSITION') { visibile = false; }
      blocco.hidden = !visibile;
      if (tetto) { tetto.disabled = !visibile; }
      var piu = visibile && tetto && parseInt(tetto.value, 10) > 1;
      if (sePiu) {
        sePiu.hidden = !piu;
        spegni(sePiu, !piu);
      }
      syncFase(!!piu, !!(piu && parseInt(tetto.value, 10) === 2));
    }

    /* Le card di «Composizione dei gironi»: la spunta segue la scelta. */
    Array.prototype.forEach.call(
      blocco.querySelectorAll('.c7-choice input[type="radio"]'),
      function (radio) {
        radio.addEventListener('change', function () {
          Array.prototype.forEach.call(
            blocco.querySelectorAll('input[name="' + radio.name + '"]'),
            function (r) { r.closest('.c7-choice').classList.toggle('is-selected', r.checked); }
          );
        });
      }
    );

    if (strategia) { strategia.addEventListener('change', sync); }
    if (sistema) { sistema.addEventListener('change', sync); }
    if (tetto) { tetto.addEventListener('change', sync); }
    if (fase) {
      Array.prototype.forEach.call(
        fase.querySelectorAll('input[type="radio"]'),
        function (radio) { radio.addEventListener('change', sync); }
      );
    }
    Array.prototype.forEach.call(
      blocco.querySelectorAll('[data-fase-regola-modo]'),
      function (modo) { modo.addEventListener('change', sync); }
    );
    sync();
  }

  /* Nel modulo è scelta una fase finale dopo i gironi — il tabellone o le
   * finali per piazzamento? In entrambe si gioca «al N». Un blocco nascosto
   * ha i campi spenti, quindi conta solo quello visibile. */
  window.gironiConFaseFinale = function () {
    return !!document.querySelector(
      '[data-gironi]:not([hidden]) [data-fase-al-n]:checked:not(:disabled)'
    );
  };

  function preparaEtichette(menu) {
    var strategia = document.querySelector(menu.dataset.segueStrategia);
    if (!strategia) { return; }
    var girone = menu.dataset.girone;

    function sync() {
      var eGirone = strategia.value === girone;
      Array.prototype.forEach.call(
        menu.querySelectorAll('option[data-label-girone]'),
        function (option) {
          option.textContent = eGirone ? option.dataset.labelGirone : option.dataset.label;
        }
      );
    }

    strategia.addEventListener('change', sync);
    sync();
  }

  document.addEventListener('DOMContentLoaded', function () {
    Array.prototype.forEach.call(document.querySelectorAll('[data-gironi]'), preparaBlocco);
    /* Le regole del tabellone fuori dal blocco dei gironi: la pagina della
     * gara avviata, dove il tabellone è già deciso. */
    Array.prototype.forEach.call(
      document.querySelectorAll('[data-fase-regola]'),
      function (contenitore) {
        if (contenitore.closest('[data-gironi]')) { return; }
        var modo = contenitore.querySelector('[data-fase-regola-modo]');
        if (modo) {
          modo.addEventListener('change', function () { syncTempo(contenitore, true); });
        }
        syncTempo(contenitore, true);
      }
    );
    Array.prototype.forEach.call(
      document.querySelectorAll('select[data-segue-strategia]'),
      preparaEtichette
    );
  });
})();
