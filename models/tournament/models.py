"""
Module: models/tournament/models.py
Purpose: Tournament domain model
Data Structures: Tournament
Dependencies: models.base.db, models.user.models
ADR Reference: docs/ADR/ADR-0010-domain-separation-phase2.md
"""

from datetime import datetime
from models.base import db
from models.user.models import User, TournamentDirector


class Tournament(db.Model):
    """Core tournament entity with configuration and lifecycle management."""

    __tablename__ = "tournament"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)

    # Campi configurazione
    tournament_type = db.Column(db.String(50), nullable=False, default="Amalfi")
    without_x = db.Column(db.Boolean, default=False)  # Opzione "senza X"
    final_playoffs = db.Column(db.Boolean, default=True)  # Play off finali
    challenge_mode = db.Column(db.Boolean, default=False)  # Challenge

    # Status e date
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relazioni
    provas = db.relationship(
        "Prova", backref="tournament", lazy=True, cascade="all, delete-orphan"
    )
    directors = db.relationship(
        "User",
        secondary="tournament_director",
        primaryjoin=(id == TournamentDirector.tournament_id),
        secondaryjoin=(User.id == TournamentDirector.user_id),
        foreign_keys=[TournamentDirector.tournament_id, TournamentDirector.user_id],
        viewonly=True,
    )

    def can_be_modified(self):
        """Verifica se il torneo può essere modificato"""
        for prova in self.provas:
            if prova.status in ["inscription", "playing", "completed"]:
                return False
        return True

    def can_be_deleted(self):
        """Verifica se il torneo può essere cancellato"""
        for prova in self.provas:
            if prova.inscriptions:  # Se ha iscrizioni
                return False
        return True

    def get_status(self):
        """Restituisce lo status del torneo"""
        if not self.provas:
            return "setup"

        has_playing = any(p.status == "playing" for p in self.provas)
        has_completed = any(p.status == "completed" for p in self.provas)
        has_inscription = any(p.status == "inscription" for p in self.provas)

        if has_playing:
            return "in_progress"
        elif has_completed and not has_playing and not has_inscription:
            return "completed"
        elif has_inscription:
            return "registration_open"
        else:
            return "setup"

    def get_status_badge_class(self):
        """Restituisce la classe CSS per il badge status"""
        status = self.get_status()
        return {
            "setup": "bg-warning",
            "registration_open": "bg-info",
            "in_progress": "bg-primary",
            "completed": "bg-success",
        }.get(status, "bg-secondary")

    def get_status_text(self):
        """Restituisce il testo dello status"""
        status = self.get_status()
        return {
            "setup": "Setup",
            "registration_open": "Iscrizioni Aperte",
            "in_progress": "In Corso",
            "completed": "Completato",
        }.get(status, "Sconosciuto")

    def __repr__(self):
        return f"<Tournament {self.name}>"
