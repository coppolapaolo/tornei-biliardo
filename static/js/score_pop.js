/**
 * score_pop.js — la cifra del punteggio che cambia si vede cambiare.
 *
 * Il numero grande di una partita cambia sotto gli occhi di chi guarda: al
 * tocco di chi segna, e sull'altro telefono all'arrivo dell'evento live. Un
 * 3 che diventa 4 senza nessun movimento si perde; con la scala del
 * movimento (tokens-7c.css) la cifra nuova sale da sotto e si accende in
 * `--c7-dur-base`. Tutto qui: `.is-pop` sull'elemento, l'animazione la fa il
 * CSS (`c7-pop` in theme-7c.css).
 *
 * Due strade portano una cifra nuova sullo schermo:
 *
 * 1. il tabellone orizzontale la riscrive in JavaScript (`c7Board.aggiorna`):
 *    chiama `segna(elemento, valore)`, che mette il testo e fa partire
 *    l'animazione solo se il valore è cambiato — e la fa ripartire anche la
 *    seconda volta, con il riflusso fra togliere e rimettere la classe;
 * 2. la card verticale cambia con un ricaricamento della pagina, e dopo un
 *    ricaricamento il DOM è nuovo: nessuno sa cosa c'era prima. Allora si
 *    salva in `sessionStorage`, a `pagehide`, quello che le cifre dicevano;
 *    al caricamento successivo della **stessa** pagina, entro pochi secondi,
 *    le cifre diverse da allora ricevono `.is-pop`. Una pagina diversa, o
 *    una ricarica di un minuto dopo, non fanno niente: sarebbe un movimento
 *    che non spiega nessun cambiamento.
 *
 * Presidio: tests/frontend/test_score_pop.cjs (jsdom).
 */
(function () {
    'use strict';

    var CHIAVE = 'c7-score-prima';
    var SELETTORE = '.c7-score__num';
    var FINESTRA_MS = 15000;

    /**
     * Scrive `valore` nella cifra e la fa saltare, solo se è cambiato.
     * @returns {boolean} true se la cifra è cambiata
     */
    function segna(el, valore) {
        var nuovo = String(valore);
        if (el.textContent.trim() === nuovo) {
            return false;
        }
        el.classList.remove('is-pop');
        // Il riflusso fra togliere e rimettere la classe: senza, la seconda
        // cifra della stessa partita non si anima.
        void el.offsetWidth;
        el.textContent = nuovo;
        el.classList.add('is-pop');
        return true;
    }

    /** Cosa dicono le cifre adesso, per confrontarle dopo il ricaricamento. */
    function salva() {
        var cifre = document.querySelectorAll(SELETTORE);
        if (!cifre.length) {
            return;
        }
        try {
            sessionStorage.setItem(CHIAVE, JSON.stringify({
                pagina: location.pathname,
                quando: Date.now(),
                valori: Array.prototype.map.call(cifre, function (c) {
                    return c.textContent.trim();
                })
            }));
        } catch (e) {
            // sessionStorage negato (navigazione privata stretta): nessun salto.
        }
    }

    /**
     * Dopo un ricaricamento: le cifre diverse da prima saltano.
     * @returns {number} quante cifre sono saltate
     */
    function ripristina() {
        var grezzo = null;
        try {
            grezzo = sessionStorage.getItem(CHIAVE);
            sessionStorage.removeItem(CHIAVE);
        } catch (e) {
            return 0;
        }
        if (!grezzo) {
            return 0;
        }
        var prima;
        try {
            prima = JSON.parse(grezzo);
        } catch (e) {
            return 0;
        }
        if (!prima || prima.pagina !== location.pathname
            || Date.now() - prima.quando > FINESTRA_MS) {
            return 0;
        }
        var cifre = document.querySelectorAll(SELETTORE);
        if (cifre.length !== prima.valori.length) {
            return 0;
        }
        var saltate = 0;
        Array.prototype.forEach.call(cifre, function (c, i) {
            if (c.textContent.trim() !== prima.valori[i]) {
                c.classList.add('is-pop');
                saltate += 1;
            }
        });
        return saltate;
    }

    window.c7ScorePop = { segna: segna, salva: salva, ripristina: ripristina };

    window.addEventListener('pagehide', salva);
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', ripristina);
    } else {
        ripristina();
    }
})();
