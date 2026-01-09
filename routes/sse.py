# routes/sse.py
"""Server-Sent Events (SSE) for real-time updates.

Provides SSE endpoints for real-time updates across the application:
- Trio matches: rack updates, undo, forfeit
- Gara: match results, round changes, inscriptions
- User: XP gains, level-ups, achievements

Architecture:
    Domain Events → EventBus → SSE Bridge → SSE Store → Browser EventSource
    (see routes/sse_bridge.py for event routing)
"""

import json
import time
from collections import defaultdict
from threading import Lock
from typing import Dict, List, Tuple, Literal

from flask import Blueprint, Response, abort
from flask_login import login_required, current_user

sse_bp = Blueprint("sse", __name__, url_prefix="/sse")

# ═══════════════════════════════════════════════════════════════════════════
# Event Store
# ═══════════════════════════════════════════════════════════════════════════

# Scope types supported
ScopeType = Literal["trio", "gara", "user"]

# Multi-scope event store
# Structure: {scope: {scope_id: [(event_type, data, timestamp), ...]}}
_events: Dict[str, Dict[int, List[Tuple[str, dict, float]]]] = {
    "trio": defaultdict(list),
    "gara": defaultdict(list),
    "user": defaultdict(list),
}
_events_lock = Lock()

# Max age for events (60 seconds) - auto-cleanup
MAX_EVENT_AGE = 60


# ═══════════════════════════════════════════════════════════════════════════
# Emit Functions
# ═══════════════════════════════════════════════════════════════════════════


def emit_event(scope: ScopeType, scope_id: int, event_type: str, data: dict) -> None:
    """Emit an SSE event for any scope.

    This is the main entry point for emitting events. Called by:
    - SSE Bridge (routes/sse_bridge.py) for domain events
    - Direct calls for trio-specific events (backward compatibility)

    Args:
        scope: Event scope ("trio", "gara", "user")
        scope_id: ID within scope (trio_match.id, gara.id, user.id)
        event_type: Type of event (e.g., "match_completed", "xp_gained")
        data: Event payload to send to clients
    """
    if scope not in _events:
        raise ValueError(f"Invalid scope: {scope}. Must be one of: {list(_events.keys())}")

    with _events_lock:
        now = time.time()
        # Add new event
        _events[scope][scope_id].append((event_type, data, now))
        # Cleanup old events for this scope_id
        _events[scope][scope_id] = [
            (et, d, ts)
            for et, d, ts in _events[scope][scope_id]
            if now - ts < MAX_EVENT_AGE
        ]


def emit_trio_event(trio_id: int, event_type: str, data: dict) -> None:
    """Emit an event for a trio match (backward compatibility).

    Called when a rack is added, removed, or match state changes.

    Args:
        trio_id: ID of the trio match
        event_type: Type of event (rack_added, rack_removed, match_updated)
        data: Event data to send to clients
    """
    emit_event("trio", trio_id, event_type, data)


def emit_gara_event(gara_id: int, event_type: str, data: dict) -> None:
    """Emit an event for a gara (competition).

    Called when match results change, rounds start/complete, etc.

    Args:
        gara_id: ID of the gara
        event_type: Type of event (match_completed, round_started, etc.)
        data: Event data to send to clients
    """
    emit_event("gara", gara_id, event_type, data)


def emit_user_event(user_id: int, event_type: str, data: dict) -> None:
    """Emit an event for a user.

    Called for user-specific notifications (XP, level-ups, achievements).

    Args:
        user_id: ID of the user
        event_type: Type of event (xp_gained, level_up, achievement, etc.)
        data: Event data to send to clients
    """
    emit_event("user", user_id, event_type, data)


# ═══════════════════════════════════════════════════════════════════════════
# Stream Generator
# ═══════════════════════════════════════════════════════════════════════════


def _create_event_stream(scope: ScopeType, scope_id: int):
    """Create an SSE stream generator for a scope.

    Args:
        scope: Event scope
        scope_id: ID within scope

    Yields:
        SSE formatted event strings
    """
    last_check = time.time()

    # Send initial connection message
    yield f"event: connected\ndata: {json.dumps({scope: scope_id})}\n\n"

    while True:
        # Check for new events
        with _events_lock:
            events = _events[scope].get(scope_id, [])
            new_events = [(et, d, ts) for et, d, ts in events if ts > last_check]

        for event_type, data, _ in new_events:
            yield f"event: {event_type}\ndata: {json.dumps(data)}\n\n"

        last_check = time.time()

        # Send keepalive every 15 seconds
        yield ": keepalive\n\n"

        # Sleep for 2 seconds before checking again
        time.sleep(2)


def _create_sse_response(scope: ScopeType, scope_id: int) -> Response:
    """Create an SSE Response object.

    Args:
        scope: Event scope
        scope_id: ID within scope

    Returns:
        Flask Response with SSE stream
    """
    return Response(
        _create_event_stream(scope, scope_id),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


# ═══════════════════════════════════════════════════════════════════════════
# SSE Endpoints
# ═══════════════════════════════════════════════════════════════════════════


@sse_bp.route("/trio/<int:trio_id>")
@login_required
def trio_stream(trio_id: int):
    """SSE stream for trio match updates.

    Events:
        - connected: Initial connection confirmation
        - rack_added: New rack result
        - rack_removed: Undo performed
        - forfeit: Player forfeited
        - confirmed: Result confirmed
    """
    return _create_sse_response("trio", trio_id)


@sse_bp.route("/gara/<int:gara_id>")
@login_required
def gara_stream(gara_id: int):
    """SSE stream for gara (competition) updates.

    Events:
        - connected: Initial connection confirmation
        - match_completed: A match finished
        - match_updated: Match status changed (pending→playing)
        - round_started: New round created
        - inscription_added: New player registered
        - gara_completed: Gara finished
    """
    return _create_sse_response("gara", gara_id)


@sse_bp.route("/user/<int:user_id>")
@login_required
def user_stream(user_id: int):
    """SSE stream for user-specific updates.

    Security: Only allows subscribing to own user stream.

    Events:
        - connected: Initial connection confirmation
        - xp_gained: XP earned
        - level_up: New level reached
        - achievement: Achievement unlocked
        - my_match_completed: Own match finished
    """
    # Security: only allow subscribing to own events
    if current_user.id != user_id:
        abort(403)

    return _create_sse_response("user", user_id)
