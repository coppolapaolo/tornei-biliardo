"""
Module: models/classification/models.py
Purpose: Classification domain models
(Classification, RoundClassification, GaraClassification, PlayerEncounter)
Data Structures:
    Classification, RoundClassification, GaraClassification, PlayerEncounter
Dependencies: models.base.db, datetime

Phase 5 Refactor Notes:
- GaraClassification added for final gara rankings
- Strategy pattern implemented in strategies/ subdirectory
- StrategyBasedClassificationService is the new recommended API
- Legacy static methods preserved for backward compatibility
"""

from models.base import db, TimestampMixin, utc_now
from sqlalchemy.orm import backref
from models.transaction.manager import transactional


class Classification(db.Model, TimestampMixin):
    """
    Campionato overall classification tracking.

    Tracks the overall performance of players across all provas in a campionato,
    maintaining total wins, point differences, and final rankings.
    """

    __tablename__ = "classification"

    id = db.Column(db.Integer, primary_key=True)
    campionato_id = db.Column(
        db.Integer, db.ForeignKey("campionato.id", ondelete="CASCADE"), nullable=False
    )
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    position = db.Column(db.Integer)
    total_matches_won = db.Column(db.Integer, default=0)
    total_racks_won = db.Column(db.Integer, default=0)  # For Random strategy sort key
    total_point_difference = db.Column(db.Integer, default=0)  # = rack_difference
    gare_played = db.Column(db.Integer, default=0)

    # Relations
    campionato = db.relationship(
        "Campionato",
        backref=backref(
            "classifications",
            cascade="all, delete-orphan",
            passive_deletes=True,
        ),
    )
    user = db.relationship("User", back_populates="classifications")

    def __repr__(self):
        return f"<Classification {self.user_id} -> {self.position}>"


class RoundClassification(db.Model):
    """
    Dynamic classification after each round.

    Tracks player standings after each round of play, enabling pairing
    systems (Amalfi, Random, etc.) to create balanced matches based on
    current performance.

    Note: Different classification strategies are implemented in
    models/classification/strategies/. Use StrategyBasedClassificationService
    for new code instead of the static method on this class.
    """

    __tablename__ = "round_classification"

    id = db.Column(db.Integer, primary_key=True)
    gara_id = db.Column(
        db.Integer, db.ForeignKey("gara.id", ondelete="CASCADE"), nullable=False
    )
    round_number = db.Column(db.Integer, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    # Classification data
    position = db.Column(db.Integer, nullable=False)
    matches_won = db.Column(db.Integer, default=0)
    # SEMPRE la differenza vera (rack vinti - rack persi), in ogni gara.
    rack_difference = db.Column(db.Integer, default=0)
    # SEMPRE il totale dei rack vinti. È il criterio di classifica delle gare
    # RACK, che prima veniva stipato dentro `rack_difference` facendone cambiare
    # significato a seconda di `gara.classification_system` — un'ambiguità che è
    # costata bug ogni volta che si aggiungeva un punto di scrittura.
    # NULL solo sulle righe scritte prima della separazione (vedi migration
    # 20260728): usare `ranking_rack_value`, che gestisce il fallback.
    racks_won = db.Column(db.Integer)
    previous_position = db.Column(db.Integer)  # posizione turno precedente

    # Metadata
    created_at = db.Column(db.DateTime, default=utc_now)

    # Relations
    gara = db.relationship(
        "Gara",
        backref=backref(
            "round_classifications",
            cascade="all, delete-orphan",
            passive_deletes=True,
        ),
    )
    user = db.relationship("User", back_populates="round_classifications")

    # Constraint: one entry per player per round
    __table_args__ = (
        db.UniqueConstraint(
            "gara_id", "round_number", "user_id", name="unique_round_classification"
        ),
    )

    @property
    def is_rack_ranking(self) -> bool:
        """True se la gara classifica per rack totali invece che per vittorie."""
        gara = self.gara
        if gara is None:
            return False
        return (gara.classification_system or "WINS").upper() == "RACK"

    @property
    def ranking_rack_value(self) -> int:
        """Il numero di rack da mostrare in classifica per questa gara.

        Totale rack nelle gare RACK, differenza altrove. Unico punto in cui la
        scelta dipende dalla configurazione: le due colonne, prese da sole,
        hanno un significato fisso.

        Fallback per le righe pre-separazione, dove `racks_won` è NULL e il
        totale si trovava dentro `rack_difference`.
        """
        if not self.is_rack_ranking:
            return self.rack_difference or 0
        if self.racks_won is not None:
            return self.racks_won
        return self.rack_difference or 0

    @staticmethod
    def calculate_classification_after_round(gara_id, round_number):
        """
        Calculate classification after a specific round.

        .. deprecated::
            Adattatore di compatibilità: l'implementazione è una sola, in
            `StrategyBasedClassificationService.calculate_round_classification`.
            Il codice nuovo usi direttamente quel servizio.

        Questo metodo è stato per anni la seconda implementazione parallela del
        calcolo, e la divergenza costava bug: B14 (semantica di
        `rack_difference` nelle gare RACK) e il tiebreak SSR vivevano solo qui,
        il rispetto di ADR-027 sulla distanza dei trii e la gestione del
        walkover trio solo nell'altra. Ora entrambe le porte d'ingresso
        chiamano lo stesso codice — l'equivalenza è fissata da
        `tests/new/unit/test_classification_calculators_equivalence.py`.

        Non è `@transactional`: lo è già il servizio sottostante, e annidare i
        decoratori provoca rollback (vedi CLAUDE.md).

        Args:
            gara_id: ID of the gara
            round_number: Round number to calculate classification for

        Returns:
            List of (player_id, stats) tuples sorted by classification.
            `rack_difference` è sempre la differenza vera (vinti - persi),
            anche nelle gare RACK: la conversione B14 riguarda solo il valore
            persistito in colonna.
        """
        from models.classification.gara_classification import (
            StrategyBasedClassificationService,
        )

        result = StrategyBasedClassificationService().calculate_round_classification(
            gara_id, round_number
        )

        return [
            (
                entry.player_id,
                {
                    "matches_won": entry.score.matches_won,
                    "rack_won": entry.score.racks_won,
                    "rack_lost": entry.score.racks_lost,
                    "rack_difference": entry.score.rack_difference,
                },
            )
            for entry in result.entries
        ]

    def __repr__(self):
        return (
            f"<RoundClassification {self.user_id} -> {self.position} "
            f"(Round {self.round_number})>"
        )


class GaraClassification(db.Model, TimestampMixin):
    """
    Final gara classification.

    Tracks the final standings of players in a gara after all rounds
    are completed, including tiebreaker resolution. This is the official
    result used for:
    - Prize positions
    - Campionato points (if part of a campionato)
    - Historical records
    """

    __tablename__ = "gara_classification"

    id = db.Column(db.Integer, primary_key=True)
    gara_id = db.Column(
        db.Integer, db.ForeignKey("gara.id", ondelete="CASCADE"), nullable=False
    )
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    # Final position (1-based)
    position = db.Column(db.Integer, nullable=False)

    # Statistics
    matches_won = db.Column(db.Integer, default=0)
    matches_lost = db.Column(db.Integer, default=0)
    racks_won = db.Column(db.Integer, default=0)
    racks_lost = db.Column(db.Integer, default=0)
    rack_difference = db.Column(db.Integer, default=0)

    # Tiebreaker resolution
    tied_with_player_ids = db.Column(
        db.JSON, nullable=True
    )  # IDs of originally tied players
    tiebreaker_resolved = db.Column(db.Boolean, default=True)
    spot_shot_wins = db.Column(db.Integer, default=0)

    # Points for campionato (if applicable)
    campionato_points = db.Column(db.Integer, default=0)

    # Relations
    gara = db.relationship(
        "Gara",
        backref=backref(
            "final_classifications",
            cascade="all, delete-orphan",
            passive_deletes=True,
        ),
    )
    user = db.relationship("User", back_populates="gara_classifications")

    # Constraint: one entry per player per gara
    __table_args__ = (
        db.UniqueConstraint("gara_id", "user_id", name="unique_gara_classification"),
    )

    def __repr__(self):
        return (
            f"<GaraClassification {self.user_id} -> {self.position} "
            f"(Gara {self.gara_id})>"
        )


class PlayerEncounter(db.Model):
    """
    Player encounter tracking for anti-reincontro logic.

    Tracks which players have already faced each other in a gara,
    enabling the Pairing algorithm to avoid repeat pairings when possible.
    Do not use if pairing algorithm allows to rematch
    """

    __tablename__ = "player_encounter"

    id = db.Column(db.Integer, primary_key=True)
    gara_id = db.Column(
        db.Integer, db.ForeignKey("gara.id", ondelete="CASCADE"), nullable=False
    )
    player1_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    player2_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    round_number = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=utc_now)

    # Relations
    gara = db.relationship(
        "Gara",
        backref=backref(
            "player_encounters",
            cascade="all, delete-orphan",
            passive_deletes=True,
        ),
    )
    player1 = db.relationship(
        "User", foreign_keys=[player1_id], back_populates="player1_encounters"
    )
    player2 = db.relationship(
        "User", foreign_keys=[player2_id], back_populates="player2_encounters"
    )
    # Constraint: ensure player1_id < player2_id for consistency
    __table_args__ = (
        db.CheckConstraint("player1_id < player2_id", name="ordered_players"),
        db.UniqueConstraint(
            "gara_id",
            "player1_id",
            "player2_id",
            name="unique_encounter_per_gara",
        ),
    )

    @staticmethod
    def have_played(gara_id, player1_id, player2_id):
        """
        Check if two players have already played against each other.

        Args:
            gara_id: ID of the gara
            player1_id: ID of first player
            player2_id: ID of second player

        Returns:
            Boolean indicating if players have met
        """
        # Ensure consistent ordering
        p1, p2 = min(player1_id, player2_id), max(player1_id, player2_id)

        encounter = (
            db.session.query(PlayerEncounter)
            .filter_by(gara_id=gara_id, player1_id=p1, player2_id=p2)
            .first()
        )

        return encounter is not None

    @staticmethod
    @transactional(domain="classification")
    def record_encounter(gara_id, player1_id, player2_id, round_number):
        """
        Record that two players have played against each other.

        Args:
            gara_id: ID of the gara
            player1_id: ID of first player
            player2_id: ID of second player
            round_number: Round when they played

        Returns:
            Created or existing PlayerEncounter instance
        """
        # Ensure consistent ordering
        p1, p2 = min(player1_id, player2_id), max(player1_id, player2_id)

        # Check if encounter already exists
        existing = (
            db.session.query(PlayerEncounter)
            .filter_by(gara_id=gara_id, player1_id=p1, player2_id=p2)
            .first()
        )

        if existing:
            return existing

        encounter = PlayerEncounter(
            gara_id=gara_id,
            player1_id=p1,
            player2_id=p2,
            round_number=round_number,
        )
        db.session.add(encounter)
        # Transaction managed by @transactional decorator
        return encounter

    @staticmethod
    @transactional(domain="classification")
    def delete_round_encounters(gara_id: int, round_number: int) -> int:
        """
        Delete all encounter records for a specific round.

        Used when a round is cancelled to clear stale anti-rematch data.

        Args:
            gara_id: ID of the gara
            round_number: Round number to delete encounters for

        Returns:
            Number of encounters deleted
        """
        deleted = (
            db.session.query(PlayerEncounter)
            .filter_by(gara_id=gara_id, round_number=round_number)
            .delete()
        )

        return deleted

    def __repr__(self):
        return (
            f"<PlayerEncounter {self.player1_id} vs {self.player2_id} "
            f"(Round {self.round_number})>"
        )
