"""
Module: models/competition/models.py
Purpose: Competition domain models (Gara, Inscription)
Data Structures: Gara, Inscription
Dependencies: models.base.db, datetime
"""

from datetime import datetime
from models.base import db, SoftDeleteMixin, utc_now
from enum import Enum
from models.status_enum import GaraStatus, MatchStatus, ProvaDerivedStatus
from models.matchmaking.configuration import (
    MatchmakingStrategy,
    FirstRoundPolicy,
    OddNumberPolicy,
)
from models.status_enum import WithdrawPolicy
from models.competition.constants import (
    DEFAULT_MIN_PARTICIPANTS,
    DEFAULT_ROUNDS_COUNT,
    DEFAULT_ENTRY_FEE,
    DEFAULT_WITHDRAW_POLICY,
)
from typing import TYPE_CHECKING, Optional, List
import json

if TYPE_CHECKING:
    pass


class WaitlistReason(str, Enum):
    """Reason why an inscription is on the waiting list.

    CAPACITY: max_participants exceeded (standard waitlist)
    PARITY: odd_number_policy=NO and player count became odd
    """

    CAPACITY = "capacity"
    PARITY = "parity"


class Gara(SoftDeleteMixin, db.Model):
    """Competition round within a campionato or standalone.

    Supports soft delete via SoftDeleteMixin:
    - deleted_at: datetime when soft deleted
    - is_deleted: property to check if deleted
    - Automatic query filtering via soft_delete_filter
    """

    __tablename__ = "gara"

    id = db.Column(db.Integer, primary_key=True)

    # Soft delete reason (optional)
    deleted_reason = db.Column(db.String(255), nullable=True)

    # FK nullable per supportare standalone competitions
    # RESOLVED: See docs/ARCHITECTURAL_DECISIONS.md ADR-002.
    # Decision: Keep FK in Gara (natural direction, efficient queries).
    campionato_id = db.Column(
        db.Integer, db.ForeignKey("campionato.id", ondelete="CASCADE"),
        nullable=True
    )

    # Director FK per standalone competitions
    director_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)

    # RESOLVED: See docs/ARCHITECTURAL_DECISIONS.md ADR-005.
    # Decision: Keep on Gara, add validation for standalone gare.
    number = db.Column(db.Integer, nullable=False)  # 1-10
    name = db.Column(db.String(100))
    date = db.Column(db.Date, nullable=False)
    time = db.Column(db.Time, nullable=True)  # Ora della gara

    # Location - FK to BilliardHall (nullable for backward compatibility)
    billiard_hall_id = db.Column(
        db.Integer, db.ForeignKey("billiard_hall.id", ondelete="SET NULL"), nullable=True
    )
    # Legacy: string-based location (kept for backward compatibility and display cache)
    location = db.Column(db.String(200))
    # Available tables for this gara - JSON list: '["2", "3", "5"]'
    # If set, overrides venue's tables. If None, uses venue's tables.
    available_tables = db.Column(db.Text, nullable=True)
    description = db.Column(db.Text)  # Descrizione opzionale
    rounds_count = db.Column(
        db.Integer, nullable=False, default=DEFAULT_ROUNDS_COUNT
    )  # Numero di turni per questa gara
    min_participants = db.Column(
        db.Integer, default=DEFAULT_MIN_PARTICIPANTS
    )  # Minimo iscritti
    max_participants = db.Column(db.Integer)  # Massimo iscritti (opzionale)
    entry_fee = db.Column(
        db.Float, default=DEFAULT_ENTRY_FEE
    )  # Quota di partecipazione

    # Game settings
    discipline = db.Column(db.String(50), nullable=False)  # palla 8, 9, 10
    # Distance configuration (use distance_config property for abstraction)
    distance = db.Column(db.Integer, nullable=False)
    is_race_to = db.Column(
        db.Boolean, default=False
    )  # Se True: "al N rack", se False: "esatto numero"

    # Multi-set configuration (Phase 6: Frontend Integration)
    is_multi_set = db.Column(db.Boolean, default=False, nullable=False)
    match_distance = db.Column(db.Integer, nullable=True)  # Number of sets
    is_race_to_sets = db.Column(db.Boolean, default=True, nullable=True)  # Race-to vs exact sets

    # Date iscrizioni
    inscription_start = db.Column(db.DateTime)
    inscription_end = db.Column(db.DateTime)

    # Stato della gara
    status = db.Column(
        db.String(20), default=GaraStatus.SETUP.value
    )  # setup, inscription, playing, completed
    current_round = db.Column(db.Integer, default=0)  # 0=non iniziata, 1,2,3=turni

    withdraw_policy = db.Column(
        db.String(10), nullable=False, default=DEFAULT_WITHDRAW_POLICY
    )

    # Classification system: RACK (rack totali), WINS (vittorie+diff), POSITION (bracket)
    # See docs/CLASSIFICATION_SYSTEM.md for constraints per system
    classification_system = db.Column(
        db.String(10), nullable=False, default="WINS"
    )  # RACK, WINS, POSITION

    # Matchmaking strategy configuration
    matchmaking_strategy = db.Column(
        db.String(50), nullable=False, default=MatchmakingStrategy.AMALFI.value
    )  # amalfi, round_robin, direct_elimination, double_knockout, random
    first_round_policy = db.Column(
        db.String(50), default=FirstRoundPolicy.RANDOM.value
    )  # random, rating, classification
    odd_number_policy = db.Column(
        db.String(50), default=OddNumberPolicy.BYE.value
    )  # bye, trio (trio solo per alcune strategie e distanze)
    anti_rematch_enabled = db.Column(
        db.Boolean, default=True
    )  # Evita reincontri tra giocatori

    # Tiebreaker configuration (spareggio fine gara)
    tiebreaker_enabled = db.Column(
        db.Boolean, default=True
    )  # Se True, spareggio per pari merito nel podio
    tiebreaker_until_position = db.Column(
        db.Integer, default=3
    )  # Spareggio fino a questa posizione (es. 3 = podio)
    tiebreaker_mode = db.Column(
        db.String(20), default="playoff_match"
    )  # "playoff_match" (partita secca) | "challenge" (drill dalla banca dati)
    tiebreaker_challenge_id = db.Column(
        db.Integer, db.ForeignKey("challenge.id", ondelete="SET NULL"), nullable=True
    )  # FK a Challenge se mode = "challenge"

    # Playoff configuration (if this gara is a playoff)
    playoff_config_id = db.Column(
        db.Integer, db.ForeignKey("playoff_configuration.id", ondelete="SET NULL"),
        nullable=True
    )  # If set, this gara is a playoff tournament

    # Relazioni
    inscriptions = db.relationship(
        "Inscription",
        backref="gara",
        lazy=True,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    matches = db.relationship(
        "Match",
        backref="gara",
        lazy=True,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    director = db.relationship(
        "User", foreign_keys=[director_id], backref="standalone_garas"
    )
    tiebreaker_challenge = db.relationship(
        "Challenge", foreign_keys=[tiebreaker_challenge_id]
    )
    billiard_hall = db.relationship(
        "BilliardHall", foreign_keys=[billiard_hall_id]
    )
    playoff_config = db.relationship(
        "PlayoffConfiguration", foreign_keys=[playoff_config_id],
        back_populates="gara"
    )

    @property
    def is_playoff(self) -> bool:
        """Check if this gara is a playoff tournament."""
        return self.playoff_config_id is not None

    # Co-directors relationship (similar to campionati)
    @property
    def directors(self):
        """Get co-directors for this gara."""
        from models.user.models import DirectorAssignment, User

        return (
            db.session.query(User)
            .join(DirectorAssignment, User.id == DirectorAssignment.user_id)
            .filter(
                DirectorAssignment.entity_type == "gara",
                DirectorAssignment.entity_id == self.id,
            )
            .all()
        )

    @property
    def venue(self):
        """Get the associated BilliardHall.

        Prefers FK relationship, falls back to name lookup for legacy data.
        """
        # Prefer FK if set
        if self.billiard_hall:
            return self.billiard_hall
        # Fallback: lookup by name for legacy data
        if not self.location:
            return None
        from models.location.models import BilliardHall
        return BilliardHall.query.filter_by(name=self.location).first()

    @property
    def location_display(self) -> str:
        """Get display name for location.

        Returns billiard_hall.name if FK set, otherwise falls back
        to legacy location string.

        Returns:
            str: Location name for display
        """
        if self.billiard_hall:
            return self.billiard_hall.name
        return self.location or ""

    @staticmethod
    def parse_tables_input(input_str: str) -> List[str]:
        """Parse user input to list of table names.

        Handles:
        - Multiple spaces around commas
        - Alphanumeric table names (letters, numbers, words)
        - Single integer interpreted as count (1-N)

        Examples:
        - "2,3,5" → ["2", "3", "5"]
        - "2, 3, 5" → ["2", "3", "5"]
        - "2,  a,      7  , 1" → ["2", "a", "7", "1"]
        - "Sala A, Sala B" → ["Sala A", "Sala B"]
        - "5" → ["1", "2", "3", "4", "5"]  (single integer = count)
        - "" → []
        """
        if not input_str or not input_str.strip():
            return []

        input_str = input_str.strip()

        # Check if it's a single integer (interpreted as count)
        if input_str.isdigit():
            count = int(input_str)
            if count > 0:
                return [str(i) for i in range(1, count + 1)]
            return []

        # Otherwise, split by comma and strip each element
        tables = [t.strip() for t in input_str.split(",")]
        # Filter out empty strings
        return [t for t in tables if t]

    def get_available_tables(self) -> List[str]:
        """Return available table names for this gara.

        Priority:
        1. gara.available_tables if set (parsed from JSON)
        2. venue.get_table_names() if venue exists
        3. Empty list
        """
        # Priority 1: gara-specific tables
        if self.available_tables:
            try:
                return json.loads(self.available_tables)
            except (json.JSONDecodeError, TypeError):
                return []

        # Priority 2: venue tables
        venue = self.venue
        if venue:
            return venue.get_table_names()

        # Priority 3: no tables
        return []

    def set_available_tables(self, tables: List[str]) -> None:
        """Set available tables from a list.

        Args:
            tables: List of table names, or empty list for None
        """
        if tables:
            self.available_tables = json.dumps(tables)
        else:
            self.available_tables = None

    # Property per identificare se è standalone
    # RESOLVED: See docs/ARCHITECTURAL_DECISIONS.md ADR-002 - keep bidirectional
    @property
    def is_standalone(self):
        """Check if this is a standalone competition."""
        return self.campionato_id is None

    # RESOLVED: See docs/ARCHITECTURAL_DECISIONS.md ADR-002.
    # Decision: Keep bidirectional - Gara has FK, Campionato has property.
    def get_display_name(self):
        """Get display name including campionato/standalone info."""
        if self.is_standalone:
            return f"{self.name} (Standalone)"
        return f"{self.name} - {self.campionato.name}"

    def get_real_status(self):
        """Restituisce lo status reale, considerando anche round e iscrizioni"""
        if self.status == GaraStatus.PLAYING.value:
            matches_list = getattr(self, "matches", []) or []

            # First check: Are ALL matches across ALL rounds completed?
            # This handles cases where current_round wasn't updated properly
            # Note: VALIDATED (bilateral player confirmation) also counts as finished
            if matches_list:
                all_matches_completed = all(
                    m.status in [MatchStatus.COMPLETED.value, MatchStatus.VALIDATED.value]
                    for m in matches_list
                )
                # Check if we have matches for all rounds
                rounds_with_matches = set(
                    m.round_number for m in matches_list if hasattr(m, "round_number")
                )
                all_rounds_have_matches = (
                    len(rounds_with_matches) == self.rounds_count
                    and max(rounds_with_matches) == self.rounds_count
                )

                if all_matches_completed and all_rounds_have_matches:
                    return ProvaDerivedStatus.TOURNAMENT_COMPLETED.value

            # Fallback: Check current round status
            current_round_matches = [
                m
                for m in matches_list
                if hasattr(m, "round_number") and m.round_number == self.current_round
            ]
            # Important: Only consider round completed if there ARE matches
            # in the current round. Empty list means round not started yet.
            # Note: VALIDATED (bilateral player confirmation) also counts as finished
            if current_round_matches:
                all_matches_finished = all(
                    m.status in [MatchStatus.COMPLETED.value, MatchStatus.VALIDATED.value]
                    for m in current_round_matches
                )
                if all_matches_finished:
                    if self.current_round < self.rounds_count:
                        return ProvaDerivedStatus.ROUND_COMPLETED.value
                    else:
                        return ProvaDerivedStatus.TOURNAMENT_COMPLETED.value
        elif self.status == GaraStatus.INSCRIPTION.value:
            if self.inscription_end and utc_now() > self.inscription_end:
                return ProvaDerivedStatus.INSCRIPTION_CLOSED.value
        return self.status

    def get_status_badge_info(self):
        """Restituisce info per badge status nel template"""
        real_status = self.get_real_status()
        return {
            GaraStatus.SETUP.value: {"class": "bg-warning", "text": "Setup"},
            GaraStatus.INSCRIPTION.value: {
                "class": "bg-info",
                "text": "Iscrizioni Aperte",
            },
            "inscription_closed": {
                "class": "bg-secondary",
                "text": "Iscrizioni Chiuse",
            },
            "ready_to_start": {"class": "bg-primary", "text": "Pronta per Iniziare"},
            GaraStatus.PLAYING.value: {"class": "bg-success", "text": "In Corso"},
            GaraStatus.AWAITING_SSR.value: {"class": "bg-warning", "text": "Spareggi"},
            GaraStatus.COMPLETED.value: {"class": "bg-dark", "text": "Completata"},
            "round_completed": {"class": "bg-info", "text": "Turno Completato"},
            "campionato_completed": {"class": "bg-dark", "text": "Gara Completata"},
        }.get(real_status, {"class": "bg-secondary", "text": "Sconosciuto"})

    def can_start_new_round(self):
        """Verifica se si può iniziare un nuovo round"""
        if self.status != GaraStatus.PLAYING.value:
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
        # Must have matches in current round AND all must be finished
        # Note: VALIDATED (bilateral player confirmation) also counts as finished
        return bool(current_round_matches) and all(
            m.status in [MatchStatus.COMPLETED.value, MatchStatus.VALIDATED.value]
            for m in current_round_matches
        )

    def can_inscribe(self):
        """Verifica se si possono fare iscrizioni"""
        if self.status != GaraStatus.INSCRIPTION.value:
            return False
        if self.inscription_end and utc_now() > self.inscription_end:
            return False
        return True

    def is_user_inscribed(self, user_id) -> bool:
        """Verifica se un utente è iscritto"""
        inscriptions_list = getattr(self, "inscriptions", []) or []
        return any(insc.user_id == user_id for insc in inscriptions_list)

    def validate_strategy_configuration(self):
        """Valida coerenza strategia (delegato a StrategyConfiguration).

        Usa models.matchmaking.configuration.StrategyConfiguration
        per validazione centralizzata.
        """
        from models.matchmaking.configuration import StrategyConfiguration

        # Crea config da gara e valida
        config = StrategyConfiguration.from_gara(self)
        num_participants = len(getattr(self, "inscriptions", []) or [])

        # Delega validazione a StrategyConfiguration
        return config.validate(
            num_players=num_participants if num_participants > 0 else None,
            distance=self.distance,
            is_race_to=self.is_race_to,
        )

    def calculate_rounds_for_strategy(self, num_players):
        """Calcola turni ottimali (delegato a configuration module).

        Usa models.matchmaking.configuration.calculate_rounds_for_strategy
        """
        from models.matchmaking.configuration import (
            calculate_rounds_for_strategy,
            MatchmakingStrategy,
        )

        strategy = MatchmakingStrategy(self.matchmaking_strategy)
        return calculate_rounds_for_strategy(strategy, num_players)

    def get_strategy_constraints(self):
        """Vincoli strategia (delegato a STRATEGY_CONSTRAINTS).

        Usa models.matchmaking.configuration.STRATEGY_CONSTRAINTS
        """
        from models.matchmaking.configuration import (
            STRATEGY_CONSTRAINTS,
            MatchmakingStrategy,
        )

        try:
            strategy = MatchmakingStrategy(self.matchmaking_strategy)
            return STRATEGY_CONSTRAINTS.get(
                strategy, STRATEGY_CONSTRAINTS[MatchmakingStrategy.AMALFI]
            )
        except (ValueError, KeyError):
            # Fallback to Amalfi if strategy not found
            return STRATEGY_CONSTRAINTS[MatchmakingStrategy.AMALFI]

    # =========================================================================
    # Strategy Behavior Methods
    # =========================================================================
    # These methods provide access to strategy-specific behaviors defined in
    # models/matchmaking/configuration.py (StrategyBehaviorConfig)

    def get_strategy_behavior(self):
        """Get the StrategyBehaviorConfig for this gara's strategy.

        Returns:
            StrategyBehaviorConfig with all behavioral settings

        Example:
            behavior = gara.get_strategy_behavior()
            if behavior.supports_round_locking:
                # Apply round locking logic
        """
        from models.matchmaking.configuration import (
            get_strategy_behavior,
            MatchmakingStrategy,
            STRATEGY_BEHAVIORS,
        )

        try:
            strategy = MatchmakingStrategy(self.matchmaking_strategy)
            return get_strategy_behavior(strategy)
        except (ValueError, KeyError):
            # Fallback to Amalfi behavior
            return STRATEGY_BEHAVIORS[MatchmakingStrategy.AMALFI]

    def supports_round_locking(self) -> bool:
        """Check if this gara's strategy supports round locking.

        Random strategy: False (all rounds modifiable)
        Other strategies: True (past rounds locked)
        """
        return self.get_strategy_behavior().supports_round_locking

    def get_classification_type(self):
        """Get classification structure type for this strategy.

        Returns:
            ClassificationType.PER_ROUND or ClassificationType.OVERALL
        """
        return self.get_strategy_behavior().classification_type

    def get_classification_criteria(self):
        """Get ranking criteria for this strategy.

        Returns:
            ClassificationCriteria.MATCH_WINS or ClassificationCriteria.RACKS_WON
        """
        return self.get_strategy_behavior().classification_criteria

    def should_update_classification_on_match_complete(self) -> bool:
        """Check if classification should update after each match.

        Random strategy: True (update after each match)
        Other strategies: False (update after round completes)
        """
        from models.matchmaking.configuration import ClassificationUpdateTiming

        timing = self.get_strategy_behavior().classification_update
        return timing == ClassificationUpdateTiming.ON_MATCH_COMPLETE

    def get_default_odd_policy(self):
        """Get default odd number policy based on strategy and distance.

        Random (distance <= 7): TRIO
        Random (distance > 7): BYE_WITH_CHALLENGE
        Other strategies: BYE
        """
        return self.get_strategy_behavior().get_default_odd_policy(self.distance)

    def can_use_trio(self) -> bool:
        """Check if trio matches are allowed for this gara.

        Trio matches only allowed for distances 2-5 (per ADR-005).
        """
        return self.get_strategy_behavior().can_use_trio(self.distance)

    def creates_all_rounds_at_startup(self) -> bool:
        """Check if this strategy creates all rounds at tournament startup.

        Random strategy creates all rounds at once (no progressive round creation).
        Other strategies create rounds one at a time.
        """
        return self.get_strategy_behavior().creates_all_rounds_at_startup

    def can_modify_inscription_dates(self):
        """Verifica se si possono modificare le date iscrizioni"""
        # Permetti modifica in setup, inscription, o quando le iscrizioni sono scadute
        # ma la gara non è ancora iniziata
        return self.status in [GaraStatus.SETUP.value, GaraStatus.INSCRIPTION.value]

    def can_be_modified(self):
        """Verifica se la gara può essere modificata"""
        inscriptions_list = getattr(self, "inscriptions", []) or []
        return not inscriptions_list and self.status == GaraStatus.SETUP.value

    def can_be_deleted(self):
        """Verifica se la gara può essere cancellata"""
        inscriptions_list = getattr(self, "inscriptions", []) or []
        return not inscriptions_list and self.status == GaraStatus.SETUP.value

    def soft_delete(self, reason: str = "") -> None:
        """Override soft_delete to support deleted_reason field.

        Args:
            reason: Optional reason for deletion
        """
        from datetime import datetime
        self.deleted_at = utc_now()
        self.deleted_reason = reason

    def can_cancel_round(self, round_number: Optional[int] = None) -> bool:
        """Verifica se l'avvio di un turno può essere cancellato.

        Args:
            round_number: Numero del turno da verificare. Se None, usa
                current_round.

        Returns:
            bool: True se il turno può essere cancellato, False altrimenti.

        Business Rules:
            - La gara deve essere in stato PLAYING
            - Il turno specificato deve esistere
            - Non devono esserci risultati inseriti (neanche parziali)
            - Tutti i match devono essere in stato PENDING
        """
        if self.status != GaraStatus.PLAYING.value:
            return False

        # Use current_round if round_number not specified
        target_round = round_number if round_number is not None else self.current_round

        # Verifica che non ci siano risultati inseriti nelle partite del turno
        try:
            from models.match.models import Match

            round_matches = Match.query.filter_by(
                gara_id=self.id, round_number=target_round
            ).all()
            if not round_matches:
                return False

            # Controlla che non ci siano risultati inseriti (neanche parziali)
            # Esclude i match bye che sono auto-completati con 3-0
            for match in round_matches:
                if match.is_bye:
                    continue  # Skip bye matches - they're auto-completed

                # Check normal match scores
                if match.player1_score > 0 or match.player2_score > 0:
                    return False

                # Check trio match scores
                if match.is_trio and match.trio_match:
                    trio = match.trio_match
                    if (
                        trio.player1_racks > 0
                        or trio.player2_racks > 0
                        or trio.player3_racks > 0
                        or trio.is_completed
                    ):
                        return False

            return True
        except Exception:
            return False

    @property
    def distance_config(self):
        """Get Distance value object for this gara.

        Returns unified Distance abstraction supporting both single-set
        and multi-set configurations.

        Returns:
            Distance: Immutable distance configuration
        """
        from models.match.distance import Distance

        if not self.is_multi_set:
            # Single-set configuration (backward compatible)
            return Distance(
                racks=self.distance,
                is_race_to_racks=self.is_race_to,
                is_multi_set=False,
                sets=1,
                is_race_to_sets=True
            )
        else:
            # Multi-set configuration (Phase 6: Frontend Integration)
            return Distance(
                racks=self.distance,
                is_race_to_racks=self.is_race_to,
                is_multi_set=True,
                sets=self.match_distance if self.match_distance else 1,
                is_race_to_sets=self.is_race_to_sets if self.is_race_to_sets is not None else True
            )

    def copy_settings_from(self, source_gara):
        """Copia le impostazioni da un'altra gara"""
        self.discipline = source_gara.discipline
        self.distance = source_gara.distance
        self.is_race_to = source_gara.is_race_to
        self.rounds_count = source_gara.rounds_count
        self.min_participants = source_gara.min_participants
        self.max_participants = source_gara.max_participants
        self.entry_fee = source_gara.entry_fee

    def get_active_inscriptions_count(self):
        """Conta le iscrizioni attive (non in lista d'attesa e non ritirate)"""
        return len(
            [i for i in self.inscriptions if not i.is_withdrawn and not i.is_waitlist]
        )

    def get_waitlist_count(self):
        """Conta i giocatori in lista d'attesa"""
        return len(
            [i for i in self.inscriptions if i.is_waitlist and not i.is_withdrawn]
        )

    def get_podium(self):
        """
        Restituisce il podio (top positions) della classifica finale in base a tiebreaker_until_position.

        Returns:
            List[dict]: Lista di dizionari con 'position', 'user', 'username'
                        per i premiati. Lista vuota se la gara
                        non è completata o non ha classifiche.
        """
        if self.status != GaraStatus.COMPLETED.value:
            return []

        try:
            from models.classification.services import RoundClassificationService

            # Use tiebreaker_until_position to define the podium size
            limit = self.tiebreaker_until_position or 3

            standings = RoundClassificationService.get_round_standings(
                self.id, self.rounds_count
            )
            podium = []
            for rc in standings[:limit]:
                podium.append(
                    {
                        "position": rc.position,
                        "user": rc.user,
                        "username": rc.user.username if rc.user else "?",
                    }
                )
            return podium
        except Exception:
            return []

    def is_full(self):
        """Verifica se la gara ha raggiunto il numero massimo di partecipanti"""
        if not self.max_participants:
            return False
        return self.get_active_inscriptions_count() >= self.max_participants

    def has_waitlist(self):
        """Verifica se la gara ha una lista d'attesa attiva"""
        return self.max_participants is not None and self.is_full()

    def __repr__(self):
        if self.is_standalone:
            return f"<Gara Standalone '{self.name}'>"
        return f"<Gara {self.name} (Campionato {self.campionato_id})>"


class Inscription(db.Model):
    """Player registration to a competition round."""

    __tablename__ = "inscription"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    gara_id = db.Column(
        db.Integer, db.ForeignKey("gara.id", ondelete="CASCADE"), nullable=False
    )
    created_at = db.Column(db.DateTime, default=utc_now)
    initial_order = db.Column(db.Integer)  # ordine sorteggio iniziale

    user = db.relationship("User", back_populates="inscriptions")

    is_withdrawn = db.Column(db.Boolean, default=False, nullable=False)
    withdrawn_at = db.Column(db.DateTime, nullable=True)

    # Forfait status (for withdraw policy handling)
    is_forfeit = db.Column(db.Boolean, default=False, nullable=False)
    forfeit_at = db.Column(db.DateTime, nullable=True)

    # Lista d'attesa
    is_waitlist = db.Column(db.Boolean, default=False, nullable=False)
    waitlist_position = db.Column(db.Integer, nullable=True)
    # Reason for waitlist: 'capacity' (max exceeded) or 'parity' (odd count with NO policy)
    waitlist_reason = db.Column(db.String(20), nullable=True)

    def __repr__(self):
        return f"<Inscription {self.user_id} -> {self.gara_id}>"
