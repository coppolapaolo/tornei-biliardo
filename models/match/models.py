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
    # gara_id nullable to support standalone matches (detached from deleted gara)
    gara_id = db.Column(
        db.Integer, db.ForeignKey("gara.id", ondelete="SET NULL"), nullable=True
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

    @property
    def is_standalone(self) -> bool:
        """Check if this match is standalone (no gara association).

        A match becomes standalone when its gara is soft-deleted
        with the 'keep_matches' option.
        """
        return self.gara_id is None

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
    """Special handling for trio matches (3 players).

    A trio is a mini round-robin tournament where each player plays against
    each other player. The number of rounds (gironi) depends on the gara distance.
    See ADR-005 and models/match/trio_config.py for details.
    """

    __tablename__ = "trio_match"

    id = db.Column(db.Integer, primary_key=True)
    match_id = db.Column(db.Integer, db.ForeignKey("match.id"), nullable=False)

    # I tre giocatori del trio
    player1_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    player2_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    player3_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    # Stato corrente del trio (chi gioca, chi aspetta)
    current_player1_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    current_player2_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    waiting_player_id = db.Column(db.Integer, db.ForeignKey("user.id"))

    # NOTE: player1_racks, player2_racks, player3_racks, total_racks_played,
    # current_round, current_rack_in_round are now computed properties
    # based on TrioRack records. Old columns will be removed by migration.

    bonus_applied = db.Column(db.Boolean, default=False)  # Bonus rack flag

    # Stato del trio
    is_completed = db.Column(db.Boolean, default=False)
    awaiting_confirmation = db.Column(db.Boolean, default=False)  # Validation step
    forfeit_player_id = db.Column(
        db.Integer, db.ForeignKey("user.id")
    )  # Player who forfeited (if any)
    winner_id = db.Column(
        db.Integer, db.ForeignKey("user.id")
    )  # Con classifica rack-based, winner_id puo' essere NULL (pareggio)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relations
    # uselist=False because each Match has at most one TrioMatch (1:1 relationship)
    match = db.relationship("Match", backref=db.backref("trio_match", uselist=False))
    player1 = db.relationship("User", foreign_keys=[player1_id])
    player2 = db.relationship("User", foreign_keys=[player2_id])
    player3 = db.relationship("User", foreign_keys=[player3_id])
    current_player1 = db.relationship("User", foreign_keys=[current_player1_id])
    current_player2 = db.relationship("User", foreign_keys=[current_player2_id])
    waiting_player = db.relationship("User", foreign_keys=[waiting_player_id])
    winner = db.relationship("User", foreign_keys=[winner_id])
    forfeit_player = db.relationship("User", foreign_keys=[forfeit_player_id])

    @property
    def trio_config(self):
        """Get TrioConfig based on gara distance."""
        from models.match.trio_config import TrioConfig

        match_obj = db.session.get(Match, self.match_id)
        if match_obj and match_obj.gara:
            return TrioConfig(distance=match_obj.gara.distance)
        # Default fallback
        return TrioConfig(distance=2)

    @property
    def player_ids(self):
        """List of player IDs in order."""
        return [self.player1_id, self.player2_id, self.player3_id]

    @property
    def active_racks(self) -> list:
        """Get all non-deleted racks, ordered by rack_number."""
        if not hasattr(self, "racks"):
            return []
        return [r for r in self.racks.all() if not r.is_deleted]

    @property
    def last_rack(self):
        """Get the last active rack, or None."""
        racks = self.active_racks
        return max(racks, key=lambda r: r.rack_number) if racks else None

    @property
    def rack_history(self) -> list:
        """Get history of played racks for UI display.

        Returns racks in reverse order (most recent first) with metadata
        for UI rendering: player names, winner, and can_undo flag.
        Only the most recent rack can be undone.
        """
        racks = sorted(self.active_racks, key=lambda r: r.rack_number, reverse=True)
        last_rack_number = racks[0].rack_number if racks else 0

        return [
            {
                "rack_number": r.rack_number,
                "player1": r.player1,
                "player2": r.player2,
                "waiting_player": r.waiting_player,
                "winner": r.winner,
                "winner_id": r.winner_id,
                "can_undo": r.rack_number == last_rack_number,
            }
            for r in racks
        ]

    @property
    def player1_racks(self) -> int:
        """Computed: count of racks won by player1."""
        return sum(1 for r in self.active_racks if r.winner_id == self.player1_id)

    @property
    def player2_racks(self) -> int:
        """Computed: count of racks won by player2."""
        return sum(1 for r in self.active_racks if r.winner_id == self.player2_id)

    @property
    def player3_racks(self) -> int:
        """Computed: count of racks won by player3."""
        return sum(1 for r in self.active_racks if r.winner_id == self.player3_id)

    @property
    def total_racks_played(self) -> int:
        """Computed: total active racks."""
        return len(self.active_racks)

    @property
    def current_round(self) -> int:
        """Computed: current round based on racks played."""
        config = self.trio_config
        return config.get_round_for_rack(self.total_racks_played)

    @property
    def current_rack_in_round(self) -> int:
        """Computed: rack position within current round (0-2)."""
        if self.total_racks_played == 0:
            return 0
        return (self.total_racks_played - 1) % 3

    @property
    def player_racks_list(self):
        """List of rack scores in order."""
        return [self.player1_racks, self.player2_racks, self.player3_racks]

    def get_player_index(self, player_id: int) -> int:
        """Get 0-based index for a player ID, or -1 if not found."""
        try:
            return self.player_ids.index(player_id)
        except ValueError:
            return -1

    def add_rack_win(
        self, winner_id: int, added_by_id: int = None
    ) -> "TrioRack | None":
        """Add a rack win for a player in the round-robin.

        Creates a TrioRack record. Returns the created rack or None if invalid.
        """
        if self.is_completed:
            return None

        config = self.trio_config

        # Check if all racks are already played
        if self.total_racks_played >= config.total_played_racks:
            return None

        # Get current matchup from config
        next_rack_number = self.total_racks_played + 1
        matchup = config.get_matchup_for_rack(next_rack_number)
        if not matchup:
            return None

        p1_idx, p2_idx, waiting_idx = matchup
        current_p1_id = self.player_ids[p1_idx]
        current_p2_id = self.player_ids[p2_idx]
        waiting_id = self.player_ids[waiting_idx]

        # Verify winner is one of the current players
        if winner_id not in [current_p1_id, current_p2_id]:
            return None

        # Create TrioRack record
        trio_rack = TrioRack(
            trio_match_id=self.id,
            rack_number=next_rack_number,
            winner_id=winner_id,
            player1_id=current_p1_id,
            player2_id=current_p2_id,
            waiting_player_id=waiting_id,
            added_by_id=added_by_id,
        )
        db.session.add(trio_rack)

        # Flush to ensure the new rack is visible in the relationship
        db.session.flush()

        # Update current players for next rack
        self._update_current_players()

        # Check if trio is completed
        if self.total_racks_played >= config.total_played_racks:
            self._apply_bonus_and_complete()

        return trio_rack

    def remove_last_rack(self, removed_by_id: int) -> "TrioRack | None":
        """Remove the last rack (undo).

        Soft-deletes the most recent active rack.
        Returns the removed TrioRack, or None if no racks to remove.
        """
        last = self.last_rack
        if not last:
            return None

        # Soft delete
        last.soft_delete(removed_by_id)

        # If trio was awaiting confirmation, reset it
        if self.awaiting_confirmation:
            self.awaiting_confirmation = False
            self.bonus_applied = False  # Revert bonus that was pre-applied

        # If trio was completed, reopen it
        if self.is_completed:
            self.is_completed = False
            self.winner_id = None
            self.bonus_applied = False

            # Revert associated match status
            match_obj = db.session.get(Match, self.match_id)
            if match_obj:
                match_obj.status = "playing"
                match_obj.winner_id = None

        # Update current players to show the matchup for the removed rack
        self._update_current_players()

        return last

    def _update_current_players(self):
        """Update current_player1, current_player2, waiting_player based on next rack."""
        config = self.trio_config
        next_rack = self.total_racks_played + 1

        if next_rack > config.total_played_racks:
            # All racks done
            return

        matchup = config.get_matchup_for_rack(next_rack)
        if matchup:
            p1_idx, p2_idx, waiting_idx = matchup
            self.current_player1_id = self.player_ids[p1_idx]
            self.current_player2_id = self.player_ids[p2_idx]
            self.waiting_player_id = self.player_ids[waiting_idx]

    def initialize_matchup(self):
        """Initialize current players for the first rack.

        Should be called immediately after trio creation to set up
        the initial matchup (P1 vs P2, P3 waits).
        """
        if self.total_racks_played == 0 and self.current_player1_id is None:
            self._update_current_players()

    def _apply_bonus_and_complete(self):
        """Apply bonus flag and set trio to awaiting confirmation.

        Note: bonus_racks don't create actual rack records - the bonus is virtual
        and applied equally to all players for display/classification purposes.
        Since it's equal for all, it doesn't affect winner determination.

        The trio enters 'awaiting_confirmation' state - user must call
        confirm_result() to finalize the match.
        """
        config = self.trio_config

        # Set bonus flag (for UI display - bonus is virtual, not actual racks)
        if config.bonus_racks > 0:
            self.bonus_applied = True

        # Flush to ensure computed properties see all racks
        db.session.flush()

        # Determine winner (highest racks, or None if tie)
        scores = [
            (self.player1_racks, self.player1_id),
            (self.player2_racks, self.player2_id),
            (self.player3_racks, self.player3_id),
        ]
        scores.sort(reverse=True)

        # Check for tie at the top
        if scores[0][0] > scores[1][0]:
            self.winner_id = scores[0][1]
        else:
            # Tie - no single winner (valid for rack-based classification)
            self.winner_id = None

        # Enter awaiting confirmation state (don't complete yet)
        self.awaiting_confirmation = True

    def confirm_result(self) -> bool:
        """Confirm the trio result and finalize the match.

        Must be called after all racks are played and trio is awaiting_confirmation.
        Updates the parent Match status and winner.

        Returns:
            True if confirmed successfully, False if not in awaiting_confirmation state.
        """
        if not self.awaiting_confirmation:
            return False

        # Mark as completed
        self.awaiting_confirmation = False
        self.is_completed = True

        # Update associated match
        match_obj = db.session.get(Match, self.match_id)
        if match_obj:
            match_obj.winner_id = self.winner_id
            match_obj.status = "completed"
            # Store total racks in match scores for quick access
            match_obj.player1_score = self.player1_racks
            match_obj.player2_score = self.player2_racks
            match_obj._check_and_complete_gara_if_needed(match_obj)

        return True

    def handle_forfeit(self, forfeiting_player_id: int, added_by_id: int = None) -> bool:
        """Handle player forfeit in trio match.

        When a player forfeits:
        - Remaining racks where they would play are auto-assigned to opponent
        - They don't receive bonus rack
        - Match enters awaiting_confirmation state

        Args:
            forfeiting_player_id: ID of the player who is forfeiting
            added_by_id: ID of user who registered the forfeit

        Returns:
            True if forfeit was processed, False if invalid
        """
        if self.is_completed or self.awaiting_confirmation:
            return False

        # Validate player is in this trio
        if forfeiting_player_id not in self.player_ids:
            return False

        # Already forfeited?
        if self.forfeit_player_id is not None:
            return False

        self.forfeit_player_id = forfeiting_player_id
        config = self.trio_config

        # Auto-complete remaining racks where forfeiting player would have played
        while self.total_racks_played < config.total_played_racks:
            next_rack_number = self.total_racks_played + 1
            matchup = config.get_matchup_for_rack(next_rack_number)
            if not matchup:
                break

            p1_idx, p2_idx, waiting_idx = matchup
            current_p1_id = self.player_ids[p1_idx]
            current_p2_id = self.player_ids[p2_idx]
            waiting_id = self.player_ids[waiting_idx]

            # If forfeiting player is in this matchup, assign win to opponent
            if forfeiting_player_id == current_p1_id:
                winner_id = current_p2_id
            elif forfeiting_player_id == current_p2_id:
                winner_id = current_p1_id
            else:
                # Forfeiting player is waiting - this is a normal rack between others
                # Stop auto-completing, let the other two play normally
                break

            # Create TrioRack for auto-assigned win
            trio_rack = TrioRack(
                trio_match_id=self.id,
                rack_number=next_rack_number,
                winner_id=winner_id,
                player1_id=current_p1_id,
                player2_id=current_p2_id,
                waiting_player_id=waiting_id,
                added_by_id=added_by_id,
            )
            db.session.add(trio_rack)
            db.session.flush()

            # Update matchup for next rack
            self._update_current_players()

        # If all racks now played, apply bonus and enter confirmation
        if self.total_racks_played >= config.total_played_racks:
            self._apply_bonus_and_complete_forfeit()

        return True

    def _apply_bonus_and_complete_forfeit(self):
        """Apply bonus (excluding forfeit player) and set to awaiting confirmation.

        Similar to _apply_bonus_and_complete but forfeit player doesn't get bonus.
        """
        config = self.trio_config

        # Set bonus flag (for UI display)
        if config.bonus_racks > 0:
            self.bonus_applied = True

        db.session.flush()

        # Determine winner (forfeit player can't win)
        scores = []
        for pid, racks in [
            (self.player1_id, self.player1_racks),
            (self.player2_id, self.player2_racks),
            (self.player3_id, self.player3_racks),
        ]:
            if pid != self.forfeit_player_id:
                scores.append((racks, pid))

        scores.sort(reverse=True)

        # Check for tie at the top (among non-forfeit players)
        if len(scores) >= 2 and scores[0][0] > scores[1][0]:
            self.winner_id = scores[0][1]
        else:
            # Tie or only one player left
            self.winner_id = scores[0][1] if scores else None

        self.awaiting_confirmation = True

    def set_result_direct(
        self, player1_racks: int, player2_racks: int, player3_racks: int
    ) -> bool:
        """Set trio result directly (for quick result entry).

        Creates synthetic TrioRack records to match the given scores.
        Validates that total racks match expected for the distance.
        """
        config = self.trio_config

        # Validate total racks
        total = player1_racks + player2_racks + player3_racks
        if total != config.total_played_racks:
            return False

        # Delete any existing racks
        for rack in self.racks.all():
            db.session.delete(rack)
        db.session.flush()

        # Create synthetic racks matching the scores
        # Track remaining wins needed for each player
        remaining_wins = {
            self.player1_id: player1_racks,
            self.player2_id: player2_racks,
            self.player3_id: player3_racks,
        }

        # Go through round-robin sequence and assign winners
        for rack_num in range(1, config.total_played_racks + 1):
            matchup = config.get_matchup_for_rack(rack_num)
            if not matchup:
                continue

            p1_idx, p2_idx, waiting_idx = matchup
            current_p1_id = self.player_ids[p1_idx]
            current_p2_id = self.player_ids[p2_idx]
            waiting_id = self.player_ids[waiting_idx]

            # Assign winner: prefer player who still needs wins
            if remaining_wins.get(current_p1_id, 0) > 0:
                winner_id = current_p1_id
            elif remaining_wins.get(current_p2_id, 0) > 0:
                winner_id = current_p2_id
            else:
                # Should not happen if scores are valid
                winner_id = current_p1_id

            remaining_wins[winner_id] = remaining_wins.get(winner_id, 0) - 1

            trio_rack = TrioRack(
                trio_match_id=self.id,
                rack_number=rack_num,
                winner_id=winner_id,
                player1_id=current_p1_id,
                player2_id=current_p2_id,
                waiting_player_id=waiting_id,
            )
            db.session.add(trio_rack)

        # Set bonus flag and complete
        self.bonus_applied = config.bonus_racks > 0
        self.is_completed = True

        # Update current players (will point past end since completed)
        self._update_current_players()

        # Flush to ensure computed properties work
        db.session.flush()

        # Determine winner
        scores = [
            (player1_racks, self.player1_id),
            (player2_racks, self.player2_id),
            (player3_racks, self.player3_id),
        ]
        scores.sort(reverse=True)

        if scores[0][0] > scores[1][0]:
            self.winner_id = scores[0][1]
        else:
            self.winner_id = None  # Tie

        # Update associated match
        match_obj = db.session.get(Match, self.match_id)
        if match_obj:
            match_obj.winner_id = self.winner_id
            match_obj.status = "completed"
            match_obj.player1_score = player1_racks
            match_obj.player2_score = player2_racks
            match_obj._check_and_complete_gara_if_needed(match_obj)

        return True

    def reset(self):
        """Reset trio to initial state by deleting all TrioRack records.

        Preserves table assignment - status is set based on whether table is assigned:
        - PLAYING if table is assigned (ready to play)
        - PENDING if no table (waiting for assignment)
        """
        # Hard delete all rack records (not soft delete - this is a full reset)
        for rack in self.racks.all():
            db.session.delete(rack)

        # Reset state flags
        self.bonus_applied = False
        self.is_completed = False
        self.winner_id = None

        # Set initial players for first rack (P1 vs P2, P3 waits)
        self._update_current_players()

        # Reset associated match - preserve table assignment
        match_obj = db.session.get(Match, self.match_id)
        if match_obj:
            match_obj.winner_id = None
            match_obj.player1_score = 0
            match_obj.player2_score = 0
            # Status based on table assignment (like regular match reset)
            if match_obj.table_assignment:
                match_obj.status = MatchStatus.PLAYING.value
            else:
                match_obj.status = MatchStatus.PENDING.value

    def get_current_state(self):
        """Return current state of the trio for UI rendering."""
        config = self.trio_config
        next_rack = self.total_racks_played + 1

        return {
            "players": {
                "player1": {
                    "id": self.player1_id,
                    "user": self.player1,
                    "racks": self.player1_racks,
                },
                "player2": {
                    "id": self.player2_id,
                    "user": self.player2,
                    "racks": self.player2_racks,
                },
                "player3": {
                    "id": self.player3_id,
                    "user": self.player3,
                    "racks": self.player3_racks,
                },
            },
            "current_matchup": {
                "player1": self.current_player1,
                "player2": self.current_player2,
                "waiting": self.waiting_player,
            },
            "progress": {
                "current_round": self.current_round,
                "total_rounds": config.num_rounds,
                "rack_in_round": self.current_rack_in_round + 1,
                "racks_per_round": config.racks_per_round,
                "total_racks_played": self.total_racks_played,
                "total_racks_needed": config.total_played_racks,
                "next_rack": next_rack if next_rack <= config.total_played_racks else None,
            },
            "config": {
                "distance": config.distance,
                "num_rounds": config.num_rounds,
                "bonus_racks": config.bonus_racks,
                "max_racks_per_player": config.max_racks_per_player,
            },
            "is_completed": self.is_completed,
            "bonus_applied": self.bonus_applied,
            "winner": self.winner,
        }

    def __repr__(self):
        return f"<TrioMatch {self.player1_id}-{self.player2_id}-{self.player3_id}>"


class TrioRack(db.Model):
    """Tracking of individual racks within a trio match.

    Follows the same pattern as Rack for regular matches.
    Each rack records who won and the matchup at that moment.
    Supports soft delete for undo functionality.
    """

    __tablename__ = "trio_rack"

    id = db.Column(db.Integer, primary_key=True)
    trio_match_id = db.Column(
        db.Integer, db.ForeignKey("trio_match.id", ondelete="CASCADE"), nullable=False
    )
    rack_number = db.Column(db.Integer, nullable=False)  # 1-based, chronological order

    # Who won this rack
    winner_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    # Matchup at the moment of this rack (for audit/debugging)
    player1_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    player2_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    waiting_player_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    # Audit trail
    added_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Soft delete for undo
    is_deleted = db.Column(db.Boolean, default=False, nullable=False)
    removed_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    removed_at = db.Column(db.DateTime, nullable=True)

    # Relationships
    trio_match = db.relationship(
        "TrioMatch",
        backref=db.backref("racks", lazy="dynamic", order_by="TrioRack.rack_number"),
    )
    winner = db.relationship("User", foreign_keys=[winner_id])
    player1 = db.relationship("User", foreign_keys=[player1_id])
    player2 = db.relationship("User", foreign_keys=[player2_id])
    waiting_player = db.relationship("User", foreign_keys=[waiting_player_id])
    added_by = db.relationship("User", foreign_keys=[added_by_id])
    removed_by = db.relationship("User", foreign_keys=[removed_by_id])

    @property
    def is_active(self) -> bool:
        """Rack not deleted."""
        return not self.is_deleted

    def soft_delete(self, removed_by_id: int) -> None:
        """Mark rack as deleted (undo)."""
        self.is_deleted = True
        self.removed_by_id = removed_by_id
        self.removed_at = datetime.utcnow()

    def __repr__(self):
        return f"<TrioRack {self.rack_number} trio={self.trio_match_id} winner={self.winner_id}>"
