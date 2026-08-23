"""
Module: models/playoff/models.py
Purpose: Playoff domain models for campionato playoffs system
Requirements: SPECIFICHE.md - Playoff system with qualification criteria
              and special campionati
Data Structures: PlayoffConfiguration, PlayoffQualification, PlayoffTournament
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, TYPE_CHECKING
from enum import Enum


from ..base import db, BaseModel, utc_now
from ..transaction import transactional
from ..status_enum import Discipline

if TYPE_CHECKING:
    from ..classification.models import Classification


class PlayoffType(Enum):
    """Types of playoff configurations."""

    TOP_N = "top_n"  # Top N players (e.g., top 6)
    ELITE_ACADEMY = "elite_academy"  # Elite and Academy divisions
    CONDITIONAL = "conditional"  # Based on specific criteria
    BOTTOM_EXCLUDE = "bottom_exclude"  # Exclude top players (e.g., 3rd place and below)


class QualificationStatus(Enum):
    """Status of playoff qualification."""

    PENDING = "pending"  # Waiting for player response
    CONFIRMED = "confirmed"  # Player confirmed participation
    DECLINED = "declined"  # Player declined participation
    EXPIRED = "expired"  # Qualification offer expired
    REPLACED = "replaced"  # Replaced by next eligible player


class PlayoffConfiguration(BaseModel):
    """Configuration for campionato playoffs."""

    __tablename__ = "playoff_configuration"

    id = db.Column(db.Integer, primary_key=True)
    campionato_id = db.Column(
        db.Integer, db.ForeignKey("campionato.id", ondelete="CASCADE"), nullable=False
    )

    # Configuration details
    name = db.Column(
        db.String(100), nullable=False
    )  # e.g., "Elite Playoff", "Academy Playoff"
    playoff_type = db.Column(db.Enum(PlayoffType), nullable=False)
    description = db.Column(db.Text, nullable=True)

    # Qualification criteria
    max_participants = db.Column(db.Integer, nullable=False)
    # Minimum provas to qualify
    min_garas_played = db.Column(db.Integer, nullable=True)
    # Simplified position-based criteria (preferred over JSON)
    # e.g. 1 for Elite, 6 for Top 6
    positions_from = db.Column(db.Integer, nullable=True)
    positions_to = db.Column(db.Integer, nullable=True)
    # Legacy JSON criteria for complex cases
    qualification_criteria = db.Column(
        db.Text, nullable=True
    )  # JSON string with criteria (optional)

    # Playoff campionato details
    location = db.Column(db.String(255), nullable=True)
    scheduled_date = db.Column(db.DateTime, nullable=True)
    entry_fee = db.Column(db.Numeric(10, 2), nullable=True)

    # Configuration
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    auto_generate = db.Column(
        db.Boolean, nullable=False, default=True
    )  # Auto-generate at campionato end

    # Response deadline
    response_deadline = db.Column(db.DateTime, nullable=True)

    # Gara parameters (NULL = inherit from campionato's first completed gara)
    discipline = db.Column(db.String(50), nullable=True)
    distance = db.Column(db.Integer, nullable=True)
    rounds_count = db.Column(db.Integer, nullable=True)
    strategy_type = db.Column(db.String(50), nullable=True)
    odd_number_policy = db.Column(db.String(20), nullable=True)

    # Relationships
    campionato = db.relationship("Campionato")
    qualifications = db.relationship(
        "PlayoffQualification",
        back_populates="configuration",
        cascade="all, delete-orphan",
    )
    playoff_campionato = db.relationship(
        "PlayoffTournament", back_populates="configuration", uselist=False
    )
    # The playoff gara (linked from Gara.playoff_config_id)
    gara = db.relationship("Gara", back_populates="playoff_config", uselist=False)

    def has_qualifications(self) -> bool:
        """Check if qualifications have been generated for this config."""
        return (
            PlayoffQualification.query.filter_by(configuration_id=self.id).first()
            is not None
        )

    def get_gara_params(self) -> Dict[str, Any]:
        """Return gara creation parameters, falling back to campionato defaults.

        Explicit values on this config override; NULL fields inherit from
        the first completed gara of the campionato.
        """
        from ..competition.models import Gara
        from ..status_enum import GaraStatus

        # Find first completed gara in campionato for defaults
        default_gara = (
            Gara.query.filter_by(campionato_id=self.campionato_id)
            .filter(Gara.status == GaraStatus.COMPLETED.value)
            .filter(Gara.deleted_at.is_(None))
            .order_by(Gara.number)
            .first()
        )

        params: Dict[str, Any] = {}

        # Resolve each param: explicit override or campionato default
        params["discipline"] = (
            self.discipline
            if self.discipline is not None
            else (
                default_gara.discipline if default_gara else Discipline.NINE_BALL.value
            )
        )
        params["distance"] = (
            self.distance
            if self.distance is not None
            else (default_gara.distance if default_gara else 5)
        )
        params["rounds_count"] = (
            self.rounds_count
            if self.rounds_count is not None
            else (default_gara.rounds_count if default_gara else 1)
        )
        if self.strategy_type is not None:
            params["matchmaking_strategy"] = self.strategy_type
        elif default_gara and default_gara.matchmaking_strategy:
            params["matchmaking_strategy"] = default_gara.matchmaking_strategy
        if self.odd_number_policy is not None:
            params["odd_number_policy"] = self.odd_number_policy
        elif (
            default_gara
            and hasattr(default_gara, "odd_number_policy")
            and default_gara.odd_number_policy
        ):
            params["odd_number_policy"] = default_gara.odd_number_policy

        # Additional fields from config
        if self.location:
            params["location"] = self.location
        elif default_gara and default_gara.location:
            params["location"] = default_gara.location
        if self.entry_fee is not None:
            params["entry_fee"] = float(self.entry_fee)

        return params

    def get_qualification_criteria(self) -> Dict[str, Any]:
        """Parse qualification criteria from JSON."""
        try:
            return json.loads(self.qualification_criteria)
        except (json.JSONDecodeError, TypeError):
            return {}

    def set_qualification_criteria(self, criteria: Dict[str, Any]) -> None:
        """Set qualification criteria as JSON."""
        self.qualification_criteria = json.dumps(criteria)

    def evaluate_qualifications(
        self, posti: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Evaluate which players qualify for this playoff based on criteria.

        `posti` allarga la finestra oltre `max_participants`, e serve alla
        **cascata dei rifiuti** (`SPECIFICHE.md` riga 186: «se un giocatore
        rifiuta, la notifica passa al primo degli esclusi e così via»).

        Sono due domande diverse, e confonderle è costato un posto vuoto in
        finale: «chi entra?» si ferma ai posti disponibili, «chi viene dopo?»
        deve guardare **oltre** quel taglio. Con la sola lista tagliata,
        `PlayoffService.find_replacement_player` cercava un sostituto fra
        giocatori che avevano già tutti una qualificazione — declinante
        compreso — e non lo trovava mai.

        Le bande di ELITE_ACADEMY non si allargano: lì il gruppo è definito da
        una fascia di posizioni, non dai posti, e sconfinare vorrebbe dire
        ripescare un academy dentro l'elite.
        """
        from ..classification.models import Classification

        criteria = self.get_qualification_criteria()
        finestra = self.max_participants if posti is None else posti

        # Get campionato final classification
        classifications = (
            Classification.query.filter_by(campionato_id=self.campionato_id)
            .order_by(Classification.position)
            .all()
        )

        qualified_players = []

        if self.playoff_type == PlayoffType.TOP_N:
            # Top N players — allargato a `finestra` quando si cercano i
            # sostituti, altrimenti la cascata non vedrebbe mai gli esclusi.
            top_n = criteria.get("top_positions", self.max_participants)
            if posti is not None:
                top_n = max(top_n, posti)
            for i, classification in enumerate(classifications[:top_n]):
                if self._meets_minimum_requirements(classification.user_id):
                    qualified_players.append(
                        {
                            "user_id": classification.user_id,
                            "position": classification.position,
                            "qualification_reason": f"Top {top_n} position",
                        }
                    )

        elif self.playoff_type == PlayoffType.ELITE_ACADEMY:
            # Elite: top positions, Academy: next positions
            elite_positions = criteria.get("elite_positions", 6)
            academy_positions = criteria.get("academy_positions", 6)

            if criteria.get("category") == "elite":
                target_classifications = classifications[:elite_positions]
                reason = "Elite qualification"
            else:
                target_classifications = classifications[
                    elite_positions : elite_positions + academy_positions
                ]
                reason = "Academy qualification"

            for classification in target_classifications:
                if self._meets_minimum_requirements(classification.user_id):
                    qualified_players.append(
                        {
                            "user_id": classification.user_id,
                            "position": classification.position,
                            "qualification_reason": reason,
                        }
                    )

        elif self.playoff_type == PlayoffType.BOTTOM_EXCLUDE:
            # Exclude top N, include rest up to max_participants
            exclude_top = criteria.get("exclude_top_positions", 2)
            eligible_classifications = classifications[exclude_top:]

            for classification in eligible_classifications[:finestra]:
                if self._meets_minimum_requirements(classification.user_id):
                    qualified_players.append(
                        {
                            "user_id": classification.user_id,
                            "position": classification.position,
                            "qualification_reason": (
                                f"Position {classification.position} "
                                f"(excluding top {exclude_top})"
                            ),
                        }
                    )

        elif self.playoff_type == PlayoffType.CONDITIONAL:
            # Custom criteria evaluation
            for classification in classifications:
                if self._evaluate_custom_criteria(classification, criteria):
                    qualified_players.append(
                        {
                            "user_id": classification.user_id,
                            "position": classification.position,
                            "qualification_reason": "Met custom criteria",
                        }
                    )

        return qualified_players[:finestra]

    def _meets_minimum_requirements(self, user_id: int) -> bool:
        """Check if user meets minimum requirements for playoff.

        Usa `Classification.gare_played` (popolato da
        `ClassificationService._count_gare_played` che conta le gare con
        almeno un match completed/validated). Filtrare per
        `Gara.status == "completed"` non e' affidabile perche' una gara
        puo' essere di fatto conclusa pur restando in PLAYING finche' il
        director non la chiude formalmente.
        """
        if not self.min_garas_played:
            return True

        from ..classification.models import Classification

        classification = Classification.query.filter_by(
            campionato_id=self.campionato_id, user_id=user_id
        ).first()
        if not classification:
            return False
        return (classification.gare_played or 0) >= self.min_garas_played

    def _evaluate_custom_criteria(
        self, classification: "Classification", criteria: Dict[str, Any]
    ) -> bool:
        """Evaluate custom qualification criteria."""
        # Example custom criteria evaluation
        # This can be extended based on specific requirements

        min_matches_won = criteria.get("min_matches_won")
        if min_matches_won and classification.total_matches_won < min_matches_won:
            return False

        min_point_difference = criteria.get("min_point_difference")
        if (
            min_point_difference
            and classification.total_point_difference < min_point_difference
        ):
            return False

        max_position = criteria.get("max_position")
        if max_position and classification.position > max_position:
            return False

        return True

    @transactional()
    def generate_qualifications(self) -> List["PlayoffQualification"]:
        """Generate playoff qualifications based on criteria."""
        qualified_players = self.evaluate_qualifications()
        qualifications = []

        for player_data in qualified_players:
            # Check if qualification already exists
            existing = PlayoffQualification.query.filter_by(
                configuration_id=self.id, user_id=player_data["user_id"]
            ).first()

            if not existing:
                qualification = PlayoffQualification(
                    configuration_id=self.id,
                    user_id=player_data["user_id"],
                    qualifying_position=player_data["position"],
                    qualification_reason=player_data["qualification_reason"],
                )
                db.session.add(qualification)
                qualifications.append(qualification)

        return qualifications

    def __repr__(self) -> str:
        return f"<PlayoffConfiguration {self.name} for Campionato {self.campionato_id}>"


class PlayoffQualification(BaseModel):
    """Individual player qualification for a playoff."""

    __tablename__ = "playoff_qualification"

    id = db.Column(db.Integer, primary_key=True)
    configuration_id = db.Column(
        db.Integer,
        db.ForeignKey("playoff_configuration.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )

    # Qualification details
    qualifying_position = db.Column(db.Integer, nullable=False)
    qualification_reason = db.Column(db.String(255), nullable=False)

    # Status tracking
    status = db.Column(
        db.Enum(QualificationStatus),
        nullable=False,
        default=QualificationStatus.PENDING,
    )
    # Invitation timing (individual per invitation for batch management)
    # When invitation was sent
    invited_at = db.Column(db.DateTime, nullable=True)
    # Individual deadline for this invitation
    expires_at = db.Column(db.DateTime, nullable=True)
    responded_at = db.Column(db.DateTime, nullable=True)  # When player responded
    # Legacy field (kept for compatibility)
    notified_at = db.Column(db.DateTime, nullable=True)  # Deprecated: use invited_at

    # Replacement tracking
    replaced_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    replacement_position = db.Column(
        db.Integer, nullable=True
    )  # Position in replacement queue

    # Relationships
    configuration = db.relationship(
        "PlayoffConfiguration", back_populates="qualifications"
    )
    user = db.relationship("User", foreign_keys=[user_id])
    replaced_by = db.relationship("User", foreign_keys=[replaced_by_id])

    def confirm_participation(self) -> None:
        """Confirm participation in playoff."""
        if self.status != QualificationStatus.PENDING:
            raise ValueError("Can only confirm pending qualifications")

        self.status = QualificationStatus.CONFIRMED
        self.responded_at = utc_now()

    def decline_participation(self) -> None:
        """Decline participation (solo cambio status).

        La ricerca del sostituto è responsabilità del service layer
        (PlayoffService.find_replacement_player), non del modello: prima qui
        si chiamava self.configuration._find_replacement() protetto da hasattr,
        ma PlayoffConfiguration NON definisce quel metodo → guardia sempre
        False → nessun sostituto veniva mai cercato sul decline.
        """
        if self.status != QualificationStatus.PENDING:
            raise ValueError("Can only decline pending qualifications")

        self.status = QualificationStatus.DECLINED
        self.responded_at = utc_now()

    def expire_qualification(self) -> None:
        """Mark qualification as expired (solo cambio status).

        Come decline_participation, la ricerca del sostituto è del service
        layer (vedi PlayoffService.expire_old_qualifications).
        """
        if self.status != QualificationStatus.PENDING:
            return

        self.status = QualificationStatus.EXPIRED

    def __repr__(self) -> str:
        return (
            f"<PlayoffQualification {self.user_id} -> "
            f"{self.configuration.name}: {self.status.value}>"
        )


class PlayoffTournament(BaseModel):
    """The actual playoff campionato/gara."""

    __tablename__ = "playoff_campionato"

    id = db.Column(db.Integer, primary_key=True)
    configuration_id = db.Column(
        db.Integer,
        db.ForeignKey("playoff_configuration.id", ondelete="CASCADE"),
        nullable=False,
    )
    gara_id = db.Column(
        db.Integer, db.ForeignKey("gara.id"), nullable=True
    )  # The actual playoff gara

    # Campionato details
    name = db.Column(db.String(100), nullable=False)
    status = db.Column(
        db.String(20), nullable=False, default="setup"
    )  # setup, registration, playing, completed

    # Schedule
    registration_start = db.Column(db.DateTime, nullable=True)
    registration_end = db.Column(db.DateTime, nullable=True)
    campionato_date = db.Column(db.DateTime, nullable=True)
    location = db.Column(db.String(255), nullable=True)

    # Configuration
    entry_fee = db.Column(db.Numeric(10, 2), nullable=True)
    max_participants = db.Column(db.Integer, nullable=False)
    confirmed_participants = db.Column(db.Integer, nullable=False, default=0)

    # Results
    completed_at = db.Column(db.DateTime, nullable=True)
    winner_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)

    # Relationships
    configuration = db.relationship(
        "PlayoffConfiguration", back_populates="playoff_campionato"
    )
    gara = db.relationship("Gara")
    winner = db.relationship("User", foreign_keys=[winner_id])

    def start_registration(self) -> None:
        """Mark tournament as in registration phase.

        Note: player inscriptions are handled by PlayoffService.create_playoff_gara(),
        not by this method. This only updates the tournament status.
        """
        if self.status != "setup":
            raise ValueError("Can only start registration from setup status")

        self.status = "registration"
        self.registration_start = utc_now()

    def complete_campionato(self, winner_id: Optional[int] = None) -> None:
        """Mark campionato as completed."""
        self.status = "completed"
        self.completed_at = utc_now()
        if winner_id:
            self.winner_id = winner_id

    def get_qualified_players(self) -> List["PlayoffQualification"]:
        """Get all qualified players for this campionato."""
        confirmed_quals = PlayoffQualification.query.filter_by(
            configuration_id=self.configuration_id,
            status=QualificationStatus.CONFIRMED,
        ).all()
        pending_quals = PlayoffQualification.query.filter_by(
            configuration_id=self.configuration_id,
            status=QualificationStatus.PENDING,
        ).all()
        all_quals = confirmed_quals + pending_quals
        all_quals.sort(key=lambda q: q.qualifying_position)
        return all_quals

    def __repr__(self) -> str:
        return f"<PlayoffTournament {self.name}: {self.status}>"
