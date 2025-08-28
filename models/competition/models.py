"""
Module: models/competition/models.py
Purpose: Competition domain models (Prova, Inscription)
Data Structures: Prova, Inscription
Dependencies: models.base.db, datetime
"""

from datetime import datetime
from models.base import db
from enum import Enum
from models.status_enum import ProvaStatus, MatchStatus
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


class WithdrawPolicy(str, Enum):
    # mantiene negli abbinamenti, assegna vittoria massima agli avversari
    FORFEIT = "Forfeit"
    EXCLUDE = "Exclude"  # default: tratta come X


class Prova(db.Model):
    """Competition round within a tournament or standalone."""

    __tablename__ = "prova"

    id = db.Column(db.Integer, primary_key=True)

    # FK nullable per supportare standalone competitions
    tournament_id = db.Column(
        db.Integer, db.ForeignKey("tournament.id", ondelete="CASCADE"), nullable=True
    )

    # Director FK per standalone competitions
    director_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)

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
        db.String(20), default=ProvaStatus.SETUP.value
    )  # setup, inscription, playing, completed
    current_round = db.Column(db.Integer, default=0)  # 0=non iniziata, 1,2,3=turni

    withdraw_policy = db.Column(
        db.String(10), nullable=False, default=WithdrawPolicy.EXCLUDE.value
    )

    # Relazioni
    inscriptions = db.relationship(
        "Inscription",
        backref="prova",
        lazy=True,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    matches = db.relationship(
        "Match",
        backref="prova",
        lazy=True,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    director = db.relationship(
        "User", foreign_keys=[director_id], backref="standalone_provas"
    )

    # Property per identificare se è standalone
    @property
    def is_standalone(self):
        """Check if this is a standalone competition."""
        return self.tournament_id is None

    def get_organizer(self):
        """Get the competition organizer (director or tournament owner)."""
        if self.is_standalone:
            return self.director
        if self.tournament and self.tournament.directors:
            return self.tournament.directors[0]
        return None

    def get_display_name(self):
        """Get display name including tournament/standalone info."""
        if self.is_standalone:
            return f"{self.name} (Standalone)"
        return f"{self.name} - {self.tournament.name}"

    def get_real_status(self):
        """Restituisce lo status reale, considerando anche round e iscrizioni"""
        if self.status == ProvaStatus.PLAYING.value:
            # Se tutti i match del round corrente sono finiti
            matches_list = getattr(self, "matches", []) or []
            current_round_matches = [
                m
                for m in matches_list
                if hasattr(m, "round_number") and m.round_number == self.current_round
            ]
            all_matches_finished = all(
                m.status == MatchStatus.COMPLETED.value for m in current_round_matches
            )
            if all_matches_finished:
                if self.current_round < self.rounds_count:
                    return "round_completed"
                else:
                    return "tournament_completed"
        elif self.status == ProvaStatus.INSCRIPTION.value:
            if self.inscription_end and datetime.utcnow() > self.inscription_end:
                return "inscription_closed"
        return self.status

    def get_status_badge_info(self):
        """Restituisce info per badge status nel template"""
        real_status = self.get_real_status()
        return {
            ProvaStatus.SETUP.value: {"class": "bg-warning", "text": "Setup"},
            ProvaStatus.INSCRIPTION.value: {
                "class": "bg-info",
                "text": "Iscrizioni Aperte",
            },
            "inscription_closed": {
                "class": "bg-secondary",
                "text": "Iscrizioni Chiuse",
            },
            "ready_to_start": {"class": "bg-primary", "text": "Pronta per Iniziare"},
            ProvaStatus.PLAYING.value: {"class": "bg-success", "text": "In Corso"},
            ProvaStatus.COMPLETED.value: {"class": "bg-dark", "text": "Completata"},
            "round_completed": {"class": "bg-info", "text": "Turno Completato"},
            "tournament_completed": {"class": "bg-dark", "text": "Torneo Completato"},
        }.get(real_status, {"class": "bg-secondary", "text": "Sconosciuto"})

    def can_start_new_round(self):
        """Verifica se si può iniziare un nuovo round"""
        if self.status != ProvaStatus.PLAYING.value:
            return False
        if self.current_round >= self.rounds_count:
            return False
        # Tutti i match del round corrente devono essere completati
        matches_list = getattr(self, "matches", []) or []
        current_round_matches = [
            m
            for m in matches_list
            if hasattr(m, "round_number") and m.round_number == self.current_round
        ]
        return all(
            m.status == MatchStatus.COMPLETED.value for m in current_round_matches
        )

    def can_inscribe(self):
        """Verifica se si possono fare iscrizioni"""
        if self.status != ProvaStatus.INSCRIPTION.value:
            return False
        if self.inscription_end and datetime.utcnow() > self.inscription_end:
            return False
        return True

    def is_user_inscribed(self, user_id) -> bool:
        """Verifica se un utente è iscritto"""
        inscriptions_list = getattr(self, "inscriptions", []) or []
        return any(insc.user_id == user_id for insc in inscriptions_list)

    def can_modify_inscription_dates(self):
        """Verifica se si possono modificare le date iscrizioni"""
        return self.status == ProvaStatus.SETUP.value

    def can_be_modified(self):
        """Verifica se la prova può essere modificata"""
        return self.status == ProvaStatus.SETUP.value

    def can_be_deleted(self):
        """Verifica se la prova può essere cancellata"""
        inscriptions_list = getattr(self, "inscriptions", []) or []
        return not inscriptions_list and self.status == ProvaStatus.SETUP.value

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
        if self.is_standalone:
            return f"<Prova Standalone '{self.name}'>"
        return f"<Prova {self.name} (Torneo {self.tournament_id})>"


class Inscription(db.Model):
    """Player registration to a competition round."""

    __tablename__ = "inscription"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    prova_id = db.Column(
        db.Integer, db.ForeignKey("prova.id", ondelete="CASCADE"), nullable=False
    )
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    initial_order = db.Column(db.Integer)  # ordine sorteggio iniziale

    user = db.relationship("User", back_populates="inscriptions")

    is_withdrawn = db.Column(db.Boolean, default=False, nullable=False)
    withdrawn_at = db.Column(db.DateTime, nullable=True)

    def __repr__(self):
        return f"<Inscription {self.user_id} -> {self.prova_id}>"
