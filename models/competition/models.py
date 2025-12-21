"""
Module: models/competition/models.py
Purpose: Competition domain models (Gara, Inscription)
Data Structures: Gara, Inscription
Dependencies: models.base.db, datetime
"""

from datetime import datetime
from models.base import db
from enum import Enum
from models.status_enum import GaraStatus, MatchStatus, ProvaDerivedStatus
from models.matchmaking.configuration import (
    MatchmakingStrategy,
    FirstRoundPolicy,
    OddNumberPolicy,
)
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    pass


class WithdrawPolicy(str, Enum):
    # mantiene negli abbinamenti, assegna vittoria massima agli avversari
    FORFEIT = "Forfeit"
    EXCLUDE = "Exclude"  # default: tratta come X


class Gara(db.Model):
    """Competition round within a campionato or standalone."""

    __tablename__ = "gara"

    id = db.Column(db.Integer, primary_key=True)

    # FK nullable per supportare standalone competitions
    # TODO: è giusto che gara sappia di campionato? oppure sarebbe piu'
    # corretto che fosse modellata con una relazione e fosse campionato a
    # sapere di gara?
    campionato_id = db.Column(
        db.Integer, db.ForeignKey("campionato.id", ondelete="CASCADE"),
        nullable=True
    )

    # Director FK per standalone competitions
    director_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)

    # TODO: number è informazione relativa a Campionato e non a gara
    # e dovrebbe essere modellata dentro campionato
    number = db.Column(db.Integer, nullable=False)  # 1-10
    name = db.Column(db.String(100))
    date = db.Column(db.Date, nullable=False)
    time = db.Column(db.Time, nullable=True)  # Ora della gara

    # NUOVI CAMPI
    location = db.Column(db.String(200))  # Luogo della gara
    description = db.Column(db.Text)  # Descrizione opzionale
    rounds_count = db.Column(
        db.Integer, nullable=False, default=3
    )  # Numero di turni per questa gara
    min_participants = db.Column(db.Integer, default=6)  # Minimo iscritti
    max_participants = db.Column(db.Integer)  # Massimo iscritti (opzionale)
    entry_fee = db.Column(db.Float, default=0.0)  # Quota di partecipazione

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
        db.String(10), nullable=False, default=WithdrawPolicy.EXCLUDE.value
    )

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

    # Property per identificare se è standalone
    # TODO: se la modellazione cambia e la relazione viene spostata in
    # Campionato, forse anche questa non e' piu' una proprieta' di gara,
    # ma un servizio legato al campionato? Qual e' il modo migliore di
    # modellare questa cosa?
    @property
    def is_standalone(self):
        """Check if this is a standalone competition."""
        return self.campionato_id is None

    # TODO: da rivedere se si cambia il modello ed e' Campionato l'unico a
    # sapere di gara
    def get_display_name(self):
        """Get display name including campionato/standalone info."""
        if self.is_standalone:
            return f"{self.name} (Standalone)"
        return f"{self.name} - {self.campionato.name}"

    def get_real_status(self):
        """Restituisce lo status reale, considerando anche round e iscrizioni"""
        if self.status == GaraStatus.PLAYING.value:
            # Se tutti i match del round corrente sono finiti
            matches_list = getattr(self, "matches", []) or []
            current_round_matches = [
                m
                for m in matches_list
                if hasattr(m, "round_number") and m.round_number == self.current_round
            ]
            all_matches_finished = all(
                m.status == MatchStatus.COMPLETED.value
                for m in current_round_matches
            )
            if all_matches_finished:
                if self.current_round < self.rounds_count:
                    return ProvaDerivedStatus.ROUND_COMPLETED.value
                else:
                    return ProvaDerivedStatus.TOURNAMENT_COMPLETED.value
        elif self.status == GaraStatus.INSCRIPTION.value:
            if self.inscription_end and datetime.utcnow() > self.inscription_end:
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
        return all(
            m.status == MatchStatus.COMPLETED.value for m in current_round_matches
        )

    def can_inscribe(self):
        """Verifica se si possono fare iscrizioni"""
        if self.status != GaraStatus.INSCRIPTION.value:
            return False
        if self.inscription_end and datetime.utcnow() > self.inscription_end:
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
            for match in round_matches:
                if (
                    match.player1_score > 0
                    or match.player2_score > 0
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

    def get_winning_score(self):
        """Restituisce il punteggio per vincere.

        DEPRECATED: Use distance_config.get_winning_racks() instead.
        Maintained for backward compatibility.
        """
        return self.distance_config.get_winning_racks()

    def is_match_finished(self, score1, score2):
        """Verifica se una partita è finita.

        DEPRECATED: Use RackScore.is_complete() instead.
        Maintained for backward compatibility.

        Args:
            score1: Player 1 rack count
            score2: Player 2 rack count

        Returns:
            bool: True if match is complete
        """
        from models.match.score import RackScore

        rack_score = RackScore(
            distance=self.distance_config,
            player1_racks=score1,
            player2_racks=score2
        )
        return rack_score.is_complete()

    # TODO: verificare che siano tutte le info e non manchino cose
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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
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

    def __repr__(self):
        return f"<Inscription {self.user_id} -> {self.gara_id}>"
