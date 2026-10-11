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

  function preparaBlocco(blocco) {
    var tetto = blocco.querySelector('[data-gironi-tetto]');
    var sePiu = blocco.querySelector('[data-gironi-se-piu]');
    var strategia = blocco.dataset.strategiaDa
      ? document.querySelector(blocco.dataset.strategiaDa)
      : null;
    var sistema = blocco.dataset.piazzamentiDa
      ? document.querySelector(blocco.dataset.piazzamentiDa)
      : null;

    function sync() {
      var visibile = strategia
        ? strategia.value === blocco.dataset.girone
        : !blocco.hidden;
      if (sistema && sistema.value !== 'POSITION') { visibile = false; }
      blocco.hidden = !visibile;
      if (tetto) { tetto.disabled = !visibile; }
      if (sePiu) {
        var piu = visibile && tetto && parseInt(tetto.value, 10) > 1;
        sePiu.hidden = !piu;
        spegni(sePiu, !piu);
      }
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
    sync();
  }

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
    Array.prototype.forEach.call(
      document.querySelectorAll('select[data-segue-strategia]'),
      preparaEtichette
    );
  });
})();
