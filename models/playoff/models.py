"""
Module: models/playoff/models.py
Purpose: Playoff domain models for tournament playoffs system
Requirements: SPECIFICHE.md - Playoff system with qualification criteria and special tournaments
Data Structures: PlayoffConfiguration, PlayoffQualification, PlayoffTournament
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional, TYPE_CHECKING
from enum import Enum

from sqlalchemy import func
from sqlalchemy.orm import backref
from sqlalchemy.sql import or_

from ..base import db, BaseModel, TimestampMixin

if TYPE_CHECKING:
    from ..user.models import User
    from ..tournament.models import Tournament
    from ..competition.models import Prova
    from ..classification.models import Classification


class PlayoffType(Enum):
    """Types of playoff configurations."""

    TOP_N = "top_n"  # Top N players (e.g., top 6)
    ELITE_ACADEMY = "elite_academy"  # Elite and Academy divisions
    CONDITIONAL = "conditional"  # Based on specific criteria
    BOTTOM_EXCLUDE = "bottom_exclude"  # Exclude top players (e.g., 3rd place and below)


class QualificationStatus(Enum):
    """Status of playoff qualification."""

    PENDING = "pending"  # Waiting for player response
    CONFIRMED = "confirmed"  # Player confirmed participation
    DECLINED = "declined"  # Player declined participation
    EXPIRED = "expired"  # Qualification offer expired
    REPLACED = "replaced"  # Replaced by next eligible player


class PlayoffConfiguration(BaseModel, TimestampMixin):
    """Configuration for tournament playoffs."""

    __tablename__ = "playoff_configuration"

    id = db.Column(db.Integer, primary_key=True)
    tournament_id = db.Column(
        db.Integer, db.ForeignKey("tournament.id", ondelete="CASCADE"), nullable=False
    )

    # Configuration details
    name = db.Column(
        db.String(100), nullable=False
    )  # e.g., "Elite Playoff", "Academy Playoff"
    playoff_type = db.Column(db.Enum(PlayoffType), nullable=False)
    description = db.Column(db.Text, nullable=True)

    # Qualification criteria
    max_participants = db.Column(db.Integer, nullable=False)
    min_provas_played = db.Column(
        db.Integer, nullable=True
    )  # Minimum provas to qualify
    qualification_criteria = db.Column(
        db.Text, nullable=False
    )  # JSON string with criteria

    # Playoff tournament details
    location = db.Column(db.String(255), nullable=True)
    scheduled_date = db.Column(db.DateTime, nullable=True)
    entry_fee = db.Column(db.Numeric(10, 2), nullable=True)

    # Configuration
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    auto_generate = db.Column(
        db.Boolean, nullable=False, default=True
    )  # Auto-generate at tournament end

    # Response deadline
    response_deadline = db.Column(db.DateTime, nullable=True)

    # Relationships
    tournament = db.relationship("Tournament")
    qualifications = db.relationship(
        "PlayoffQualification",
        back_populates="configuration",
        cascade="all, delete-orphan",
    )
    playoff_tournament = db.relationship(
        "PlayoffTournament", back_populates="configuration", uselist=False
    )

    def get_qualification_criteria(self) -> Dict[str, Any]:
        """Parse qualification criteria from JSON."""
        try:
            return json.loads(self.qualification_criteria)
        except (json.JSONDecodeError, TypeError):
            return {}

    def set_qualification_criteria(self, criteria: Dict[str, Any]) -> None:
        """Set qualification criteria as JSON."""
        self.qualification_criteria = json.dumps(criteria)

    def evaluate_qualifications(self) -> List[Dict[str, Any]]:
        """Evaluate which players qualify for this playoff based on criteria."""
        from ..classification.models import Classification
        from ..competition.models import Inscription, Prova

        criteria = self.get_qualification_criteria()

        # Get tournament final classification
        classifications = (
            Classification.query.filter_by(tournament_id=self.tournament_id)
            .order_by(Classification.position)
            .all()
        )

        qualified_players = []

        if self.playoff_type == PlayoffType.TOP_N:
            # Top N players
            top_n = criteria.get("top_positions", self.max_participants)
            for i, classification in enumerate(classifications[:top_n]):
                if self._meets_minimum_requirements(classification.user_id):
                    qualified_players.append(
                        {
                            "user_id": classification.user_id,
                            "position": classification.position,
                            "qualification_reason": f"Top {top_n} position",
                        }
                    )

        elif self.playoff_type == PlayoffType.ELITE_ACADEMY:
            # Elite: top positions, Academy: next positions
            elite_positions = criteria.get("elite_positions", 6)
            academy_positions = criteria.get("academy_positions", 6)

            if criteria.get("category") == "elite":
                target_classifications = classifications[:elite_positions]
                reason = "Elite qualification"
            else:
                target_classifications = classifications[
                    elite_positions : elite_positions + academy_positions
                ]
                reason = "Academy qualification"

            for classification in target_classifications:
                if self._meets_minimum_requirements(classification.user_id):
                    qualified_players.append(
                        {
                            "user_id": classification.user_id,
                            "position": classification.position,
                            "qualification_reason": reason,
                        }
                    )

        elif self.playoff_type == PlayoffType.BOTTOM_EXCLUDE:
            # Exclude top N, include rest up to max_participants
            exclude_top = criteria.get("exclude_top_positions", 2)
            eligible_classifications = classifications[exclude_top:]

            for classification in eligible_classifications[: self.max_participants]:
                if self._meets_minimum_requirements(classification.user_id):
                    qualified_players.append(
                        {
                            "user_id": classification.user_id,
                            "position": classification.position,
                            "qualification_reason": f"Position {classification.position} (excluding top {exclude_top})",
                        }
                    )

        elif self.playoff_type == PlayoffType.CONDITIONAL:
            # Custom criteria evaluation
            for classification in classifications:
                if self._evaluate_custom_criteria(classification, criteria):
                    qualified_players.append(
                        {
                            "user_id": classification.user_id,
                            "position": classification.position,
                            "qualification_reason": "Met custom criteria",
                        }
                    )

        return qualified_players[: self.max_participants]

    def _meets_minimum_requirements(self, user_id: int) -> bool:
        """Check if user meets minimum requirements for playoff."""
        if not self.min_provas_played:
            return True

        from ..competition.models import Inscription, Prova

        provas_played = (
            Inscription.query.join(Prova)
            .filter(
                Inscription.user_id == user_id,
                Prova.tournament_id == self.tournament_id,
                Prova.status == "completed",
            )
            .count()
        )

        return provas_played >= self.min_provas_played

    def _evaluate_custom_criteria(
        self, classification: "Classification", criteria: Dict[str, Any]
    ) -> bool:
        """Evaluate custom qualification criteria."""
        # Example custom criteria evaluation
        # This can be extended based on specific requirements

        min_matches_won = criteria.get("min_matches_won")
        if min_matches_won and classification.total_matches_won < min_matches_won:
            return False

        min_point_difference = criteria.get("min_point_difference")
        if (
            min_point_difference
            and classification.total_point_difference < min_point_difference
        ):
            return False

        max_position = criteria.get("max_position")
        if max_position and classification.position > max_position:
            return False

        return True

    def generate_qualifications(self) -> List["PlayoffQualification"]:
        """Generate playoff qualifications based on criteria."""
        qualified_players = self.evaluate_qualifications()
        qualifications = []

        for player_data in qualified_players:
            # Check if qualification already exists
            existing = PlayoffQualification.query.filter_by(
                configuration_id=self.id, user_id=player_data["user_id"]
            ).first()

            if not existing:
                qualification = PlayoffQualification(
                    configuration_id=self.id,
                    user_id=player_data["user_id"],
                    qualifying_position=player_data["position"],
                    qualification_reason=player_data["qualification_reason"],
                )
                db.session.add(qualification)
                qualifications.append(qualification)

        db.session.commit()
        return qualifications

    def __repr__(self) -> str:
        return f"<PlayoffConfiguration {self.name} for Tournament {self.tournament_id}>"


class PlayoffQualification(BaseModel, TimestampMixin):
    """Individual player qualification for a playoff."""

    __tablename__ = "playoff_qualification"

    id = db.Column(db.Integer, primary_key=True)
    configuration_id = db.Column(
        db.Integer,
        db.ForeignKey("playoff_configuration.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )

    # Qualification details
    qualifying_position = db.Column(db.Integer, nullable=False)
    qualification_reason = db.Column(db.String(255), nullable=False)

    # Status tracking
    status = db.Column(
        db.Enum(QualificationStatus),
        nullable=False,
        default=QualificationStatus.PENDING,
    )
    notified_at = db.Column(db.DateTime, nullable=True)
    responded_at = db.Column(db.DateTime, nullable=True)

    # Replacement tracking
    replaced_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    replacement_position = db.Column(
        db.Integer, nullable=True
    )  # Position in replacement queue

    # Relationships
    configuration = db.relationship(
        "PlayoffConfiguration", back_populates="qualifications"
    )
    user = db.relationship("User", foreign_keys=[user_id])
    replaced_by = db.relationship("User", foreign_keys=[replaced_by_id])

    def confirm_participation(self) -> None:
        """Confirm participation in playoff."""
        if self.status != QualificationStatus.PENDING:
            raise ValueError("Can only confirm pending qualifications")

        self.status = QualificationStatus.CONFIRMED
        self.responded_at = datetime.utcnow()

    def decline_participation(self) -> Optional["PlayoffQualification"]:
        """Decline participation and trigger replacement process."""
        if self.status != QualificationStatus.PENDING:
            raise ValueError("Can only decline pending qualifications")

        self.status = QualificationStatus.DECLINED
        self.responded_at = datetime.utcnow()

        # Find next eligible player for replacement
        return (
            self.configuration._find_replacement()
            if hasattr(self.configuration, "_find_replacement")
            else None
        )

    def expire_qualification(self) -> Optional["PlayoffQualification"]:
        """Mark qualification as expired and find replacement."""
        if self.status != QualificationStatus.PENDING:
            return None

        self.status = QualificationStatus.EXPIRED

        # Find replacement
        return (
            self.configuration._find_replacement()
            if hasattr(self.configuration, "_find_replacement")
            else None
        )

    def __repr__(self) -> str:
        return f"<PlayoffQualification {self.user_id} -> {self.configuration.name}: {self.status.value}>"


class PlayoffTournament(BaseModel, TimestampMixin):
    """The actual playoff tournament/prova."""

    __tablename__ = "playoff_tournament"

    id = db.Column(db.Integer, primary_key=True)
    configuration_id = db.Column(
        db.Integer,
        db.ForeignKey("playoff_configuration.id", ondelete="CASCADE"),
        nullable=False,
    )
    prova_id = db.Column(
        db.Integer, db.ForeignKey("prova.id"), nullable=True
    )  # The actual playoff prova

    # Tournament details
    name = db.Column(db.String(100), nullable=False)
    status = db.Column(
        db.String(20), nullable=False, default="setup"
    )  # setup, registration, playing, completed

    # Schedule
    registration_start = db.Column(db.DateTime, nullable=True)
    registration_end = db.Column(db.DateTime, nullable=True)
    tournament_date = db.Column(db.DateTime, nullable=True)
    location = db.Column(db.String(255), nullable=True)

    # Configuration
    entry_fee = db.Column(db.Numeric(10, 2), nullable=True)
    max_participants = db.Column(db.Integer, nullable=False)
    confirmed_participants = db.Column(db.Integer, nullable=False, default=0)

    # Results
    completed_at = db.Column(db.DateTime, nullable=True)
    winner_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)

    # Relationships
    configuration = db.relationship(
        "PlayoffConfiguration", back_populates="playoff_tournament"
    )
    prova = db.relationship("Prova")
    winner = db.relationship("User", foreign_keys=[winner_id])

    def start_registration(self) -> None:
        """Start the registration process for confirmed qualifiers."""
        if self.status != "setup":
            raise ValueError("Can only start registration from setup status")

        self.status = "registration"
        self.registration_start = datetime.utcnow()

        # Create inscriptions for confirmed qualifiers
        from ..competition.services import ProvaService

        confirmed_qualifications = self.configuration.qualifications.filter_by(
            status=QualificationStatus.CONFIRMED
        ).all()

        if not self.prova_id:
            # Create the playoff prova if it doesn't exist
            # TODO: Fix ProvaService.create_prova call with proper parameters
            # prova = ProvaService.create_prova(
            #     tournament_id=self.configuration.tournament_id,
            #     director_id=1,  # Admin or first director
            #     name=self.name,
            #     location=self.location or "TBD",
            #     date=self.tournament_date or datetime.utcnow(),
            #     is_playoff=True
            # )
            # self.prova_id = prova.id
            pass

        # Auto-inscribe confirmed players
        for qualification in confirmed_qualifications:
            try:
                # TODO: Fix ProvaService.inscribe_user call - method doesn't exist
                # ProvaService.inscribe_user(self.prova_id, qualification.user_id)
                # self.confirmed_participants += 1
                pass
            except Exception as e:
                print(f"Failed to inscribe user {qualification.user_id}: {e}")

    def complete_tournament(self, winner_id: Optional[int] = None) -> None:
        """Mark tournament as completed."""
        self.status = "completed"
        self.completed_at = datetime.utcnow()
        if winner_id:
            self.winner_id = winner_id

    def get_qualified_players(self) -> List["PlayoffQualification"]:
        """Get all qualified players for this tournament."""
        confirmed_quals = self.configuration.qualifications.filter_by(
            status=QualificationStatus.CONFIRMED
        ).all()
        pending_quals = self.configuration.qualifications.filter_by(
            status=QualificationStatus.PENDING
        ).all()
        all_quals = confirmed_quals + pending_quals
        all_quals.sort(key=lambda q: q.qualifying_position)
        return all_quals

    def __repr__(self) -> str:
        return f"<PlayoffTournament {self.name}: {self.status}>"
