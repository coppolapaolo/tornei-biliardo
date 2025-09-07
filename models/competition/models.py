"""
Module: models/competition/models.py
Purpose: Competition domain models (Gara, Inscription)
Data Structures: Gara, Inscription
Dependencies: models.base.db, datetime
"""

from datetime import datetime
from models.base import db
from enum import Enum
from models.status_enum import GaraStatus, MatchStatus
from typing import TYPE_CHECKING

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
    campionato_id = db.Column(
        db.Integer, db.ForeignKey("campionato.id", ondelete="CASCADE"), nullable=True
    )

    # Director FK per standalone competitions
    director_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)

    number = db.Column(db.Integer, nullable=False)  # 1-10
    name = db.Column(db.String(100))
    date = db.Column(db.Date, nullable=False)

    # NUOVI CAMPI
    location = db.Column(db.String(200))  # Luogo della gara
    description = db.Column(db.Text)  # Descrizione opzionale
    rounds_count = db.Column(
        db.Integer, nullable=False, default=3
    )  # Numero di turni per questa gara
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
        db.String(50), nullable=False, default="amalfi"
    )  # amalfi, round_robin, direct_elimination, double_knockout, random
    first_round_policy = db.Column(
        db.String(50), default="random"
    )  # random, rating, classification
    odd_number_policy = db.Column(
        db.String(50), default="bye"
    )  # bye, trio (trio solo per alcune strategie e distanze)
    anti_rematch_enabled = db.Column(
        db.Boolean, default=True
    )  # Evita reincontri tra giocatori
    rating_type = db.Column(
        db.String(20), default="fargo"
    )  # Tipo di rating da usare: fargo, elo

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
                DirectorAssignment.entity_type == 'gara',
                DirectorAssignment.entity_id == self.id
            )
            .all()
        )

    # Property per identificare se è standalone
    @property
    def is_standalone(self):
        """Check if this is a standalone competition."""
        return self.campionato_id is None

    def get_organizer(self):
        """Get the competition organizer (director or campionato owner)."""
        if self.is_standalone:
            return self.director
        if self.campionato and self.campionato.directors:
            return self.campionato.directors[0]
        return None

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
                m.status == MatchStatus.COMPLETED.value for m in current_round_matches
            )
            if all_matches_finished:
                if self.current_round < self.rounds_count:
                    return "round_completed"
                else:
                    return "campionato_completed"
        elif self.status == GaraStatus.INSCRIPTION.value:
            if self.inscription_end and datetime.utcnow() > self.inscription_end:
                return "inscription_closed"
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
        """Valida la coerenza tra strategia di abbinamento e configurazioni."""
        errors = []
        
        # Validazioni per round robin
        if self.matchmaking_strategy == "round_robin":
            if self.first_round_policy != "random":
                errors.append("Round robin supporta solo abbinamento casuale")
            if self.odd_number_policy == "trio":
                errors.append("Round robin non supporta match a tre")
        
        # Validazioni per eliminazione diretta
        elif self.matchmaking_strategy == "direct_elimination":
            if self.odd_number_policy == "trio":
                errors.append("Eliminazione diretta non supporta match a tre")
        
        # Validazioni per strategia casuale
        elif self.matchmaking_strategy == "random":
            if self.first_round_policy != "random":
                errors.append("Strategia casuale usa sempre abbinamento casuale")
        
        # Validazioni per trio matches
        if self.odd_number_policy == "trio":
            if self.distance > 7:
                errors.append("Match a tre supportati solo fino a distanza 7")
            if self.matchmaking_strategy not in ["amalfi", "random"]:
                errors.append(f"Match a tre non supportati con strategia {self.matchmaking_strategy}")
        
        return errors

    def calculate_rounds_for_strategy(self, num_players):
        """Calcola il numero di turni ottimale per la strategia e numero di giocatori."""
        if self.matchmaking_strategy == "round_robin":
            return num_players - 1 if num_players > 1 else 1
        elif self.matchmaking_strategy == "direct_elimination":
            import math
            return math.ceil(math.log2(num_players)) if num_players > 1 else 1
        elif self.matchmaking_strategy == "double_knockout":
            import math
            # Double elimination richiede circa 2 * log2(n) turni
            return 2 * math.ceil(math.log2(num_players)) if num_players > 1 else 1
        else:
            # Per amalfi e random, usa il valore configurato o un default sensato
            return self.rounds_count or min(num_players - 1, 5)

    def get_strategy_constraints(self):
        """Restituisce i vincoli della strategia selezionata."""
        constraints = {
            "round_robin": {
                "first_round_policies": ["random"],
                "odd_policies": ["bye"],
                "fixed_rounds": True,
                "anti_rematch": False,
                "allow_trio": False
            },
            "direct_elimination": {
                "first_round_policies": ["random", "rating", "classification"],
                "odd_policies": ["bye"],
                "fixed_rounds": True,
                "anti_rematch": False,
                "allow_trio": False
            },
            "double_knockout": {
                "first_round_policies": ["random", "rating", "classification"],
                "odd_policies": ["bye"],
                "fixed_rounds": True,
                "anti_rematch": False,
                "allow_trio": False
            },
            "amalfi": {
                "first_round_policies": ["random", "rating", "classification"],
                "odd_policies": ["bye", "bye_with_challenge", "trio"],
                "fixed_rounds": False,
                "anti_rematch": True
            },
            "random": {
                "first_round_policies": ["random"],
                "odd_policies": ["bye", "bye_with_challenge", "trio"],
                "fixed_rounds": False,
                "anti_rematch": True
            }
        }
        return constraints.get(self.matchmaking_strategy, constraints["amalfi"])

    def can_modify_inscription_dates(self):
        """Verifica se si possono modificare le date iscrizioni"""
        # Permetti modifica in setup, inscription, o quando le iscrizioni sono scadute
        # ma la gara non è ancora iniziata
        return self.status in [GaraStatus.SETUP.value, GaraStatus.INSCRIPTION.value]

    def can_be_modified(self):
        """Verifica se la gara può essere modificata"""
        return self.status == GaraStatus.SETUP.value

    def can_be_deleted(self):
        """Verifica se la gara può essere cancellata"""
        inscriptions_list = getattr(self, "inscriptions", []) or []
        return not inscriptions_list and self.status == GaraStatus.SETUP.value

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

    def copy_settings_from(self, source_gara):
        """Copia le impostazioni da un'altra gara"""
        self.discipline = source_gara.discipline
        self.distance = source_gara.distance
        self.best_of = source_gara.best_of
        self.rounds_count = source_gara.rounds_count
        self.min_participants = source_gara.min_participants
        self.max_participants = source_gara.max_participants
        self.entry_fee = source_gara.entry_fee
    
    def get_active_inscriptions_count(self):
        """Conta le iscrizioni attive (non in lista d'attesa e non ritirate)"""
        return len([i for i in self.inscriptions if not i.is_withdrawn and not i.is_waitlist])
    
    def get_waitlist_count(self):
        """Conta i giocatori in lista d'attesa"""
        return len([i for i in self.inscriptions if i.is_waitlist and not i.is_withdrawn])
    
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
    
    # Lista d'attesa
    is_waitlist = db.Column(db.Boolean, default=False, nullable=False)
    waitlist_position = db.Column(db.Integer, nullable=True)

    def __repr__(self):
        return f"<Inscription {self.user_id} -> {self.gara_id}>"
