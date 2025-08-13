"""
Module: models/user/models.py
Purpose: User domain models (User, TournamentDirector, DirectorRequest) –
    Task 1.4 completo.
Data Structures: User, TournamentDirector, DirectorRequest
Dependencies: models.base.db, flask_login, werkzeug.security
ADR Reference: docs/ADR/2025-08-01-task1-4-1-6-completion.md
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, TYPE_CHECKING

from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from ..base import db, BaseModel  # BaseModel for timestamps

if TYPE_CHECKING:  # Avoid runtime circular imports
    from ..match.models import Match
    from ..tournament.models import Tournament

from models.base import TimestampMixin, SoftDeleteMixin


# ────────────────────────────────────────────────────────────────────────────────
# USER
# ────────────────────────────────────────────────────────────────────────────────
class User(UserMixin, BaseModel, TimestampMixin, SoftDeleteMixin):
    """Core user entity with role-based permissions and rich statistics."""

    __tablename__ = "user"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=True)
    password_hash = db.Column(db.String(120), nullable=False)

    role = db.Column(db.String(20), nullable=False, default="player")
    # admin|director|player
    phone = db.Column(db.String(20), nullable=True)

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
    playoff_participations = db.relationship(
        "Playoff", back_populates="user", lazy=True
    )
    # Additional relationships for classification domain
    round_classifications = db.relationship(
        "RoundClassification", back_populates="user", lazy=True
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
        return self.role == "admin"

    @property
    def is_director(self) -> bool:
        return self.role == "director"

    @property
    def is_player(self) -> bool:
        return self.role == "player"

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
    def can_manage_tournament(self, tournament_id: int) -> bool:
        from .permissions import PermissionChecker

        return PermissionChecker.can_manage_tournament(self, tournament_id)

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

    # ───────────────────
    # Task 1.4 – implementations
    # ───────────────────
    def get_managed_tournaments(self) -> List["Tournament"]:
        """Tornei che l’utente può gestire."""
        if self.is_admin:
            from ..tournament.models import Tournament

            return Tournament.query.all()
        if self.is_director:
            return [assoc.tournament for assoc in self.tournament_director_associations]
        return []

    def get_statistics(self) -> Dict[str, Any]:
        """Statistiche complete usate da dashboard & analytics."""
        # import locale, evita circolari
        from ..competition.models import (
            Inscription,
            Prova,
        )
        from ..match.models import Match

        total_inscriptions = Inscription.query.filter_by(user_id=self.id).count()

        matches: List["Match"] = Match.query.filter(
            db.or_(Match.player1_id == self.id, Match.player2_id == self.id),
            Match.status == "completed",
        ).all()

        total_matches = len(matches)
        won_matches = sum(m.winner_id == self.id for m in matches)
        lost_matches = total_matches - won_matches
        win_percentage = (won_matches / total_matches * 100) if total_matches else 0

        tournaments_played = (
            Inscription.query.filter_by(user_id=self.id)
            .join(Prova)
            .with_entities(Prova.tournament_id)
            .distinct()
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

    # debug ─────────────────────────────────────────────────────────────────────
    def __repr__(self) -> str:  # pragma: no cover
        return f"<User {self.username} ({self.role})>"


# ────────────────────────────────────────────────────────────────────────────────
# TOURNAMENT DIRECTOR ASSOCIATION
# ────────────────────────────────────────────────────────────────────────────────
class TournamentDirector(BaseModel):
    __tablename__ = "tournament_director"

    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), primary_key=True)
    tournament_id = db.Column(
        db.Integer, db.ForeignKey("tournament.id"), primary_key=True
    )
    assigned_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow)

    director = db.relationship(
        "User", foreign_keys=[user_id], backref="tournament_director_associations"
    )
    assigned_by = db.relationship("User", foreign_keys=[assigned_by_id])
    tournament = db.relationship("Tournament", backref="directors_association")


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
        self.status = "approved"
        self.processed_at = datetime.utcnow()
        self.processed_by = admin
        self.user.role = "director"

    def reject(self, admin: "User", notes: str | None = None) -> None:
        self.status = "rejected"
        self.processed_at = datetime.utcnow()
        self.processed_by = admin
        if notes:
            self.notes = notes

    def __repr__(self) -> str:  # pragma: no cover
        return f"<DirectorRequest {self.id} {self.status}>"
