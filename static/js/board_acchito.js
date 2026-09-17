/**
 * Le due domande dell'acchito sul tabellone orizzontale (ADR-056).
 *
 * «Regole generali pool» 1.2: chi vince l'acchito **sceglie chi** esegue il
 * tiro di apertura, e può scegliere l'avversario. Quindi due domande — chi ha
 * vinto? chi apre? — e due risposte indipendenti.
 *
 * Si risponde **toccando i nomi**, tutte e due le volte: il primo tocco dice
 * chi ha vinto e cambia la domanda, il secondo dice chi apre e invia. Fino al
 * 17/09/2026 il secondo tocco spostava solo l'apertura e per proseguire
 * serviva «Comincia», nella fascia in basso: era l'unico stato del tabellone
 * in cui il bersaglio non era la mezza schermata, e in gara ha voluto dire
 * «ho segnato chi ha vinto e non andava avanti». Il caso comune — apre chi ha
 * vinto — costa gli stessi due tocchi di prima, sullo stesso nome.
 *
 * Nella fascia resta «Ricomincia», per chi ha sbagliato il primo tocco: è un
 * rimedio, non la strada, quindi se non si vede non blocca nessuno.
 *
 * L'invio lo fa la pagina ospite (`invia(vinto, apre, lato)`): l'indirizzo di
 * una gara e quello di una sfida sono due. Spegne il lato toccato finché la
 * risposta non arriva (`withLoading`), ed è da lì che qui si capisce che un
 * invio è in corso: a lato spento i tocchi non contano, a lato riacceso —
 * cioè a invio fallito — si riprova.
 */
(function (root) {
  'use strict';

  function avvia(lag, invia) {
    var vinto = null;
    var apre = null;
    var lati = Array.prototype.slice.call(lag.querySelectorAll('[data-lag-player]'));
    var titolo = lag.querySelector('[data-lag-title]');
    var nota = lag.querySelector('[data-lag-note]');
    var ricomincia = lag.querySelector('[data-lag-reset]');

    function idDi(lato) {
      return Number(lato.getAttribute('data-lag-player'));
    }

    function inCorso() {
      return lati.some(function (lato) { return lato.disabled; });
    }

    function disegna() {
      var seconda = vinto !== null;
      if (titolo) titolo.textContent = lag.getAttribute(seconda ? 'data-domanda-due' : 'data-domanda-uno');
      if (nota) nota.textContent = lag.getAttribute(seconda ? 'data-nota-due' : 'data-nota-uno');
      if (ricomincia) ricomincia.disabled = !seconda;
      lati.forEach(function (lato) {
        var id = idDi(lato);
        var pill = lato.querySelector('.c7-board__lagq-pill');
        var mostra = (id === vinto) || (id === apre);
        if (pill) {
          pill.hidden = !mostra;
          if (mostra) {
            pill.textContent = lag.getAttribute(
              (id === vinto && id === apre) ? 'data-et-entrambi'
                : (id === vinto ? 'data-et-acchito' : 'data-et-apre'));
          }
          pill.classList.toggle('is-breaking', id === apre);
        }
        lato.classList.toggle('c7-board__half--breaks', id === apre);
      });
    }

    lati.forEach(function (lato) {
      lato.addEventListener('click', function () {
        if (inCorso()) { return; }
        var id = idDi(lato);
        if (vinto === null) {
          vinto = id;
          disegna();
          return;
        }
        apre = id;
        disegna();
        if (typeof invia === 'function') { invia(vinto, apre, lato); }
      });
    });

    if (ricomincia) {
      ricomincia.addEventListener('click', function () {
        if (inCorso()) { return; }
        vinto = null;
        apre = null;
        disegna();
      });
    }

    disegna();
  }

  root.c7BoardAcchito = { avvia: avvia };
})(window);
