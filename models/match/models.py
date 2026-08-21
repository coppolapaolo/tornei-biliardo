"""
Module: models/match/models.py
Purpose: Match domain models (Match, Rack, MatchResult, TrioMatch)
Data Structures: Match, Rack, MatchResult, TrioMatch
Dependencies: models.base.db, datetime
"""

from typing import Any, Optional, TYPE_CHECKING

from sqlalchemy import event, inspect

from models.base import db, TimestampMixin, utc_now
from models.status_enum import MatchStatus, Discipline
from .base_match import BaseMatchMixin

if TYPE_CHECKING:
    from .set_models import Set


class Match(db.Model, TimestampMixin, BaseMatchMixin):
    """Core match entity representing a game between players."""

    __tablename__ = "match"
    __table_args__ = (
        db.Index(
            "ix_match_bracket",
            "gara_id",
            "bracket_group",
            "bracket_type",
            "bracket_round",
            "bracket_slot",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    # gara_id nullable to support standalone matches (detached from deleted gara)
    gara_id = db.Column(
        db.Integer, db.ForeignKey("gara.id", ondelete="SET NULL"), nullable=True
    )
    round_number = db.Column(
        db.Integer, nullable=False
    )  # 1, 2, 3. See ADR-003 (YAGNI) in docs/_archive/
    # 2025-12-architectural-decisions-pre-adr.md

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

    # Distance configuration. Per ADR-027 questi campi sono override per
    # match (e quindi indirettamente per turno) sopra la configurazione gara:
    # - single-set: match_distance = rack per vincere
    # - multi-set:  match_distance = set per vincere il match
    # is_race_to / is_race_to_sets nullable: NULL = eredita da gara.
    # Use distance_config property for the unified abstraction.
    match_distance = db.Column(db.Integer, default=1)
    is_multi_set = db.Column(db.Boolean, default=False)
    is_race_to = db.Column(db.Boolean, nullable=True)  # NULL = eredita da gara
    is_race_to_sets = db.Column(db.Boolean, nullable=True)  # NULL = eredita da gara
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
    created_at = db.Column(db.DateTime, default=utc_now)
    is_trio = db.Column(db.Boolean, default=False)  # Indica se è un trio

    # Coordinate nel tabellone (eliminazione diretta / doppio KO).
    # NULL su tutte e tre = match non appartenente a un tabellone (amalfi,
    # round robin, random) oppure gara a tabellone antecedente all'introduzione
    # di questi campi: in quel caso le strategie ricadono sul ramo legacy.
    #
    # Tre colonne invece di un singolo indice heap perché il losers bracket NON
    # è un albero binario completo (alterna round minori e maggiori con lo
    # stesso numero di match): la tripla le rappresenta uniformemente entrambi.
    # Il "seat" nel match successivo non è persistito: è derivato da
    # bracket_slot % 2 (vedi bracket.wb_feed), e una colonna in più sarebbe
    # ridondanza desincronizzabile.
    bracket_type = db.Column(
        db.String(8), nullable=True
    )  # W | L | GF | GFR | 3P (vedi models/matchmaking/bracket.py)
    bracket_round = db.Column(db.Integer, nullable=True)  # turno interno al bracket
    bracket_slot = db.Column(db.Integer, nullable=True)  # posizione 0-based nel round
    # Girone di appartenenza nella formula FISBB (Step 12): i gironi sono
    # doppi KO troncati giocati in parallelo, quindi la tripla sopra non è più
    # univoca dentro la gara. NULL = tabellone finale, oppure gara senza fase
    # a gironi (che è il caso di tutte le altre strategie a tabellone).
    bracket_group = db.Column(db.Integer, nullable=True)  # indice 0-based del girone

    # Time tracking for statistics
    started_at = db.Column(db.DateTime, nullable=True)  # Set when match starts playing
    ended_at = db.Column(db.DateTime, nullable=True)  # Set when match completes

    # Table assignment for venue management
    table_assignment = db.Column(
        db.String(10), nullable=True
    )  # e.g., "A", "B", "sala rossa"

    # Handicap system
    # NULL = eredita da gara (→ campionato). Vedi effective_has_handicap.
    # Un match con handicap effettivo NON aggiorna il rating Elo.
    has_handicap = db.Column(db.Boolean, nullable=True, default=None)
    player1_handicap = db.Column(
        db.Integer, default=0
    )  # Starting advantage for player1
    player2_handicap = db.Column(
        db.Integer, default=0
    )  # Starting advantage for player2
    # NB: c'era una `handicap_rule_id` con FK verso `handicap_rule`, tolta con
    # quella tabella (ADR-049). Sui DB con SQLite < 3.35 la colonna sopravvive
    # sul disco, orfana: non essendo dichiarata qui, SQLAlchemy non la
    # seleziona e non la scrive mai. Vedi migrations/20260819.
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

    def is_completed(self) -> bool:
        """Check if match is completed."""
        return self.status == MatchStatus.CLOSED_UNILATERALLY.value

    @property
    def is_walkover(self) -> bool:
        """True if completed without real racks played (bye, forfeit, trio walkover).

        Used by gamification/rating handlers to skip XP/Elo updates for walkover
        outcomes and by classification to credit the nominal winner with distance
        racks in trio walkovers.

        Rack count uses an explicit `db.session.query(Rack)` by match_id rather
        than `self.racks`, which would lazy-load the relationship and raise
        `DetachedInstanceError` if the Match instance is detached (relevant for
        future async dispatch where handlers receive detached objects).
        """
        if (
            self.status != MatchStatus.CLOSED_UNILATERALLY.value
            or self.winner_id is None
        ):
            return False
        if self.is_trio:
            return (
                self.trio_match is not None and self.trio_match.total_racks_played == 0
            )
        return db.session.query(Rack).filter_by(match_id=self.id).count() == 0

    @property
    def is_at_distance(self) -> bool:
        """Check if match has reached its required distance.

        Returns True when the match has played all required racks,
        regardless of whether there's a clear winner.

        For regular matches:
        - Race to N: one player reached N racks
        - Exactly N: total racks played == N

        For trio matches:
        - All required racks have been played per TrioConfig
        """
        if self.is_trio and self.trio_match:
            config = self.trio_match.trio_config
            return self.trio_match.total_racks_played >= config.total_played_racks

        # Regular 2-player match — usa Distance VO per rispettare gli override
        # per match/turno (ADR-027). Niente accesso diretto a self.gara.distance.
        distance = self.effective_distance
        if self.effective_is_race_to:
            return self.player1_score >= distance or self.player2_score >= distance
        return self.player1_score + self.player2_score == distance

    @property
    def is_player_validated(self) -> bool:
        """Check if all players have confirmed the result.

        For regular matches: both player1 and player2 confirmed.
        For trio matches: all three players confirmed.
        """
        if self.is_trio and self.trio_match:
            return (
                self.trio_match.player1_confirmed
                and self.trio_match.player2_confirmed
                and self.trio_match.player3_confirmed
            )
        return self.player1_confirmed and self.player2_confirmed

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
        """Numero di rack per vincere il match (single-set).

        Per ADR-027 round-creation popola sempre `match_distance` con la
        distanza effettiva (override round o default gara). La migration
        20260509 ha uniformato i match legacy che avevano match_distance=1.

        Heuristic single-set: `match_distance == 1` viene trattato come "non
        popolato" (default schema) e fa fallback a `gara.distance`. In
        pratica nessuno vuole una gara race-to-1, quindi il valore 1 è
        sempre un default residuale di Match() istanziato senza override
        esplicito (es. test legacy o codice che crea match programmatici
        senza passare per round-creation).

        Per match standalone (gara_id NULL), fallback a 5.
        """
        if self.match_distance and self.match_distance > 1:
            return self.match_distance
        if self.match_distance == 1 and self.gara is None:
            # Standalone match con default — fallback al default standalone
            return 5
        return self.gara.distance if self.gara else 5

    @property
    def effective_is_race_to(self) -> bool:
        """Modalità (race-to vs esatto) per questo match.

        Override per match (NULL = eredita da gara). Per ADR-027.
        """
        if self.is_race_to is not None:
            return self.is_race_to
        return self.gara.is_race_to if self.gara else True

    @property
    def effective_is_race_to_sets(self) -> bool:
        """Modalità multi-set: race-to-N-sets vs esatto N sets."""
        if self.is_race_to_sets is not None:
            return self.is_race_to_sets
        if self.gara is not None:
            return getattr(self.gara, "is_race_to_sets", True)
        return True

    @property
    def effective_has_handicap(self) -> bool:
        """Handicap mode effettivo: override match → gara → campionato → False.

        NULL su `has_handicap` significa "eredita dalla gara" (che a sua volta
        eredita dal campionato). Per match standalone (gara NULL) il fallback è
        False. Un match con handicap effettivo NON deve aggiornare i rating
        (Elo): vedi RatingEventHandlers.handle_match_completed.
        """
        if self.has_handicap is not None:
            return self.has_handicap
        if self.gara is not None:
            return self.gara.effective_has_handicap
        return False

    @property
    def counts_for_rating(self) -> bool:
        """Questa partita muove i rating Elo?

        Accessore comodo per template, script e diagnosi. La regola vera —
        walkover, handicap, stessa categoria — sta tutta in
        ``RatingEligibility``, in un posto solo: qui si delega e basta.

        NB: fa due query per leggere le categorie. Nei cicli su molti match
        usare ``RatingEligibility.build_index`` e passare l'indice.
        """
        from models.rating.eligibility import RatingEligibility

        return RatingEligibility.counts_for_rating(self)

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

    def start_next_set(self) -> "Set":
        """Start the next set in a multi-set match. Delegates to SetLifecycleService."""
        from .set_lifecycle_service import SetLifecycleService

        return SetLifecycleService.start_next_set(self)

    def get_current_set(self) -> Optional["Set"]:
        """Get the current set being played. Delegates to SetLifecycleService."""
        from .set_lifecycle_service import SetLifecycleService

        return SetLifecycleService.get_current_set(self)

    def complete_set(self, set_number: int, winner_id: int) -> None:
        """Complete a set and check if match is finished. Delegates to SetLifecycleService."""  # noqa: E501
        from .set_lifecycle_service import SetLifecycleService

        SetLifecycleService.complete_set(self, set_number, winner_id)

    def _remove_last_rack(self, user_id: int) -> None:
        """
        Implementation of BaseMatch abstract method.
        Remove last rack from match (soft delete).

        Also resets player confirmations since the score has changed.
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
            last_rack.removed_at = utc_now()

            # Update match scores
            if last_rack.winner_id == self.player1_id:
                self.player1_score = max(0, self.player1_score - 1)
            elif last_rack.winner_id == self.player2_id:
                self.player2_score = max(0, self.player2_score - 1)

            # Reset confirmations since score changed
            self.reset_confirmations()


@event.listens_for(Match, "before_insert")
@event.listens_for(Match, "before_update")
def _timbra_la_fine(_mapper: Any, _connection: Any, match: "Match") -> None:
    """Una partita che entra in uno stato finale riceve la sua data di fine.

    **Perché un hook e non una riga nei chiamanti.** Fino al 2026-08-21
    ``ended_at`` non era una proprietà dello stato finale: era l'effetto
    collaterale di chiamare ``MatchStateService.to_completed``. Chi chiudeva
    una partita per altre strade non scriveva la data, e le strade erano
    quattro:

    * la doppia conferma dei giocatori (``BaseMatchMixin``), che per giunta
      ci provava dentro un ``hasattr(self, "completed_at")`` rimasto falso
      dopo il rinomino della colonna;
    * il **pareggio** a rack esatti non validato dal direttore
      (``ScoringService._handle_rack_completion``);
    * il **ritiro** di un giocatore, che chiude d'ufficio le sue partite
      (``WithdrawPolicyService``);
    * il **bye** Amalfi chiuso col punteggio della sfida
      (``AmalfiChallengeByeService``).

    In produzione erano 63 partite finite senza data su 367. E non era un
    buco innocuo: SQLite ordina i NULL **per primi**, quindi
    ``recalculate_all_elo`` — che rigioca la storia con ``ORDER BY ended_at``
    — le processava prima di tutte le altre, mentre il pool globale le
    spingeva in coda. I due pool ricostruivano due storie diverse.

    Correggere i quattro punti avrebbe lasciato scoperto il quinto, quello
    che ancora non esiste. Qui l'invariante è garantita dove si scrive:
    qualunque percorso, presente o futuro, la rispetta senza saperlo.

    **Solo sulla transizione.** Un aggiornamento qualunque di una partita già
    chiusa non deve inventarle una data di oggi: le 63 righe storiche vanno
    riparate ricostruendo la data vera
    (``scripts/repair_match_ended_at.py``), non timbrandole quando qualcuno
    le sfiora. Per questo si controlla che lo stato sia **cambiato** in
    questo flush.

    Una data già presente non viene mai toccata: il direttore può fissare
    data e ora di fine a mano (``MatchService``), e la sua vince.
    """
    if match.ended_at is not None:
        return
    if not MatchStatus.is_finished(match.status):
        return

    storia = inspect(match).attrs.status.history
    if not storia.has_changes():
        return

    match.ended_at = utc_now()


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

    created_at = db.Column(db.DateTime, default=utc_now)

    # Nuovi campi per UX semplificata (log operazioni)
    added_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    added_at = db.Column(db.DateTime, nullable=True, default=utc_now)
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
    created_at = db.Column(db.DateTime, default=utc_now)

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

    # Individual player confirmations - all 3 needed OR admin validation to complete
    player1_confirmed = db.Column(db.Boolean, default=False)
    player2_confirmed = db.Column(db.Boolean, default=False)
    player3_confirmed = db.Column(db.Boolean, default=False)

    forfeit_player_id = db.Column(
        db.Integer, db.ForeignKey("user.id")
    )  # Player who forfeited (if any)
    winner_id = db.Column(
        db.Integer, db.ForeignKey("user.id")
    )  # Con classifica rack-based, winner_id puo' essere NULL (pareggio)

    created_at = db.Column(db.DateTime, default=utc_now)

    # Relations
    # uselist=False because each Match has at most one TrioMatch (1:1 relationship).
    # cascade="all, delete-orphan" ensures TrioMatch is removed when parent Match
    # is deleted (e.g. AdvancedRoundManager.cancel_round, round_cancellation.py).
    # Prevents orphan TrioMatch rows with dangling match_id references.
    match = db.relationship(
        "Match",
        backref=db.backref(
            "trio_match",
            uselist=False,
            cascade="all, delete-orphan",
        ),
    )
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
        """Get TrioConfig basato sulla distanza effettiva del match.

        ADR-027: usa match.effective_distance per rispettare gli override
        per turno. Senza questo, un trio in un round con override esatti
        userebbe sempre la distanza della gara.
        """
        from models.match.trio_config import TrioConfig

        match_obj = db.session.get(Match, self.match_id)
        if match_obj:
            return TrioConfig(distance=match_obj.effective_distance)
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

    # NOTE: add_rack_win() moved to TrioScoringService.add_rack_win()
    # NOTE: remove_last_rack() moved to TrioScoringService.remove_last_rack()

    def initialize_matchup(self):
        """Initialize current players for the first rack.

        Should be called immediately after trio creation to set up
        the initial matchup (P1 vs P2, P3 waits).
        """
        if self.total_racks_played == 0 and self.current_player1_id is None:
            from .trio_scoring_service import TrioScoringService

            TrioScoringService._update_current_players(self)

    def confirm_result_by_player(self, user_id: int) -> dict:
        """Confirm the trio result by a specific player.

        All 3 players must confirm for the match to complete.
        Returns confirmation status.

        Args:
            user_id: ID of the player confirming

        Returns:
            dict with 'success', 'is_completed', 'confirmations' count

        Raises:
            ValueError: If user is not in this trio or not awaiting confirmation
        """
        if not self.awaiting_confirmation:
            raise ValueError("Trio non in attesa di conferma")

        if user_id not in self.player_ids:
            raise ValueError("Utente non è un giocatore di questo trio")

        # Track which player confirmed
        if user_id == self.player1_id:
            self.player1_confirmed = True
        elif user_id == self.player2_id:
            self.player2_confirmed = True
        elif user_id == self.player3_id:
            self.player3_confirmed = True

        confirmations = sum(
            [self.player1_confirmed, self.player2_confirmed, self.player3_confirmed]
        )

        # Complete if all 3 confirmed
        if confirmations == 3:
            self._finalize_trio(closed_by_director=False)
            return {
                "success": True,
                "is_completed": True,
                "confirmations": 3,
                "message": "Tutti i giocatori hanno confermato, partita completata",
            }

        return {
            "success": True,
            "is_completed": False,
            "confirmations": confirmations,
            "message": f"Conferma registrata ({confirmations}/3)",
        }

    def confirm_result_by_admin(self) -> dict:
        """Confirm the trio result by admin/director - bypasses player confirmations.

        Returns:
            dict with 'success', 'is_completed'

        Raises:
            ValueError: If not awaiting confirmation
        """
        if not self.awaiting_confirmation:
            raise ValueError("Trio non in attesa di conferma")

        self._finalize_trio(closed_by_director=True)

        return {
            "success": True,
            "is_completed": True,
            "message": "Partita validata dall'amministratore",
        }

    def _finalize_trio(self, closed_by_director: bool = False) -> None:
        """Chiude il trio, in uno dei due stati finali.

        Args:
            closed_by_director: ha firmato il direttore scavalcando le
                conferme. Porta a `CLOSED_UNILATERALLY`: il risultato e' agli
                atti e nessun giocatore puo' piu' annullare.

                Con `False` hanno confermato tutti e tre, e la partita va in
                `CONFIRMED_BY_BOTH` — esattamente come una partita a due
                chiusa dai suoi due giocatori. E' la parita' che al trio
                mancava: prima entrambe le strade finivano in
                `CLOSED_UNILATERALLY`, quindi la finestra per annullare
                l'ultimo triangolo si chiudeva nell'istante della terza
                conferma invece che alla validazione del direttore.
        """
        from .state_service import MatchStateService

        # Mark as completed
        self.awaiting_confirmation = False
        self.is_completed = True

        # Update associated match via state service for SSE emission
        match_obj = db.session.get(Match, self.match_id)
        if match_obj:
            match_obj.winner_id = self.winner_id
            # Store total racks in match scores for quick access
            match_obj.player1_score = self.player1_racks
            match_obj.player2_score = self.player2_racks

            # Qui c'era `match_obj.validated_by_admin = True`, un attributo
            # che su `Match` non esiste (vive su `Rack`) e che serviva solo a
            # farsi rileggere da `to_completed`. Oltre che invisibile era
            # anche superfluo: quel guard lascia passare i trio a prescindere,
            # perché `is_trio` è una colonna vera e questa partita ce l'ha.
            #
            # Use state service to complete match and emit SSE
            MatchStateService.to_completed(
                match_obj.id, confirmed_by_players=not closed_by_director
            )

    def handle_forfeit(
        self, forfeiting_player_id: int, added_by_id: int = None
    ) -> bool:
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
            from .trio_scoring_service import TrioScoringService

            TrioScoringService._update_current_players(self)

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

        # Determine winner using Condorcet/Schulze (excluding forfeit player)
        from models.match.trio_schulze import determine_trio_winner

        remaining = [pid for pid in self.player_ids if pid != self.forfeit_player_id]
        self.winner_id = determine_trio_winner(self.active_racks, remaining)

        self.awaiting_confirmation = True

    # NOTE: set_result_direct() moved to TrioScoringService.set_result_direct()
    # NOTE: reset() moved to TrioScoringService.reset()

    def get_current_state(self):
        """Return current state of the trio for UI rendering. Delegates to TrioStateSerializer."""  # noqa: E501
        from .trio_state_serializer import TrioStateSerializer

        return TrioStateSerializer.serialize(self)

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
    created_at = db.Column(db.DateTime, default=utc_now)

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
        self.removed_at = utc_now()

    def __repr__(self):
        return (
            f"<TrioRack {self.rack_number} "
            f"trio={self.trio_match_id} winner={self.winner_id}>"
        )
