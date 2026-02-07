"""
Re-export shim for match services.

Split into match_service.py, rack_service.py, result_service.py
for maintainability (Round 3 P4). All external imports continue
to work unchanged via this module.
"""

from .match_service import MatchService
from .rack_service import RackService
from .result_service import MatchResultService

from models.exceptions import InvalidTransitionError


# Helper function for simplified rack addition
def add_rack(match_id: int, winner_id: int, added_by_id: int):
    """
    Simplified helper to add a rack to a match.

    Args:
        match_id: ID of the match
        winner_id: ID of the player who won the rack
        added_by_id: ID of the user adding the rack

    Returns:
        The created Rack instance

    Raises:
        ValueError: If match not found or rack cannot be added
    """
    from models.base import db
    from .models import Match, Rack

    match = db.session.get(Match, match_id)
    if not match:
        raise ValueError(f"Match {match_id} not found")

    # Determine next rack number
    from sqlalchemy import func

    max_rack = (
        db.session.query(func.max(Rack.rack_number))
        .filter_by(match_id=match_id)
        .scalar()
    )
    rack_number = (max_rack or 0) + 1

    # Use RackService to add the rack with validation
    return RackService.add_rack_result(
        match_id=match_id,
        rack_number=rack_number,
        winner_id=winner_id,
        reported_by_id=added_by_id,
        confirmed_by_player=False,
        validated_by_admin=False,
    )


__all__ = [
    "MatchService",
    "RackService",
    "MatchResultService",
    "InvalidTransitionError",
    "add_rack",
]
