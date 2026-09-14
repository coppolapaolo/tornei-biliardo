"""
Module: models/individual_match/match_models.py
Purpose: Match, Set, and Rack models for individual match system
Split from: models/individual_match/models.py (P3a refactoring)
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, TYPE_CHECKING
from enum import Enum

from sqlalchemy import func

from ..base import db, BaseModel, utc_now
from ..status_enum import Discipline, MatchStatus
from ..match.base_match import BaseMatchMixin
from ..match.break_rules import (
    DEFAULT_BREAK_RULE,
    DEFAULT_START_RULE,
    BreakRule,
    StartRule,
)

if TYPE_CHECKING:
    from ..user.models import User


class IndividualMatch(BaseModel, BaseMatchMixin):
    """
    An individual match between two players (casual match).

    Inherits from BaseMatch to share validation/confirmation workflow
    with tournament matches (Match).
    """

    __tablename__ = "individual_match"

    id = db.Column(db.Integer, primary_key=True)
    proposal_id = db.Column(
        db.Integer, db.ForeignKey("match_proposal.id"), nullable=True
    )

    # Players
    player1_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    player2_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )

    # Match details - Location
    # Note: kept separate from proposal for matches created without proposal
    # New: FK to BilliardHall (nullable for backward compatibility)
    billiard_hall_id = db.Column(
        db.Integer,
        db.ForeignKey("billiard_hall.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Legacy: string-based location (kept for backward compatibility)
    location = db.Column(
        db.String(255), nullable=True
    )  # Made nullable - prefer billiard_hall_id
    scheduled_at = db.Column(db.DateTime, nullable=False)
    status = db.Column(
        db.Enum(
            MatchStatus,
            # Sul disco finiscono i **valori** ("validated"), non i nomi dei
            # membri ("VALIDATED"). Senza `values_callable` SQLAlchemy salva
            # il nome, e allora rinominare un membro dell'enum — un'operazione
            # che sembra puramente lessicale, e che i test non vedono perché
            # scrivono e rileggono lo stesso nome nello stesso processo —
            # rende **illeggibili le righe già scritte**:
            #
            #   LookupError: 'VALIDATED' is not among the defined enum values
            #
            # È successo il 2026-08-17, con il rinomino di COMPLETED/VALIDATED
            # in CLOSED_UNILATERALLY/CONFIRMED_BY_BOTH: `match.status` (una
            # `db.String`, quindi già a valori) non se n'è accorto, questa
            # colonna sì, e la dashboard è andata in 500.
            #
            # Con i valori la colonna diventa indifferente ai nomi Python, e
            # allineata a `match.status`, che è lo stesso dominio.
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
        ),
        nullable=False,
        default=MatchStatus.SCHEDULED,
    )

    # Game configuration
    # Note: duplicated from proposal for matches created without proposal
    # or when proposal is deleted. This denormalization is intentional.
    discipline = db.Column(
        db.String(50), nullable=False, default=Discipline.EIGHT_BALL.value
    )
    # Distance: None = free format (no limit), players end match manually
    # Note: No default - service layer should set 5 for normal matches
    distance = db.Column(db.Integer, nullable=True)
    is_race_to = db.Column(db.Boolean, nullable=False, default=True)
    break_rule = db.Column(db.String(20), nullable=False, default="alternate")
    # Sulle sfide individuali una gara da cui ereditare non c'è: il match **è**
    # la radice, e porta le sue due regole (ADR-056). `break_rule` c'era già dal
    # 2026-02 — scritto, mostrato e testato, ma mai letto da nessuno per dedurre
    # chi aprisse un triangolo. Adesso lo si legge.
    start_rule = db.Column(
        db.String(20), nullable=False, default=DEFAULT_START_RULE.value
    )  # first_player, lag (acchito)

    # I due fatti che l'acchito produce al tavolo (vedi `Match`, stessa forma).
    lag_winner_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    first_break_player_id = db.Column(
        db.Integer, db.ForeignKey("user.id"), nullable=True
    )

    # Multi-set configuration (Phase 6: Frontend Integration)
    is_multi_set = db.Column(db.Boolean, default=False, nullable=False)
    match_distance = db.Column(db.Integer, nullable=True)  # Number of sets
    is_race_to_sets = db.Column(
        db.Boolean, default=True, nullable=True
    )  # Race-to vs exact sets

    # Optional
    notes = db.Column(db.Text, nullable=True)

    # Results
    started_at = db.Column(db.DateTime, nullable=True)
    ended_at = db.Column(db.DateTime, nullable=True)  # Renamed from completed_at
    # Scores: racks won (single-set) or sets won (multi-set)
    # See distance_config property for winning threshold logic
    player1_score = db.Column(db.Integer, nullable=False, default=0)
    player2_score = db.Column(db.Integer, nullable=False, default=0)
    winner_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)

    # Validazione finale del risultato
    player1_confirmed = db.Column(db.Boolean, default=False, nullable=False)
    player2_confirmed = db.Column(db.Boolean, default=False, nullable=False)
    player1_confirmed_at = db.Column(db.DateTime, nullable=True)
    player2_confirmed_at = db.Column(db.DateTime, nullable=True)

    # Relationships
    proposal = db.relationship("MatchProposal", back_populates="individual_match")
    billiard_hall = db.relationship("BilliardHall", foreign_keys=[billiard_hall_id])
    player1 = db.relationship("User", foreign_keys=[player1_id])
    player2 = db.relationship("User", foreign_keys=[player2_id])
    winner = db.relationship("User", foreign_keys=[winner_id])
    lag_winner = db.relationship("User", foreign_keys=[lag_winner_id])
    first_break_player = db.relationship("User", foreign_keys=[first_break_player_id])

    # UNIQUE on proposal_id prevents double-accept of same proposal (TOCTOU guard).
    # SQLite allows multiple NULLs → matches without proposal remain valid.
    __table_args__ = (
        db.UniqueConstraint("proposal_id", name="uq_individual_match_proposal"),
    )

    # Individual racks within this match
    racks = db.relationship(  # type: ignore[assignment]
        "IndividualRack",
        back_populates="match",
        cascade="all, delete-orphan",
        order_by="IndividualRack.rack_number",
    )

    # Sets for multi-set matches
    sets = db.relationship(  # type: ignore[assignment]
        "IndividualSet",
        back_populates="match",
        cascade="all, delete-orphan",
        order_by="IndividualSet.set_number",
    )

    @property
    def distance_config(self):
        """Get Distance value object for this individual match.

        Returns unified Distance abstraction supporting both single-set
        and multi-set configurations.

        Returns:
            Distance: Immutable distance configuration, or None for free format
        """
        from models.match.distance import Distance

        # Free format: no distance limit
        if self.distance is None:
            return None

        if not self.is_multi_set:
            # Single-set configuration (backward compatible)
            return Distance(
                racks=self.distance,
                is_race_to_racks=self.is_race_to,
                is_multi_set=False,
                sets=1,
                is_race_to_sets=True,
            )
        else:
            # Multi-set configuration (Phase 6: Frontend Integration)
            return Distance(
                racks=self.distance,
                is_race_to_racks=self.is_race_to,
                is_multi_set=True,
                sets=self.match_distance if self.match_distance else 1,
                is_race_to_sets=self.is_race_to_sets,
            )

    @property
    def rack_score(self):
        """Get score value object for this match.

        For single-set matches, returns RackScore tracking racks won.
        For multi-set matches, returns MatchScore tracking sets won.
        For free format (distance=None), returns None.

        The returned object provides is_complete() and get_winner() methods
        used by BaseMatchMixin for validation workflow.

        Returns:
            RackScore, MatchScore, or None: Current scoring state
        """
        from models.match.score import RackScore, MatchScore

        # Free format: no distance limit, no scoring object
        if self.distance is None:
            return None

        if self.is_multi_set:
            # Multi-set: player1_score/player2_score are SETS won
            return MatchScore(
                distance=self.distance_config,
                player1_sets=self.player1_score,
                player2_sets=self.player2_score,
            )
        else:
            # Single-set: player1_score/player2_score are RACKS won
            return RackScore(
                distance=self.distance_config,
                player1_racks=self.player1_score,
                player2_racks=self.player2_score,
            )

    # ------------------------------------------------------------------
    # Chi apre (ADR-056)
    # ------------------------------------------------------------------

    @property
    def effective_start_rule(self) -> StartRule:
        """Qui il match **è** la radice: nessuna gara da cui ereditare."""
        return StartRule.normalize(self.start_rule) or DEFAULT_START_RULE

    @property
    def effective_break_rule(self) -> BreakRule:
        """Qui il match **è** la radice: nessuna gara da cui ereditare."""
        return BreakRule.normalize(self.break_rule) or DEFAULT_BREAK_RULE

    # ------------------------------------------------------------------
    # Chi prende parte, e com'è finita per lui
    # ------------------------------------------------------------------

    def outcome_for(self, user_id: int) -> str:
        """Com'è finita per questo giocatore: ``won``, ``lost`` o ``tie``.

        Il pareggio è un **esito**, non l'assenza di una vittoria: su
        «esattamente N» triangoli si finisce pari, e dedurre le sconfitte per
        differenza (``perse = giocate - vinte``) è il modo in cui la stessa
        partita finiva fra le sconfitte in cinque conteggi diversi.

        Stesso vocabolario di ``PlayerHistoryService``, che lo storico usa
        già per tenere insieme partite di gara e sfide individuali.
        """
        if self.winner_id is None:
            return "tie"
        return "won" if self.winner_id == user_id else "lost"

    def can_add_rack(self) -> bool:
        """Check if a rack can be added to the match.

        Overrides BaseMatchMixin to handle free format matches (distance=None).

        Returns:
            bool: True if rack can be added
        """
        from models.status_enum import MatchStatus as SharedMatchStatus

        # Status-based validation
        status_val = self.status.value if hasattr(self.status, "value") else self.status

        allowed_states = [
            SharedMatchStatus.PENDING.value,
            SharedMatchStatus.PLAYING.value,
            SharedMatchStatus.IN_PROGRESS.value,
        ]

        if status_val not in allowed_states:
            return False

        # Free format: can always add racks while in progress
        if self.distance is None:
            return True

        # Normal match: cannot add rack if match is at validation stage
        return not self.is_ready_for_validation()

    def is_ready_for_validation(self) -> bool:
        """Check if match is ready for player confirmation.

        Overrides BaseMatchMixin to handle free format matches (distance=None).

        For free format:
          - Ready when at least one rack played (players end manually)

        For normal matches:
          - Ready when distance is reached

        Returns:
            bool: True if match can be validated
        """
        from models.status_enum import MatchStatus as SharedMatchStatus

        # Status-based validation
        status_val = self.status.value if hasattr(self.status, "value") else self.status

        active_states = [
            SharedMatchStatus.PLAYING.value,
            SharedMatchStatus.IN_PROGRESS.value,
        ]

        if status_val not in active_states:
            return False

        # Free format: ready when at least one rack played
        if self.distance is None:
            total_racks = self.player1_score + self.player2_score
            return total_racks > 0

        # Normal match: check using RackScore/MatchScore
        score = self.rack_score
        if score is None:
            return False
        return score.is_complete()

    @property
    def awaiting_confirmation_from_id(self) -> Optional[int]:
        """Il giocatore di cui la partita aspetta la firma, se c'è.

        Aspetta la firma di X quando è pronta per la validazione, l'avversario
        ha già confermato e X no. Arrivati alla distanza chi vince firma
        d'ufficio (``IndividualRackService.add_rack_for_player``); nel formato
        libero firma chi preme «Termina». Senza nessuna firma la partita non
        aspetta nessuno in particolare: nel formato libero è «pronta» dal primo
        triangolo, mentre i due stanno ancora giocando.

        Vedi ``models/individual_match/pending_confirmation.py``.
        """
        if not self.is_ready_for_validation():
            return None
        if self.player1_confirmed and not self.player2_confirmed:
            return self.player2_id
        if self.player2_confirmed and not self.player1_confirmed:
            return self.player1_id
        return None

    @property
    def awaiting_confirmation_since(self) -> Optional[datetime]:
        """Da quando la partita aspetta quella firma: l'ora della prima."""
        waiting_for = self.awaiting_confirmation_from_id
        if waiting_for is None:
            return None
        if waiting_for == self.player1_id:
            return self.player2_confirmed_at
        return self.player1_confirmed_at

    def _complete_match_after_confirmation(self) -> None:
        """Complete the match after both players have confirmed.

        Overrides BaseMatchMixin to handle free format matches (distance=None).
        For free format, winner is the player with the higher score.
        """
        # Determine winner
        if self.distance is None:
            # Free format: winner is whoever has more racks
            if self.player1_score > self.player2_score:
                self.winner_id = self.player1_id
            elif self.player2_score > self.player1_score:
                self.winner_id = self.player2_id
            else:
                self.winner_id = None  # Tie
        else:
            # Normal match: use rack_score
            score = self.rack_score
            if score is None:
                self.winner_id = None
            else:
                winner_number = score.get_winner()
                if winner_number is None:
                    self.winner_id = None  # Tie
                else:
                    self.winner_id = (
                        self.player1_id if winner_number == 1 else self.player2_id
                    )

        # Update status to VALIDATED (bilateral confirmation complete)
        self.status = MatchStatus.CONFIRMED_BY_BOTH

        if hasattr(self, "ended_at"):
            self.ended_at = utc_now()

        # Emetti l'evento SOLO qui: questo metodo scatta unicamente dalla
        # conferma bilaterale (confirm_result). Forfait e complete_match
        # impostano COMPLETED senza passare di qui → casual gated, mai forfait.
        self._emit_individual_match_completed_event()

    def _emit_individual_match_completed_event(self) -> None:
        """Pubblica IndividualMatchCompletedEvent dopo la validazione bilaterale.

        Evento dedicato (NON MatchCompletedEvent): i consumer di quest'ultimo
        leggono la tabella `match`, mentre i casual vivono su `individual_match`.
        Vedi docstring dell'evento in models/events/match_events.py.
        """
        from models.events.match_events import IndividualMatchCompletedEvent
        from models.events.base import EventBus

        player1_name = self.player1.username if self.player1 else "Player 1"
        player2_name = self.player2.username if self.player2 else "Player 2"
        winner_name = None
        if self.winner_id and self.winner:
            winner_name = self.winner.username

        event = IndividualMatchCompletedEvent(
            match_id=self.id,
            player1_id=self.player1_id,
            player1_name=player1_name,
            player2_id=self.player2_id,
            player2_name=player2_name,
            winner_id=self.winner_id,
            winner_name=winner_name,
            score=f"{self.player1_score}-{self.player2_score}",
        )
        EventBus.publish(event)

    @property
    def location_display(self) -> str:
        """Get display name for location.

        Returns billiard_hall.name if available, otherwise falls back
        to legacy location string.

        Returns:
            str: Location name for display
        """
        if self.billiard_hall:
            return self.billiard_hall.name
        return self.location or ""

    def start_match(self) -> None:
        """Start the match.

        For multi-set matches, this also creates and starts the first set.
        """
        if self.status != MatchStatus.SCHEDULED:
            raise ValueError("Match cannot be started")

        self.status = MatchStatus.IN_PROGRESS
        self.started_at = utc_now()

        # For multi-set matches, create the first set
        if self.is_multi_set:
            self.start_first_set()

    def add_rack_result(
        self, winner_id: int, rack_number: Optional[int] = None
    ) -> "IndividualRack":
        """Add a rack result to the match.

        For multi-set matches, delegates to the current set which handles
        rack creation, set scores, set completion, and match score updates.

        For single-set matches, directly updates match scores.
        """
        if self.status != MatchStatus.IN_PROGRESS:
            raise ValueError("Cannot add rack result to non-active match")

        if not self.can_add_rack():
            raise ValueError(
                "Cannot add rack: match has reached maximum and needs validation"
            )

        if winner_id not in [self.player1_id, self.player2_id]:
            raise ValueError("Winner must be one of the match players")

        # Multi-set: delegate to current set
        if self.is_multi_set:
            current_set = self.get_current_set()
            if not current_set:
                raise ValueError("No active set in multi-set match")
            return current_set.add_rack_result(winner_id, rack_number)

        # Single-set: existing logic
        # Auto-assign rack number if not provided
        if rack_number is None:
            max_rack = (
                db.session.query(func.max(IndividualRack.rack_number))
                .filter_by(match_id=self.id)
                .scalar()
            )
            rack_number = (max_rack or 0) + 1

        rack = IndividualRack(
            match_id=self.id, rack_number=rack_number, winner_id=winner_id
        )

        db.session.add(rack)

        # Update scores for single-set matches
        if winner_id == self.player1_id:
            self.player1_score += 1
        else:
            self.player2_score += 1

        # Match no longer auto-completes when distance is reached.
        # Instead, is_ready_for_validation() returns True and players must
        # confirm the result via confirm_result(). When both confirm,
        # the match transitions to VALIDATED status.
        # This enables bilateral confirmation for casual matches.

        return rack

    def complete_match(self, winner_id: int) -> None:
        """Complete the match with a winner."""
        if self.status != MatchStatus.IN_PROGRESS:
            raise ValueError("Match is not in progress")

        # Data-integrity guard (C1): the winner MUST be one of the two players.
        # Without this, a player could close a match declaring an arbitrary
        # winner_id, corrupting stats/ELO downstream.
        if winner_id not in (self.player1_id, self.player2_id):
            raise ValueError("Winner must be one of the match players")

        self.status = MatchStatus.CLOSED_UNILATERALLY
        self.ended_at = utc_now()
        self.winner_id = winner_id

    def has_recorded_play(self) -> bool:
        """Se su questa partita è già stato registrato qualcosa.

        È la condizione che decide se la sfida si può ancora annullare o
        modificare: finché non è stato segnato niente, cambiare la distanza o
        far sparire la partita non riscrive nessun fatto. Dopo il primo
        triangolo sì, e allora la strada è chiuderla o abbandonarla.

        «Niente segnato» è più di «punteggio 0 a 0», e le tre differenze
        contano tutte:

        * nei match a set ``player*_score`` conta i **set**, quindi 0-0 può
          voler dire un set in corso con dei triangoli dentro;
        * un referto TPA può avere decine di comandi — buche, errori, turni —
          e ancora nessun rack chiuso (ADR-044). Quei comandi sono lavoro;
        * un triangolo tolto con l'annulla riporta il punteggio a 0-0, ma è
          un rack cancellato in modo morbido, non un rack mai esistito.
          Quello **non** blocca: la partita è tornata dov'era davvero.
        """
        if (self.player1_score or 0) + (self.player2_score or 0) > 0:
            return True

        if any(
            (s.player1_racks or 0) + (s.player2_racks or 0) > 0
            for s in (self.sets or [])  # type: ignore[union-attr]
        ):
            return True

        if any(
            not r.is_deleted for r in (self.racks or [])  # type: ignore[union-attr]
        ):
            return True

        from models.tpa.models import TpaReferto

        referto = TpaReferto.query.filter_by(individual_match_id=self.id).first()
        return referto is not None and len(referto.comandi or []) > 0

    def can_be_revised(self) -> bool:
        """Se la sfida è ancora annullabile e modificabile.

        Una sola condizione per le due azioni, di proposito: sono la stessa
        domanda posta due volte — «questa partita ha già prodotto dei fatti?».
        Tenerle separate avrebbe fatto divergere le due risposte al primo caso
        limite.
        """
        return (
            self.status in (MatchStatus.SCHEDULED, MatchStatus.IN_PROGRESS)
            and not self.has_recorded_play()
        )

    def cancel_match(self, reason: Optional[str] = None) -> None:
        """Annulla la sfida, se non è ancora stato segnato niente.

        Prima bastava che non fosse ``CLOSED_UNILATERALLY``: passava quindi
        anche una partita ``CONFIRMED_BY_BOTH``, cioè chiusa dalla doppia
        conferma dei due giocatori — che è l'unica cosa che muove l'Elo
        globale (ADR-051). Annullarla lasciava l'Elo dov'era: il risultato
        spariva e i suoi effetti no.
        """
        if self.status not in (MatchStatus.SCHEDULED, MatchStatus.IN_PROGRESS):
            raise ValueError(
                "Si annulla una sfida solo prima che finisca: "
                "questa è già chiusa o annullata"
            )

        if self.has_recorded_play():
            raise ValueError(
                "La sfida è cominciata: con dei triangoli già segnati "
                "si chiude o si abbandona, non si annulla"
            )

        self.status = MatchStatus.CANCELLED
        if reason:
            self.notes = f"Cancelled: {reason}"

    def forfeit_match(self, user_id: int) -> None:
        """Forfeit the match - user loses, opponent wins.

        The forfeiting player keeps their current score (racks already won).
        The opponent receives the winning score (distance).

        Args:
            user_id: ID of player forfeiting

        Raises:
            ValueError: If user is not a player or match cannot be forfeited
        """
        # Validate user is a player
        if user_id not in [self.player1_id, self.player2_id]:
            raise ValueError("User is not a player in this match")

        # Validate match status
        if self.status not in [MatchStatus.SCHEDULED, MatchStatus.IN_PROGRESS]:
            raise ValueError("Can only forfeit scheduled or in-progress matches")

        # Winning threshold (C2): for multi-set matches player*_score counts
        # SETS won, so the winner must reach get_winning_sets() (= match_distance),
        # not get_winning_racks() (racks-per-set). For single-set it's racks.
        winning_score = None
        if self.distance_config:
            winning_score = (
                self.distance_config.get_winning_sets()
                if self.is_multi_set
                else self.distance_config.get_winning_racks()
            )

        # Determine winner (opponent of forfeiting player)
        if user_id == self.player1_id:
            self.winner_id = self.player2_id
            # Ensure winner has at least the winning score (if distance is set)
            if winning_score is not None and self.player2_score < winning_score:
                self.player2_score = winning_score
            # Keep player1_score as-is (racks/sets already won)
        else:
            self.winner_id = self.player1_id
            if winning_score is not None and self.player1_score < winning_score:
                self.player1_score = winning_score
            # Keep player2_score as-is (racks/sets already won)

        # Complete the match
        self.status = MatchStatus.CLOSED_UNILATERALLY
        self.ended_at = utc_now()

    def get_opponent(self, user_id: int) -> Optional["User"]:
        """Get the opponent for a given user."""
        from typing import cast

        if user_id == self.player1_id:
            return cast("User", self.player2)
        elif user_id == self.player2_id:
            return cast("User", self.player1)
        return None

    def get_user_score(self, user_id: int) -> int:
        """Get score for a specific user."""
        if user_id == self.player1_id:
            return self.player1_score
        elif user_id == self.player2_id:
            return self.player2_score
        return 0

    def _remove_last_rack(self, user_id: int) -> None:
        """
        Implementation of BaseMatch abstract method.
        Remove last rack from match (soft delete).

        For multi-set matches, delegates to the current set.
        For single-set matches, directly removes the last rack.
        """
        # Multi-set: delegate to current set
        if self.is_multi_set:
            current_set = self.get_current_set()
            if current_set:
                current_set.remove_last_rack(user_id)
            return

        # Single-set: existing logic
        last_rack = (
            IndividualRack.query.filter_by(match_id=self.id, is_deleted=False)
            .order_by(IndividualRack.rack_number.desc())
            .first()
        )

        if last_rack:
            last_rack.is_deleted = True
            last_rack.removed_by_id = user_id
            last_rack.removed_at = utc_now()

            # Update scores
            if last_rack.winner_id == self.player1_id:
                self.player1_score = max(0, self.player1_score - 1)
            else:
                self.player2_score = max(0, self.player2_score - 1)

    # -------------------------
    # Multi-Set Methods
    # -------------------------
    def get_current_set(self) -> Optional["IndividualSet"]:
        """Get the current active set for multi-set matches.

        Returns:
            The currently playing set, or None if not multi-set or no active set.
        """
        if not self.is_multi_set:
            return None

        # Find the set that is currently playing, or the last completed set
        for s in self.sets:  # type: ignore
            if s.status == MatchStatus.PLAYING.value:
                return s

        # No playing set - return None (need to start next set)
        return None

    def start_first_set(self) -> "IndividualSet":
        """Create and start the first set for a multi-set match.

        Called automatically when start_match() is invoked on a multi-set match.

        Returns:
            The newly created and started IndividualSet.
        """
        if not self.is_multi_set:
            raise ValueError("Cannot create set for single-set match")

        if len(self.sets) > 0:  # type: ignore
            raise ValueError("First set already exists")

        new_set = IndividualSet(
            match_id=self.id,
            set_number=1,
            distance=self.distance,
            is_race_to=self.is_race_to,
            status="playing",
            started_at=utc_now(),
        )
        # Append to collection to update relationship and cascade persist
        self.sets.append(new_set)  # type: ignore[union-attr]

        return new_set

    def start_next_set(self) -> "IndividualSet":
        """Start the next set in a multi-set match.

        Returns:
            The newly created and started IndividualSet.
        """
        if not self.is_multi_set:
            raise ValueError("Cannot create set for single-set match")

        # Check that current set is completed
        current_set = self.get_current_set()
        if current_set and current_set.status == MatchStatus.PLAYING.value:
            raise ValueError(f"Set {current_set.set_number} is still in progress")

        # Check if match is already complete
        if self._is_multi_set_complete():
            raise ValueError("Match is already complete")

        # Determine next set number
        next_set_number = len(self.sets) + 1  # type: ignore

        new_set = IndividualSet(
            match_id=self.id,
            set_number=next_set_number,
            distance=self.distance,
            is_race_to=self.is_race_to,
            status="playing",
            started_at=utc_now(),
        )
        # Append to collection to update relationship and cascade persist
        self.sets.append(new_set)  # type: ignore[union-attr]

        return new_set

    def _is_multi_set_complete(self) -> bool:
        """Check if multi-set match is complete.

        Returns:
            True if a player has won enough sets.
        """
        if not self.is_multi_set:
            return False

        match_distance = self.match_distance or 1

        if self.is_race_to_sets:
            return (
                self.player1_score >= match_distance
                or self.player2_score >= match_distance
            )
        else:
            return (self.player1_score + self.player2_score) >= match_distance

    def _check_multi_set_completion(self) -> None:
        """Check and complete match if multi-set threshold is reached."""
        if not self._is_multi_set_complete():
            return

        # Determine winner. In modalita' exact-sets (is_race_to_sets=False) il
        # completamento puo' scattare in parita' (es. 1-1 con match_distance=2):
        # un tie NON e' una vittoria di player2, quindi nessun vincitore.
        if self.player1_score > self.player2_score:
            self.winner_id = self.player1_id
        elif self.player2_score > self.player1_score:
            self.winner_id = self.player2_id
        else:
            self.winner_id = None

        # Note: We don't auto-complete the match status here.
        # The match uses bilateral confirmation flow via is_ready_for_validation().

    def __repr__(self) -> str:
        return (
            f"<IndividualMatch {self.player1_id} vs "
            f"{self.player2_id} at {self.location}>"
        )


class IndividualSetStatus(Enum):
    """Status of an individual set within a multi-set match."""

    PENDING = "pending"
    PLAYING = "playing"
    COMPLETED = "completed"


class IndividualSet(BaseModel):
    """A single set within a multi-set individual match.

    Follows the same pattern as Set model for tournament matches.
    """

    __tablename__ = "individual_set"

    id = db.Column(db.Integer, primary_key=True)
    match_id = db.Column(
        db.Integer,
        db.ForeignKey("individual_match.id", ondelete="CASCADE"),
        nullable=False,
    )
    set_number = db.Column(db.Integer, nullable=False)

    # Configuration
    distance = db.Column(db.Integer, nullable=False)
    is_race_to = db.Column(db.Boolean, default=True, nullable=False)

    # Scores
    player1_racks = db.Column(db.Integer, default=0, nullable=False)
    player2_racks = db.Column(db.Integer, default=0, nullable=False)

    # Result
    status = db.Column(
        db.String(20), default="pending", nullable=False
    )  # pending, playing, completed
    winner_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    started_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)

    # Relationships
    match = db.relationship("IndividualMatch", back_populates="sets")
    winner = db.relationship("User", foreign_keys=[winner_id])
    racks = db.relationship(
        "IndividualRack",
        back_populates="individual_set",
        cascade="all, delete-orphan",
        order_by="IndividualRack.rack_number",
    )

    __table_args__ = (
        db.UniqueConstraint("match_id", "set_number", name="uq_individual_match_set"),
    )

    def start_set(self) -> None:
        """Start the set."""
        if self.status != MatchStatus.PENDING.value:
            raise ValueError("Set can only be started from pending status")

        self.status = MatchStatus.PLAYING.value
        self.started_at = utc_now()

    def add_rack_result(
        self,
        winner_id: int,
        rack_number: Optional[int] = None,
    ) -> "IndividualRack":
        """Add a rack result to this set."""
        if self.status != MatchStatus.PLAYING.value:
            raise ValueError("Cannot add rack result to non-playing set")

        if winner_id not in [self.match.player1_id, self.match.player2_id]:
            raise ValueError("Winner must be one of the match players")

        # Auto-assign rack number if not provided
        # Note: UNIQUE constraint is on (match_id, rack_number), so we must
        # find max across the entire match, not just this set
        if rack_number is None:
            max_rack = (
                db.session.query(func.max(IndividualRack.rack_number))
                .filter_by(match_id=self.match_id)
                .scalar()
            )
            rack_number = (max_rack or 0) + 1

        # Create rack record
        rack = IndividualRack(
            match_id=self.match_id,
            individual_set_id=self.id,
            rack_number=rack_number,
            winner_id=winner_id,
        )

        db.session.add(rack)

        # Update set scores
        if winner_id == self.match.player1_id:
            self.player1_racks += 1
        else:
            self.player2_racks += 1

        # Check if set is completed
        self._check_set_completion()

        return rack

    def _check_set_completion(self) -> None:
        """Check if set is completed based on scoring rules."""
        if self.is_race_to:
            # Race to X: first to reach distance wins
            if self.player1_racks >= self.distance:
                self._complete_set(self.match.player1_id)
            elif self.player2_racks >= self.distance:
                self._complete_set(self.match.player2_id)
        else:
            # Fixed distance: play exactly distance racks
            total_racks = self.player1_racks + self.player2_racks
            if total_racks >= self.distance:
                if self.player1_racks > self.player2_racks:
                    self._complete_set(self.match.player1_id)
                elif self.player2_racks > self.player1_racks:
                    self._complete_set(self.match.player2_id)
                # Tie - continue playing (sudden death)

    def _complete_set(self, winner_id: int) -> None:
        """Complete the set with a winner."""
        self.status = MatchStatus.CLOSED_UNILATERALLY.value
        self.completed_at = utc_now()
        self.winner_id = winner_id

        # Update match set scores
        if winner_id == self.match.player1_id:
            self.match.player1_score += 1
        else:
            self.match.player2_score += 1

        # Check if match is completed
        self.match._check_multi_set_completion()

    def is_completed(self) -> bool:
        """Check if set is completed."""
        return self.status == MatchStatus.CLOSED_UNILATERALLY.value

    def remove_last_rack(
        self, user_id: int, player_id: Optional[int] = None
    ) -> Optional["IndividualRack"]:
        """Remove the last rack from this set (soft delete).

        Args:
            user_id: ID of user removing the rack
            player_id: se dato, si toglie l'ultimo triangolo **vinto da lui**.
                Il segnapunti al meglio dei set ha due comandi distinti, uno
                per giocatore: senza questo filtro toglierebbe l'ultimo
                triangolo del set chiunque l'avesse vinto, cioè una cosa
                diversa da quella scritta sul pulsante.

        Returns:
            The removed rack, or None if no racks to remove
        """
        # Find last rack in this set
        query = IndividualRack.query.filter_by(
            individual_set_id=self.id, is_deleted=False
        )
        if player_id is not None:
            query = query.filter_by(winner_id=player_id)
        last_rack = query.order_by(IndividualRack.rack_number.desc()).first()

        if not last_rack:
            return None

        # Soft delete the rack
        last_rack.is_deleted = True
        last_rack.removed_by_id = user_id
        last_rack.removed_at = utc_now()

        # Update set scores
        if last_rack.winner_id == self.match.player1_id:
            self.player1_racks = max(0, self.player1_racks - 1)
        else:
            self.player2_racks = max(0, self.player2_racks - 1)

        # If set was completed, reopen it
        if self.status == MatchStatus.CLOSED_UNILATERALLY.value:
            self.status = MatchStatus.PLAYING.value
            self.completed_at = None

            # Also revert the match set score that was incremented when set completed
            if self.winner_id == self.match.player1_id:
                self.match.player1_score = max(0, self.match.player1_score - 1)
            else:
                self.match.player2_score = max(0, self.match.player2_score - 1)

            self.winner_id = None

        return last_rack

    @property
    def distance_config(self):
        """Get Distance value object for this set."""
        from models.match.distance import Distance

        return Distance(
            racks=self.distance,
            is_race_to_racks=self.is_race_to,
            is_multi_set=False,
            sets=1,
            is_race_to_sets=True,
        )

    def __repr__(self) -> str:
        return (
            f"<IndividualSet {self.match_id}-{self.set_number}: "
            f"{self.player1_racks}-{self.player2_racks}>"
        )


class IndividualRack(BaseModel):
    """A single rack within an individual match.

    For multi-set matches, racks belong to a specific IndividualSet.
    For single-set matches, individual_set_id is NULL.
    """

    __tablename__ = "individual_rack"

    id = db.Column(db.Integer, primary_key=True)
    match_id = db.Column(
        db.Integer,
        db.ForeignKey("individual_match.id", ondelete="CASCADE"),
        nullable=False,
    )
    # FK to set (nullable for backward compatibility with single-set matches)
    individual_set_id = db.Column(
        db.Integer,
        db.ForeignKey("individual_set.id", ondelete="CASCADE"),
        nullable=True,
    )
    rack_number = db.Column(db.Integer, nullable=False)
    winner_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    # Optional details
    #: Chi ha eseguito il tiro di apertura. La colonna c'era dal 2026-02 e non
    #: la valorizzava nessuno: adesso la scrive chi crea il triangolo,
    #: deducendola dalla regola di apertura della sfida (ADR-056).
    break_player_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    #: Triangolo chiuso in una visita, marcato dal trattino sul tabellone.
    is_run_out = db.Column(db.Boolean, nullable=False, default=False)
    notes = db.Column(db.Text, nullable=True)

    # Log delle operazioni per tracciare chi ha aggiunto/rimosso rack
    added_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    added_at = db.Column(db.DateTime, nullable=True, default=utc_now)
    removed_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    removed_at = db.Column(db.DateTime, nullable=True)
    is_deleted = db.Column(
        db.Boolean, default=False, nullable=False
    )  # Soft delete per il log

    # Relationships
    match = db.relationship("IndividualMatch", back_populates="racks")
    individual_set = db.relationship("IndividualSet", back_populates="racks")
    winner = db.relationship("User", foreign_keys=[winner_id])
    break_player = db.relationship("User", foreign_keys=[break_player_id])
    added_by = db.relationship("User", foreign_keys=[added_by_id])
    removed_by = db.relationship("User", foreign_keys=[removed_by_id])

    # Unique constraint: one rack per number per match
    __table_args__ = (
        db.UniqueConstraint("match_id", "rack_number", name="uq_match_rack"),
    )

    @property
    def is_break_and_run(self) -> bool:
        """Chiuso in una visita **avendolo aperto**: si deduce, non si sceglie."""
        return bool(
            self.is_run_out
            and self.break_player_id is not None
            and self.break_player_id == self.winner_id
        )

    def __repr__(self) -> str:
        return (
            f"<IndividualRack {self.match_id}-{self.rack_number}: "
            f"winner={self.winner_id}>"
        )
