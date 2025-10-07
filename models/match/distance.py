"""Distance Value Object for Match Configuration.

This module provides the Distance abstraction that replaces the legacy
distance/best_of pattern with a unified, type-safe value object.

A Distance can be:
1. Single-set: Only racks matter (e.g., "Best of 7 racks")
2. Multi-set: Sets AND racks per set (e.g., "Best of 3 sets, each best of 5 racks")

Examples:
    Single-set best-of:
        Distance(racks=7, racks_best_of=True, is_multi_set=False)
        → "Best of 7 racks" (first to 4 wins)

    Single-set exact:
        Distance(racks=4, racks_best_of=False, is_multi_set=False)
        → "Exactly 4 racks" (play all 4, winner by count)

    Multi-set best-of sets, best-of racks:
        Distance(racks=5, racks_best_of=True, is_multi_set=True,
                 sets=3, sets_best_of=True)
        → "Best of 3 sets, each set best of 5 racks"

    Multi-set exact sets, best-of racks:
        Distance(racks=3, racks_best_of=True, is_multi_set=True,
                 sets=4, sets_best_of=False)
        → "Exactly 4 sets, each set best of 3 racks"
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Distance:
    """Immutable Distance configuration for a match.

    Attributes:
        racks: Number of racks per set (or total if single-set)
        racks_best_of: If True, "best of N racks". If False, "exactly N racks"
        is_multi_set: If True, match has multiple sets
        sets: Number of sets (only relevant if is_multi_set=True)
        sets_best_of: If True, "best of N sets". If False, "exactly N sets"
    """

    racks: int
    racks_best_of: bool = True
    is_multi_set: bool = False
    sets: int = 1
    sets_best_of: bool = True

    def __post_init__(self) -> None:
        """Validate Distance configuration."""
        if self.racks <= 0:
            raise ValueError("racks must be positive")
        if self.sets <= 0:
            raise ValueError("sets must be positive")
        if not self.is_multi_set and self.sets != 1:
            raise ValueError("sets must be 1 for single-set matches")
        if self.racks_best_of and self.racks % 2 == 0:
            raise ValueError("best_of racks must be odd number")
        if self.is_multi_set and self.sets_best_of and self.sets % 2 == 0:
            raise ValueError("best_of sets must be odd number")

    def get_winning_racks(self) -> int:
        """Get number of racks needed to win ONE set.

        Returns:
            For best-of: (racks // 2) + 1 (e.g., best of 7 → 4 to win)
            For exact: racks (play all, winner by count)
        """
        if self.racks_best_of:
            return (self.racks // 2) + 1
        else:
            return self.racks

    def get_winning_sets(self) -> int:
        """Get number of sets needed to win the match.

        Returns:
            For single-set: Always 1
            For multi-set best-of: (sets // 2) + 1
            For multi-set exact: sets (play all, winner by count)
        """
        if not self.is_multi_set:
            return 1
        if self.sets_best_of:
            return (self.sets // 2) + 1
        else:
            return self.sets

    def to_display_string(self) -> str:
        """Generate human-readable description.

        Returns:
            Examples:
                "Best of 7 racks"
                "Exactly 4 racks"
                "Best of 3 sets, each set best of 5 racks"
                "Exactly 2 sets, each set exactly 3 racks"  # noqa

        """
        if not self.is_multi_set:
            # Single-set
            racks_desc = (
                f"best of {self.racks}"
                if self.racks_best_of
                else f"exactly {self.racks}"
            )
            return f"{racks_desc.capitalize()} racks"
        else:
            # Multi-set
            sets_desc = (
                f"best of {self.sets}"
                if self.sets_best_of
                else f"exactly {self.sets}"
            )
            racks_desc = (
                f"best of {self.racks}"
                if self.racks_best_of
                else f"exactly {self.racks}"
            )
            sets_part = f"{sets_desc.capitalize()} sets"
            racks_part = f"each set {racks_desc} racks"
            return f"{sets_part}, {racks_part}"

    @classmethod
    def from_gara(cls, gara) -> "Distance":
        """Factory: Create single-set Distance from Gara model.

        Args:
            gara: Gara model instance with distance and best_of fields

        Returns:
            Distance object representing the gara's configuration
        """
        return cls(
            racks=gara.distance,
            racks_best_of=gara.best_of,
            is_multi_set=False,
            sets=1,
            sets_best_of=True
        )

    @classmethod
    def from_match(cls, match) -> "Distance":
        """Factory: Create Distance from Match model.

        Handles both single-set and multi-set matches.

        Args:
            match: Match model instance

        Returns:
            Distance object representing the match's configuration
        """
        if not match.is_multi_set:
            # Single-set match - use gara's distance
            return cls.from_gara(match.gara)
        else:
            # Multi-set match
            return cls(
                racks=match.gara.distance,
                racks_best_of=match.gara.best_of,
                is_multi_set=True,
                sets=match.match_distance,
                sets_best_of=True  # Assume best-of for sets
            )

    @classmethod
    def from_set(cls, set_obj) -> "Distance":
        """Factory: Create single-set Distance from Set model.

        Args:
            set_obj: Set model instance with distance and best_of fields

        Returns:
            Distance object representing rack configuration for this set
        """
        return cls(
            racks=set_obj.distance,
            racks_best_of=set_obj.best_of,
            is_multi_set=False,
            sets=1,
            sets_best_of=True
        )
