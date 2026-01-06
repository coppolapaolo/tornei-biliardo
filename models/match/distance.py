"""Distance Value Object for Match Configuration.

This module provides the Distance abstraction that replaces the legacy
distance/best_of pattern with a unified, type-safe value object.

A Distance can be:
1. Single-set: Only racks matter (e.g., "Race to 4 racks" or "Exactly 4 racks")
2. Multi-set: Sets AND racks per set (e.g., "Race to 2 sets, each race to 4 racks")

Examples:
    Single-set race-to:
        Distance(racks=4, is_race_to_racks=True, is_multi_set=False)
        → "Al 4 rack" (EN: "Race to 4 racks")

    Single-set exact:
        Distance(racks=4, is_race_to_racks=False, is_multi_set=False)
        → "Exactly 4 racks" (play all 4, winner by count)

    Multi-set race-to sets, race-to racks:
        Distance(racks=4, is_race_to_racks=True, is_multi_set=True,
                 sets=2, is_race_to_sets=True)
        → "Race to 2 sets, each set race to 4 racks"
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Distance:
    """Immutable Distance configuration for a match.

    Attributes:
        racks: Number of racks per set (or total if single-set)
        is_race_to_racks: If True, "race to N racks". If False, "exactly N racks"
        is_multi_set: If True, match has multiple sets
        sets: Number of sets (only relevant if is_multi_set=True)
        is_race_to_sets: If True, "race to N sets". If False, "exactly N sets"
    """

    racks: int
    is_race_to_racks: bool = True
    is_multi_set: bool = False
    sets: int = 1
    is_race_to_sets: bool = True

    def __post_init__(self) -> None:
        """Validate Distance configuration."""
        if self.racks <= 0:
            raise ValueError("racks must be positive")
        if self.sets <= 0:
            raise ValueError("sets must be positive")
        if not self.is_multi_set and self.sets != 1:
            raise ValueError("sets must be 1 for single-set matches")

    def get_winning_racks(self) -> int:
        """Get number of racks needed to win ONE set.

        Returns:
            For race-to: racks (e.g., race to 4 → 4 to win)
            For exact: racks (play all, winner by count)
        """
        return self.racks

    def get_winning_sets(self) -> int:
        """Get number of sets needed to win the match.

        Returns:
            For single-set: Always 1
            For multi-set race-to: sets
            For multi-set exact: sets (play all, winner by count)
        """
        if not self.is_multi_set:
            return 1
        return self.sets

    def to_display_string(self) -> str:
        """Generate human-readable description.

        Returns:
            Examples:
                "Al 4 rack" (Race to)
                "Exactly 4 racks"
                "Al 2 set, ogni set al 4 rack"

        """
        if not self.is_multi_set:
            # Single-set
            racks_desc = (
                f"al {self.racks}"
                if self.is_race_to_racks
                else f"exactly {self.racks}"
            )
            return f"{racks_desc.capitalize()} rack" if self.is_race_to_racks else f"{racks_desc.capitalize()} racks"
        else:
            # Multi-set
            sets_desc = (
                f"al {self.sets}"
                if self.is_race_to_sets
                else f"exactly {self.sets}"
            )
            racks_desc = (
                f"al {self.racks}"
                if self.is_race_to_racks
                else f"exactly {self.racks}"
            )
            sets_part = f"{sets_desc.capitalize()} set" if self.is_race_to_sets else f"{sets_desc.capitalize()} sets"
            racks_part = f"ogni set {racks_desc} rack"
            return f"{sets_part}, {racks_part}"

    @classmethod
    def from_gara(cls, gara) -> "Distance":
        """Factory: Create single-set Distance from Gara model.

        Args:
            gara: Gara model instance with distance and is_race_to fields

        Returns:
            Distance object representing the gara's configuration
        """
        return cls(
            racks=gara.distance,
            is_race_to_racks=getattr(gara, "is_race_to", getattr(gara, "best_of", True)),
            is_multi_set=getattr(gara, "is_multi_set", False),
            sets=getattr(gara, "match_distance", 1) if getattr(gara, "is_multi_set", False) else 1,
            is_race_to_sets=getattr(gara, "is_race_to_sets", True)  # Fallback for now
        )

    @classmethod
    def from_match(cls, match) -> "Distance":
        """Factory: Create Distance from Match model.

        Handles both single-set and multi-set matches.
        Uses match.match_distance for per-round distance overrides.

        Args:
            match: Match model instance

        Returns:
            Distance object representing the match's configuration
        """
        if not match.is_multi_set:
            # Single-set match - use match's distance (supports per-round overrides)
            # Fall back to gara.distance for legacy matches without match_distance set
            # Legacy matches have match_distance=1 (default), so we need to detect this
            match_dist = getattr(match, "match_distance", None)
            gara_dist = match.gara.distance

            # Use match_distance if explicitly set to a value different from default (1)
            # or if it equals gara.distance (confirming it was set intentionally)
            if match_dist and match_dist > 1:
                effective_distance = match_dist
            elif match_dist and match_dist == gara_dist:
                effective_distance = match_dist
            else:
                # Legacy match with default match_distance=1, use gara.distance
                effective_distance = gara_dist

            return cls(
                racks=effective_distance,
                is_race_to_racks=getattr(match.gara, "is_race_to", getattr(match.gara, "best_of", True)),
                is_multi_set=False,
                sets=1,
                is_race_to_sets=True
            )
        else:
            # Multi-set match
            return cls(
                racks=match.gara.distance,
                is_race_to_racks=getattr(match.gara, "is_race_to", getattr(match.gara, "best_of", True)),
                is_multi_set=True,
                sets=getattr(match, "match_distance", 1),
                is_race_to_sets=True  # Assume race-to for sets
            )

    @classmethod
    def from_set(cls, set_obj) -> "Distance":
        """Factory: Create single-set Distance from Set model.

        Args:
            set_obj: Set model instance with distance and is_race_to fields

        Returns:
            Distance object representing rack configuration for this set
        """
        return cls(
            racks=set_obj.distance,
            is_race_to_racks=getattr(set_obj, "is_race_to", getattr(set_obj, "best_of", True)),
            is_multi_set=False,
            sets=1,
            is_race_to_sets=True
        )
