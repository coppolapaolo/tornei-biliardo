/**
 * Polling utility for real-time updates (replaces SSE).
 *
 * SSE connections were blocking uWSGI workers on PythonAnywhere.
 * Polling with 3s interval provides near-real-time updates without blocking.
 *
 * See ADR-021 for details.
 */

window.Polling = (function() {
    'use strict';

    var DEFAULT_INTERVAL = 3000; // 3 seconds

    /**
     * Create a poller for a specific scope.
     *
     * @param {Object} config - Configuration object
     * @param {string} config.url - Polling endpoint URL (e.g., '/sse/poll/gara/8')
     * @param {function} config.onEvent - Callback for each event: function(event)
     * @param {number} [config.interval=3000] - Polling interval in ms
     * @param {function} [config.onError] - Error callback: function(error)
     * @returns {Object} Poller instance with start() and stop() methods
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

        // Start with current time to avoid fetching old events on page load
        var lastTimestamp = Date.now() / 1000;
        var timerId = null;
        var running = false;

        function poll() {
            if (!running) return;

            fetch(url + '?since=' + lastTimestamp)
                .then(function(response) {
                    if (!response.ok) throw new Error('Poll failed: ' + response.status);
                    return response.json();
                })
                .then(function(result) {
                    lastTimestamp = result.timestamp;
                    if (result.events && result.events.length > 0) {
                        result.events.forEach(onEvent);
                    }
                })
                .catch(onError);
        }

        return {
            start: function() {
                if (running) return;
                running = true;
                // Initial poll after short delay
                setTimeout(poll, 500);
                // Then poll at regular intervals
                timerId = setInterval(poll, interval);
            },
            stop: function() {
                running = false;
                if (timerId) {
                    clearInterval(timerId);
                    timerId = null;
                }
            }
        };
    }

    /**
     * Convenience method: create and start a poller that reloads on specific events.
     *
     * @param {Object} config - Configuration object
     * @param {string} config.url - Polling endpoint URL
     * @param {string[]} config.reloadOn - Event types that trigger page reload
     * @param {number} [config.interval=3000] - Polling interval in ms
     * @returns {Object} Poller instance
     */
    function reloadOnEvents(config) {
        var reloadEvents = config.reloadOn || [];

        var poller = create({
            url: config.url,
            interval: config.interval,
            onEvent: function(event) {
                if (reloadEvents.includes(event.type)) {
                    console.log('[Polling] ' + event.type + ', reloading...');
                    location.reload();
                }
            }
        });

        poller.start();
        return poller;
    }

    return {
        create: create,
        reloadOnEvents: reloadOnEvents
    };
})();
