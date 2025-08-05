"""
Module: models/competition/models.py
Purpose: Competition domain models (Prova, Inscription)
Data Structures: Prova, Inscription
Dependencies: models.base.db, datetime
ADR Reference: docs/ADR/ADR-0010-domain-separation-phase2.md
"""

from datetime import datetime
from models.base import db


class Prova(db.Model):
    """Competition round within a tournament."""

    __tablename__ = "prova"

    id = db.Column(db.Integer, primary_key=True)
    tournament_id = db.Column(
        db.Integer, db.ForeignKey("tournament.id"), nullable=False
    )
    number = db.Column(db.Integer, nullable=False)  # 1-10
    name = db.Column(db.String(100))
    date = db.Column(db.Date, nullable=False)

    # NUOVI CAMPI
    location = db.Column(db.String(200))  # Luogo della prova
    description = db.Column(db.Text)  # Descrizione opzionale
    rounds_count = db.Column(
        db.Integer, nullable=False, default=3
    )  # Numero di turni per questa prova
    min_participants = db.Column(db.Integer, default=2)  # Minimo iscritti
    max_participants = db.Column(db.Integer)  # Massimo iscritti (opzionale)
    entry_fee = db.Column(db.Float, default=0.0)  # Quota di partecipazione

    # Game settings
    discipline = db.Column(db.String(50), nullable=False)  # palla 8, 9, 10
    distance = db.Column(db.Integer, nullable=False)  # numero rack da giocare
    best_of = db.Column(
        db.Boolean, default=False
    )  # Se True: "al meglio di", se False: "esatto numero"

    # Date iscrizioni
    inscription_start = db.Column(db.DateTime)
    inscription_end = db.Column(db.DateTime)

    # Stato della prova
    status = db.Column(
        db.String(20), default="setup"
    )  # setup, inscription, playing, completed
    current_round = db.Column(db.Integer, default=0)  # 0=non iniziata, 1,2,3=turni

    # Relazioni
    inscriptions = db.relationship("Inscription", backref="prova", lazy=True)
    matches = db.relationship("Match", backref="prova", lazy=True)

    def get_real_status(self):
        """Restituisce lo status reale della prova"""
        if self.status == "setup":
            return "setup"
        elif self.status == "inscription":
            if self.inscription_end and datetime.utcnow() > self.inscription_end:
                return "inscription_closed"
            return "inscription"
        elif self.status == "playing":
            if self.current_round > 0:
                return "playing"
            else:
                return "ready_to_start"
        elif self.status == "completed":
            return "completed"
        return "setup"

    def get_status_badge_info(self):
        """Restituisce info per badge status"""
        real_status = self.get_real_status()
        return {
            "setup": {"class": "bg-warning", "text": "Setup"},
            "inscription": {"class": "bg-info", "text": "Iscrizioni Aperte"},
            "inscription_closed": {
                "class": "bg-secondary",
                "text": "Iscrizioni Chiuse",
            },
            "ready_to_start": {"class": "bg-primary", "text": "Pronta per Iniziare"},
            "playing": {"class": "bg-success", "text": "In Corso"},
            "completed": {"class": "bg-dark", "text": "Completata"},
        }.get(real_status, {"class": "bg-secondary", "text": "Sconosciuto"})

    def can_inscribe(self):
        """Verifica se si possono fare iscrizioni"""
        if self.status != "inscription":
            return False
        if self.inscription_end and datetime.utcnow() > self.inscription_end:
            return False
        return True

    def is_user_inscribed(self, user_id) -> bool:
        """Verifica se un utente è iscritto"""
        return any(insc.user_id == user_id for insc in self.inscriptions)

    def can_modify_inscription_dates(self):
        """Verifica se si possono modificare le date iscrizioni"""
        return self.status == "setup"

    def can_be_modified(self):
        """Verifica se la prova può essere modificata"""
        return self.status == "setup"

    def can_be_deleted(self):
        """Verifica se la prova può essere cancellata"""
        return not self.inscriptions and self.status == "setup"

    def get_winning_score(self):
        """Restituisce il punteggio per vincere"""
        if self.best_of:
            return (self.distance // 2) + 1
        else:
            return self.distance

    def is_match_finished(self, score1, score2):
        """Verifica se una partita è finita"""
        winning_score = self.get_winning_score()
        return score1 >= winning_score or score2 >= winning_score

    def copy_settings_from(self, source_prova):
        """Copia le impostazioni da un'altra prova"""
        self.discipline = source_prova.discipline
        self.distance = source_prova.distance
        self.best_of = source_prova.best_of
        self.rounds_count = source_prova.rounds_count
        self.min_participants = source_prova.min_participants
        self.max_participants = source_prova.max_participants
        self.entry_fee = source_prova.entry_fee

    def __repr__(self):
        return f"<Prova {self.name} (Torneo {self.tournament_id})>"


class Inscription(db.Model):
    """Player registration to a competition round."""

    __tablename__ = "inscription"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    prova_id = db.Column(db.Integer, db.ForeignKey("prova.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    initial_order = db.Column(db.Integer)  # ordine sorteggio iniziale

    def __repr__(self):
        return f"<Inscription {self.user_id} -> {self.prova_id}>"
