"""
Set models for multi-set matches.
"""

from typing import Optional, List, Dict, Any

from models.base import db, BaseModel, TimestampMixin, utc_now


class Set(BaseModel):
    """A set within a multi-set match."""

    __tablename__ = "set"

    id = db.Column(db.Integer, primary_key=True)
    match_id = db.Column(
        db.Integer, db.ForeignKey("match.id", ondelete="CASCADE"), nullable=False
    )
    set_number = db.Column(db.Integer, nullable=False)

    # Scoring configuration
    distance = db.Column(db.Integer, nullable=False, default=5)
    is_race_to = db.Column(db.Boolean, nullable=False, default=True)

    # Current scores
    player1_racks = db.Column(db.Integer, nullable=False, default=0)
    player2_racks = db.Column(db.Integer, nullable=False, default=0)

    # Status and result
    status = db.Column(
        db.String(20), nullable=False, default="pending"
    )  # pending, playing, completed
    winner_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    started_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)

    # Multi-discipline support
    discipline = db.Column(db.String(50), nullable=True)  # Primary discipline
    is_multi_discipline = db.Column(db.Boolean, nullable=False, default=False)
    discipline_rotation = db.Column(
        db.JSON, nullable=True
    )  # List of disciplines for rotation
    discipline_assignment = db.Column(
        db.JSON, nullable=True
    )  # Specific rack->discipline mapping

    # Relationships
    match = db.relationship("Match", back_populates="sets")
    winner = db.relationship("User", foreign_keys=[winner_id])
    racks = db.relationship(
        "SetRack",
        back_populates="set",
        lazy=True,
        cascade="all, delete-orphan",
        order_by="SetRack.rack_number",
    )

    # Unique constraint: one set per number per match
    __table_args__ = (
        db.UniqueConstraint("match_id", "set_number", name="uq_match_set_number"),
    )

    def can_be_modified(self) -> bool:
        """Check if set can be modified (racks added/removed)."""
        return self.status == "playing"

    def configure_multi_discipline(
        self, disciplines: List[str], mode: str = "rotation"
    ) -> None:
        """Configure multi-discipline mode for the set.

        Args:
            disciplines: List of discipline names
            mode: 'rotation' (cycle through), 'assignment' (specific mapping), or 'random'
        """
        if not disciplines or len(disciplines) < 2:
            raise ValueError(
                "At least 2 disciplines required for multi-discipline mode"
            )

        self.is_multi_discipline = True

        if mode == "rotation":
            self.discipline_rotation = disciplines
            self.discipline_assignment = None
        elif mode == "assignment":
            # Caller must provide specific rack->discipline mapping via set_discipline_assignment
            self.discipline_rotation = disciplines
            self.discipline_assignment = {}
        else:
            raise ValueError(f"Unsupported multi-discipline mode: {mode}")

    def set_discipline_assignment(self, rack_disciplines: Dict[int, str]) -> None:
        """Set specific discipline assignments for racks.

        Args:
            rack_disciplines: Dict mapping rack number to discipline name
        """
        if not self.is_multi_discipline:
            raise ValueError("Set must be in multi-discipline mode")

        # Convert integer keys to strings for consistent JSON storage
        self.discipline_assignment = {str(k): v for k, v in rack_disciplines.items()}

    def get_discipline_for_rack(self, rack_number: int) -> str:
        """Get the discipline that should be played for a specific rack."""
        if not self.is_multi_discipline:
            return (
                self.discipline
                or getattr(self.match, "discipline", "palla_8")
                or "palla_8"
            )

        # Check specific assignment first
        if (
            self.discipline_assignment
            and str(rack_number) in self.discipline_assignment
        ):
            return self.discipline_assignment[str(rack_number)]

        # Use rotation if available
        if self.discipline_rotation:
            rotation_index = (rack_number - 1) % len(self.discipline_rotation)
            return self.discipline_rotation[rotation_index]

        # Fallback to set or match discipline
        return (
            self.discipline or getattr(self.match, "discipline", "palla_8") or "palla_8"
        )

    def get_discipline_summary(self) -> Dict[str, Any]:
        """Get summary of disciplines used in this set."""
        if not self.is_multi_discipline:
            discipline = (
                self.discipline
                or getattr(self.match, "discipline", "palla_8")
                or "palla_8"
            )
            return {
                "is_multi_discipline": False,
                "primary_discipline": discipline,
                "disciplines_used": [discipline],
            }

        disciplines_played = []
        discipline_counts = {}

        for rack in self.racks:  # type: ignore
            rack_discipline = rack.discipline_override or self.get_discipline_for_rack(
                rack.rack_number
            )
            if rack_discipline not in disciplines_played:
                disciplines_played.append(rack_discipline)
            discipline_counts[rack_discipline] = (
                discipline_counts.get(rack_discipline, 0) + 1
            )

        return {
            "is_multi_discipline": True,
            "rotation": self.discipline_rotation,
            "assignment": self.discipline_assignment,
            "disciplines_played": disciplines_played,
            "discipline_counts": discipline_counts,
            "total_racks": len(self.racks),  # type: ignore
        }

    def __repr__(self) -> str:
        return f"<Set {self.match_id}-{self.set_number}: {self.player1_racks}-{self.player2_racks}>"

    def start_set(self) -> None:
        """Start the set."""
        if self.status != "pending":
            raise ValueError("Set can only be started from pending status")

        self.status = "playing"
        self.started_at = utc_now()

    def add_rack_result(
        self,
        winner_id: int,
        rack_number: Optional[int] = None,
        discipline_override: Optional[str] = None,
    ) -> "SetRack":
        """Add a rack result to this set."""
        if self.status != "playing":
            raise ValueError("Cannot add rack result to non-playing set")

        if winner_id not in [self.match.player1_id, self.match.player2_id]:
            raise ValueError("Winner must be one of the match players")

        # Auto-assign rack number if not provided
        if rack_number is None:
            from sqlalchemy import func

            max_rack = (
                db.session.query(func.max(SetRack.rack_number))
                .filter_by(set_id=self.id)
                .scalar()
            )
            rack_number = (max_rack or 0) + 1

        # At this point, rack_number is guaranteed to be an int
        assert rack_number is not None

        # Determine discipline for this rack
        rack_discipline = discipline_override or self.get_discipline_for_rack(
            rack_number
        )

        # Create rack record
        rack = SetRack(
            set_id=self.id,
            rack_number=rack_number,
            winner_id=winner_id,
            discipline_override=(
                rack_discipline
                if rack_discipline != self.get_discipline_for_rack(rack_number)
                else None
            ),
        )

        db.session.add(rack)

        # Update set scores
        if winner_id == self.match.player1_id:
            self.player1_racks += 1
        else:
            self.player2_racks += 1

        # Check if set is completed
        self._check_set_completion()

        return rack

    def _check_set_completion(self) -> None:
        """Check if set is completed based on scoring rules."""
        if self.is_race_to:
            # Race to X: first to reach distance wins
            if self.player1_racks >= self.distance:
                self._complete_set(self.match.player1_id)
            elif self.player2_racks >= self.distance:
                self._complete_set(self.match.player2_id)
        else:
            # Fixed distance: play exactly distance racks
            total_racks = self.player1_racks + self.player2_racks
            if total_racks >= self.distance:
                if self.player1_racks > self.player2_racks:
                    self._complete_set(self.match.player1_id)
                elif self.player2_racks > self.player1_racks:
                    self._complete_set(self.match.player2_id)
                else:
                    # Tie - need sudden death or other tiebreaker
                    # For now, continue playing
                    pass

    def _complete_set(self, winner_id: int) -> None:
        """Complete the set with a winner."""
        self.status = "completed"
        self.completed_at = utc_now()
        self.winner_id = winner_id

        # Notify match to check if it's completed
        self.match.complete_set(self.set_number, winner_id)

    def is_completed(self) -> bool:
        """Check if set is completed."""
        return self.status == "completed"

    @property
    def distance_config(self):
        """Get Distance value object for this set.

        Returns unified Distance abstraction for rack configuration.
        Always returns single-set configuration.

        Returns:
            Distance: Immutable distance configuration
        """
        from .distance import Distance

        return Distance(
            racks=self.distance,
            is_race_to_racks=self.is_race_to,
            is_multi_set=False,
            sets=1,
            is_race_to_sets=True
        )

    @property
    def rack_score(self):
        """Get RackScore value object for this set.

        Returns current rack scoring within this set.

        Returns:
            RackScore: Current rack scoring
        """
        from .score import RackScore

        return RackScore(
            distance=self.distance_config,
            player1_racks=self.player1_racks,
            player2_racks=self.player2_racks
        )

    def get_score_summary(self) -> Dict[str, Any]:
        """Get set score summary."""
        return {
            "set_number": self.set_number,
            "distance": self.distance,
            "is_race_to": self.is_race_to,
            "discipline": self.discipline,
            "is_multi_discipline": self.is_multi_discipline,
            "player1_racks": self.player1_racks,
            "player2_racks": self.player2_racks,
            "total_racks_played": self.player1_racks + self.player2_racks,
            "winner_id": self.winner_id,
            "status": self.status,
            "is_completed": self.is_completed(),
        }

    def get_rack_history(self) -> List[Dict[str, Any]]:
        """Get detailed rack-by-rack history."""
        return [
            {
                "rack_number": rack.rack_number,
                "winner_id": rack.winner_id,
                "discipline": rack.discipline_override
                or self.get_discipline_for_rack(rack.rack_number),
                "created_at": rack.created_at,
            }
            for rack in self.racks  # type: ignore
        ]


class SetRack(BaseModel):
    """A rack within a set.

    Separato da Rack per contesti diversi: SetRack per multi-set matches
    (con discipline_override, break_player), Rack per single-set (con soft delete).
    """

    __tablename__ = "set_rack"

    id = db.Column(db.Integer, primary_key=True)
    set_id = db.Column(
        db.Integer, db.ForeignKey("set.id", ondelete="CASCADE"), nullable=False
    )
    rack_number = db.Column(db.Integer, nullable=False)
    winner_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    # Optional details
    break_player_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    discipline_override = db.Column(
        db.String(50), nullable=True
    )  # Different discipline for this rack
    notes = db.Column(db.Text, nullable=True)

    # Confirmation tracking (similar to main Rack model)
    reported_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    confirmed_by_player = db.Column(db.Boolean, nullable=False, default=False)
    validated_by_admin = db.Column(db.Boolean, nullable=False, default=False)

    # Relationships
    set = db.relationship("Set", back_populates="racks")
    winner = db.relationship("User", foreign_keys=[winner_id])
    break_player = db.relationship("User", foreign_keys=[break_player_id])
    reported_by = db.relationship("User", foreign_keys=[reported_by_id])

    # Unique constraint: one rack per number per set
    __table_args__ = (
        db.UniqueConstraint("set_id", "rack_number", name="uq_set_rack_number"),
    )

    def can_be_confirmed(self, current_user_id: int) -> bool:
        """Check if rack can be confirmed by the current user."""
        if self.confirmed_by_player or self.validated_by_admin:
            return False

        # Only the opponent can confirm
        match = self.set.match
        if current_user_id == match.player1_id:
            return self.reported_by_id == match.player2_id
        elif current_user_id == match.player2_id:
            return self.reported_by_id == match.player1_id

        return False

    def confirm_rack(self, confirming_user_id: int) -> None:
        """Confirm the rack result."""
        if not self.can_be_confirmed(confirming_user_id):
            raise ValueError("User cannot confirm this rack")

        self.confirmed_by_player = True

    def get_effective_discipline(self) -> str:
        """Get the effective discipline for this rack."""
        return self.discipline_override or self.set.get_discipline_for_rack(
            self.rack_number
        )

    def __repr__(self) -> str:
        return f"<SetRack {self.set_id}-{self.rack_number}: winner={self.winner_id}>"
