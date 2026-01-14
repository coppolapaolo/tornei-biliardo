"""
Module: models/campionato/models.py
Purpose: Campionato domain model
Data Structures: Campionato
Dependencies: models.base.db, models.user.models
"""

from datetime import datetime
from typing import TYPE_CHECKING
from models.base import db
from models.status_enum import TournamentStatus, GaraStatus, EntityType
from models.matchmaking.configuration import MatchmakingStrategy, OddNumberPolicy

if TYPE_CHECKING:
    from models.user.models import User, TournamentDirector


class Campionato(db.Model):
    """Core campionato entity with configuration and lifecycle management."""

    __tablename__ = "campionato"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)

    # Campi configurazione
    campionato_type = db.Column(
        db.String(50), nullable=False, default=MatchmakingStrategy.AMALFI.value
    )  # Matchmaking strategy type (Amalfi, Random, etc.)
    challenge_mode = db.Column(db.Boolean, default=False)  # Challenge drill mode
    planned_gare_count = db.Column(
        db.Integer, nullable=False, default=10
    )  # Target number of gare in campionato

    # Default values inherited by gare
    default_venue_id = db.Column(
        db.Integer, db.ForeignKey("billiard_hall.id"), nullable=True
    )  # Default venue for gare
    default_entry_fee = db.Column(db.Float, nullable=True)  # Default entry fee
    default_rounds_count = db.Column(
        db.Integer, nullable=False, default=3
    )  # Default rounds per gara
    default_odd_policy = db.Column(
        db.String(30), nullable=False, default=OddNumberPolicy.BYE.value
    )  # Default odd number handling (bye, bye_with_challenge, trio)
    default_anti_rematch = db.Column(
        db.Boolean, nullable=False, default=True
    )  # Default anti-rematch setting
    default_classification_system = db.Column(
        db.String(10), nullable=False, default="WINS"
    )  # Default: RACK, WINS, POSITION (see docs/CLASSIFICATION_SYSTEM.md)

    # DEPRECATED - To be removed in future migration
    # Use default_odd_policy instead of without_x
    without_x = db.Column(db.Boolean, default=False)  # DEPRECATED: use default_odd_policy
    # Playoff configuration now in PlayoffConfiguration model
    final_playoffs = db.Column(db.Boolean, default=True)  # DEPRECATED: use PlayoffConfiguration
    # Scoring is now automatic based on campionato_type
    scoring_policy = db.Column(
        db.String(50), nullable=False, default="classic"
    )  # DEPRECATED: automatic from campionato_type

    # Status e date
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Soft delete functionality
    is_deleted = db.Column(db.Boolean, default=False)
    deleted_at = db.Column(db.DateTime, nullable=True)
    deleted_reason = db.Column(db.String(255), nullable=True)

    # Relazioni
    gare = db.relationship(
        "Gara", backref="campionato", lazy=True, cascade="all, delete-orphan"
    )
    default_venue = db.relationship(
        "BilliardHall", foreign_keys=[default_venue_id], lazy=True
    )

    @property
    def directors(self):
        """Get directors for this campionato."""
        from models.user.models import DirectorAssignment, User

        return (
            db.session.query(User)
            .join(DirectorAssignment, User.id == DirectorAssignment.user_id)
            .filter(
                DirectorAssignment.entity_type == EntityType.CAMPIONATO.value,
                DirectorAssignment.entity_id == self.id,
            )
            .all()
        )

    # Enhanced playoff relationships
    playoff_configurations = db.relationship(
        "PlayoffConfiguration",
        back_populates="campionato",
        cascade="all, delete-orphan",
    )

    def can_be_modified(self):
        """Verifica se il campionato può essere modificato"""
        # Fix: Properly access the relationship collection
        gare = getattr(self, "gare", [])
        for gara in gare:
            # Cannot modify if gara has advanced status or has inscriptions
            if gara.status in [
                GaraStatus.INSCRIPTION.value,
                GaraStatus.PLAYING.value,
                GaraStatus.COMPLETED.value,
            ]:
                return False
            if getattr(gara, "inscriptions", []):  # Se ha iscrizioni
                return False
        return True

    def can_be_deleted(self):
        """Verifica se il campionato può essere cancellato"""
        # Properly access the relationship collection
        gare = getattr(self, "gare", [])
        for gara in gare:
            if getattr(gara, "inscriptions", []):
                return False
        return True

    def get_status(self):
        """Restituisce lo status del campionato"""
        gare = getattr(self, "gare", [])
        if not gare:
            return TournamentStatus.SETUP.value

        has_playing = any(p.status == GaraStatus.PLAYING.value for p in gare)
        has_completed = any(
            p.status == GaraStatus.COMPLETED.value for p in gare
        )
        has_inscription = any(
            p.status == GaraStatus.INSCRIPTION.value for p in gare
        )

        if has_playing:
            return TournamentStatus.IN_PROGRESS.value
        elif has_completed and not has_playing and not has_inscription:
            return TournamentStatus.COMPLETED.value
        elif has_inscription:
            return TournamentStatus.REGISTRATION_OPEN.value
        else:
            return TournamentStatus.SETUP.value

    def can_be_hard_deleted(self) -> bool:
        """Check if campionato permanently deletable (no matches)."""
        from models.status_enum import MatchStatus

        # Properly access the relationship collections
        gare = getattr(self, "gare", [])
        for gara in gare:
            matches = getattr(gara, "matches", [])
            for match in matches:
                if match.status in [
                    MatchStatus.COMPLETED.value,
                    MatchStatus.PLAYING.value,
                ]:
                    return False
        return True

    def get_status_badge_class(self):
        """Restituisce la classe CSS per il badge status"""
        status = self.get_status()
        return {
            TournamentStatus.SETUP.value: "bg-warning",
            TournamentStatus.REGISTRATION_OPEN.value: "bg-info",
            TournamentStatus.IN_PROGRESS.value: "bg-primary",
            TournamentStatus.COMPLETED.value: "bg-success",
        }.get(status, "bg-secondary")

    def get_status_text(self):
        """Restituisce il testo dello status"""
        status = self.get_status()
        return {
            TournamentStatus.SETUP.value: "Setup",
            TournamentStatus.REGISTRATION_OPEN.value: "Iscrizioni Aperte",
            TournamentStatus.IN_PROGRESS.value: "In Corso",
            TournamentStatus.COMPLETED.value: "Completato",
        }.get(status, "Sconosciuto")

    def has_playoff_configurations(self) -> bool:
        """Check if campionato has playoff configurations."""
        configurations = getattr(self, "playoff_configurations", [])
        return len(configurations) > 0

    def can_generate_playoffs(self) -> bool:
        """Check if campionato is ready for playoff generation."""
        return (
            self.get_status() == TournamentStatus.COMPLETED.value
            and self.has_playoff_configurations()
        )

    def generate_playoff_qualifications(self) -> dict:
        """Generate playoff qualifications for all configurations."""
        if not self.can_generate_playoffs():
            raise ValueError("Campionato is not ready for playoff generation")

        from ..playoff.services import PlayoffService

        return PlayoffService.generate_all_qualifications(self.id)

    def get_playoff_status(self) -> dict:
        """Get comprehensive playoff status."""
        from ..playoff.services import PlayoffService

        return PlayoffService.get_campionato_playoff_status(self.id)

    def soft_delete(self, reason: str = "") -> bool:
        """Perform soft delete on campionato with played matches."""
        if self.is_deleted:
            return False

        self.is_deleted = True
        self.deleted_at = datetime.utcnow()
        self.deleted_reason = reason or "Campionato deleted by administrator"
        self.is_active = False

        # Also soft delete related provas
        gare = getattr(self, "gare", [])
        for gara in gare:
            if hasattr(gara, "soft_delete"):
                # Fix: Ensure we pass a string to gara.soft_delete()
                delete_reason = (
                    f"Campionato deleted: {reason}"
                    if reason
                    else "Campionato deleted: Administrator action"
                )
                gara.soft_delete(delete_reason)

        return True

    def restore(self) -> bool:
        """Restore a soft-deleted campionato.

        Also restores all related gare that were soft-deleted with the
        campionato.
        """
        if not self.is_deleted:
            return False

        self.is_deleted = False
        self.deleted_at = None
        self.deleted_reason = None
        self.is_active = True

        # Also restore related gare that were soft-deleted
        gare = getattr(self, "gare", [])
        for gara in gare:
            if hasattr(gara, "is_deleted") and gara.is_deleted:
                if hasattr(gara, "restore"):
                    gara.restore()

        return True

    def get_scoring_system(self) -> dict:
        """Get the automatic scoring system based on campionato_type.

        Returns a dict with ordering criteria for classification.
        The scoring system is automatically determined by the campionato type:
        - AMALFI: Wins DESC → Rack diff DESC → SSR DESC → Previous order
        - RANDOM: Racks won DESC → SSR DESC → Previous order
        """
        if self.campionato_type == MatchmakingStrategy.AMALFI.value:
            return {
                "type": "amalfi",
                "ordering": ["wins", "rack_difference", "ssr", "previous_order"],
                "description": "Vittorie → Differenza rack → SSR → Ordine precedente"
            }
        elif self.campionato_type == MatchmakingStrategy.RANDOM.value:
            return {
                "type": "random",
                "ordering": ["racks_won", "ssr", "previous_order"],
                "description": "Rack vinti → SSR → Ordine precedente"
            }
        else:
            # Default fallback for other strategies
            return {
                "type": "default",
                "ordering": ["wins", "rack_difference", "previous_order"],
                "description": "Vittorie → Differenza rack → Ordine precedente"
            }

    def get_scoring_policy_name(self) -> str:
        """DEPRECATED: Use get_scoring_system() instead.

        Get the name of the scoring policy for this campionato.
        Scoring is now automatic based on campionato_type.
        """
        # Return automatic type based on campionato_type
        return self.get_scoring_system()["type"]

    def set_scoring_policy(self, policy_name: str) -> None:
        """DEPRECATED: Scoring policy is now automatic based on campionato_type.

        This method is kept for backwards compatibility but does nothing.
        The scoring system is automatically determined by campionato_type:
        - AMALFI → amalfi scoring
        - RANDOM → random scoring

        Args:
            policy_name: Ignored (kept for API compatibility)
        """
        # No-op: scoring is now automatic
        pass

    def _legacy_set_scoring_policy(self, policy_name: str) -> None:
        """Internal legacy method for migration purposes only."""
        valid_policies = ["classic", "fargo", "elo"]
        if policy_name not in valid_policies:
            raise ValueError(
                f"Invalid scoring policy: {policy_name}. "
                f"Valid options: {valid_policies}"
            )
        self.scoring_policy = policy_name

    @classmethod
    def get_active_campionatos(cls):
        """Get all non-deleted campionati."""
        return cls.query.filter_by(is_deleted=False)

    @classmethod
    def get_deleted_campionatos(cls):
        """Get all soft-deleted campionati."""
        return cls.query.filter_by(is_deleted=True)

    def __repr__(self):
        return f"<Campionato {self.name}>"
