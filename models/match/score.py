"""Score Value Objects for Match and Rack Tracking.

This module provides RackScore and MatchScore abstractions that replace
legacy player_score fields with type-safe, behavior-rich value objects.

Two-Level Scoring System:
1. RackScore: Tracks racks won within ONE set (or single-set match)
2. MatchScore: Tracks sets won in multi-set match

Examples:
    Single-set match (best of 7):
        rack_score = RackScore(
            distance=Distance(racks=7, is_race_to_racks=True),
            player1_racks=4,
            player2_racks=2
        )
        → Player 1 wins (4 racks, first to 4)

    Multi-set match (best of 3 sets):
        match_score = MatchScore(
            distance=Distance(racks=5, is_multi_set=True, sets=3),
            player1_sets=2,
            player2_sets=0
        )
        → Player 1 wins match (2 sets, first to 2)
"""

from dataclasses import dataclass
from typing import Optional, Tuple
from .distance import Distance


@dataclass
class RackScore:
    """Score for racks within ONE set (or single-set match).

    Tracks how many racks each player has won in the current set.
    Used for:
    - Single-set matches (entire match scoring)
    - Individual sets in multi-set matches

    Attributes:
        distance: Distance configuration (must be single-set or per-set config)
        player1_racks: Number of racks won by player 1
        player2_racks: Number of racks won by player 2
        player3_racks: Number of racks won by player 3 (trio only)
    """

    distance: Distance
    player1_racks: int = 0
    player2_racks: int = 0
    player3_racks: Optional[int] = None

    def __post_init__(self) -> None:
        """Validate RackScore state."""
        if self.player1_racks < 0 or self.player2_racks < 0:
            raise ValueError("Rack counts cannot be negative")
        if self.player3_racks is not None and self.player3_racks < 0:
            raise ValueError("Player 3 rack count cannot be negative")
        if self.distance.is_multi_set:
            raise ValueError(
                "RackScore requires single-set Distance configuration"
            )

    def add_rack_win(self, player_number: int) -> None:
        """Record a rack win for the specified player.

        Args:
            player_number: Player who won (1, 2, or 3)

        Raises:
            ValueError: If player_number invalid or match already complete
        """
        if self.is_complete():
            raise ValueError("Cannot add rack win: match/set already complete")

        if player_number == 1:
            self.player1_racks += 1
        elif player_number == 2:
            self.player2_racks += 1
        elif player_number == 3:
            if self.player3_racks is None:
                raise ValueError("No player 3 in this match")
            self.player3_racks += 1
        else:
            raise ValueError(f"Invalid player number: {player_number}")

    def is_complete(self) -> bool:
        """Check if set/match is complete.

        Returns:
            True if a player has reached winning score or all racks played
        """
        winning_racks = self.distance.get_winning_racks()

        if self.distance.is_race_to_racks:
            # Race-to: First to winning_racks
            if self.player3_racks is not None:
                # Trio match
                return (
                    self.player1_racks >= winning_racks
                    or self.player2_racks >= winning_racks
                    or self.player3_racks >= winning_racks
                )
            else:
                # Two-player match
                return (
                    self.player1_racks >= winning_racks
                    or self.player2_racks >= winning_racks
                )
        else:
            # Exact: All racks must be played
            total_racks = self.player1_racks + self.player2_racks
            if self.player3_racks is not None:
                total_racks += self.player3_racks
            return total_racks >= self.distance.racks

    def get_winner(self) -> Optional[int]:
        """Get the winning player number.

        Returns:
            Player number (1, 2, or 3) if complete, None if incomplete/tie
        """
        if not self.is_complete():
            return None

        if self.player3_racks is not None:
            # Trio match - highest score wins
            max_score = max(
                self.player1_racks, self.player2_racks, self.player3_racks
            )
            # Check for tie
            scores = [
                self.player1_racks, self.player2_racks, self.player3_racks
            ]
            if scores.count(max_score) > 1:
                return None  # Tie

            if self.player1_racks == max_score:
                return 1
            elif self.player2_racks == max_score:
                return 2
            else:
                return 3
        else:
            # Two-player match
            if self.player1_racks > self.player2_racks:
                return 1
            elif self.player2_racks > self.player1_racks:
                return 2
            else:
                return None  # Tie

    def get_score_tuple(self) -> Tuple[int, int, Optional[int]]:
        """Get score as tuple for easy comparison.

        Returns:
            (player1_racks, player2_racks, player3_racks)
        """
        return (self.player1_racks, self.player2_racks, self.player3_racks)

    def to_display_string(self) -> str:
        """Generate display string for UI.

        Returns:
            Examples: "4-2", "3-3-1" (trio)
        """
        if self.player3_racks is not None:
            return (
                f"{self.player1_racks}-{self.player2_racks}"
                f"-{self.player3_racks}"
            )
        else:
            return f"{self.player1_racks}-{self.player2_racks}"


@dataclass
class MatchScore:
    """Score for sets in a multi-set match.

    Tracks how many sets each player has won.
    Only used for multi-set matches.

    Attributes:
        distance: Distance configuration (must be multi-set)
        player1_sets: Number of sets won by player 1
        player2_sets: Number of sets won by player 2
    """

    distance: Distance
    player1_sets: int = 0
    player2_sets: int = 0

    def __post_init__(self) -> None:
        """Validate MatchScore state."""
        if self.player1_sets < 0 or self.player2_sets < 0:
            raise ValueError("Set counts cannot be negative")
        if not self.distance.is_multi_set:
            raise ValueError(
                "MatchScore requires multi-set Distance configuration"
            )

    def add_set_win(self, player_number: int) -> None:
        """Record a set win for the specified player.

        Args:
            player_number: Player who won the set (1 or 2)

        Raises:
            ValueError: If player_number invalid or match already complete
        """
        if self.is_complete():
            raise ValueError("Cannot add set win: match already complete")

        if player_number == 1:
            self.player1_sets += 1
        elif player_number == 2:
            self.player2_sets += 1
        else:
            raise ValueError(f"Invalid player number: {player_number}")

    def is_complete(self) -> bool:
        """Check if match is complete.

        Returns:
            True if a player has reached winning sets or all sets played
        """
        winning_sets = self.distance.get_winning_sets()

        if self.distance.is_race_to_sets:
            # Race-to: First to winning_sets
            return (
                self.player1_sets >= winning_sets
                or self.player2_sets >= winning_sets
            )
        else:
            # Exact: All sets must be played
            total_sets = self.player1_sets + self.player2_sets
            return total_sets >= self.distance.sets

    def get_winner(self) -> Optional[int]:
        """Get the winning player number.

        Returns:
            Player number (1 or 2) if complete, None if incomplete/tie
        """
        if not self.is_complete():
            return None

        if self.player1_sets > self.player2_sets:
            return 1
        elif self.player2_sets > self.player1_sets:
            return 2
        else:
            return None  # Tie

    def get_score_tuple(self) -> Tuple[int, int]:
        """Get score as tuple for easy comparison.

        Returns:
            (player1_sets, player2_sets)
        """
        return (self.player1_sets, self.player2_sets)

    def to_display_string(self) -> str:
        """Generate display string for UI.

        Returns:
            Example: "2-1" (sets)
        """
        return f"{self.player1_sets}-{self.player2_sets}"
