"""
Temporary file containing remaining non-migrated model.
This will be addressed in a future sprint.

Phase 2 Sprint 1: Successfully migrated Tournament, Competition, Match, and
Classification domains.
Only Playoff remains for future refactoring.
"""
from models.base import db


class Playoff(db.Model):
    """
    Playoff qualification tracking.

    TODO: This model will be refactored in a future sprint,
    potentially as part of a Tournament or Competition extension.
    """

    __tablename__ = "playoff"

    id = db.Column(db.Integer, primary_key=True)
    tournament_id = db.Column(
        db.Integer, db.ForeignKey("tournament.id"), nullable=False
    )
    category = db.Column(db.String(20), nullable=False)  # elite, academy
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    qualified_position = db.Column(db.Integer)  # posizione che dava diritto
    confirmation_status = db.Column(
        db.String(20), default="pending"
    )  # pending, confirmed, declined
    confirmed_at = db.Column(db.DateTime)

    # Relations
    tournament = db.relationship("Tournament", backref="playoffs")
    user = db.relationship("User", back_populates="playoff_participations")

    def __repr__(self):
        return f"<Playoff {self.user_id} ({self.category})>"
