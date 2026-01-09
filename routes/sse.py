# routes/sse.py
"""Server-Sent Events (SSE) for real-time updates.

Provides SSE endpoints for real-time updates to trio matches,
allowing waiting players to see rack updates without page refresh.
"""

import json
import time
from collections import defaultdict
from threading import Lock
from flask import Blueprint, Response
from flask_login import login_required

sse_bp = Blueprint("sse", __name__, url_prefix="/sse")

# Simple in-memory event store for trio updates
# Structure: {trio_id: [(event_type, data, timestamp), ...]}
_trio_events: dict = defaultdict(list)
_events_lock = Lock()

# Max age for events (60 seconds)
MAX_EVENT_AGE = 60


def emit_trio_event(trio_id: int, event_type: str, data: dict) -> None:
    """Emit an event for a trio match.

    Called when a rack is added, removed, or match state changes.

    Args:
        trio_id: ID of the trio match
        event_type: Type of event (rack_added, rack_removed, match_updated)
        data: Event data to send to clients
    """
    with _events_lock:
        now = time.time()
        # Add new event
        _trio_events[trio_id].append((event_type, data, now))
        # Cleanup old events
        _trio_events[trio_id] = [
            (et, d, ts)
            for et, d, ts in _trio_events[trio_id]
            if now - ts < MAX_EVENT_AGE
        ]


@sse_bp.route("/trio/<int:trio_id>")
@login_required
def trio_stream(trio_id: int):
    """SSE stream for trio match updates.

    Returns a Server-Sent Events stream that clients can subscribe to
    for real-time updates on the trio match.
    """

    def generate():
        last_check = time.time()

        # Send initial connection message
        yield f"event: connected\ndata: {json.dumps({'trio_id': trio_id})}\n\n"

        while True:
            # Check for new events
            with _events_lock:
                events = _trio_events.get(trio_id, [])
                new_events = [(et, d, ts) for et, d, ts in events if ts > last_check]

            for event_type, data, _ in new_events:
                yield f"event: {event_type}\ndata: {json.dumps(data)}\n\n"

            last_check = time.time()

            # Send keepalive every 15 seconds
            yield ": keepalive\n\n"

            # Sleep for 2 seconds before checking again
            time.sleep(2)

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )
