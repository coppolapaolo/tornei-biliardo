"""
User domain models - Clean version for Task 1.4

Focuses only on core User functionality needed for services testing.
Complex methods with external model dependencies will be added back in Task 1.5.

Author: Refactoring Phase 1 - Task 1.4
Created: 2025-08-01
"""

from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

from ..base import db, SimpleModel, BaseModel


class User(UserMixin, SimpleModel):
    """
    User model with role-based permissions.

    Clean version focused on core functionality for Task 1.4.
    Complex methods with external dependencies removed temporarily.
    """

    __tablename__ = "user"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)

    # Role system - replaces individual boolean flags
    role = db.Column(
        db.String(20), nullable=False, default="player"
    )  # admin, director, player

    # Profile information
    phone = db.Column(db.String(20))

    # Relationships using string references (resolved at runtime)
    inscriptions = db.relationship("Inscription", backref="user", lazy=True)
    match_results = db.relationship(
        "MatchResult", foreign_keys="MatchResult.user_id", lazy=True
    )
    classifications = db.relationship("Classification", backref="user", lazy=True)
    playoff_participations = db.relationship("Playoff", backref="user", lazy=True)

    def set_password(self, password):
        """Set password hash"""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """Check password"""
        return check_password_hash(self.password_hash, password)

    # Role checking properties - maintain backward compatibility
    @property
    def is_admin(self):
        return self.role == "admin"

    @property
    def is_director(self):
        return self.role == "director"

    @property
    def is_player(self):
        return self.role == "player"

    # Permission methods
    def can_manage_tournament(self, tournament_id):
        """Check if user can manage specific tournament"""
        from .permissions import PermissionChecker

        return PermissionChecker.can_manage_tournament(self, tournament_id)

    def can_manage_competition(self, competition_id):
        """Check if user can manage specific competition"""
        from .permissions import PermissionChecker

        return PermissionChecker.can_manage_competition(self, competition_id)

    def can_view_admin_panel(self):
        """Check if user can access admin panel"""
        return self.is_admin

    def can_inscribe_to_competition(self, competition_id):
        """Check if user can inscribe to competition"""
        if self.is_admin:
            return False  # Admin cannot inscribe (administrative role only)

        from .permissions import PermissionChecker

        return not PermissionChecker.can_manage_competition(self, competition_id)

    def get_managed_tournaments(self):
        """
        Get tournaments this user can manage.

        Simplified version for Task 1.4 - returns empty list.
        Will be enhanced in Task 1.5 when model dependencies are resolved.
        """
        # TODO: Implement in Task 1.5 when legacy_models.py is created
        return []

    def get_statistics(self):
        """
        Get user statistics.

        Simplified version for Task 1.4 - returns basic structure.
        Will be enhanced in Task 1.5 when model dependencies are resolved.
        """
        # TODO: Implement full statistics in Task 1.5
        return {
            "total_inscriptions": 0,
            "total_matches": 0,
            "won_matches": 0,
            "lost_matches": 0,
            "win_percentage": 0.0,
            "tournaments_played": 0,
            "total_racks_won": 0,
            "total_racks_played": 0,
            "rack_win_percentage": 0.0,
        }

    def __repr__(self):
        return f"<User {self.username} ({self.role})>"


class TournamentDirector(BaseModel):
    """
    Association table between tournaments and directors.

    Uses BaseModel because assignment tracking with timestamps
    could be useful for administrative purposes.
    """

    __tablename__ = "tournament_director"

    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), primary_key=True)
    tournament_id = db.Column(
        db.Integer, db.ForeignKey("tournament.id"), primary_key=True
    )
    assigned_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    director = db.relationship(
        "User", foreign_keys=[user_id], backref="tournament_director_associations"
    )
    assigned_by = db.relationship("User", foreign_keys=[assigned_by_id])
    # Tournament relationship will be resolved at runtime
    tournament = db.relationship("Tournament", backref="directors_association")


class DirectorRequest(BaseModel):
    """
    Request for promotion to director role.

    Uses BaseModel because request tracking with timestamps
    is important for administrative workflow.
    """

    __tablename__ = "director_request"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    status = db.Column(
        db.String(20), nullable=False, default="pending"
    )  # pending, approved, rejected
    requested_at = db.Column(db.DateTime, default=datetime.utcnow)
    processed_at = db.Column(db.DateTime)
    processed_by_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    notes = db.Column(db.Text)

    # Relationships
    user = db.relationship(
        "User",
        foreign_keys=[user_id],
        backref=db.backref("director_request", uselist=False),
    )
    processed_by = db.relationship("User", foreign_keys=[processed_by_id])

    def approve(self, admin_user):
        """Approve director request"""
        self.status = "approved"
        self.processed_at = datetime.utcnow()
        self.processed_by_id = admin_user.id

        # Promote user to director
        self.user.role = "director"

    def reject(self, admin_user, reason=None):
        """Reject director request"""
        self.status = "rejected"
        self.processed_at = datetime.utcnow()
        self.processed_by_id = admin_user.id
        if reason:
            self.notes = reason

    def __repr__(self):
        return f"<DirectorRequest {self.user.username} - {self.status}>"
