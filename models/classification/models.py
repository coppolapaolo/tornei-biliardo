"""
Module: models/classification/models.py
Purpose: Classification domain models
(Classification, RoundClassification, PlayerEncounter)
Data Structures: Classification, RoundClassification, PlayerEncounter
Dependencies: models.base.db, datetime
"""
# TODO: questo va rivisto. Manca la classifica di gara e poi possono esserci varie altre classifiche, ad esempio quella di una o piu' challenge in una gara. Una classifica prende una serie di punteggi oppure una classifica precedente e una serie di punteggi e ha una logica di ordinamento e restituisce quell'ordinamento. la classifica delle gare amalfi, ad esempio, prende la classifica dell'ultimo turno e, se ci sono pari merito, prende i risultati dello spot shot rally e ordina i pari merito secondo quei risultati. la classifica delle gare random si comporta allo stesso modo. la classifica dei campionati amalfi prende tutti i match giocati e ordina per (match vinti, differenza rack vinti-persi, spot shot rally vinti). la classifica dei campionati random, invece ordina per (totale rack vinti, spot shot rally vinti). Altri campionati possono dare dei punteggi fissi alle posizioni ottenute nelle classifiche delle singole gare (Es. 1000pt al primo, 800 al secondo, 500 al terzo e quarto, ecc.) e la classifica finale del campionato puo' essere data dalla somma dei punti delle migliori n-1 gare. La struttura di classifica deve permettere di definire tutte queste varianti

from datetime import datetime
from models.base import db, TimestampMixin
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
    total_point_difference = db.Column(db.Integer, default=0)
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


class RoundClassification(db.Model): # TODO: round classification puo' avere diverse logiche di combinare i match di un round. non vale solo per Amalfi, ma per tutte le gare con piu' round. Esistono diversi round classification che implementano diverse logiche di ordinamento. Amalfi, di solito usa (match vint, differenza rack, ordine classifica turno precedente). Random di solito usa (numero rack vinti). Ma potrebbe essere diverso e ce ne potrebbero essere molti altri.
    """
    Dynamic classification after each round for Amalfi algorithm.

    Tracks player standings after each round of play, enabling the Amalfi
    pairing system to create balanced matches based on current performance.
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
    rack_difference = db.Column(db.Integer, default=0)  # rack_vinti - rack_persi
    previous_position = db.Column(db.Integer)  # posizione turno precedente

    # Metadata
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

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

    @staticmethod
    @transactional(domain="classification")
    def calculate_classification_after_round(gara_id, round_number):
        """
        Calculate classification after a specific round.

        This method aggregates match results up to the specified round
        and creates/updates RoundClassification entries for all players.

        For Random strategy: classification is based on total racks won
        For other strategies: classification is based on matches won, then rack difference

        Args:
            gara_id: ID of the gara
            round_number: Round number to calculate classification for

        Returns:
            List of (player_id, stats) tuples sorted by classification
        """
        from models.match.models import Match
        from models.competition.models import Gara

        # Get gara to determine matchmaking strategy
        gara = db.session.get(Gara, gara_id)
        if not gara:
            raise ValueError(f"Gara {gara_id} not found")

        # Get all completed matches up to this round (including bye matches)
        completed_matches = (
            db.session.query(Match)
            .filter(
                Match.gara_id == gara_id,
                Match.round_number <= round_number,
                Match.status == "completed",  # type: ignore[operator]
            )
            .all()
        )

        # Calculate stats per player
        player_stats = {}
        for match in completed_matches:
            # Handle bye matches separately
            if match.is_bye:
                # Initialize bye player if not seen
                if match.player1_id not in player_stats:
                    player_stats[match.player1_id] = {
                        "matches_won": 0,
                        "rack_won": 0,
                        "rack_lost": 0,
                    }
                # Bye player gets automatic win
                player_stats[match.player1_id]["matches_won"] += 1
                player_stats[match.player1_id]["rack_won"] += match.player1_score or 0
                # No rack_lost for bye matches
            else:
                # Handle regular matches
                # Initialize players if not seen
                if match.player1_id not in player_stats:
                    player_stats[match.player1_id] = {
                        "matches_won": 0,
                        "rack_won": 0,
                        "rack_lost": 0,
                    }
                if match.player2_id not in player_stats:
                    player_stats[match.player2_id] = {
                        "matches_won": 0,
                        "rack_won": 0,
                        "rack_lost": 0,
                    }

                # Update stats based on match result
                if match.player1_score > match.player2_score:
                    player_stats[match.player1_id]["matches_won"] += 1
                else:
                    player_stats[match.player2_id]["matches_won"] += 1

                player_stats[match.player1_id]["rack_won"] += match.player1_score
                player_stats[match.player1_id]["rack_lost"] += match.player2_score
                player_stats[match.player2_id]["rack_won"] += match.player2_score
                player_stats[match.player2_id]["rack_lost"] += match.player1_score

        # Calculate rack difference
        for player_id, stats in player_stats.items():
            stats["rack_difference"] = stats["rack_won"] - stats["rack_lost"]

        # Sort players by classification criteria based on strategy
        if gara.matchmaking_strategy == "random":
            # For Random strategy: order by total racks won (descending), then rack difference, then player ID
            sorted_players = sorted(
                player_stats.items(),
                key=lambda x: (
                    -x[1]["rack_won"],  # Primary: total racks won
                    -x[1]["rack_difference"],  # Secondary: rack difference
                    x[0],  # Tertiary: player ID for stability
                ),
            )
        else:
            # For other strategies (Amalfi, etc): order by matches won, then rack difference
            sorted_players = sorted(
                player_stats.items(),
                key=lambda x: (
                    -x[1]["matches_won"],  # Primary: matches won
                    -x[1]["rack_difference"],  # Secondary: rack difference
                    x[0],  # Tertiary: player ID for stability
                ),
            )

        # Create/update round classifications
        for position, (player_id, stats) in enumerate(sorted_players, 1):
            # Get previous position if exists
            previous_classification = (
                db.session.query(RoundClassification)
                .filter_by(
                    gara_id=gara_id,
                    round_number=round_number - 1,
                    user_id=player_id,
                )
                .first()
            )
            previous_position = (
                previous_classification.position if previous_classification else None
            )

            # Create or update classification
            classification = (
                db.session.query(RoundClassification)
                .filter_by(
                    gara_id=gara_id,
                    round_number=round_number,
                    user_id=player_id,
                )
                .first()
            )

            if classification:
                # Update existing
                classification.position = position
                classification.matches_won = stats["matches_won"]
                # For Random strategy, store total racks won in rack_difference field for display
                # For other strategies, store actual rack difference
                if gara.matchmaking_strategy == "random":
                    classification.rack_difference = stats[
                        "rack_won"
                    ]  # Store total racks won
                else:
                    classification.rack_difference = stats[
                        "rack_difference"
                    ]  # Store rack difference
                classification.previous_position = previous_position
            else:
                # Create new
                classification = RoundClassification(
                    gara_id=gara_id,
                    round_number=round_number,
                    user_id=player_id,
                    position=position,
                    matches_won=stats["matches_won"],
                    # For Random strategy, store total racks won in rack_difference field
                    # For other strategies, store actual rack difference
                    rack_difference=(
                        stats["rack_won"]
                        if gara.matchmaking_strategy == "random"
                        else stats["rack_difference"]
                    ),
                    previous_position=previous_position,
                )
                db.session.add(classification)

        # Transaction managed by @transactional decorator
        return sorted_players

    def __repr__(self):
        return (
            f"<RoundClassification {self.user_id} -> {self.position} "
            f"(Round {self.round_number})>"
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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

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

    def __repr__(self):
        return (
            f"<PlayerEncounter {self.player1_id} vs {self.player2_id} "
            f"(Round {self.round_number})>"
        )
