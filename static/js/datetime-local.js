/**
 * datetime-local.js - Optional browser-local time conversion
 *
 * This script converts <time class="datetime-local"> elements to display
 * the user's browser-local time instead of Italian time.
 *
 * Usage:
 *   Include this script on pages where you want browser-local times:
 *   <script src="{{ url_for('static', filename='js/datetime-local.js') }}"></script>
 *
 * How it works:
 *   1. Finds all <time class="datetime-local"> elements
 *   2. Parses the ISO UTC timestamp from the datetime attribute
 *   3. Converts to browser-local time using Intl.DateTimeFormat
 *   4. Updates the displayed text
 *
 * Note: If JavaScript is disabled or this script is not included,
 * the server-rendered Italian time (Europe/Rome) is displayed.
 */

(function() {
    'use strict';

    /**
     * Format a Date object as dd/mm/yyyy, HH:MM in local timezone
     * @param {Date} date - The date to format
     * @returns {string} Formatted date string
     */
    function formatLocalDateTime(date) {
        const day = String(date.getDate()).padStart(2, '0');
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const year = date.getFullYear();
        const hours = String(date.getHours()).padStart(2, '0');
        const minutes = String(date.getMinutes()).padStart(2, '0');

        return `${day}/${month}/${year}, ${hours}:${minutes}`;
    }

    /**
     * Convert all datetime-local elements to browser-local time
     */
    function convertToLocalTime() {
        const elements = document.querySelectorAll('time.datetime-local[datetime]');

        elements.forEach(function(element) {
            const isoString = element.getAttribute('datetime');
            if (!isoString) return;

            try {
                const date = new Date(isoString);
                if (isNaN(date.getTime())) return;

                element.textContent = formatLocalDateTime(date);
            } catch (e) {
                // Keep original content on error
                console.warn('datetime-local: Failed to parse', isoString, e);
            }
        });
    }

    // Run when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', convertToLocalTime);
    } else {
        convertToLocalTime();
    }

    // Export for manual use if needed
    window.DateTimeLocal = {
        convert: convertToLocalTime,
        format: formatLocalDateTime
    };
})();
