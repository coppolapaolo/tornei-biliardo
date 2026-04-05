"""Regression tests for SSE event store memory leak (P4 in deferred-work).

The `_events` dict in `routes/sse.py` accumulates scope_id keys indefinitely
because the per-scope_id cleanup only trims stale events from the list but
never removes the key itself. These tests verify that stale scope_ids are
pruned by a throttled sweep.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from routes import sse
from routes.sse import EventScope, MAX_EVENT_AGE, emit_event, _get_events_since


@pytest.fixture(autouse=True)
def reset_event_store():
    """Clear event store and sweep timestamp before each test."""
    with sse._events_lock:
        for scope_dict in sse._events.values():
            scope_dict.clear()
        sse._last_sweep = 0.0
    yield
    with sse._events_lock:
        for scope_dict in sse._events.values():
            scope_dict.clear()
        sse._last_sweep = 0.0


def test_emit_event_stores_event():
    """Sanity: emit_event records an event under the given scope_id."""
    emit_event(EventScope.GARA, 42, "match_completed", {"match_id": 7})
    events = _get_events_since(EventScope.GARA, 42, 0.0)
    assert len(events) == 1
    assert events[0]["type"] == "match_completed"
    assert events[0]["data"] == {"match_id": 7}


def test_stale_scope_id_key_removed_after_sweep():
    """After MAX_EVENT_AGE, the scope_id key itself is pruned, not just its events.

    This is the core regression: previously the list was trimmed to [] but the
    scope_id key persisted forever, leaking memory.
    """
    # Use a realistic base time (not 100.0) to satisfy SWEEP_INTERVAL throttle
    base = 1_700_000_000.0
    with patch("routes.sse.time.time", return_value=base):
        emit_event(EventScope.GARA, 42, "match_completed", {"match_id": 7})
    assert 42 in sse._events[EventScope.GARA.value]

    # Jump past MAX_EVENT_AGE + SWEEP_INTERVAL (bigger of the two) and emit to
    # another scope_id. This should trigger the throttled sweep which prunes
    # the stale key 42.
    future = base + MAX_EVENT_AGE + 60
    with patch("routes.sse.time.time", return_value=future):
        emit_event(EventScope.GARA, 99, "match_completed", {"match_id": 8})

    # Key 42 must be gone (stale), key 99 still present (just emitted).
    assert 42 not in sse._events[EventScope.GARA.value]
    assert 99 in sse._events[EventScope.GARA.value]


def test_poll_also_triggers_sweep():
    """_get_events_since must also prune stale keys, since polling is the
    main sustained traffic source (emits can stop while polls continue)."""
    base = 1_700_000_000.0
    with patch("routes.sse.time.time", return_value=base):
        emit_event(EventScope.USER, 1, "xp_gained", {"xp": 10})
        emit_event(EventScope.USER, 2, "xp_gained", {"xp": 10})
    assert 1 in sse._events[EventScope.USER.value]
    assert 2 in sse._events[EventScope.USER.value]

    # Only poll for scope_id=2; scope_id=1 should still get swept.
    future = base + MAX_EVENT_AGE + 60
    with patch("routes.sse.time.time", return_value=future):
        _get_events_since(EventScope.USER, 2, 0.0)

    assert 1 not in sse._events[EventScope.USER.value]
    assert 2 not in sse._events[EventScope.USER.value]  # also stale now


def test_sweep_is_throttled():
    """Sweep must not run on every single emit — that would be O(N) per call.
    With SWEEP_INTERVAL of 30s, two rapid emits should only trigger one sweep."""
    base = 1_700_000_000.0
    # Seed a stale key
    with patch("routes.sse.time.time", return_value=base):
        emit_event(EventScope.TRIO, 1, "rack_added", {})

    # First emit after MAX_EVENT_AGE → sweeps (prunes key 1)
    t1 = base + MAX_EVENT_AGE + 5
    with patch("routes.sse.time.time", return_value=t1):
        emit_event(EventScope.TRIO, 2, "rack_added", {})
    assert 1 not in sse._events[EventScope.TRIO.value]
    first_sweep_ts = sse._last_sweep
    assert first_sweep_ts == t1

    # Second emit just 1 second later → should NOT re-sweep (throttled).
    # Verify by reading _last_sweep, which only advances when sweep ran.
    t2 = t1 + 1
    with patch("routes.sse.time.time", return_value=t2):
        emit_event(EventScope.TRIO, 3, "rack_added", {})
    assert sse._last_sweep == first_sweep_ts  # unchanged — no sweep ran


def test_fresh_scope_id_not_pruned():
    """Recently-updated scope_ids must survive the sweep."""
    base = 1_700_000_000.0
    with patch("routes.sse.time.time", return_value=base):
        emit_event(EventScope.MATCH, 10, "rack_added", {})

    # Only 10s later — well within MAX_EVENT_AGE
    with patch("routes.sse.time.time", return_value=base + 10):
        emit_event(EventScope.MATCH, 20, "rack_added", {})

    # Force a sweep by advancing past SWEEP_INTERVAL but not past MAX_EVENT_AGE
    # for key 20 (emitted at base+10, so stale threshold is base+10+60=base+70)
    with patch("routes.sse.time.time", return_value=base + 45):
        emit_event(EventScope.MATCH, 30, "rack_added", {})

    # Key 10 was emitted at base (45s ago → within 60s) → still alive
    assert 10 in sse._events[EventScope.MATCH.value]
    assert 20 in sse._events[EventScope.MATCH.value]
    assert 30 in sse._events[EventScope.MATCH.value]
