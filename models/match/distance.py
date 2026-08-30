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
from flask_babel import gettext as _


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

    def walkover_score(self) -> int:
        """Quanto segna chi vince a tavolino, nell'unità in cui si conta.

        `player1_score`/`player2_score` contengono i **rack** in una partita a
        set unico e i **set** in una multi-set: sono la stessa colonna con due
        significati, e la domanda «quanto vale un tavolino» va risposta una
        volta sola, qui.

        Le tre risposte sparse per il codice non concordavano (issue #260): in
        una gara «al 3 set da 4 rack» la creazione del turno segnava 4-0
        **set** invece di 3-0 — un punteggio che in quella gara nessuno può
        ottenere giocando, e che gonfiava i set vinti in classifica.
        """
        if self.is_multi_set:
            return self.get_winning_sets()
        return self.get_winning_racks()

    def to_display_string(self) -> str:
        """Generate human-readable description.

        Returns:
            Examples:
                "Al 4 rack" (Race to)
                "Esattamente 4 rack"
                "Al 2 set, ogni set al 4 rack"

        """
        if not self.is_multi_set:
            # Single-set
            if self.is_race_to_racks:
                return _("Al %(n)s triangoli", n=self.racks)
            else:
                return _("Esattamente %(n)s triangoli", n=self.racks)
        else:
            # Multi-set
            if self.is_race_to_sets:
                sets_part = _("Al %(n)s set", n=self.sets)
            else:
                sets_part = _("Esattamente %(n)s set", n=self.sets)

            if self.is_race_to_racks:
                racks_part = _("ogni set al %(n)s triangoli", n=self.racks)
            else:
                racks_part = _("ogni set esattamente %(n)s triangoli", n=self.racks)

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
            is_race_to_racks=getattr(
                gara, "is_race_to", getattr(gara, "best_of", True)
            ),
            is_multi_set=getattr(gara, "is_multi_set", False),
            sets=(
                getattr(gara, "match_distance", 1)
                if getattr(gara, "is_multi_set", False)
                else 1
            ),
            is_race_to_sets=getattr(gara, "is_race_to_sets", True),  # Fallback for now
        )

    @classmethod
    def from_match(cls, match) -> "Distance":
        """Factory: Distance dal Match model.

        Per ADR-027, ogni proprietà di gioco è leggibile dal match (override
        per match/turno) con fallback a gara. La logica di fallback è
        centralizzata nelle property `effective_*` del Match per evitare
        duplicazione: qui leggiamo solo quelle.

        Supporta match standalone (match.gara is None) tramite i fallback
        nelle property del Match.
        """
        gara = match.gara
        is_race_to = match.effective_is_race_to

        if not match.is_multi_set:
            return cls(
                racks=match.effective_distance,
                is_race_to_racks=is_race_to,
                is_multi_set=False,
                sets=1,
                is_race_to_sets=True,
            )

        # Multi-set: i rack-per-set vengono dalla gara (single source per i set
        # ancora non istanziati); per set già istanziati usa Distance.from_set.
        gara_dist = gara.distance if gara else 5
        return cls(
            racks=gara_dist,
            is_race_to_racks=is_race_to,
            is_multi_set=True,
            sets=getattr(match, "match_distance", 1) or 1,
            is_race_to_sets=match.effective_is_race_to_sets,
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
            is_race_to_racks=getattr(
                set_obj, "is_race_to", getattr(set_obj, "best_of", True)
            ),
            is_multi_set=False,
            sets=1,
            is_race_to_sets=True,
        )
