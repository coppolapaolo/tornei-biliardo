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
//   Toast Notification System
// ========================================

class GamificationToast {
    constructor() {
        this.container = null;
        this.queue = [];
        this.isProcessing = false;
        this.init();
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
            title: 'XP GUADAGNATI',
            contentType: 'xp',
            contentValue: amount,
            subtitle: reason
        });
        this.queueToast(toast, 3000);
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
            title: 'LEVEL UP!',
            contentType: 'level',
            contentValue: newLevel,
            subtitle: title || 'Hai raggiunto un nuovo livello!'
        });
        this.queueToast(toast, 5000);
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
            title: 'ACHIEVEMENT SBLOCCATO!',
            contentType: 'achievement',
            contentValue: name,
            subtitle: description
        });
        this.queueToast(toast, rarity === 'legendary' ? 7000 : 5000);
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
            title: 'STREAK!',
            contentType: 'streak',
            contentValue: streakCount,
            subtitle: hasFreeze ? 'Freeze attivo' : '',
            hasFreeze: hasFreeze
        });
        this.queueToast(toast, 4000);
    }

    /**
     * Show streak lost notification
     * @param {string} message - Encouragement message
     */
    showStreakLost(message = 'Non mollare, riprova!') {
        const toast = this.createToast('streak-lost', {
            mascotImage: MASCOT_IMAGES.sad,
            title: 'STREAK PERSA',
            contentType: 'text',
            contentValue: message,
            subtitle: ''
        });
        this.queueToast(toast, 4000);
    }

    /**
     * Show quest notification
     * @param {string} questName - Quest name
     * @param {string} description - Quest description
     */
    showQuest(questName, description = '') {
        const toast = this.createToast('quest', {
            mascotImage: MASCOT_IMAGES.quest,
            title: 'NUOVA QUEST!',
            contentType: 'text',
            contentValue: questName,
            subtitle: description
        });
        this.queueToast(toast, 4000);
    }

    /**
     * Show welcome notification
     * @param {string} username - User's name
     */
    showWelcome(username = '') {
        const toast = this.createToast('welcome', {
            mascotImage: MASCOT_IMAGES.welcome,
            title: 'BENTORNATO!',
            contentType: 'text',
            contentValue: username ? `Ciao ${username}!` : 'Ciao!',
            subtitle: 'Pronto per giocare?'
        });
        this.queueToast(toast, 3000);
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

// ========================================
//   Confetti Effect System
// ========================================

class ConfettiEffect {
    static canvas = null;
    static ctx = null;
    static particles = [];
    static animationId = null;

    static init() {
        if (this.canvas) return;

        this.canvas = document.createElement('canvas');
        this.canvas.id = 'confetti-canvas';
        document.body.appendChild(this.canvas);
        this.ctx = this.canvas.getContext('2d');
        this.resize();

        window.addEventListener('resize', () => this.resize());
    }

    static resize() {
        if (!this.canvas) return;
        this.canvas.width = window.innerWidth;
        this.canvas.height = window.innerHeight;
    }

    /**
     * Fire confetti effect
     * @param {string} type - level, rare, epic, legendary
     */
    static fire(type = 'default') {
        this.init();

        const colors = this.getColors(type);
        const particleCount = this.getParticleCount(type);

        // Create particles
        for (let i = 0; i < particleCount; i++) {
            this.particles.push(this.createParticle(colors));
        }

        // Start animation if not running
        if (!this.animationId) {
            this.animate();
        }
    }

    static getColors(type) {
        const colorSets = {
            level: ['#7c3aed', '#a78bfa', '#fbbf24', '#f59e0b', '#ffffff'],
            rare: ['#3b82f6', '#60a5fa', '#93c5fd', '#ffffff'],
            epic: ['#7c3aed', '#a78bfa', '#c4b5fd', '#fbbf24'],
            legendary: ['#fbbf24', '#f59e0b', '#fcd34d', '#ffffff', '#ef4444'],
            default: ['#4ade80', '#22c55e', '#16a34a', '#fbbf24', '#ffffff']
        };
        return colorSets[type] || colorSets.default;
    }

    static getParticleCount(type) {
        const counts = {
            level: 100,
            rare: 80,
            epic: 120,
            legendary: 150,
            default: 60
        };
        return counts[type] || counts.default;
    }

    static createParticle(colors) {
        const angle = Math.random() * Math.PI * 2;
        const velocity = 8 + Math.random() * 8;

        return {
            x: this.canvas.width / 2,
            y: this.canvas.height / 2,
            vx: Math.cos(angle) * velocity,
            vy: Math.sin(angle) * velocity - 5,
            color: colors[Math.floor(Math.random() * colors.length)],
            size: 5 + Math.random() * 10,
            rotation: Math.random() * 360,
            rotationSpeed: (Math.random() - 0.5) * 10,
            gravity: 0.3,
            friction: 0.99,
            opacity: 1,
            shape: Math.random() > 0.5 ? 'rect' : 'circle'
        };
    }

    static animate() {
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);

        for (let i = this.particles.length - 1; i >= 0; i--) {
            const p = this.particles[i];

            // Update physics
            p.vy += p.gravity;
            p.vx *= p.friction;
            p.vy *= p.friction;
            p.x += p.vx;
            p.y += p.vy;
            p.rotation += p.rotationSpeed;
            p.opacity -= 0.01;

            // Remove dead particles
            if (p.opacity <= 0 || p.y > this.canvas.height + 50) {
                this.particles.splice(i, 1);
                continue;
            }

            // Draw particle
            this.ctx.save();
            this.ctx.translate(p.x, p.y);
            this.ctx.rotate(p.rotation * Math.PI / 180);
            this.ctx.globalAlpha = p.opacity;
            this.ctx.fillStyle = p.color;

            if (p.shape === 'rect') {
                this.ctx.fillRect(-p.size / 2, -p.size / 4, p.size, p.size / 2);
            } else {
                this.ctx.beginPath();
                this.ctx.arc(0, 0, p.size / 2, 0, Math.PI * 2);
                this.ctx.fill();
            }

            this.ctx.restore();
        }

        // Continue animation or stop
        if (this.particles.length > 0) {
            this.animationId = requestAnimationFrame(() => this.animate());
        } else {
            this.animationId = null;
        }
    }
}

// ========================================
//   XP Counter Animation
// ========================================

class XPCounter {
    /**
     * Animate XP counter from current to new value
     * @param {HTMLElement} element - Element to animate
     * @param {number} startValue - Starting XP value
     * @param {number} endValue - Ending XP value
     * @param {number} duration - Animation duration in ms
     */
    static animate(element, startValue, endValue, duration = 1000) {
        if (!element) return;

        const startTime = performance.now();
        const difference = endValue - startValue;

        element.classList.add('counting');

        const update = (currentTime) => {
            const elapsed = currentTime - startTime;
            const progress = Math.min(elapsed / duration, 1);

            // Ease out cubic
            const easeProgress = 1 - Math.pow(1 - progress, 3);

            const currentValue = Math.round(startValue + (difference * easeProgress));
            element.textContent = currentValue.toLocaleString();

            if (progress < 1) {
                requestAnimationFrame(update);
            } else {
                element.classList.remove('counting');
            }
        };

        requestAnimationFrame(update);
    }
}

// ========================================
//   Progress Bar Animation
// ========================================

class ProgressBarAnimation {
    /**
     * Animate progress bar fill
     * @param {HTMLElement} element - Progress bar fill element
     * @param {number} percentage - Target percentage (0-100)
     */
    static animate(element, percentage) {
        if (!element) return;

        // Set initial state
        element.style.width = '0%';

        // Trigger animation after a small delay
        requestAnimationFrame(() => {
            requestAnimationFrame(() => {
                element.style.width = `${Math.min(100, Math.max(0, percentage))}%`;
            });
        });
    }
}

// ========================================
//   Event Listeners and Integration
// ========================================

// Global toast instance
let gamificationToast = null;

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', function() {
    gamificationToast = new GamificationToast();

    // Expose to window for console access
    window.gamificationToast = gamificationToast;

    // Initialize confetti canvas
    ConfettiEffect.init();

    // Listen for gamification events from server
    initGamificationEventListeners();

    // Animate any progress bars on page
    document.querySelectorAll('.xp-progress-fill').forEach(bar => {
        const percentage = bar.dataset.percentage || 0;
        ProgressBarAnimation.animate(bar, parseFloat(percentage));
    });
});

/**
 * Initialize event listeners for gamification events
 */
function initGamificationEventListeners() {
    // Listen for custom events dispatched from server responses
    document.addEventListener('gamification:xp', function(e) {
        const { amount, reason } = e.detail;
        gamificationToast.showXPGain(amount, reason);
    });

    document.addEventListener('gamification:levelup', function(e) {
        const { level, title } = e.detail;
        gamificationToast.showLevelUp(level, title);
    });

    document.addEventListener('gamification:achievement', function(e) {
        const { name, description, rarity, icon } = e.detail;
        gamificationToast.showAchievement(name, description, rarity, icon);
    });

    document.addEventListener('gamification:streak', function(e) {
        const { count, type, hasFreeze } = e.detail;
        gamificationToast.showStreak(count, type, hasFreeze);
    });
}

/**
 * Global function to trigger gamification notifications
 * Can be called from inline scripts or AJAX responses
 */
function showGamificationEvent(type, data) {
    if (!gamificationToast) {
        gamificationToast = new GamificationToast();
    }

    switch (type) {
        case 'xp':
            gamificationToast.showXPGain(data.amount, data.reason);
            break;
        case 'levelup':
            gamificationToast.showLevelUp(data.level, data.title);
            break;
        case 'achievement':
            gamificationToast.showAchievement(
                data.name,
                data.description,
                data.rarity,
                data.icon
            );
            break;
        case 'streak':
            gamificationToast.showStreak(data.count, data.type, data.hasFreeze);
            break;
        case 'streak_lost':
            gamificationToast.showStreakLost(data.message);
            break;
        case 'quest':
            gamificationToast.showQuest(data.name, data.description);
            break;
        case 'welcome':
            gamificationToast.showWelcome(data.username);
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
        showGamificationEvent('welcome', { username: 'Giocatore' });
    }, 500);

    // Test XP gain
    setTimeout(() => {
        showGamificationEvent('xp', { amount: 50, reason: 'Vittoria partita' });
    }, 4000);

    // Test level up
    setTimeout(() => {
        showGamificationEvent('levelup', { level: 5, title: 'Giocatore Esperto' });
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
            name: 'Campione Locale',
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
