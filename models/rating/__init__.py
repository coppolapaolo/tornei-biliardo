"""Dominio rating: i punteggi Elo, il registro dei delta e la loro policy.

Il dominio è deliberatamente piccolo. Fino ad agosto 2026 conteneva anche un
sistema di categorie e regole di handicap (`PlayerCategory`, `HandicapRule`,
`RatingService`, `HandicapService`) esposto da un blueprint `/rating`: era
codice morto — nessun template esisteva, quindi ogni view finiva nell'except —
e la sua idea di categoria era globale per utente, mentre le categorie sono
per competizione. Sostituito da `models/categoria/` (ADR-049).

Chi decide **quali partite entrano nell'Elo** è `eligibility.RatingEligibility`,
in un posto solo: la regola era duplicata in quattro punti e stava per
diventare più complicata.
"""

from .eligibility import RatingEligibility, RatingExclusion
from .models import (
    MatchRatingHistory,
    PlayerRating,
    RatingSystem,
)

__all__ = [
    # Models
    "PlayerRating",
    "MatchRatingHistory",
    # Enums
    "RatingSystem",
    # Policy
    "RatingEligibility",
    "RatingExclusion",
]


def register_rating_handlers():
    """Register domain event handlers."""
    from models.events import EventBus, MatchCompletedEvent, MatchReopenedEvent
    from models.events.match_events import IndividualMatchCompletedEvent
    from .event_handlers import RatingEventHandlers

    # EventBus.subscribe is a decorator, use register_handler for direct registration
    EventBus.register_handler(
        MatchCompletedEvent, RatingEventHandlers.handle_match_completed
    )
    EventBus.register_handler(
        IndividualMatchCompletedEvent,
        RatingEventHandlers.handle_individual_match_completed,
    )
    EventBus.register_handler(
        MatchReopenedEvent, RatingEventHandlers.handle_match_reopened
    )


# Auto-register when module is imported
register_rating_handlers()
