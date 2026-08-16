# routes/sse_bridge.py
"""SSE Event Bridge - Connects Domain Events to SSE.

This module subscribes to EventBus domain events and routes them to the
appropriate SSE scopes (gara, user, trio).

Architecture:
    Domain Events (EventBus) → SSE Bridge (this module) → SSE Store (sse.py)

Usage:
    Import this module in app.py to register handlers:
        from routes import sse_bridge  # noqa: F401

Events Routed:
    - MatchCompletedEvent → gara scope (match_completed), user scope
        (my_match_completed)
    - CompetitionStartedEvent → gara scope (round_started)
    - CompetitionCompletedEvent → gara scope (gara_completed)
    - InscriptionCreatedEvent → gara scope (inscription_added)
    - XPGainedEvent → user scope (xp_gained)
    - LevelUpEvent → user scope (level_up)
    - AchievementUnlockedEvent → user scope (achievement)
"""

import logging

from models.events.base import EventBus
from models.events.match_events import MatchCompletedEvent
from models.events.competition_events import (
    CompetitionStartedEvent,
    CompetitionCompletedEvent,
    InscriptionCreatedEvent,
)
from models.gamification.events import (
    XPGainedEvent,
    LevelUpEvent,
    AchievementUnlockedEvent,
)

from .sse import emit_gara_event, emit_user_event

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# Match Events → Gara + User SSE
# ═══════════════════════════════════════════════════════════════════════════


@EventBus.subscribe(MatchCompletedEvent)
def on_match_completed(event: MatchCompletedEvent) -> None:
    """Route match completed event to SSE.

    Routes to:
        - gara scope: match_completed (if gara_id present)
        - user scope: my_match_completed (for both players)
    """
    logger.debug(f"SSE Bridge: MatchCompletedEvent match_id={event.match_id}")

    # Route to gara scope (for gara detail page viewers)
    if event.gara_id:
        emit_gara_event(
            event.gara_id,
            "match_completed",
            {
                "match_id": event.match_id,
                "winner_id": event.winner_id,
                "winner_name": event.winner_name,
                "score": event.score,
                "player1_id": event.player1_id,
                "player2_id": event.player2_id,
            },
        )

    # Route to user scope (for player dashboards)
    for player_id in [event.player1_id, event.player2_id]:
        if player_id:
            emit_user_event(
                player_id,
                "my_match_completed",
                {
                    "match_id": event.match_id,
                    "is_winner": player_id == event.winner_id,
                    "score": event.score,
                },
            )


# ═══════════════════════════════════════════════════════════════════════════
# Competition Events → Gara SSE
# ═══════════════════════════════════════════════════════════════════════════


@EventBus.subscribe(CompetitionStartedEvent)
def on_competition_started(event: CompetitionStartedEvent) -> None:
    """Route competition started event to SSE.

    This is emitted when the first round is created.
    """
    logger.debug(f"SSE Bridge: CompetitionStartedEvent gara_id={event.gara_id}")

    emit_gara_event(
        event.gara_id,
        "round_started",
        {
            "gara_id": event.gara_id,
            "round_number": event.round_number,
            "participant_count": event.participant_count,
        },
    )


@EventBus.subscribe(CompetitionCompletedEvent)
def on_competition_completed(event: CompetitionCompletedEvent) -> None:
    """Route competition completed event to SSE."""
    logger.debug(f"SSE Bridge: CompetitionCompletedEvent gara_id={event.gara_id}")

    emit_gara_event(
        event.gara_id,
        "gara_completed",
        {
            "gara_id": event.gara_id,
            "winner_id": event.winner_id,
            "winner_name": event.winner_name,
            "total_rounds": event.total_rounds,
        },
    )


@EventBus.subscribe(InscriptionCreatedEvent)
def on_inscription_created(event: InscriptionCreatedEvent) -> None:
    """Route inscription created event to SSE."""
    logger.debug(f"SSE Bridge: InscriptionCreatedEvent gara_id={event.gara_id}")

    emit_gara_event(
        event.gara_id,
        "inscription_added",
        {
            "gara_id": event.gara_id,
            "user_id": event.user_id,
            "username": event.username,
            "inscription_status": event.inscription_status,
        },
    )


# ═══════════════════════════════════════════════════════════════════════════
# Gamification Events → User SSE
# ═══════════════════════════════════════════════════════════════════════════


@EventBus.subscribe(XPGainedEvent)
def on_xp_gained(event: XPGainedEvent) -> None:
    """Route XP gained event to user SSE."""
    logger.debug(f"SSE Bridge: XPGainedEvent user_id={event.user_id}")

    emit_user_event(
        event.user_id,
        "xp_gained",
        {
            "xp_amount": event.xp_amount,
            "transaction_type": event.transaction_type.value,
            "new_total_xp": event.new_total_xp,
            "level_before": event.level_before,
            "level_after": event.level_after,
        },
    )


@EventBus.subscribe(LevelUpEvent)
def on_level_up(event: LevelUpEvent) -> None:
    """Route level up event to user SSE."""
    logger.debug(f"SSE Bridge: LevelUpEvent user_id={event.user_id}")

    emit_user_event(
        event.user_id,
        "level_up",
        {
            "old_level": event.old_level,
            "new_level": event.new_level,
            "unlocks": event.unlocks,
            "total_xp": event.total_xp,
        },
    )


@EventBus.subscribe(AchievementUnlockedEvent)
def on_achievement_unlocked(event: AchievementUnlockedEvent) -> None:
    """Route achievement unlocked event to user SSE."""
    logger.debug(f"SSE Bridge: AchievementUnlockedEvent user_id={event.user_id}")

    emit_user_event(
        event.user_id,
        "achievement",
        {
            "achievement_id": event.achievement_id,
            "achievement_name": event.achievement_name,
            "achievement_slug": event.achievement_slug,
            "achievement_category": event.achievement_category,
            "xp_awarded": event.xp_awarded,
        },
    )


# ═══════════════════════════════════════════════════════════════════════════
# Helper Functions
# ═══════════════════════════════════════════════════════════════════════════


def get_registered_handlers() -> dict:
    """Get list of registered SSE bridge handlers for debugging."""
    return {
        "match_completed": (
            "MatchCompletedEvent → gara:match_completed, user:my_match_completed"
        ),
        "competition_started": "CompetitionStartedEvent → gara:round_started",
        "competition_completed": "CompetitionCompletedEvent → gara:gara_completed",
        "inscription_created": "InscriptionCreatedEvent → gara:inscription_added",
        "xp_gained": "XPGainedEvent → user:xp_gained",
        "level_up": "LevelUpEvent → user:level_up",
        "achievement_unlocked": "AchievementUnlockedEvent → user:achievement",
    }
