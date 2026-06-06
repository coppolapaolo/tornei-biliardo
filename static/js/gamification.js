/**
 * Gamification Effects JavaScript
 *
 * Provides interactive feedback for gamification events:
 * - Toast notifications for XP, levels, achievements, streaks
 * - Confetti effects for celebrations
 * - XP counter animations
 * - Mascot "Chalky" integration
 */

// ========================================
//   Mascot Image Paths
// ========================================

const MASCOT_IMAGES = {
    xp: '/static/img/chalk1.png',           // Thumbs up - XP gained
    levelup: '/static/img/chalk2.png',      // Celebration - Level up
    achievement: '/static/img/chalk3.png',  // Trophy - Achievement unlocked
    streak: '/static/img/chalk4.png',       // Fire - Streak active
    sad: '/static/img/chalk5.png',          // Sad - Streak lost
    encourage: '/static/img/chalk6.png',    // Encouraging - Try again
    quest: '/static/img/chalk7.png',        // Curious - New quest
    surprised: '/static/img/chalk8.png',    // Surprised - Rare achievement
    welcome: '/static/img/chalk9.png',      // Waving - Welcome/Login
    legendary: '/static/img/chalk10.png'    // Crown - Legendary achievement
};

// ========================================
//   Toast Durations (ms)
// ========================================

const TOAST_DURATIONS = {
    xp: 3000,
    levelup: 5000,
    achievement: 5000,
    achievementLegendary: 7000,
    streak: 4000,
    streakLost: 4000,
    quest: 4000,
    welcome: 5000  // Increased from 3000 to 5000
};

// ========================================
//   Toast Notification System
// ========================================

class GamificationToast {
    constructor() {
        this.container = null;
        this.queue = [];
        this.isProcessing = false;
        this.config = this.loadConfig();
        this.init();
    }

    loadConfig() {
        try {
            const configElement = document.getElementById('gamification-config');
            if (configElement) {
                return JSON.parse(configElement.textContent);
            }
        } catch (e) {
            console.error("Error loading gamification i18n config:", e);
        }
        return { i18n: {} };
    }

    getI18n(key, defaultValue) {
        return this.config.i18n[key] || defaultValue;
    }

    init() {
        // Create container if it doesn't exist
        if (!document.querySelector('.gamification-toast-container')) {
            this.container = document.createElement('div');
            this.container.className = 'gamification-toast-container';
            document.body.appendChild(this.container);
        } else {
            this.container = document.querySelector('.gamification-toast-container');
        }
    }

    /**
     * Show XP gain notification
     * @param {number} amount - XP amount gained
     * @param {string} reason - Reason for XP gain
     */
    showXPGain(amount, reason = '') {
        const toast = this.createToast('xp-gain', {
            mascotImage: MASCOT_IMAGES.xp,
            title: this.getI18n('xp_title', 'XP OTTENUTI'),
            contentType: 'xp',
            contentValue: amount,
            subtitle: reason
        });
        this.queueToast(toast, TOAST_DURATIONS.xp);
    }

    /**
     * Show level up notification
     * @param {number} newLevel - New level reached
     * @param {string} title - Optional level title
     */
    showLevelUp(newLevel, title = '') {
        // Trigger confetti for level ups
        this.triggerConfetti('level');

        const toast = this.createToast('level-up', {
            mascotImage: MASCOT_IMAGES.levelup,
            title: this.getI18n('level_up_title', 'LEVEL UP!'),
            contentType: 'level',
            contentValue: newLevel,
            subtitle: title || this.getI18n('level_up_subtitle', 'Hai raggiunto un nuovo livello!')
        });
        this.queueToast(toast, TOAST_DURATIONS.levelup);
    }

    /**
     * Show achievement unlock notification
     * @param {string} name - Achievement name
     * @param {string} description - Achievement description
     * @param {string} rarity - common, rare, epic, legendary
     * @param {string} icon - Achievement icon (unused, kept for API compatibility)
     */
    showAchievement(name, description, rarity = 'common', icon = '🏆') {
        // Trigger confetti for rare+ achievements
        if (['rare', 'epic', 'legendary'].includes(rarity)) {
            this.triggerConfetti(rarity);
        }

        // Select mascot based on rarity
        let mascotImage = MASCOT_IMAGES.achievement;
        if (rarity === 'legendary') {
            mascotImage = MASCOT_IMAGES.legendary;
        } else if (rarity === 'epic' || rarity === 'rare') {
            mascotImage = MASCOT_IMAGES.surprised;
        }

        const rarityClass = rarity !== 'common' ? rarity : '';
        const toast = this.createToast(`achievement ${rarityClass}`, {
            mascotImage: mascotImage,
            title: this.getI18n('achievement_title', 'NUOVO TRAGUARDO!'),
            contentType: 'achievement',
            contentValue: name,
            subtitle: description
        });
        const duration = rarity === 'legendary' ? TOAST_DURATIONS.achievementLegendary : TOAST_DURATIONS.achievement;
        this.queueToast(toast, duration);
    }

    /**
     * Show streak milestone notification
     * @param {number} streakCount - Current streak count
     * @param {string} streakType - Type of streak
     * @param {boolean} hasFreeze - Whether streak freeze is active
     */
    showStreak(streakCount, streakType = 'weekly', hasFreeze = false) {
        const toast = this.createToast('streak', {
            mascotImage: MASCOT_IMAGES.streak,
            title: this.getI18n('streak_title', 'STREAK!'),
            contentType: 'streak',
            contentValue: streakCount,
            subtitle: hasFreeze ? this.getI18n('streak_freeze', 'Freeze attivo') : '',
            hasFreeze: hasFreeze
        });
        this.queueToast(toast, TOAST_DURATIONS.streak);
    }

    /**
     * Show streak lost notification
     * @param {string} message - Encouragement message
     */
    showStreakLost(message = '') {
        const msg = message || this.getI18n('streak_lost_subtitle', 'Non mollare, riprova!');
        const toast = this.createToast('streak-lost', {
            mascotImage: MASCOT_IMAGES.sad,
            title: this.getI18n('streak_lost_title', 'STREAK PERSA'),
            contentType: 'text',
            contentValue: msg,
            subtitle: ''
        });
        this.queueToast(toast, TOAST_DURATIONS.streakLost);
    }

    /**
     * Show quest notification
     * @param {string} questName - Quest name
     * @param {string} description - Quest description
     */
    showQuest(questName, description = '') {
        const toast = this.createToast('quest', {
            mascotImage: MASCOT_IMAGES.quest,
            title: this.getI18n('quest_title', 'QUEST COMPLETATA!'),
            contentType: 'text',
            contentValue: questName,
            subtitle: description
        });
        this.queueToast(toast, TOAST_DURATIONS.quest);
    }

    /**
     * Show welcome notification
     * @param {string} username - User's name
     * @param {string} title - Custom title (optional)
     * @param {string} subtitle - Custom subtitle (optional)
     */
    showWelcome(username = '', title = '', subtitle = '') {
        let content = '';
        if (username) {
            content = this.getI18n('welcome_user', 'Ciao %(username)s!').replace('%(username)s', username);
        } else {
            content = this.getI18n('welcome_anonymous', 'Ciao!');
        }

        const toast = this.createToast('welcome', {
            mascotImage: MASCOT_IMAGES.welcome,
            title: title || this.getI18n('welcome_title', 'TI DIAMO IL BENTORNATO!'),
            contentType: 'text',
            contentValue: content,
            subtitle: subtitle || this.getI18n('welcome_subtitle', 'Pronto per giocare?')
        });
        this.queueToast(toast, TOAST_DURATIONS.welcome);
    }

    /**
     * Show Nudge notification for unlocked feature
     * @param {string} code - Feature code
     * @param {string} name - Feature name
     * @param {string} description - Feature description
     */
    showNudge(code, name, description) {
        const toast = this.createToast('nudge', {
            mascotImage: MASCOT_IMAGES.quest, // Curious mascot
            title: this.getI18n('nudge_title', 'NUOVA POSSIBILITÀ!'),
            contentType: 'text',
            contentValue: name,
            subtitle: description || this.getI18n('nudge_subtitle', 'Hai sbloccato questa funzione, provala subito!')
        });
        this.queueToast(toast, TOAST_DURATIONS.quest);
    }

    /**
     * Show Feature Unlock notification
     * @param {string} code - Feature code
     * @param {string} name - Feature name
     * @param {string} description - Feature description
     */
    showUnlock(code, name, description) {
        this.triggerConfetti('rare'); // Small celebration

        const toast = this.createToast('unlock', {
            mascotImage: MASCOT_IMAGES.levelup, // Celebration mascot
            title: this.getI18n('unlock_title', 'FUNZIONE SBLOCCATA!'),
            contentType: 'text',
            contentValue: name,
            subtitle: description
        });
        this.queueToast(toast, TOAST_DURATIONS.levelup);
    }

    /**
     * Create a toast element using safe DOM methods
     */
    createToast(type, { mascotImage, title, contentType, contentValue, subtitle, hasFreeze }) {
        const toast = document.createElement('div');
        toast.className = `gamification-toast ${type}`;

        // Create mascot image
        const mascotImg = document.createElement('img');
        mascotImg.src = mascotImage;
        mascotImg.alt = 'Chalky';
        mascotImg.className = 'mascot-icon';
        toast.appendChild(mascotImg);

        // Create content container
        const contentDiv = document.createElement('div');
        contentDiv.className = 'toast-content';

        // Create title span
        const titleSpan = document.createElement('span');
        titleSpan.className = 'toast-title';
        titleSpan.textContent = title;
        contentDiv.appendChild(titleSpan);

        // Create message div based on content type
        const messageDiv = document.createElement('div');
        messageDiv.className = 'toast-message';

        switch (contentType) {
            case 'xp':
                const xpSpan = document.createElement('span');
                xpSpan.className = 'xp-amount';
                xpSpan.textContent = `+${contentValue} XP`;
                messageDiv.appendChild(xpSpan);
                break;

            case 'level':
                const levelSpan = document.createElement('span');
                levelSpan.className = 'level-number';
                levelSpan.textContent = `Livello ${contentValue}`;
                messageDiv.appendChild(levelSpan);
                break;

            case 'achievement':
                const nameStrong = document.createElement('strong');
                nameStrong.textContent = contentValue;
                messageDiv.appendChild(nameStrong);
                break;

            case 'streak':
                const streakSpan = document.createElement('span');
                streakSpan.className = 'streak-count';
                streakSpan.textContent = `${contentValue} settimane`;
                messageDiv.appendChild(streakSpan);
                break;

            case 'text':
            default:
                const textSpan = document.createElement('span');
                textSpan.textContent = contentValue;
                messageDiv.appendChild(textSpan);
        }

        contentDiv.appendChild(messageDiv);

        // Create subtitle if present
        if (subtitle) {
            const subtitleSpan = document.createElement('span');
            subtitleSpan.className = 'toast-subtitle';

            if (hasFreeze) {
                const freezeSpan = document.createElement('span');
                freezeSpan.className = 'streak-freeze';
                freezeSpan.textContent = '❄️ ' + subtitle;
                subtitleSpan.appendChild(freezeSpan);
            } else {
                subtitleSpan.textContent = subtitle;
            }

            contentDiv.appendChild(subtitleSpan);
        }

        toast.appendChild(contentDiv);

        return toast;
    }

    /**
     * Queue and display toast
     */
    queueToast(toast, duration) {
        this.queue.push({ toast, duration });
        if (!this.isProcessing) {
            this.processQueue();
        }
    }

    /**
     * Process toast queue
     */
    async processQueue() {
        this.isProcessing = true;

        while (this.queue.length > 0) {
            const { toast, duration } = this.queue.shift();
            this.container.appendChild(toast);

            // Wait for display duration
            await this.delay(duration);

            // Add hiding animation
            toast.classList.add('hiding');

            // Wait for animation to complete
            await this.delay(400);

            // Remove toast
            if (toast.parentNode) {
                toast.parentNode.removeChild(toast);
            }

            // Small gap between toasts
            if (this.queue.length > 0) {
                await this.delay(200);
            }
        }

        this.isProcessing = false;
    }

    /**
     * Utility delay function
     */
    delay(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    /**
     * Trigger confetti effect
     */
    triggerConfetti(type = 'default') {
        if (typeof ConfettiEffect !== 'undefined') {
            ConfettiEffect.fire(type);
        }
    }
}

// ... ConfettiEffect code similar to existing ...

// ========================================
//   Navbar Badge "vivo" (§11-quater)
//   Feedback ambient e sobrio: anello di progresso + pulse su XP + glow su
//   level-up. Sostituisce il toast per i micro-eventi. È idempotente rispetto
//   ai valori già renderizzati server-side dal context processor (base.html).
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
     * Micro guadagno XP → count-up + pulse, nessun toast (scala d'intensità).
     * Il valore renderizzato (data-current-xp) è già quello nuovo: animiamo
     * dal valore precedente (nuovo - amount) a quello corrente.
     */
    addXP(amount) {
        if (!this.available) return;
        const target = parseInt(this.el.dataset.currentXp || '0', 10);
        const delta = parseInt(amount, 10) || 0;
        this._countUp(Math.max(0, target - delta), target);
        this._pulse('badge-pulse');
        this._refreshRing();
    }

    /** Level-up → glow + aggiornamento livello (l'unico momento forte sul badge). */
    levelUp(newLevel) {
        if (!this.available) return;
        if (newLevel != null && this.levelEl) {
            this.levelEl.textContent = newLevel;
            this.el.dataset.level = newLevel;
        }
        // Il server ha già renderizzato current_xp/progress del nuovo livello.
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
        // Forza il reflow per ri-triggerare l'animazione su eventi ravvicinati.
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

// Global instances
let gamificationToast = null;
let gamificationBadge = null;

function getGamificationBadge() {
    if (!gamificationBadge) {
        gamificationBadge = new GamificationBadge();
    }
    return gamificationBadge;
}

/**
 * Cap anti-invasività (§11): al più UN toast celebrativo "capped" per sessione
 * di navigazione (sessionStorage). Il level-up ne è esente — è l'unico toast
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
        // sessionStorage non disponibile (privacy mode) → non bloccare.
        return true;
    }
}

// Global function to trigger gamification notifications
function showGamificationEvent(type, data) {
    if (!gamificationToast) {
        gamificationToast = new GamificationToast();
    }
    const badge = getGamificationBadge();

    switch (type) {
        case 'xp':
            // Scala d'intensità: micro XP → solo badge (count-up + pulse), niente toast.
            badge.addXP(data.amount);
            break;
        case 'levelup':
            // Momento forte: glow del badge + l'unico toast celebrativo giustificato.
            badge.levelUp(data.level);
            gamificationToast.showLevelUp(data.level, data.title);
            break;
        case 'achievement':
            badge.pulse();
            if (cappedToastAllowed()) {
                gamificationToast.showAchievement(
                    data.name,
                    data.description,
                    data.rarity,
                    data.icon
                );
            }
            break;
        case 'streak':
            badge.pulse();
            if (cappedToastAllowed()) {
                gamificationToast.showStreak(data.count, data.type, data.hasFreeze);
            }
            break;
        case 'quest':
            badge.pulse();
            if (cappedToastAllowed()) {
                gamificationToast.showQuest(data.name, data.description);
            }
            break;
        case 'streak_lost':
            gamificationToast.showStreakLost(data.message);
            break;
        case 'welcome':
            gamificationToast.showWelcome(data.username, data.title, data.subtitle);
            break;
        case 'nudge':
            // Scoperta funzioni (obiettivo #3): resta un toast azionabile.
            gamificationToast.showNudge(data.code, data.name, data.description);
            break;
        case 'unlock':
            gamificationToast.showUnlock(data.code, data.name, data.description);
            break;
    }
}

/**
 * Demo function to test all effects with Chalky mascot
 * Call from browser console: testGamificationEffects()
 */
function testGamificationEffects() {
    console.log('Testing gamification effects with Chalky mascot...');

    // Test welcome
    setTimeout(() => {
        showGamificationEvent('welcome', { username: 'Atleta' });
    }, 500);

    // Test XP gain
    setTimeout(() => {
        showGamificationEvent('xp', { amount: 50, reason: 'Vittoria partita' });
    }, 4000);

    // Test level up
    setTimeout(() => {
        showGamificationEvent('levelup', { level: 5, title: 'Talento del Biliardo' });
    }, 8000);

    // Test achievement (common)
    setTimeout(() => {
        showGamificationEvent('achievement', {
            name: 'Prima Vittoria',
            description: 'Hai vinto la tua prima partita!',
            rarity: 'common'
        });
    }, 14000);

    // Test achievement (rare) - shows surprised Chalky
    setTimeout(() => {
        showGamificationEvent('achievement', {
            name: 'Star Locale',
            description: 'Hai vinto 10 partite consecutive!',
            rarity: 'rare'
        });
    }, 20000);

    // Test streak
    setTimeout(() => {
        showGamificationEvent('streak', {
            count: 5,
            type: 'weekly',
            hasFreeze: true
        });
    }, 26000);

    // Test quest
    setTimeout(() => {
        showGamificationEvent('quest', {
            name: 'Sfida Settimanale',
            description: 'Gioca 3 partite questa settimana'
        });
    }, 31000);

    // Test streak lost
    setTimeout(() => {
        showGamificationEvent('streak_lost', {
            message: 'Non mollare, riprova!'
        });
    }, 36000);

    // Test legendary achievement - shows king Chalky
    setTimeout(() => {
        showGamificationEvent('achievement', {
            name: 'Leggenda del Biliardo',
            description: 'Hai raggiunto 1000 vittorie!',
            rarity: 'legendary'
        });
    }, 41000);

    console.log('Chalky will appear in 9 different poses over 45 seconds!');
}

// Expose test function to window for console access
window.testGamificationEffects = testGamificationEffects;
window.showGamificationEvent = showGamificationEvent;

// Export for module systems if needed
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        GamificationToast,
        ConfettiEffect,
        XPCounter,
        ProgressBarAnimation,
        showGamificationEvent,
        testGamificationEffects
    };
}
