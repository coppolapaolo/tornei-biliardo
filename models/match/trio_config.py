# models/match/trio_config.py
"""
Value object for trio match configuration based on distance.

A trio is a mini round-robin tournament between 3 players.
Each "girone" (round) consists of 3 matches:
  - P1 vs P2 (P3 waits)
  - P1 vs P3 (P2 waits)
  - P2 vs P3 (P1 waits)

To ensure fairness with normal matches (where max racks = distance),
bonus racks are added when distance is odd.

See ADR-005 for full specification.
"""

from dataclasses import dataclass
from typing import List, Tuple, Optional


@dataclass(frozen=True)
class TrioConfig:
    """Configuration for trio matches based on distance.

    Attributes:
        distance: The "Exactly N" distance configured for the gara.
    """

    distance: int

    # Trio is only allowed for distances 2-5
    MIN_DISTANCE = 2
    MAX_DISTANCE = 5

    @property
    def is_trio_allowed(self) -> bool:
        """Check if trio is allowed for this distance."""
        return self.MIN_DISTANCE <= self.distance <= self.MAX_DISTANCE

    @property
    def num_rounds(self) -> int:
        """Number of round-robin rounds (gironi).

        - Distance 2: 1 round
        - Distance 3: 1 round
        - Distance 4: 2 rounds
        - Distance 5: 2 rounds
        """
        if not self.is_trio_allowed:
            return 0
        # Formula from ADR-005: ceil((distance - 1) / 2)
        # Simplified: distance // 2
        # 2->1, 3->1, 4->2, 5->2
        return self.distance // 2

    @property
    def bonus_racks(self) -> int:
        """Bonus racks to equalize with normal matches.

        Added when distance is odd (3, 5) so trio players
        can achieve the same max racks as normal match players.
        """
        if not self.is_trio_allowed:
            return 0
        return self.distance % 2  # 1 if odd, 0 if even

    @property
    def max_racks_per_player(self) -> int:
        """Maximum racks a player can win (equals distance)."""
        return self.distance

    @property
    def racks_per_round(self) -> int:
        """Racks played in each round-robin round (always 3)."""
        return 3

    @property
    def total_played_racks(self) -> int:
        """Total racks played in the trio (excluding bonus)."""
        return self.num_rounds * self.racks_per_round

    @property
    def total_racks_with_bonus(self) -> int:
        """Total racks including bonus (for tracking completion)."""
        return self.total_played_racks + (1 if self.bonus_racks > 0 else 0)

    def get_matchup_for_rack(self, rack_number: int) -> Optional[Tuple[int, int, int]]:
        """Get which players play and who waits for a given rack.

        Args:
            rack_number: 1-based rack number

        Returns:
            Tuple of (player1_index, player2_index, waiting_index) where
            indices are 0-based (0=P1, 1=P2, 2=P3), or None if invalid.
        """
        if rack_number < 1 or rack_number > self.total_played_racks:
            return None

        # Rack position within current round (0-2)
        rack_in_round = (rack_number - 1) % 3

        # Round-robin matchups (who plays, who waits)
        # Rack 1: P1 vs P2, P3 waits -> (0, 1, 2)
        # Rack 2: P1 vs P3, P2 waits -> (0, 2, 1)
        # Rack 3: P2 vs P3, P1 waits -> (1, 2, 0)
        matchups = [
            (0, 1, 2),  # P1 vs P2, P3 waits
            (0, 2, 1),  # P1 vs P3, P2 waits
            (1, 2, 0),  # P2 vs P3, P1 waits
        ]
        return matchups[rack_in_round]

    def get_round_for_rack(self, rack_number: int) -> int:
        """Get which round (girone) a rack belongs to (1-based)."""
        if rack_number < 1 or rack_number > self.total_played_racks:
            return 0
        return ((rack_number - 1) // 3) + 1

    def get_all_matchups(self) -> List[Tuple[int, int, int, int]]:
        """Get all matchups for the trio.

        Returns:
            List of (round_number, player1_idx, player2_idx, waiting_idx)
        """
        matchups = []
        for rack in range(1, self.total_played_racks + 1):
            round_num = self.get_round_for_rack(rack)
            matchup = self.get_matchup_for_rack(rack)
            if matchup:
                p1, p2, waiting = matchup
                matchups.append((round_num, p1, p2, waiting))
        return matchups

    def __str__(self) -> str:
        if not self.is_trio_allowed:
            return f"TrioConfig(distance={self.distance}, NOT ALLOWED)"
        return (
            f"TrioConfig(distance={self.distance}, "
            f"rounds={self.num_rounds}, bonus={self.bonus_racks})"
        )


# Factory function for convenience
def get_trio_config(distance: int) -> TrioConfig:
    """Create a TrioConfig from distance."""
    return TrioConfig(distance=distance)


def get_trio_config_from_gara(gara) -> Optional[TrioConfig]:
    """Create a TrioConfig from a Gara model.

    Returns None if gara doesn't allow trio (wrong classification type,
    wrong distance, etc.)
    """
    # Check if gara uses rack-based classification
    # (trio only makes sense with rack-based classification)
    if gara.matchmaking_strategy == "elimination":
        return None

    config = TrioConfig(distance=gara.distance)
    if not config.is_trio_allowed:
        return None

    return config
