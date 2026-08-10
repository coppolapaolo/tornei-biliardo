/**
 * Gamification Effects — Design System 7c
 *
 * Toast della mascotte Chalky.
 * API pubblica invariata rispetto alla versione precedente:
 *   window.showGamificationEvent(type, data)
 *   window.testGamificationEffects()
 * Cambia solo il rendering: markup .c7-chalky dentro #chalky-container,
 * stile dai token 7c, coda con un toast pieno e i successivi rientrati.
 *
 * Il markup e' costruito con metodi DOM sicuri: nessun innerHTML.
 */

// ========================================
//   Pose della mascotte
//   Sovrascrivibili da #gamification-config -> mascot { base, <chiave> }
// ========================================

const MASCOT_IMAGES = {
    xp: '/static/img/chalk1.png',           // pollice in su
    levelup: '/static/img/chalk2.png',      // esulta
    achievement: '/static/img/chalk3.png',  // trofeo
    streak: '/static/img/chalk4.png',       // streak
    sad: '/static/img/chalk5.png',          // streak persa
    encourage: '/static/img/chalk6.png',    // incoraggia / funzione sbloccata
    quest: '/static/img/chalk7.png',        // curioso
    surprised: '/static/img/chalk8.png',    // sorpreso / traguardo raro
    welcome: '/static/img/chalk9.png',      // saluta
    legendary: '/static/img/chalk10.png'    // corona
};

// Mappa chiavi di configurazione -> chiavi interne
const CONFIG_MASCOT_KEYS = {
    xp: 'xp',
    level_up: 'levelup',
    achievement: 'achievement',
    achievement_rare: 'surprised',
    streak: 'streak',
    streak_lost: 'sad',
    quest: 'quest',
    unlock: 'encourage',
    welcome: 'welcome',
    legendary: 'legendary'
};

// ========================================
//   Durate (ms) — 5 s e' il passo di riferimento
// ========================================

const TOAST_DURATIONS = {
    xp: 3500,
    levelup: 5000,
    achievement: 5000,
    achievementLegendary: 7000,
    streak: 4500,
    streakLost: 4500,
    quest: 4500,
    welcome: 5000
};

// Gerarchia per collassare eventi simultanei: badge > level up > XP.
const EVENT_PRIORITY = {
    achievement: 40,
    unlock: 35,
    levelup: 30,
    streak: 25,
    streak_lost: 25,
    quest: 20,
    nudge: 15,
    welcome: 10,
    xp: 5
};

// ========================================
//   Toast
// ========================================

class GamificationToast {
    constructor() {
        this.container = null;
        this.queue = [];
        this.isProcessing = false;
        this.config = this.loadConfig();
        this.applyMascotConfig();
        this.init();
    }

    loadConfig() {
        try {
            const configElement = document.getElementById('gamification-config');
            if (configElement) {
                return JSON.parse(configElement.textContent);
            }
        } catch (e) {
            console.error('Error loading gamification config:', e);
        }
        return { i18n: {} };
    }

    /** Le pose possono arrivare da base.html (url_for corretto in sottodirectory). */
    applyMascotConfig() {
        const m = this.config.mascot;
        if (!m) return;
        const base = m.base || '';
        Object.keys(CONFIG_MASCOT_KEYS).forEach(function (cfgKey) {
            if (m[cfgKey]) {
                MASCOT_IMAGES[CONFIG_MASCOT_KEYS[cfgKey]] = base + m[cfgKey];
            }
        });
    }

    getI18n(key, defaultValue) {
        return (this.config.i18n && this.config.i18n[key]) || defaultValue;
    }

    init() {
        const selector = this.config.container || '#chalky-container';
        this.container = document.querySelector(selector);
        if (!this.container) {
            this.container = document.createElement('div');
            this.container.id = 'chalky-container';
            this.container.setAttribute('aria-live', 'polite');
            document.body.appendChild(this.container);
        }
    }

    // ---------- Eventi ----------

    showXPGain(amount, reason = '') {
        this.queueToast({
            mascot: MASCOT_IMAGES.xp,
            kicker: this.getI18n('xp_title', 'XP OTTENUTI'),
            xp: '+' + amount + ' XP',
            sub: reason,
            duration: TOAST_DURATIONS.xp,
            priority: EVENT_PRIORITY.xp
        });
    }

    showLevelUp(newLevel, title = '') {
        this.triggerConfetti('level');
        this.queueToast({
            mascot: MASCOT_IMAGES.levelup,
            kicker: this.getI18n('level_up_title', 'LEVEL UP!'),
            title: 'Livello ' + newLevel,
            sub: title || this.getI18n('level_up_subtitle', 'Nuovo livello raggiunto!'),
            variant: 'level',
            duration: TOAST_DURATIONS.levelup,
            priority: EVENT_PRIORITY.levelup
        });
    }

    showAchievement(name, description, rarity = 'common', icon = '') {
        const isRare = ['rare', 'epic', 'legendary'].includes(rarity);
        if (isRare) this.triggerConfetti(rarity);

        let mascot = MASCOT_IMAGES.achievement;
        let variant = null;
        let kicker = this.getI18n('achievement_title', 'NUOVO TRAGUARDO!');

        if (rarity === 'legendary') {
            mascot = MASCOT_IMAGES.legendary;
            variant = 'rare';
            kicker = this.getI18n('achievement_legendary_title', 'NUOVO TRAGUARDO · LEGGENDARIO');
        } else if (rarity === 'epic' || rarity === 'rare') {
            mascot = MASCOT_IMAGES.surprised;
            variant = 'rare';
            kicker = this.getI18n('achievement_rare_title', 'TRAGUARDO RARO!');
        }

        this.queueToast({
            mascot: mascot,
            kicker: kicker,
            title: name,
            sub: description,
            variant: variant,
            duration: rarity === 'legendary' ? TOAST_DURATIONS.achievementLegendary : TOAST_DURATIONS.achievement,
            priority: EVENT_PRIORITY.achievement
        });
    }

    showStreak(streakCount, streakType = 'weekly', hasFreeze = false) {
        this.queueToast({
            mascot: MASCOT_IMAGES.streak,
            kicker: this.getI18n('streak_title', 'STREAK!'),
            title: streakCount + ' ' + (streakType === 'daily' ? 'giorni' : 'settimane'),
            chip: hasFreeze ? this.getI18n('streak_freeze', 'Freeze attivo') : '',
            duration: TOAST_DURATIONS.streak,
            priority: EVENT_PRIORITY.streak
        });
    }

    showStreakLost(message = '') {
        this.queueToast({
            mascot: MASCOT_IMAGES.sad,
            kicker: this.getI18n('streak_lost_title', 'STREAK PERSA'),
            title: message || this.getI18n('streak_lost_subtitle', 'Non mollare, riprova!'),
            variant: 'lost',
            duration: TOAST_DURATIONS.streakLost,
            priority: EVENT_PRIORITY.streak_lost
        });
    }

    showQuest(questName, description = '') {
        this.queueToast({
            mascot: MASCOT_IMAGES.quest,
            kicker: this.getI18n('quest_title', 'QUEST COMPLETATA!'),
            title: questName,
            sub: description,
            duration: TOAST_DURATIONS.quest,
            priority: EVENT_PRIORITY.quest
        });
    }

    showWelcome(username = '', title = '', subtitle = '') {
        const content = username
            ? this.getI18n('welcome_user', 'Ciao %(username)s!').replace('%(username)s', username)
            : this.getI18n('welcome_anonymous', 'Ciao!');

        this.queueToast({
            mascot: MASCOT_IMAGES.welcome,
            kicker: title || this.getI18n('welcome_title', 'TI DIAMO IL BENTORNATO!'),
            title: content,
            sub: subtitle || this.getI18n('welcome_subtitle', 'Pronto per giocare?'),
            duration: TOAST_DURATIONS.welcome,
            priority: EVENT_PRIORITY.welcome
        });
    }

    showNudge(code, name, description) {
        this.queueToast({
            mascot: MASCOT_IMAGES.quest,
            kicker: this.getI18n('nudge_title', 'NUOVA POSSIBILITÀ!'),
            title: name,
            sub: description || this.getI18n('nudge_subtitle', 'Hai sbloccato questa funzione, provala subito!'),
            duration: TOAST_DURATIONS.quest,
            priority: EVENT_PRIORITY.nudge
        });
    }

    showUnlock(code, name, description) {
        this.triggerConfetti('rare');
        this.queueToast({
            mascot: MASCOT_IMAGES.encourage,
            kicker: this.getI18n('unlock_title', 'NUOVA POSSIBILITÀ!'),
            title: name,
            sub: description,
            duration: TOAST_DURATIONS.levelup,
            priority: EVENT_PRIORITY.unlock
        });
    }

    // ---------- Rendering ----------

    /**
     * Costruisce l'elemento .c7-chalky.
     * @param {object} o - { mascot, kicker, title, sub, xp, chip, variant }
     */
    createToast(o) {
        const toast = document.createElement('div');
        toast.className = 'c7-chalky' + (o.variant ? ' c7-chalky--' + o.variant : '');
        toast.setAttribute('role', 'status');

        const img = document.createElement('img');
        img.src = o.mascot;
        img.alt = 'Chalky';
        img.loading = 'lazy';
        toast.appendChild(img);

        const body = document.createElement('div');
        body.className = 'c7-chalky__body';

        if (o.kicker) {
            const kicker = document.createElement('div');
            kicker.className = 'c7-kicker';
            kicker.textContent = o.kicker;
            body.appendChild(kicker);
        }

        if (o.xp) {
            const xp = document.createElement('div');
            xp.className = 'c7-chalky__xp';
            xp.textContent = o.xp;
            body.appendChild(xp);
        }

        if (o.title) {
            const title = document.createElement('div');
            title.className = 'c7-chalky__title';
            title.textContent = o.title;
            body.appendChild(title);
        }

        if (o.sub) {
            const sub = document.createElement('div');
            sub.className = 'c7-chalky__sub';
            sub.textContent = o.sub;
            body.appendChild(sub);
        }

        if (o.chip) {
            const chip = document.createElement('span');
            chip.className = 'c7-state c7-state--info mt-2';
            chip.textContent = o.chip;
            body.appendChild(chip);
        }

        toast.appendChild(body);

        const close = document.createElement('button');
        close.type = 'button';
        close.className = 'btn-close';
        close.setAttribute('aria-label', 'Chiudi');
        close.addEventListener('click', function () { toast.remove(); });
        toast.appendChild(close);

        return toast;
    }

    /**
     * Accoda. Eventi accodati insieme vengono collassati: resta il piu' alto
     * in gerarchia (badge > level up > XP), gli altri finiscono nel riepilogo
     * di fine gara lato server.
     */
    queueToast(item) {
        this.queue.push(item);
        if (!this.isProcessing) {
            // Lascia arrivare gli eventi dello stesso ciclo prima di decidere.
            setTimeout(this.processQueue.bind(this), 0);
        }
    }

    collapseBurst() {
        if (this.queue.length <= 1) return;
        let best = 0;
        for (let i = 1; i < this.queue.length; i++) {
            if ((this.queue[i].priority || 0) > (this.queue[best].priority || 0)) best = i;
        }
        // Tiene il piu' importante in testa, gli altri restano come "in coda".
        const lead = this.queue.splice(best, 1)[0];
        this.queue.unshift(lead);
    }

    async processQueue() {
        if (this.isProcessing) return;
        this.isProcessing = true;
        this.collapseBurst();

        while (this.queue.length > 0) {
            const item = this.queue.shift();
            const toast = this.createToast(item);
            this.container.appendChild(toast);

            // Anteprima dei successivi, rientrata e attenuata.
            const previews = this.renderPreviews();

            await this.delay(item.duration || 4500);

            toast.classList.add('is-leaving');
            toast.style.transition = 'opacity .3s, transform .3s';
            toast.style.opacity = '0';
            toast.style.transform = 'translateY(-10px)';
            previews.forEach(function (el) { el.remove(); });

            await this.delay(300);
            toast.remove();

            if (this.queue.length > 0) await this.delay(200);
        }

        this.isProcessing = false;
    }

    /** Mostra al massimo due anteprime dei toast in coda. */
    renderPreviews() {
        const out = [];
        this.queue.slice(0, 2).forEach(function (item) {
            const el = this.createToast(item);
            el.classList.add('is-queued');
            const close = el.querySelector('.btn-close');
            if (close) close.remove();
            this.container.appendChild(el);
            out.push(el);
        }, this);
        return out;
    }

    delay(ms) {
        return new Promise(function (resolve) { setTimeout(resolve, ms); });
    }

    triggerConfetti(type = 'default') {
        if (typeof ConfettiEffect !== 'undefined') {
            const reduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
            if (!reduced) ConfettiEffect.fire(type);
        }
    }
}

// ========================================
//   Badge di livello "vivo" (§11-quater)
//   Feedback ambient e sobrio: anello di progresso + pulse sugli XP + glow al
//   level-up. Per i micro-eventi sostituisce il toast, che resta ai momenti
//   forti. E' idempotente rispetto ai valori che il context processor ha gia'
//   renderizzato nella testata (templates/base.html).
// ========================================

class GamificationBadge {
    constructor() {
        this.el = document.getElementById('gami-badge');
        this.levelEl = document.getElementById('gami-badge-level');
        this.xpEl = document.getElementById('gami-badge-xp');
        this.ringEl = this.el ? this.el.querySelector('.gami-badge-ring') : null;
        this.reducedMotion = window.matchMedia
            && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    }

    get available() {
        return !!this.el;
    }

    /**
     * Micro guadagno XP → count-up + pulse, nessun toast (scala d'intensita').
     * Il valore renderizzato (data-current-xp) e' gia' quello nuovo: si anima
     * dal precedente (nuovo - amount) a quello corrente.
     *
     * Piu' eventi XP possono arrivare nella stessa risposta (XP partita + bonus
     * serie + XP missione): `target` e' gia' il totale finale per tutti, quindi
     * ricalcolare `target - delta` a ogni chiamata farebbe *tornare indietro*
     * il contatore per poi risalire. Il punto di partenza si fissa una volta
     * sola e le chiamate successive accumulano il delta.
     */
    addXP(amount) {
        if (!this.available) return;
        const target = parseInt(this.el.dataset.currentXp || '0', 10);
        const delta = parseInt(amount, 10) || 0;

        if (this._xpAnimated) {
            // Gia' animato in questa pagina: il valore mostrato e' quello
            // finale. Solo il pulse, niente count-up all'indietro.
            this._pulse('badge-pulse');
            this._refreshRing();
            return;
        }
        this._xpAnimated = true;
        this._countUp(Math.max(0, target - delta), target);
        this._pulse('badge-pulse');
        this._refreshRing();
    }

    /** Level-up → glow + livello aggiornato (l'unico momento forte del badge). */
    levelUp(newLevel) {
        if (!this.available) return;
        if (newLevel != null && this.levelEl) {
            this.levelEl.textContent = newLevel;
            this.el.dataset.level = newLevel;
        }
        // Il server ha gia' renderizzato current_xp/progress del nuovo livello.
        if (this.xpEl) {
            this.xpEl.textContent = parseInt(this.el.dataset.currentXp || '0', 10);
        }
        this._refreshRing();
        this._pulse('badge-levelup');
    }

    /** Pulse discreto (achievement/streak/quest accompagnano il toast). */
    pulse() {
        this._pulse('badge-pulse');
    }

    _refreshRing() {
        if (!this.ringEl) return;
        const pct = parseFloat(this.el.dataset.progress || '0');
        this.ringEl.style.setProperty('--gami-progress', isNaN(pct) ? 0 : pct);
    }

    _pulse(cls) {
        if (!this.available || this.reducedMotion) return;
        this.el.classList.remove(cls);
        // Forza il reflow per ri-innescare l'animazione su eventi ravvicinati.
        void this.el.offsetWidth;
        this.el.classList.add(cls);
        setTimeout(() => this.el.classList.remove(cls), 1300);
    }

    _countUp(from, to) {
        if (!this.xpEl) return;
        if (this.reducedMotion || from === to) {
            this.xpEl.textContent = to;
            return;
        }
        const duration = 700;
        const start = performance.now();
        const step = (now) => {
            const t = Math.min(1, (now - start) / duration);
            const eased = t * (2 - t); // ease-out quadratico
            this.xpEl.textContent = Math.round(from + (to - from) * eased);
            if (t < 1) requestAnimationFrame(step);
        };
        requestAnimationFrame(step);
    }
}

// ========================================
//   API pubblica
// ========================================

let gamificationToast = null;
let gamificationBadge = null;

function getGamificationToast() {
    if (!gamificationToast) {
        gamificationToast = new GamificationToast();
    }
    return gamificationToast;
}

function getGamificationBadge() {
    if (!gamificationBadge) {
        gamificationBadge = new GamificationBadge();
    }
    return gamificationBadge;
}

/**
 * Cap anti-invasivita' (§11): al piu' UN toast celebrativo "capped" per sessione
 * di navigazione (sessionStorage). Il level-up ne e' esente — e' l'unico toast
 * celebrativo giustificato (§11-quater) — e gli XP non producono mai toast.
 * Achievement/streak/quest condividono l'unico slot: il primo si mostra, gli
 * altri restano silenziosi (solo pulse del badge).
 */
const GAMI_CAPPED_TOAST_KEY = 'gamiCappedToastShown';

function cappedToastAllowed() {
    try {
        if (sessionStorage.getItem(GAMI_CAPPED_TOAST_KEY)) return false;
        sessionStorage.setItem(GAMI_CAPPED_TOAST_KEY, '1');
        return true;
    } catch (e) {
        // sessionStorage non disponibile (navigazione privata) → non bloccare.
        return true;
    }
}

function showGamificationEvent(type, data) {
    data = data || {};
    // Il toast si istanzia solo quando serve: gli eventi 'xp' sono badge-only
    // (§11) e sono i piu' frequenti — su una pagina di soli XP non c'e' motivo
    // di costruire il container dei toast.
    const badge = getGamificationBadge();

    switch (type) {
        case 'xp':
            // Scala d'intensita': micro XP → solo badge, niente toast.
            badge.addXP(data.amount);
            break;
        case 'levelup':
            // Momento forte: glow del badge + l'unico toast celebrativo esente
            // dal cap.
            badge.levelUp(data.level);
            getGamificationToast().showLevelUp(data.level, data.title);
            break;
        case 'achievement':
            badge.pulse();
            if (cappedToastAllowed()) {
                getGamificationToast().showAchievement(data.name, data.description, data.rarity, data.icon);
            }
            break;
        case 'streak':
            badge.pulse();
            if (cappedToastAllowed()) {
                getGamificationToast().showStreak(data.count, data.type, data.hasFreeze);
            }
            break;
        case 'quest':
            badge.pulse();
            if (cappedToastAllowed()) {
                getGamificationToast().showQuest(data.name, data.description);
            }
            break;
        case 'streak_lost':
            getGamificationToast().showStreakLost(data.message);
            break;
        case 'welcome':
            getGamificationToast().showWelcome(data.username, data.title, data.subtitle);
            break;
        case 'nudge':
            // Scoperta funzioni: resta un toast, perche' e' azionabile.
            getGamificationToast().showNudge(data.code, data.name, data.description);
            break;
        case 'unlock':
            getGamificationToast().showUnlock(data.code, data.name, data.description);
            break;
        default:
            console.warn('Evento gamification sconosciuto:', type);
    }
}

/** Demo: testGamificationEffects() dalla console. */
function testGamificationEffects() {
    const seq = [
        ['welcome', { username: 'Marco' }],
        ['xp', { amount: 50, reason: 'Vittoria partita' }],
        ['levelup', { level: 5, title: 'Talento del biliardo' }],
        ['achievement', { name: 'Prima vittoria', description: 'Hai vinto la tua prima partita!', rarity: 'common' }],
        ['achievement', { name: 'Star locale', description: '10 partite vinte di fila', rarity: 'rare' }],
        ['streak', { count: 5, type: 'weekly', hasFreeze: true }],
        ['quest', { name: 'Sfida settimanale', description: 'Gioca 3 partite questa settimana' }],
        ['streak_lost', { message: 'Non mollare, riprova!' }],
        ['unlock', { code: 'direct_match', name: 'Tornei diretti', description: 'Hai sbloccato questa funzione, provala subito!' }],
        ['achievement', { name: 'Testa di serie', description: 'Girone chiuso al primo posto senza sconfitte', rarity: 'legendary' }]
    ];
    seq.forEach(function (pair, i) {
        setTimeout(function () { showGamificationEvent(pair[0], pair[1]); }, i * 300);
    });
    console.log('Chalky in coda: ' + seq.length + ' eventi.');
}

window.testGamificationEffects = testGamificationEffects;
window.showGamificationEvent = showGamificationEvent;

if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        GamificationToast,
        GamificationBadge,
        showGamificationEvent,
        testGamificationEffects,
        MASCOT_IMAGES
    };
}
