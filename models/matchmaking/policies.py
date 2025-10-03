"""Tournament pairing policies for handling odd player counts and rematch prevention.

Provides business logic functions and enums for tournament management decisions
that affect pairing quality and player experience. These policies ensure fair
competition while adapting to practical constraints like odd player counts.

Business Context:
    Pool tournaments must balance competitive fairness with practical constraints.
    These policies codify best practices for handling common tournament scenarios.
"""

from __future__ import annotations
from enum import Enum


class OddResolution(Enum):
    """Enumeration of strategies for handling odd player counts in tournaments.

    When tournaments have odd player numbers, one player would normally sit out.
    These policies provide alternatives that maintain player engagement.

    Values:
        BYE: Traditional bye - one player sits out the round
        TRIO: Three-player match format to keep all players active
    """
    BYE = "bye"
    TRIO = "trio"


def decide_trio_or_bye(
    *, campionato_without_x: bool, can_trio: bool
) -> OddResolution:
    """Determine optimal resolution for odd player count.

    Business Logic:
    - Trio matches maximize player engagement when tournament format supports them
    - Bye assignment is used when trio matches aren't feasible or desirable
    - Decision considers tournament rules and match feasibility

    Args:
        campionato_without_x: Whether tournament allows trio match
            alternatives to byes
        can_trio: Whether current round structure supports trio match format

    Returns:
        OddResolution indicating whether to use trio match or bye assignment

    Design Principle:
        Pure function with no side effects - enables testing and
        consistent behavior
    """
    return (
        OddResolution.TRIO if (campionato_without_x and can_trio) else OddResolution.BYE
    )


def anti_rematch_allowed(gara_id: int, a_id: int, b_id: int) -> bool:
    """Check if two players can be paired without creating a rematch.

    Anti-rematch logic is crucial for tournament fairness and player
    satisfaction. Players expect variety in opponents throughout a tournament,
    and excessive rematches can create competitive imbalances or frustration.

    Args:
        gara_id: Tournament identifier to scope encounter history
        a_id: First player's unique identifier
        b_id: Second player's unique identifier

    Returns:
        True if players haven't faced each other in this tournament,
        False for rematch

    Business Logic:
        Uses read-only access to PlayerEncounter domain to check historical
        matchups. This approach maintains data consistency while enabling
        concurrent access.

    Performance Note:
        This function may be called frequently during pairing generation.
        PlayerEncounter.have_played() should be optimized for
        tournament-scoped queries.
    """
    # Import locally to avoid circular import
    from models.classification.models import PlayerEncounter

    # Delegate to domain model for encounter history lookup with tournament scope
    return not PlayerEncounter.have_played(gara_id, a_id, b_id)
