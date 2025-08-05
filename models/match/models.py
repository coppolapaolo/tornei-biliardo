"""
Module: models/match/models.py
Purpose: Match domain models (Match, Rack, MatchResult, TrioMatch)
Data Structures: Match, Rack, MatchResult, TrioMatch
Dependencies: models.base.db, datetime
ADR Reference: docs/ADR/ADR-0010-domain-separation-phase2.md
"""

from datetime import datetime
from models.base import db


class Match(db.Model):
    """Core match entity representing a game between players."""

    __tablename__ = "match"

    id = db.Column(db.Integer, primary_key=True)
    prova_id = db.Column(db.Integer, db.ForeignKey("prova.id"), nullable=False)
    round_number = db.Column(db.Integer, nullable=False)  # 1, 2, 3

    player1_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    player2_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    is_bye = db.Column(db.Boolean, default=False)  # partita contro X

    # Risultati
    player1_score = db.Column(db.Integer, default=0)
    player2_score = db.Column(db.Integer, default=0)
    winner_id = db.Column(db.Integer, db.ForeignKey("user.id"))

    # Stato
    status = db.Column(
        db.String(20), default="pending"
    )  # pending, playing, completed, validated
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_trio = db.Column(db.Boolean, default=False)  # Indica se è un trio
    amalfi_round = db.Column(db.Integer)  # Turno secondo algoritmo Amalfi
    salto_applied = db.Column(db.Integer)  # Salto utilizzato per questo abbinamento

    # Relazioni
    player1 = db.relationship("User", foreign_keys=[player1_id])
    player2 = db.relationship("User", foreign_keys=[player2_id])
    winner = db.relationship("User", foreign_keys=[winner_id])
    racks = db.relationship("Rack", backref="match", lazy=True)

    def __repr__(self):
        return (
            f"<Match {self.player1_id} vs {self.player2_id} "
            f"(Round {self.round_number})>"
        )


class Rack(db.Model):
    """Detailed tracking of individual racks within a match."""

    __tablename__ = "rack"

    id = db.Column(db.Integer, primary_key=True)
    match_id = db.Column(db.Integer, db.ForeignKey("match.id"), nullable=False)
    rack_number = db.Column(db.Integer, nullable=False)
    winner_id = db.Column(db.Integer, db.ForeignKey("user.id"))

    # NUOVI CAMPI per conferma punti
    reported_by_id = db.Column(db.Integer, db.ForeignKey("user.id"))  # chi ha segnato
    confirmed_by_player = db.Column(
        db.Boolean, default=False
    )  # confermato dall'altro giocatore
    validated_by_admin = db.Column(db.Boolean, default=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relazioni
    winner = db.relationship("User", foreign_keys=[winner_id])
    reported_by = db.relationship("User", foreign_keys=[reported_by_id])

    def can_be_removed(self, current_user_id):
        """Verifica se il rack può essere rimosso"""
        if self.validated_by_admin:
            return False
        return self.reported_by_id == current_user_id

    def can_be_confirmed(self, current_user_id):
        """Verifica se il rack può essere confermato"""
        if self.confirmed_by_player or self.validated_by_admin:
            return False
        # Solo l'altro giocatore può confermare
        if self.match.player1_id == current_user_id:
            return self.match.player2_id == self.reported_by_id
        elif self.match.player2_id == current_user_id:
            return self.match.player1_id == self.reported_by_id
        return False

    def can_remove_confirmation(self, current_user_id):
        """Verifica se la conferma può essere rimossa"""
        if not self.confirmed_by_player or self.validated_by_admin:
            return False
        # Solo chi ha confermato può rimuovere la conferma
        if self.match.player1_id == current_user_id:
            return self.match.player2_id == self.reported_by_id
        elif self.match.player2_id == current_user_id:
            return self.match.player1_id == self.reported_by_id
        return False

    def __repr__(self):
        return f"<Rack {self.rack_number} (Match {self.match_id})>"


class MatchResult(db.Model):
    """Tracking of match results submitted by players."""

    __tablename__ = "match_result"

    id = db.Column(db.Integer, primary_key=True)
    match_id = db.Column(db.Integer, db.ForeignKey("match.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    player1_score = db.Column(db.Integer)
    player2_score = db.Column(db.Integer)
    winner_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relazioni
    reporter = db.relationship("User", foreign_keys=[user_id], overlaps="match_results")
    winner = db.relationship("User", foreign_keys=[winner_id])

    def __repr__(self):
        return f"<MatchResult {self.match_id} by {self.user_id}>"


class TrioMatch(db.Model):
    """Special handling for trio matches (3 players)."""

    __tablename__ = "trio_match"

    id = db.Column(db.Integer, primary_key=True)
    match_id = db.Column(db.Integer, db.ForeignKey("match.id"), nullable=False)

    # I tre giocatori del trio
    player1_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    player2_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    player3_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    # Stato corrente del trio
    current_player1_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    current_player2_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    waiting_player_id = db.Column(db.Integer, db.ForeignKey("user.id"))

    # Punteggi individuali nel trio
    player1_racks = db.Column(db.Integer, default=0)
    player2_racks = db.Column(db.Integer, default=0)
    player3_racks = db.Column(db.Integer, default=0)

    # Stato del trio
    is_completed = db.Column(db.Boolean, default=False)
    winner_id = db.Column(db.Integer, db.ForeignKey("user.id"))

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relations
    match = db.relationship("Match", backref="trio_match")
    player1 = db.relationship("User", foreign_keys=[player1_id])
    player2 = db.relationship("User", foreign_keys=[player2_id])
    player3 = db.relationship("User", foreign_keys=[player3_id])
    current_player1 = db.relationship("User", foreign_keys=[current_player1_id])
    current_player2 = db.relationship("User", foreign_keys=[current_player2_id])
    waiting_player = db.relationship("User", foreign_keys=[waiting_player_id])
    winner = db.relationship("User", foreign_keys=[winner_id])

    def add_rack_win(self, winner_id):
        """Aggiunge una vittoria di rack"""
        if self.is_completed:
            return False

        # Aggiorna il punteggio del vincitore
        if winner_id == self.player1_id:
            self.player1_racks += 1
        elif winner_id == self.player2_id:
            self.player2_racks += 1
        elif winner_id == self.player3_id:
            self.player3_racks += 1
        else:
            return False

        # Controlla se qualcuno ha vinto (almeno 2 rack)
        max_racks = max(self.player1_racks, self.player2_racks, self.player3_racks)
        if max_racks >= 2:
            # Trova il vincitore
            if self.player1_racks >= 2:
                self.winner_id = self.player1_id
            elif self.player2_racks >= 2:
                self.winner_id = self.player2_id
            elif self.player3_racks >= 2:
                self.winner_id = self.player3_id

            self.is_completed = True
            # Aggiorna anche il match associato
            if self.match:
                self.match.winner_id = self.winner_id
                self.match.status = "completed"
                self.match.player1_score = self.player1_racks
                self.match.player2_score = self.player2_racks

        # Ruota i giocatori per il prossimo rack
        self._rotate_players()
        return True

    def _rotate_players(self):
        """Ruota i giocatori per il prossimo rack"""
        if self.is_completed:
            return

        # Se non ci sono giocatori correnti, inizializza
        if not self.current_player1_id:
            self.current_player1_id = self.player1_id
            self.current_player2_id = self.player2_id
            self.waiting_player_id = self.player3_id
            return

        # Ruota: waiting -> current1, current1 -> current2, current2 -> waiting
        new_waiting = self.current_player1_id
        self.current_player1_id = self.current_player2_id
        self.current_player2_id = self.waiting_player_id
        self.waiting_player_id = new_waiting

    def get_current_state(self):
        """Restituisce lo stato corrente del trio"""
        return {
            "current_player1": self.current_player1,
            "current_player2": self.current_player2,
            "waiting_player": self.waiting_player,
            "scores": {
                "player1": self.player1_racks,
                "player2": self.player2_racks,
                "player3": self.player3_racks,
            },
            "is_completed": self.is_completed,
            "winner": self.winner,
        }

    def __repr__(self):
        return f"<TrioMatch {self.player1_id}-{self.player2_id}-{self.player3_id}>"
