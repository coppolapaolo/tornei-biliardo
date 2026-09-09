/**
 * Modalità aiuto: la «?» accanto ai comandi e la presentazione della schermata.
 *
 * I testi non stanno qui: sono in `help_content/<lingua>/hints.yaml`, scritti
 * e riletti prima del codice, e arrivano da `/aiuto/api/schermata/<endpoint>`
 * (routes/help.py). Questo file sa solo tre cose:
 *
 * - **dove** attaccare ogni suggerimento: l'elemento che espone
 *   `data-help="<anchor>"`, con l'ancora dichiarata nel YAML. Un'ancora
 *   senza elemento, o un elemento senza ancora, non è un errore per chi usa
 *   l'app — in sviluppo lo segnala la console, in CI il test statico
 *   `tests/new/unit/test_help_anchors.py`;
 * - **quando** essere accesa. La modalità si offre dove la pagina dichiara un
 *   attivatore (`[data-help-toggle]`: oggi il banner della competizione di
 *   prova, ADR-058; domani anche altro) e resta accesa finché l'utente non la
 *   spegne da lì. La scelta vive in `localStorage`, per browser: spenta una
 *   volta, resta spenta in ogni prova. Il componente non sa cos'è una prova;
 * - **cosa ha già visto**: la presentazione (`tours` nel YAML) compare alla
 *   prima visita di ogni schermata, poi mai più (`localStorage`, per
 *   schermata). Senza `localStorage` — navigazione privata — funziona lo
 *   stesso, solo senza memoria.
 *
 * La configurazione la inietta `base.html` in un blocco JSON
 * (`#help-hints-config`): endpoint corrente, URL dell'API, flag di sviluppo
 * e le etichette tradotte. Nessuna stringa visibile è scritta qui.
 */

window.HelpHints = (function () {
    'use strict';

    var STORAGE_KEY = 'tb-help-mode';
    var SEEN_PREFIX = 'tb-help-seen:';
    // Elementi dentro cui una «?» non puo' stare: la si mette subito dopo.
    var INTERACTIVE = /^(BUTTON|A|INPUT|SELECT|TEXTAREA|SUMMARY)$/;
    var POP_WIDTH = 340;
    var GUTTER = 12;

    var config = null;
    var sessionChoice = null;   // scelta di questa pagina, se localStorage manca
    var state = { ready: undefined, pop: null, tour: null, hints: [] };

    // ------------------------------------------------------------------
    // Configurazione e memoria
    // ------------------------------------------------------------------

    function readConfig() {
        if (config) { return config; }
        var node = document.getElementById('help-hints-config');
        if (!node) { return null; }
        try {
            config = JSON.parse(node.textContent || '{}');
        } catch (e) {
            config = null;
        }
        return config;
    }

    function t(key, vars) {
        var text = (config && config.i18n && config.i18n[key]) || key;
        if (vars) {
            Object.keys(vars).forEach(function (name) {
                text = text.replace('{' + name + '}', String(vars[name]));
            });
        }
        return text;
    }

    function warn() {
        if (!config || !config.debug || !window.console) { return; }
        var args = Array.prototype.slice.call(arguments);
        console.warn.apply(console, ['[help-hints]'].concat(args));
    }

    function storageGet(key) {
        try { return window.localStorage.getItem(key); } catch (e) { return null; }
    }

    function storageSet(key, value) {
        try { window.localStorage.setItem(key, value); } catch (e) { /* privato */ }
    }

    function activatorPresent() {
        return !!document.querySelector('[data-help-toggle]');
    }

    /**
     * Accesa se la pagina la offre e l'utente non l'ha spenta. Una scelta
     * fatta senza localStorage vale per questa pagina soltanto.
     */
    function isActive() {
        if (!activatorPresent()) { return false; }
        if (sessionChoice !== null) { return sessionChoice; }
        return storageGet(STORAGE_KEY) !== '0';
    }

    function seen(screen) {
        return storageGet(SEEN_PREFIX + screen) === '1';
    }

    function markSeen(screen) {
        storageSet(SEEN_PREFIX + screen, '1');
    }

    // ------------------------------------------------------------------
    // Le «?»
    // ------------------------------------------------------------------

    function elementsFor(anchor) {
        var selector = '[data-help="' + anchor + '"]';
        return Array.prototype.slice.call(document.querySelectorAll(selector));
    }

    function makeQ(hint) {
        var q = document.createElement('button');
        q.type = 'button';
        q.className = 'c7-help-q';
        q.setAttribute('data-help-for', hint.anchor);
        q.setAttribute('aria-label', t('help') + ': ' + hint.label);
        q.setAttribute('title', hint.label);
        q.setAttribute('aria-haspopup', 'dialog');
        q.textContent = '?';
        return q;
    }

    function attach(hint) {
        var targets = elementsFor(hint.anchor);
        if (!targets.length) {
            warn('ancora senza elemento in pagina:', hint.anchor);
            return;
        }
        targets.forEach(function (el) {
            var q = makeQ(hint);
            if (INTERACTIVE.test(el.tagName)) {
                el.insertAdjacentElement('afterend', q);
            } else {
                el.appendChild(q);
            }
        });
    }

    function renderHints(payload) {
        state.hints = payload.hints || [];
        var known = {};
        state.hints.forEach(function (hint) {
            known[hint.anchor] = hint;
            attach(hint);
        });
        Array.prototype.forEach.call(document.querySelectorAll('[data-help]'), function (el) {
            var anchor = el.getAttribute('data-help');
            if (!known[anchor]) {
                warn('elemento senza suggerimento per questa schermata:', anchor);
            }
        });
    }

    function removeQs() {
        Array.prototype.forEach.call(document.querySelectorAll('.c7-help-q'), function (q) {
            q.parentNode.removeChild(q);
        });
    }

    // ------------------------------------------------------------------
    // Il fumetto
    // ------------------------------------------------------------------

    function hintFor(anchor) {
        for (var i = 0; i < state.hints.length; i += 1) {
            if (state.hints[i].anchor === anchor) { return state.hints[i]; }
        }
        return null;
    }

    function closePop() {
        if (!state.pop) { return; }
        state.pop.el.parentNode.removeChild(state.pop.el);
        state.pop.btn.setAttribute('aria-expanded', 'false');
        state.pop = null;
    }

    function positionPop(pop, btn) {
        var rect = btn.getBoundingClientRect();
        var vw = window.innerWidth || document.documentElement.clientWidth || 0;
        var vh = window.innerHeight || document.documentElement.clientHeight || 0;
        var width = Math.min(POP_WIDTH, Math.max(vw - 2 * GUTTER, 0));
        pop.style.width = width + 'px';
        var left = Math.min(Math.max(rect.left - GUTTER, GUTTER), Math.max(vw - width - GUTTER, GUTTER));
        var height = pop.offsetHeight || 0;
        var top = rect.bottom + 8;
        if (vh && top + height > vh - GUTTER && rect.top - 8 - height > GUTTER) {
            top = rect.top - 8 - height;
        }
        pop.style.left = left + 'px';
        pop.style.top = Math.max(top, GUTTER) + 'px';
    }

    function openPop(btn) {
        var hint = hintFor(btn.getAttribute('data-help-for'));
        if (!hint) { return; }
        closePop();

        var pop = document.createElement('div');
        pop.className = 'c7-help-pop';
        pop.setAttribute('role', 'dialog');
        pop.setAttribute('aria-label', hint.label);

        var head = document.createElement('div');
        head.className = 'c7-help-pop__head';
        var title = document.createElement('div');
        title.className = 'c7-help-pop__title';
        title.textContent = hint.label;
        var close = document.createElement('button');
        close.type = 'button';
        close.className = 'c7-help-pop__close';
        close.setAttribute('aria-label', t('close'));
        close.setAttribute('data-help-action', 'close');
        close.innerHTML = '<i class="fas fa-xmark" aria-hidden="true"></i>';
        head.appendChild(title);
        head.appendChild(close);
        pop.appendChild(head);

        var body = document.createElement('p');
        body.className = 'c7-help-pop__text';
        body.textContent = hint.short;
        pop.appendChild(body);

        if (hint.url) {
            var link = document.createElement('a');
            link.className = 'c7-help-pop__link';
            link.href = hint.url;
            link.textContent = t('read_more');
            pop.appendChild(link);
        }

        document.body.appendChild(pop);
        positionPop(pop, btn);
        btn.setAttribute('aria-expanded', 'true');
        state.pop = { el: pop, btn: btn };
    }

    // ------------------------------------------------------------------
    // La presentazione
    // ------------------------------------------------------------------

    function clearTargets() {
        Array.prototype.forEach.call(document.querySelectorAll('.c7-help-target'), function (el) {
            el.classList.remove('c7-help-target');
        });
    }

    function highlight(anchor) {
        clearTargets();
        if (!anchor) { return; }
        var targets = elementsFor(anchor);
        if (!targets.length) { return; }
        // Fra i doppioni mobile/desktop si preferisce quello visibile.
        var visible = targets.filter(function (el) {
            return el.getClientRects().length > 0;
        });
        var el = visible[0] || targets[0];
        el.classList.add('c7-help-target');
        if (typeof el.scrollIntoView === 'function') {
            try { el.scrollIntoView({ block: 'center', behavior: 'smooth' }); } catch (e) { /* vecchi browser */ }
        }
    }

    function closeTour(remember) {
        if (!state.tour) { return; }
        state.tour.el.parentNode.removeChild(state.tour.el);
        clearTargets();
        if (remember) { markSeen(state.tour.screen); }
        state.tour = null;
    }

    function renderTourStep() {
        var tour = state.tour;
        var step = tour.steps[tour.index];
        var last = tour.index === tour.steps.length - 1;
        tour.count.textContent = t('step_of', { n: tour.index + 1, total: tour.steps.length });
        tour.stepTitle.textContent = step.title || '';
        tour.stepText.textContent = step.text || '';
        tour.next.textContent = last ? t('done') : t('next');
        highlight(step.anchor);
    }

    function showTour(tour, screen) {
        closeTour(false);
        var steps = (tour.steps || []).filter(function (s) { return s && s.text; });
        if (!steps.length) { return; }

        var el = document.createElement('div');
        el.className = 'c7-help-tour';
        el.setAttribute('role', 'dialog');
        el.setAttribute('aria-modal', 'true');
        el.setAttribute('aria-label', tour.title || t('presentation'));

        var card = document.createElement('div');
        card.className = 'c7-help-tour__card';

        var kicker = document.createElement('div');
        kicker.className = 'c7-kicker';
        kicker.textContent = t('presentation');
        card.appendChild(kicker);

        var title = document.createElement('div');
        title.className = 'c7-help-tour__title';
        title.textContent = tour.title || '';
        card.appendChild(title);

        if (tour.intro) {
            var intro = document.createElement('p');
            intro.className = 'c7-help-tour__intro';
            intro.textContent = tour.intro;
            card.appendChild(intro);
        }

        var stepBox = document.createElement('div');
        stepBox.className = 'c7-help-tour__step';
        var count = document.createElement('div');
        count.className = 'c7-help-tour__count c7-num';
        var stepTitle = document.createElement('div');
        stepTitle.className = 'c7-help-tour__steptitle';
        var stepText = document.createElement('p');
        stepText.className = 'c7-help-tour__text';
        stepBox.appendChild(count);
        stepBox.appendChild(stepTitle);
        stepBox.appendChild(stepText);
        card.appendChild(stepBox);

        var actions = document.createElement('div');
        actions.className = 'c7-help-tour__actions';
        var skip = document.createElement('button');
        skip.type = 'button';
        skip.className = 'btn btn-secondary';
        skip.setAttribute('data-help-action', 'skip');
        skip.textContent = t('skip');
        var next = document.createElement('button');
        next.type = 'button';
        next.className = 'btn btn-primary';
        next.setAttribute('data-help-action', 'next');
        actions.appendChild(skip);
        actions.appendChild(next);
        card.appendChild(actions);

        el.appendChild(card);
        document.body.appendChild(el);

        state.tour = {
            el: el, screen: screen, steps: steps, index: 0,
            count: count, stepTitle: stepTitle, stepText: stepText, next: next
        };
        renderTourStep();
    }

    function tourNext() {
        var tour = state.tour;
        if (!tour) { return; }
        if (tour.index >= tour.steps.length - 1) {
            closeTour(true);
            return;
        }
        tour.index += 1;
        renderTourStep();
    }

    // ------------------------------------------------------------------
    // Ciclo di vita
    // ------------------------------------------------------------------

    function syncToggles() {
        var on = isActive();
        Array.prototype.forEach.call(document.querySelectorAll('[data-help-toggle]'), function (toggle) {
            if ('checked' in toggle) { toggle.checked = on; }
        });
    }

    function clear() {
        closePop();
        closeTour(false);
        removeQs();
        state.hints = [];
    }

    function render(payload) {
        renderHints(payload);
        if (payload.tour && config && !seen(config.screen)) {
            showTour(payload.tour, config.screen);
        }
    }

    /**
     * Rilegge la scelta, spegne tutto, e se la modalità è accesa chiede
     * all'API i testi della schermata e li attacca. Restituisce una promise
     * (anche `HelpHints.ready`) per chi deve aspettare il risultato.
     */
    function refresh() {
        readConfig();
        syncToggles();
        clear();
        if (!config || !config.api || !isActive()) {
            state.ready = Promise.resolve();
            return state.ready;
        }
        state.ready = window.fetch(config.api, {
            headers: { 'Accept': 'application/json' },
            credentials: 'same-origin'
        }).then(function (response) {
            if (!response.ok) {
                if (response.status === 404) {
                    warn('nessun aiuto per la schermata', config.screen);
                } else {
                    warn('API di aiuto:', response.status);
                }
                return null;
            }
            return response.json();
        }).then(function (payload) {
            if (payload && isActive()) { render(payload); }
        }).catch(function (error) {
            warn('API di aiuto non raggiungibile:', error);
        });
        return state.ready;
    }

    function setOn(on) {
        sessionChoice = !!on;
        storageSet(STORAGE_KEY, on ? '1' : '0');
        return refresh();
    }

    function onClick(event) {
        var target = event.target;
        if (!target || !target.closest) { return; }

        var q = target.closest('.c7-help-q');
        if (q) {
            // Dentro una <label> il clic attiverebbe il campo collegato.
            event.preventDefault();
            event.stopPropagation();
            if (state.pop && state.pop.btn === q) { closePop(); } else { openPop(q); }
            return;
        }

        var action = target.closest('[data-help-action]');
        if (action) {
            var name = action.getAttribute('data-help-action');
            if (name === 'close') { closePop(); }
            if (name === 'skip') { closeTour(true); }
            if (name === 'next') { tourNext(); }
            return;
        }

        if (state.pop && !state.pop.el.contains(target)) { closePop(); }
    }

    function onKeydown(event) {
        if (event.key !== 'Escape') { return; }
        if (state.pop) { closePop(); return; }
        if (state.tour) { closeTour(true); }
    }

    function onChange(event) {
        var target = event.target;
        if (target && target.matches && target.matches('[data-help-toggle]')) {
            setOn(!!target.checked);
        }
    }

    function init() {
        document.addEventListener('click', onClick, true);
        document.addEventListener('keydown', onKeydown);
        document.addEventListener('change', onChange);
        window.addEventListener('resize', closePop);

        function start() {
            // Chi ha già chiamato refresh() da fuori (test, altri script) non
            // va scavalcato da un secondo giro.
            if (state.ready === undefined) { refresh(); }
        }
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', start);
        } else {
            start();
        }
    }

    init();

    var api = {
        STORAGE_KEY: STORAGE_KEY,
        SEEN_PREFIX: SEEN_PREFIX,
        isActive: isActive,
        setOn: setOn,
        refresh: refresh,
        clear: clear
    };
    Object.defineProperty(api, 'ready', { get: function () { return state.ready; } });
    return api;
})();
