"""
Module: models/match/models.py
Purpose: Match domain models (Match, Rack, MatchResult, TrioMatch)
Data Structures: Match, Rack, MatchResult, TrioMatch
Dependencies: models.base.db, datetime
"""

from datetime import datetime
from typing import Optional, Dict, Any, TYPE_CHECKING
from models.base import db, TimestampMixin
from models.status_enum import MatchStatus, Discipline
from .base_match import BaseMatchMixin

if TYPE_CHECKING:
    from .set_models import Set


class Match(db.Model, TimestampMixin, BaseMatchMixin):
    """Core match entity representing a game between players."""

    __tablename__ = "match"

    id = db.Column(db.Integer, primary_key=True)
    gara_id = db.Column(
        db.Integer, db.ForeignKey("gara.id", ondelete="CASCADE"), nullable=False
    )
    round_number = db.Column(
        db.Integer, nullable=False
    )  # 1, 2, 3. RESOLVED: See docs/ARCHITECTURAL_DECISIONS.md ADR-003. Decision: Keep as integer field (YAGNI).

    player1_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    player2_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    is_bye = db.Column(db.Boolean, default=False)  # partita contro X

    # Risultati (use rack_score/match_score properties for abstractions)
    player1_score = db.Column(
        db.Integer, default=0
    )  # Current racks won (single-set) or sets won (multi-set)
    player2_score = db.Column(
        db.Integer, default=0
    )  # Current racks won (single-set) or sets won (multi-set)
    winner_id = db.Column(db.Integer, db.ForeignKey("user.id"))

    # Multi-set configuration (use distance_config property for abstraction)
    match_distance = db.Column(db.Integer, default=1)  # Number of sets to win the match
    is_multi_set = db.Column(
        db.Boolean, default=False
    )  # Whether this match has multiple sets
    current_set_number = db.Column(db.Integer, default=1)  # Current set being played

    # Disciplina override (se diversa da quella della gara)
    discipline = db.Column(
        db.String(50), nullable=True
    )  # Override della disciplina della gara (usa Discipline enum)

    # Stato
    status = db.Column(
        db.String(20), default=MatchStatus.PENDING.value
    )  # pending, playing, completed, validated
    is_locked = db.Column(
        db.Boolean, default=False
    )  # Match specifico bloccato per modifiche
    round_locked = db.Column(db.Boolean, default=False)  # Round bloccato per modifiche
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_trio = db.Column(db.Boolean, default=False)  # Indica se è un trio

    # Table assignment for venue management
    table_assignment = db.Column(
        db.String(10), nullable=True
    )  # e.g., "A", "B", "sala rossa"

    # Handicap system
    has_handicap = db.Column(db.Boolean, default=False)
    player1_handicap = db.Column(
        db.Integer, default=0
    )  # Starting advantage for player1
    player2_handicap = db.Column(
        db.Integer, default=0
    )  # Starting advantage for player2
    handicap_rule_id = db.Column(
        db.Integer, db.ForeignKey("handicap_rule.id"), nullable=True
    )
    handicap_explanation = db.Column(db.String(255), nullable=True)

    # Validazione finale del risultato (nuova UX semplificata)
    player1_confirmed = db.Column(db.Boolean, default=False, nullable=False)
    player2_confirmed = db.Column(db.Boolean, default=False, nullable=False)
    player1_confirmed_at = db.Column(db.DateTime, nullable=True)
    player2_confirmed_at = db.Column(db.DateTime, nullable=True)

    # Relazioni
    player1 = db.relationship("User", foreign_keys=[player1_id])
    player2 = db.relationship("User", foreign_keys=[player2_id])
    winner = db.relationship("User", foreign_keys=[winner_id])
    handicap_rule = db.relationship("HandicapRule", foreign_keys=[handicap_rule_id])
    racks = db.relationship(
        "Rack",
        backref="match",
        lazy=True,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    # Sets relationship for multi-set matches
    sets = db.relationship(
        "Set",
        back_populates="match",
        lazy=True,
        cascade="all, delete-orphan",
        order_by="Set.set_number",
    )

    # Tiebreaker relationships
    tiebreakers = db.relationship(
        "Tiebreaker", back_populates="match", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return (
            f"<Match {self.player1_id} vs {self.player2_id} "
            f"(Round {self.round_number})>"
        )

    def apply_handicap(self, handicap_data: dict) -> None:
        """Apply handicap to the match."""
        self.has_handicap = handicap_data.get("handicap", 0) > 0
        self.player1_handicap = handicap_data.get("player1_handicap", 0)
        self.player2_handicap = handicap_data.get("player2_handicap", 0)
        self.handicap_explanation = handicap_data.get("explanation")

        # Update scores with handicap
        self.player1_score += self.player1_handicap
        self.player2_score += self.player2_handicap

    def get_effective_score(self, player_id: int) -> int:
        """Get effective score including handicap for a player."""
        if player_id == self.player1_id:
            return self.player1_score
        elif player_id == self.player2_id:
            return self.player2_score
        return 0

    def get_handicap_info(self) -> dict:
        """Get handicap information for this match."""
        return {
            "has_handicap": self.has_handicap,
            "player1_handicap": self.player1_handicap,
            "player2_handicap": self.player2_handicap,
            "explanation": self.handicap_explanation,
        }

    def is_completed(self) -> bool:
        """Check if match is completed."""
        return self.status == MatchStatus.COMPLETED.value

    @property
    def distance_config(self):
        """Get Distance value object for this match.

        Returns unified Distance abstraction supporting both single-set
        and multi-set configurations.

        Returns:
            Distance: Immutable distance configuration
        """
        from .distance import Distance

        return Distance.from_match(self)

    @property
    def effective_distance(self) -> int:
        """Get the effective distance (racks to win) for this match.

        Supports per-round distance overrides. Falls back to gara.distance
        for legacy matches without match_distance set.

        Legacy matches have match_distance=1 (default), so we detect this
        and use gara.distance instead.

        Returns:
            int: Number of racks needed to win (for single-set matches)
        """
        gara_dist = self.gara.distance
        # Use match_distance if explicitly set (> 1 or equals gara.distance)
        if self.match_distance and self.match_distance > 1:
            return self.match_distance
        elif self.match_distance and self.match_distance == gara_dist:
            return self.match_distance
        else:
            # Legacy match with default match_distance=1
            return gara_dist

    @property
    def rack_score(self):
        """Get RackScore value object for single-set match.

        Only valid for single-set matches. Use set.rack_score for
        multi-set matches.

        Returns:
            RackScore: Current rack scoring

        Raises:
            ValueError: If called on multi-set match
        """
        from .score import RackScore

        if self.is_multi_set:
            raise ValueError(
                "Use set.rack_score for multi-set matches. "
                "Match.rack_score only valid for single-set matches."
            )

        return RackScore(
            distance=self.distance_config,
            player1_racks=self.player1_score,
            player2_racks=self.player2_score,
        )

    @property
    def match_score(self):
        """Get MatchScore value object for multi-set match.

        Only valid for multi-set matches where player scores represent
        sets won.

        Returns:
            MatchScore: Current set scoring

        Raises:
            ValueError: If called on single-set match
        """
        from .score import MatchScore

        if not self.is_multi_set:
            raise ValueError(
                "Match.match_score only valid for multi-set matches. "
                "Use Match.rack_score for single-set matches."
            )

        return MatchScore(
            distance=self.distance_config,
            player1_sets=self.player1_score,
            player2_sets=self.player2_score,
        )

    def get_effective_discipline(self) -> str:
        """Get effective discipline (override or gara default)."""
        if self.discipline:
            return self.discipline
        return self.gara.discipline if self.gara else Discipline.EIGHT_BALL.value

    def start_next_set(
        self,
    ) -> (
        "Set"
    ):  # RESOLVED: See docs/ARCHITECTURAL_DECISIONS.md ADR-004. Decision: Match is aggregate root for Sets.
        """Start the next set in a multi-set match."""
        if not self.is_multi_set:
            raise ValueError("This is not a multi-set match")

        # Check if current set is completed
        current_set = self.get_current_set()
        if current_set and not current_set.is_completed():
            raise ValueError("Current set must be completed before starting next set")

        # Check if match is already completed
        if self.is_completed():
            raise ValueError("Match is already completed")

        # Create new set
        from .set_models import Set

        # Get distance from previous set or default
        distance = getattr(current_set, "distance", 5) if current_set else 5

        # Multi-set matches always use race-to mode to guarantee a winner
        new_set = Set(
            match_id=self.id,
            set_number=self.current_set_number,
            distance=distance,
            is_race_to=True,  # Always race-to for multi-set to prevent ties
        )

        from ..base import db

        db.session.add(new_set)

        return new_set

    def get_current_set(self) -> Optional["Set"]:
        """Get the current set being played."""
        if not self.is_multi_set:
            return None

        # Query the database directly to avoid relationship loading issues
        from .set_models import Set

        return Set.query.filter_by(
            match_id=self.id, set_number=self.current_set_number
        ).first()

    def complete_set(self, set_number: int, winner_id: int) -> None:
        """Complete a set and check if match is finished."""
        if not self.is_multi_set:
            raise ValueError("This is not a multi-set match")

        # Update match scores (sets won)
        if winner_id == self.player1_id:
            self.player1_score += 1
        elif winner_id == self.player2_id:
            self.player2_score += 1
        else:
            raise ValueError("Winner must be one of the match players")

        # Check if match is won
        if self.player1_score >= self.match_distance:
            self.winner_id = self.player1_id
            self.status = "completed"
            # Check if all matches in gara are completed and auto-complete gara
            self._check_and_complete_gara_if_needed(self)
        elif self.player2_score >= self.match_distance:
            self.winner_id = self.player2_id
            self.status = "completed"
            # Check if all matches in gara are completed and auto-complete gara
            self._check_and_complete_gara_if_needed(self)
        else:
            # Move to next set
            self.current_set_number += 1

    def get_match_summary(self) -> dict:
        """Get comprehensive match summary."""
        if self.is_multi_set:
            sets_summary = []
            # Query sets directly from database
            from .set_models import Set

            match_sets = (
                Set.query.filter_by(match_id=self.id).order_by(Set.set_number).all()
            )

            for match_set in match_sets:
                sets_summary.append(
                    {
                        "set_number": match_set.set_number,
                        "player1_racks": match_set.player1_racks,
                        "player2_racks": match_set.player2_racks,
                        "winner_id": match_set.winner_id,
                        "is_completed": match_set.is_completed(),
                    }
                )

            return {
                "is_multi_set": True,
                "match_distance": self.match_distance,
                "sets_won": {
                    "player1": self.player1_score,
                    "player2": self.player2_score,
                },
                "current_set": self.current_set_number,
                "sets": sets_summary,
                "is_completed": self.is_completed(),
                "winner_id": self.winner_id,
            }
        else:
            # Legacy single-set match
            return {
                "is_multi_set": False,
                "racks_won": {
                    "player1": self.player1_score,
                    "player2": self.player2_score,
                },
                "is_completed": self.is_completed(),
                "winner_id": self.winner_id,
            }

    def needs_tiebreaker(self) -> bool:
        """Check if match needs a tiebreaker (tied scores)."""
        if self.status != "completed":
            return False

        # For multi-set matches, check set scores
        if self.is_multi_set:
            return self.player1_score == self.player2_score and self.player1_score > 0

        # For single matches, check rack scores
        return self.player1_score == self.player2_score and self.player1_score > 0

    def has_active_tiebreaker(self) -> bool:
        """Check if match has an active tiebreaker."""
        # Query tiebreakers directly from database
        from models.tiebreaker.models import Tiebreaker

        pending_count = Tiebreaker.query.filter(
            Tiebreaker.match_id == self.id, Tiebreaker.status == "pending"
        ).count()

        in_progress_count = Tiebreaker.query.filter(
            Tiebreaker.match_id == self.id, Tiebreaker.status == "in_progress"
        ).count()

        return (pending_count + in_progress_count) > 0

    def get_active_tiebreaker(self):
        """Get the active tiebreaker for this match."""
        # Query tiebreakers directly from database
        from models.tiebreaker.models import Tiebreaker

        # Check for pending tiebreaker first
        pending_tb = Tiebreaker.query.filter(
            Tiebreaker.match_id == self.id, Tiebreaker.status == "pending"
        ).first()

        if pending_tb:
            return pending_tb

        # Check for in-progress tiebreaker
        return Tiebreaker.query.filter(
            Tiebreaker.match_id == self.id, Tiebreaker.status == "in_progress"
        ).first()

    def can_start_tiebreaker(self) -> bool:
        """Check if a tiebreaker can be started for this match."""
        return self.needs_tiebreaker() and not self.has_active_tiebreaker()

    def supports_multi_discipline(
        self,
    ) -> (
        bool
    ):  # TODO: controllare se la modellazione cosi' e' ok. la disciplina e' un campo strutturato? deve essere strutturato? oppure e' solo una descrizione. Per i match multi disciplina avevo in mente quelli di APA in cui i primi 4 rack sono a palla 8 e gli altri sono a palla 9 e si arriva al 7. Ma se il funzionamento dell'app non cambia allora si puo' lasciare questo come semplice valore di descrizione
        """Check if match supports multi-discipline play."""
        return (
            self.is_multi_set
        )  # Only multi-set matches support multi-discipline for now

    def configure_set_disciplines(self, set_disciplines: Dict[int, str]) -> None:
        """Configure specific disciplines for sets.

        Args:
            set_disciplines: Dict mapping set number to discipline name
        """
        if not self.supports_multi_discipline():
            raise ValueError("Match must support multi-discipline mode")

        # Query sets directly from database
        from .set_models import Set

        for set_number, discipline in set_disciplines.items():
            match_set = Set.query.filter_by(
                match_id=self.id, set_number=set_number
            ).first()
            if match_set:
                match_set.discipline = discipline

    def get_multi_discipline_summary(self) -> Dict[str, Any]:
        """Get summary of disciplines used across all sets."""
        if not self.is_multi_set:
            return {
                "is_multi_discipline": False,
                "primary_discipline": getattr(self, "discipline", "palla_8"),
                "sets": [],
            }

        sets_summary = []
        all_disciplines = set()

        # Query sets directly from database
        from .set_models import Set

        match_sets = (
            Set.query.filter_by(match_id=self.id).order_by(Set.set_number).all()
        )

        for match_set in match_sets:
            set_discipline_info = match_set.get_discipline_summary()
            sets_summary.append(
                {
                    "set_number": match_set.set_number,
                    "discipline_info": set_discipline_info,
                }
            )

            if set_discipline_info.get("disciplines_used"):
                all_disciplines.update(set_discipline_info["disciplines_used"])

        return {
            "is_multi_discipline": len(all_disciplines) > 1,
            "disciplines_used": list(all_disciplines),
            "total_disciplines": len(all_disciplines),
            "sets": sets_summary,
        }

    def _check_and_complete_gara_if_needed(
        self, match_obj
    ):  # RESOLVED: See docs/ARCHITECTURAL_DECISIONS.md ADR-001. Decision: Keep coupling for pragmatic reasons.
        """
        Verifica se tutti i match della gara sono completati.

        NOTA: Non completa automaticamente la gara. Il direttore/admin deve
        esplicitamente terminare la gara usando il pulsante "Termina gara"
        nella UI. Questo permette di:
        - Resettare l'ultimo turno se necessario
        - Verificare i risultati prima della chiusura definitiva
        - Gestire eventuali contestazioni
        """
        # Metodo mantenuto per compatibilità ma non esegue più l'auto-completamento
        # La gara passa in stato "campionato_completed" (derivato) quando tutti i match
        # sono completati, ma rimane in status "playing" fino a terminazione esplicita
        pass

    def _remove_last_rack(self, user_id: int) -> None:
        """
        Implementation of BaseMatch abstract method.
        Remove last rack from match (soft delete).
        """
        # Find last non-deleted rack
        last_rack = (
            Rack.query.filter_by(match_id=self.id, is_deleted=False)
            .order_by(Rack.rack_number.desc())
            .first()
        )

        if last_rack:
            # Soft delete the rack with log info
            last_rack.is_deleted = True
            last_rack.removed_by_id = user_id
            last_rack.removed_at = datetime.utcnow()

            # Update match scores
            if last_rack.winner_id == self.player1_id:
                self.player1_score = max(0, self.player1_score - 1)
            elif last_rack.winner_id == self.player2_id:
                self.player2_score = max(0, self.player2_score - 1)


class Rack(db.Model):
    """Detailed tracking of individual racks within a match."""

    __tablename__ = "rack"

    id = db.Column(db.Integer, primary_key=True)
    match_id = db.Column(
        db.Integer, db.ForeignKey("match.id", ondelete="CASCADE"), nullable=False
    )
    rack_number = db.Column(db.Integer, nullable=False)
    winner_id = db.Column(
        db.Integer, db.ForeignKey("user.id")
    )  # Pool Continuo (Straight Pool) non supportato - future feature

    # Campi per conferma punti (reporting workflow)
    reported_by_id = db.Column(db.Integer, db.ForeignKey("user.id"))  # chi ha segnato
    confirmed_by_player = db.Column(
        db.Boolean, default=False
    )  # confermato dall'altro giocatore
    validated_by_admin = db.Column(db.Boolean, default=False)
    admin_note = db.Column(
        db.Text, nullable=True
    )  # Note admin per modifiche/correzioni

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Nuovi campi per UX semplificata (log operazioni)
    added_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    added_at = db.Column(db.DateTime, nullable=True, default=datetime.utcnow)
    removed_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    removed_at = db.Column(db.DateTime, nullable=True)
    is_deleted = db.Column(
        db.Boolean, default=False, nullable=False
    )  # Soft delete per tracciabilità

    # Relazioni
    winner = db.relationship("User", foreign_keys=[winner_id])
    reported_by = db.relationship("User", foreign_keys=[reported_by_id])
    added_by = db.relationship("User", foreign_keys=[added_by_id])
    removed_by = db.relationship("User", foreign_keys=[removed_by_id])

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

    # Punteggi individuali nel trio (vedi models/match/score.py per value objects)
    player1_racks = db.Column(db.Integer, default=0)
    player2_racks = db.Column(db.Integer, default=0)
    player3_racks = db.Column(db.Integer, default=0)

    # Stato del trio
    is_completed = db.Column(db.Boolean, default=False)
    winner_id = db.Column(
        db.Integer, db.ForeignKey("user.id")
    )  # Nel biliardo c'è sempre un vincitore (primo a 2 rack)

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
            # Query the match directly to avoid relationship property issues

            match_obj = db.session.get(Match, self.match_id)
            if match_obj:
                match_obj.winner_id = self.winner_id
                match_obj.status = "completed"
                match_obj.player1_score = self.player1_racks
                match_obj.player2_score = self.player2_racks

                # Controlla se tutti i match della gara sono completati e completa automaticamente la gara
                match_obj._check_and_complete_gara_if_needed(match_obj)

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
