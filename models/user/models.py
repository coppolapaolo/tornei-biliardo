"""
Module: models/user/models.py
Purpose: User domain models (User, TournamentDirector, DirectorRequest) –
    Task 1.4 completo.
Data Structures: User, TournamentDirector, DirectorRequest
Dependencies: models.base.db, flask_login, werkzeug.security
Updated: Added encryption for personal data (email, phone) per SPECIFICHE.md
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, TYPE_CHECKING

from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from ..base import db, BaseModel  # BaseModel for timestamps
from ..fields import EncryptedString  # Encrypted field types

if TYPE_CHECKING:
    from ..location.models import BilliardHall
from .role_enum import UserRole

if TYPE_CHECKING:  # Avoid runtime circular imports
    from ..match.models import Match
    from ..campionato.models import Campionato

from models.base import TimestampMixin, SoftDeleteMixin


# ────────────────────────────────────────────────────────────────────────────────
# USER
# ────────────────────────────────────────────────────────────────────────────────
class User(UserMixin, BaseModel, TimestampMixin, SoftDeleteMixin):
    """Core user entity with role-based permissions and rich statistics."""

    __tablename__ = "user"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(
        EncryptedString(200), unique=True, nullable=True
    )  # Encrypted personal data
    password_hash = db.Column(db.String(120), nullable=False)

    role = db.Column(db.String(20), nullable=False, default="player")
    # admin|director|player
    phone = db.Column(EncryptedString(100), nullable=True)  # Encrypted personal data

    # Rating systems (player skill metrics)
    fargo_rating = db.Column(db.Integer, nullable=True)  # Fargo rating
    elo_rating = db.Column(db.Integer, nullable=True)  # Elo rating

    # per utenti cancellati
    previous_username = db.Column(db.String(80), nullable=True)

    # Relationships (string names to postpone model imports)
    inscriptions = db.relationship("Inscription", back_populates="user", lazy=True)
    match_results = db.relationship(
        "MatchResult", foreign_keys="MatchResult.user_id", lazy=True
    )
    classifications = db.relationship(
        "Classification", back_populates="user", lazy=True
    )
    # Additional relationships for classification domain
    round_classifications = db.relationship(
        "RoundClassification", back_populates="user", lazy=True
    )
    gara_classifications = db.relationship(
        "GaraClassification", back_populates="user", lazy=True
    )

    # Player encounter relationships
    player1_encounters = db.relationship(
        "PlayerEncounter",
        foreign_keys="PlayerEncounter.player1_id",
        back_populates="player1",
        lazy=True,
    )

    player2_encounters = db.relationship(
        "PlayerEncounter",
        foreign_keys="PlayerEncounter.player2_id",
        back_populates="player2",
        lazy=True,
    )

    # Director request relationship
    director_request = db.relationship(
        "DirectorRequest",
        foreign_keys="DirectorRequest.user_id",
        uselist=False,
        viewonly=True,
        primaryjoin=(
            "and_(User.id==DirectorRequest.user_id, "
            "DirectorRequest.status=='pending')"
        ),
    )

    # ───────────────────
    # Auth helpers
    # ───────────────────
    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    # ───────────────────
    # Role shortcuts
    # ───────────────────
    @property
    def is_admin(self) -> bool:
        return self.role == UserRole.ADMIN.value

    @property
    def is_director(self) -> bool:
        return self.role == UserRole.DIRECTOR.value

    @property
    def is_venue_manager(self) -> bool:
        """Check if user is assigned as manager for any venue."""
        if self.is_admin:
            return True
        assignment = VenueManagement.query.filter_by(
            user_id=self.id, is_active=True
        ).first()
        return assignment is not None

    @property
    def is_player(self) -> bool:
        return self.role == UserRole.PLAYER.value

    # Flask-Login integration: utente attivo solo se non soft-deleted
    @property
    def is_active(self) -> bool:  # type: ignore[override]
        return not self.is_deleted

    # Operazioni di anonimizzazione (PII → NULL, username tecnico)
    def anonymize(self) -> None:
        if not self.is_deleted:
            self.deleted_at = datetime.utcnow()
        if not self.previous_username:
            self.previous_username = self.username
        # Username tecnico e univoco; UI mostrerà una versione "accattivante"
        stamp = (
            self.deleted_at.strftime("%Y%m%d")
            if self.deleted_at
            else datetime.utcnow().strftime("%Y%m%d")
        )
        self.username = f"deleted-{self.id}-{stamp}"
        self.email = None
        self.phone = None
        # opzionale: invalidare la password
        self.password_hash = "!deleted!"

    # ───────────────────
    # Permission helpers
    # ───────────────────
    def can_manage_campionato(self, campionato_id: int) -> bool:
        from .permissions import PermissionChecker

        return PermissionChecker.can_manage_campionato(self, campionato_id)

    def can_manage_competition(self, competition_id: int) -> bool:
        from .permissions import PermissionChecker

        return PermissionChecker.can_manage_competition(self, competition_id)

    def can_view_admin_panel(self) -> bool:
        return self.is_admin

    def can_inscribe_to_competition(self, competition_id: int) -> bool:
        if self.is_admin:
            return False
        from .permissions import PermissionChecker

        return not PermissionChecker.can_manage_competition(self, competition_id)

    def can_manage_venue(self, venue_id: int) -> bool:
        """Check if user can manage a specific venue."""
        if self.is_admin:
            return True
        if not self.is_venue_manager:
            return False

        # Check if user is assigned as manager for this venue
        assignment = VenueManagement.query.filter_by(
            user_id=self.id, venue_id=venue_id, is_active=True
        ).first()
        return assignment is not None

    def get_managed_venues(self) -> List["BilliardHall"]:
        """Get list of venues this user can manage."""
        if self.is_admin:
            # Admin can manage all venues
            from ..location.models import BilliardHall

            return BilliardHall.query.filter_by(is_active=True).all()

        if not self.is_venue_manager:
            return []

        # Get venues assigned to this user
        from ..location.models import BilliardHall

        venue_assignments = VenueManagement.query.filter_by(
            user_id=self.id, is_active=True
        ).all()

        venue_ids = [assignment.venue_id for assignment in venue_assignments]
        if not venue_ids:
            return []

        return BilliardHall.query.filter(
            BilliardHall.id.in_(venue_ids), BilliardHall.is_active is True
        ).all()

    # ───────────────────
    # Task 1.4 – implementations
    # ───────────────────
    def get_managed_campionatos(self) -> List["Campionato"]:
        """Campionati che l’utente può gestire."""
        if self.is_admin:
            from ..campionato.models import Campionato

            return Campionato.query.all()
        if self.is_director:
            return [
                assoc.campionato
                for assoc in self.director_assignments
                if assoc.entity_type == "campionato" and assoc.campionato
            ]
        return []

    def get_statistics(self) -> Dict[str, Any]:
        """Statistiche complete usate da dashboard & analytics."""
        # import locale, evita circolari
        from ..competition.models import (
            Inscription,
            Gara,
        )
        from ..match.models import Match

        total_inscriptions = (
            Inscription.query.filter_by(user_id=self.id).count()
        )

        matches: List["Match"] = Match.query.filter(
            db.or_(Match.player1_id == self.id, Match.player2_id == self.id),
            Match.status == "completed",
        ).all()

        total_matches = len(matches)
        won_matches = sum(m.winner_id == self.id for m in matches)
        lost_matches = total_matches - won_matches
        win_percentage = (won_matches / total_matches * 100) if total_matches else 0

        # Conta solo i campionati con almeno una gara completata dove
        # l'utente ha partecipato
        tournaments_played = (
            Inscription.query.filter_by(user_id=self.id)
            .join(Gara)
            .filter(Gara.status == "completed")  # Solo gare completate
            .with_entities(Gara.campionato_id)
            .distinct()
            .count()
        )

        # Conta le gare completate dove l'utente ha partecipato
        provas_played = (
            Inscription.query.filter_by(user_id=self.id)
            .join(Gara)
            .filter(Gara.status == "completed")  # Solo gare completate
            .count()
        )

        total_racks_won = sum(self._racks_won(m) for m in matches)
        total_racks_played = sum(m.player1_score + m.player2_score for m in matches)
        rack_win_percentage = (
            (total_racks_won / total_racks_played * 100) if total_racks_played else 0
        )

        return {
            "total_inscriptions": total_inscriptions,
            "total_matches": total_matches,
            "won_matches": won_matches,
            "lost_matches": lost_matches,
            "win_percentage": round(win_percentage, 1),
            "tournaments_played": tournaments_played,
            "provas_played": provas_played,
            "total_racks_won": total_racks_won,
            "total_racks_played": total_racks_played,
            "rack_win_percentage": round(rack_win_percentage, 1),
        }

    # helper ────────────────────────────────────────────────────────────────────
    def _racks_won(self, match: "Match") -> int:
        if match.player1_id == self.id:
            return match.player1_score
        if match.player2_id == self.id:
            return match.player2_score
        return 0

    # ───────────────────
    # Gamification helpers
    # ───────────────────
    def has_unlocked_achievement(self, achievement_slug: str) -> bool:
        """Check if user has unlocked a specific achievement.

        Args:
            achievement_slug: Slug of the achievement to check

        Returns:
            True if achievement is unlocked, False otherwise

        Usage:
            {% if current_user.has_unlocked_achievement('aspiring_director') %}
                <!-- Show director request button -->
            {% endif %}
        """
        from models.gamification.achievement_service import AchievementService

        return AchievementService.has_achievement(self.id, achievement_slug)

    # debug ─────────────────────────────────────────────────────────────────────
    def __repr__(self) -> str:  # pragma: no cover
        return f"<User {self.username} ({self.role})>"


# ────────────────────────────────────────────────────────────────────────────────
# DIRECTOR ASSIGNMENT (GENERIC)
# ────────────────────────────────────────────────────────────────────────────────
class DirectorAssignment(BaseModel):
    __tablename__ = "director_assignment"

    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), primary_key=True)
    entity_type = db.Column(db.String(20), primary_key=True)  # 'campionato' o 'gara'
    entity_id = db.Column(db.Integer, primary_key=True)
    assigned_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    director = db.relationship(
        "User", foreign_keys=[user_id], backref="director_assignments"
    )
    assigned_by = db.relationship("User", foreign_keys=[assigned_by_id])

    @property
    def campionato(self):
        """Get campionato if this is a campionato assignment."""
        if self.entity_type == "campionato":
            from models.campionato.models import Campionato

            return db.session.get(Campionato, self.entity_id)
        return None

    @property
    def gara(self):
        """Get gara if this is a gara assignment."""
        if self.entity_type == "gara":
            from models.competition.models import Gara

            return db.session.get(Gara, self.entity_id)
        return None

    def __repr__(self):
        return (
            f"<DirectorAssignment {self.user_id} -> "
            f"{self.entity_type}:{self.entity_id}>"
        )


# Legacy aliases for backward compatibility
TournamentDirector = DirectorAssignment  # Backward compatibility
GaraDirector = DirectorAssignment  # Backward compatibility


# ────────────────────────────────────────────────────────────────────────────────
# DIRECTOR REQUEST
# ────────────────────────────────────────────────────────────────────────────────
class DirectorRequest(BaseModel):
    __tablename__ = "director_request"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    requested_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(
        db.String(20), nullable=False, default="pending"
    )  # pending|approved|rejected
    processed_at = db.Column(db.DateTime)
    processed_by_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    notes = db.Column(db.Text)

    user = db.relationship("User", foreign_keys=[user_id])
    processed_by = db.relationship("User", foreign_keys=[processed_by_id])

    # state helpers ---
    def approve(self, admin: "User") -> None:
        from ..status_enum import DirectorRequestStatus

        self.status = DirectorRequestStatus.APPROVED
        self.processed_at = datetime.utcnow()
        self.processed_by = admin
        # Get the user object and update role

        session = db.session
        user = session.get(User, self.user_id)
        if user:
            user.role = "director"

    def reject(self, admin: "User", notes: str | None = None) -> None:
        from ..status_enum import DirectorRequestStatus

        self.status = DirectorRequestStatus.REJECTED
        self.processed_at = datetime.utcnow()
        self.processed_by = admin
        if notes:
            self.notes = notes

    def __repr__(self) -> str:  # pragma: no cover
        return f"<DirectorRequest {self.id} {self.status}>"


# ────────────────────────────────────────────────────────────────────────────────
# VENUE MANAGER REQUEST
# ────────────────────────────────────────────────────────────────────────────────
class VenueManagerRequest(BaseModel):
    """Request to manage a specific venue."""

    __tablename__ = "venue_manager_request"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    venue_id = db.Column(db.Integer, db.ForeignKey("billiard_hall.id"), nullable=False)
    requested_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(
        db.String(20), nullable=False, default="pending"
    )  # pending|approved|rejected|cancelled|contested
    processed_at = db.Column(db.DateTime)
    processed_by_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    notes = db.Column(db.Text)  # User notes when requesting
    admin_notes = db.Column(db.Text)  # Admin notes when processing
    is_contested = db.Column(
        db.Boolean, default=False
    )  # True if requesting already managed venue

    user = db.relationship("User", foreign_keys=[user_id])
    processed_by = db.relationship("User", foreign_keys=[processed_by_id])
    venue = db.relationship("BilliardHall", foreign_keys=[venue_id])

    __table_args__ = (
        db.UniqueConstraint("user_id", "venue_id", name="_user_venue_request_uc"),
    )

    # state helpers ---
    def approve(self, admin: "User", admin_notes: str | None = None) -> None:
        """Approve venue manager request and automatically assign venue."""
        from ..status_enum import VenueManagerRequestStatus

        self.status = VenueManagerRequestStatus.APPROVED
        self.processed_at = datetime.utcnow()
        self.processed_by = admin
        if admin_notes:
            self.admin_notes = admin_notes

        # Automatically create venue management assignment
        from .services import VenueManagementService

        VenueManagementService.assign_venue_manager(self.user_id, self.venue_id, admin)

    def reject(self, admin: "User", admin_notes: str | None = None) -> None:
        """Reject venue manager request."""
        from ..status_enum import VenueManagerRequestStatus

        self.status = VenueManagerRequestStatus.REJECTED
        self.processed_at = datetime.utcnow()
        self.processed_by = admin
        if admin_notes:
            self.admin_notes = admin_notes

    def cancel(self) -> None:
        """Cancel venue manager request."""
        from ..status_enum import VenueManagerRequestStatus

        self.status = VenueManagerRequestStatus.CANCELLED
        self.processed_at = datetime.utcnow()

    def __repr__(self) -> str:  # pragma: no cover
        return f"<VenueManagerRequest {self.id} {self.status}>"


# ────────────────────────────────────────────────────────────────────────────────
# VENUE MANAGEMENT ASSIGNMENT
# ────────────────────────────────────────────────────────────────────────────────
class VenueManagement(BaseModel):
    """Assignment of venue managers to specific venues."""

    __tablename__ = "venue_management"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    venue_id = db.Column(db.Integer, db.ForeignKey("billiard_hall.id"), nullable=False)
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow)
    assigned_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    revoked_at = db.Column(db.DateTime, nullable=True)
    revoked_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)

    # Relationships
    user = db.relationship("User", foreign_keys=[user_id])
    assigned_by = db.relationship("User", foreign_keys=[assigned_by_id])
    revoked_by = db.relationship("User", foreign_keys=[revoked_by_id])
    venue = db.relationship("BilliardHall", foreign_keys=[venue_id])

    # Unique constraint: one manager per venue
    __table_args__ = (
        db.UniqueConstraint("venue_id", "is_active", name="uq_venue_active_manager"),
    )

    def revoke(self, admin: "User") -> None:
        """Revoke venue management assignment."""
        self.is_active = False
        self.revoked_at = datetime.utcnow()
        self.revoked_by = admin

    def __repr__(self) -> str:  # pragma: no cover
        return f"<VenueManagement {self.user_id} -> {self.venue_id}>"
