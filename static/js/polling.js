/**
 * Polling per gli aggiornamenti live (al posto di SSE, vedi ADR-021).
 *
 * Protocollo col server (routes/sse.py, ADR-057):
 *
 * - il primo poll parte SENZA `since`: il server risponde con il cursore
 *   corrente e nessun evento. Non c'è più un orologio del client da
 *   confrontare con quello del server: un telefono avanti di qualche secondo
 *   perdeva i primi eventi, uno indietro riceveva eventi vecchi, ricaricava,
 *   e li riceveva di nuovo;
 * - da lì in poi `since` è il cursore restituito dal server, cioè l'id
 *   dell'ultimo evento visto. Resta fermo quando non arriva niente;
 * - `retention` è per quanti secondi il server conserva gli eventi. Una
 *   scheda rimasta nascosta più a lungo non può recuperarli: al ritorno in
 *   primo piano si chiama `onGap` (per reloadOnEvents: si ricarica);
 * - un 401 vuol dire che la sessione è finita: il poller si ferma e la pagina
 *   lo dice una volta sola, qualunque sia il numero di poller. Riprovare non
 *   serve a niente — ed è ciò che faceva prima, ogni tre secondi, per sempre.
 */

window.Polling = (function() {
    'use strict';

    var DEFAULT_INTERVAL = 3000;   // ms fra un poll e l'altro
    var DEFAULT_RETENTION = 60;    // s; il server manda il valore vero a ogni risposta
    var CONFIG_ID = 'polling-config';
    var AVVISO_ID = 'c7-session-expired';

    /**
     * L'avviso «la sessione è scaduta», uno per pagina.
     *
     * I testi e l'indirizzo del login arrivano da `#polling-config` in
     * base.html: nessuna stringa visibile vive nel JS. Il link riporta sulla
     * pagina corrente dopo l'accesso.
     */
    function avvisaSessioneScaduta() {
        if (document.getElementById(AVVISO_ID)) return;
        var nodo = document.getElementById(CONFIG_ID);
        var config = null;
        try {
            config = nodo ? JSON.parse(nodo.textContent || '{}') : null;
        } catch (e) {
            config = null;
        }
        if (!config || !config.i18n || !config.login_url) {
            console.warn('[Polling] session expired, polling stopped');
            return;
        }

        var avviso = document.createElement('div');
        avviso.id = AVVISO_ID;
        avviso.className = 'c7-session-expired';
        avviso.setAttribute('role', 'alert');

        var titolo = document.createElement('div');
        titolo.className = 'c7-session-expired__title';
        titolo.textContent = config.i18n.title;

        var testo = document.createElement('p');
        testo.className = 'c7-session-expired__text';
        testo.textContent = config.i18n.text;

        var azione = document.createElement('a');
        azione.className = 'btn btn-dark c7-session-expired__action';
        azione.setAttribute(
            'href',
            config.login_url + '?next=' + encodeURIComponent(location.pathname + location.search)
        );
        azione.textContent = config.i18n.action;

        avviso.appendChild(titolo);
        avviso.appendChild(testo);
        avviso.appendChild(azione);
        document.body.appendChild(avviso);
    }

    // --- Ricaricare, ma non sotto il dito -------------------------------
    //
    // Una pagina che si ricarica da sola lo fa quando arriva l'evento, cioe'
    // in un momento qualunque: anche mentre chi la guarda sta scorrendo. Sul
    // telefono la pagina sparisce sotto il dito, e su iPhone un ricaricamento
    // a scorrimento in corso lasciava la barra di navigazione in basso a meta'
    // schermo, sopra il contenuto (pagina gara del direttore, 12/11/2026: li'
    // l'evento e' ogni triangolo segnato a ogni tavolo).
    //
    // Si aspetta che il dito sia alzato e che la pagina sia ferma da QUIETE
    // millisecondi: l'inerzia continua a scorrere dopo il `touchend`, e la
    // dicono gli eventi `scroll`. I listener nascono col modulo perche' la
    // domanda «sta toccando?» va saputa prima che arrivi l'evento.
    var QUIETE = 400;        // ms senza toccare ne' scorrere
    var CONTROLLO = 100;     // ms fra un controllo e l'altro
    var dita = false;
    var ultimoMovimento = 0;
    var ricaricaInAttesa = false;

    function siMuove() { ultimoMovimento = Date.now(); }
    var passivo = { passive: true, capture: true };
    document.addEventListener('touchstart', function() { dita = true; siMuove(); }, passivo);
    document.addEventListener('touchmove', siMuove, passivo);
    document.addEventListener('touchend', function() { dita = false; siMuove(); }, passivo);
    document.addEventListener('touchcancel', function() { dita = false; siMuove(); }, passivo);
    document.addEventListener('scroll', siMuove, passivo);

    /**
     * Ricarica la pagina appena nessuno la sta toccando o scorrendo.
     *
     * Chiamata piu' volte ricarica una volta sola: dieci eventi arrivati
     * durante uno scorrimento sono un ricaricamento, non dieci.
     *
     * @param {function} [ricarica] - come ricaricare (default `location.reload`)
     */
    function ricaricaQuandoFermo(ricarica) {
        if (ricaricaInAttesa) return;
        ricaricaInAttesa = true;
        var esegui = ricarica || function() { location.reload(); };

        (function controlla() {
            if (!dita && Date.now() - ultimoMovimento >= QUIETE) {
                esegui();
                return;
            }
            setTimeout(controlla, CONTROLLO);
        })();
    }

    /**
     * Crea un poller per uno scope.
     *
     * @param {Object} config
     * @param {string} config.url - endpoint di poll (es. '/sse/poll/gara/8')
     * @param {function} config.onEvent - chiamata per ogni evento: function(event)
     * @param {number} [config.interval=3000] - intervallo in ms
     * @param {function} [config.onError] - function(error)
     * @param {function} [config.onGap] - la scheda è rimasta nascosta più a
     *   lungo della conservazione del server: gli eventi persi non tornano
     * @returns {Object} poller con start() e stop()
     */
    function create(config) {
        if (!config.url || !config.onEvent) {
            throw new Error('Polling.create requires url and onEvent');
        }

        var url = config.url;
        var onEvent = config.onEvent;
        var interval = config.interval || DEFAULT_INTERVAL;
        var onError = config.onError || function(err) {
            console.warn('[Polling] Error:', err.message);
        };
        var onGap = config.onGap || null;

        var cursor = null;                 // null = primo poll: lo decide il server
        var retention = DEFAULT_RETENTION;
        var hiddenAt = null;
        var timerId = null;
        var running = false;
        // Una sola richiesta per volta: poll() e' invocata sia dal timer sia
        // dal ritorno in primo piano, e due fetch concorrenti aggiornerebbero
        // il cursore fuori ordine con la risposta piu' lenta.
        var inFlight = false;

        function poll() {
            if (!running || inFlight) return;

            // Scheda in secondo piano: non consumare un worker per una pagina
            // che nessuno sta guardando. Su PythonAnywhere i worker sono
            // pochi e queste richieste competono con quelle vere.
            if (document.hidden) return;

            var primo = cursor === null;
            inFlight = true;
            fetch(url + (primo ? '' : '?since=' + cursor))
                .then(function(response) {
                    // Sessione finita. `redirected` copre chi manda ancora al
                    // login con un 302: fetch lo segue e consegna il 200 della
                    // pagina di login, che `ok` non distingue da un poll vero.
                    if (response.status === 401 || response.redirected) {
                        stop();
                        avvisaSessioneScaduta();
                        return null;
                    }
                    if (!response.ok) throw new Error('Poll failed: ' + response.status);
                    return response.json();
                })
                .then(function(result) {
                    if (!result) return;
                    cursor = result.cursor;
                    if (result.retention) retention = result.retention;
                    // Al primo giro il server non manda eventi; se mai lo
                    // facesse, il passato non va consegnato.
                    if (!primo && result.events && result.events.length > 0) {
                        result.events.forEach(onEvent);
                    }
                })
                .catch(onError)
                .then(function() { inFlight = false; });
        }

        // Al ritorno in primo piano non si aspetta il prossimo tick: si
        // recupera subito. Ma se la scheda e' stata nascosta piu' a lungo di
        // quanto il server conserva gli eventi, quelli persi non ci sono
        // piu': fingere di riprendere da dove si era lasciato mostrerebbe una
        // pagina vecchia senza dirlo a nessuno.
        function onVisibilityChange() {
            if (!running) return;
            if (document.hidden) {
                hiddenAt = Date.now();
                return;
            }
            var nascostaPer = hiddenAt === null ? 0 : (Date.now() - hiddenAt) / 1000;
            hiddenAt = null;
            if (nascostaPer > retention && onGap) {
                onGap();
            }
            poll();
        }

        function stop() {
            running = false;
            document.removeEventListener('visibilitychange', onVisibilityChange);
            if (timerId) {
                clearInterval(timerId);
                timerId = null;
            }
        }

        return {
            start: function() {
                if (running) return;
                running = true;
                document.addEventListener('visibilitychange', onVisibilityChange);
                // Primo poll dopo un breve ritardo, poi a intervalli regolari
                setTimeout(poll, 500);
                timerId = setInterval(poll, interval);
            },
            stop: stop
        };
    }

    /**
     * Crea e avvia un poller che ricarica la pagina su certi eventi — e
     * quando la scheda torna da un'assenza troppo lunga per recuperarli.
     *
     * @param {Object} config
     * @param {string} config.url - endpoint di poll
     * @param {string[]} config.reloadOn - tipi di evento che ricaricano
     * @param {number} [config.interval=3000]
     * @param {function} [config.ricarica] - come ricaricare (per i test)
     * @returns {Object} poller
     */
    function reloadOnEvents(config) {
        var reloadEvents = config.reloadOn || [];
        var ricarica = config.ricarica;

        var poller = create({
            url: config.url,
            interval: config.interval,
            onEvent: function(event) {
                if (reloadEvents.includes(event.type)) {
                    console.log('[Polling] ' + event.type + ', reloading...');
                    ricaricaQuandoFermo(ricarica);
                }
            },
            onGap: function() {
                console.log('[Polling] tab hidden longer than retention, reloading...');
                ricaricaQuandoFermo(ricarica);
            }
        });

        poller.start();
        return poller;
    }

    return {
        create: create,
        reloadOnEvents: reloadOnEvents,
        ricaricaQuandoFermo: ricaricaQuandoFermo
    };
})();
