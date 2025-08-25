"""
Module: models/classification/models.py
Purpose: Classification domain models
(Classification, RoundClassification, PlayerEncounter)
Data Structures: Classification, RoundClassification, PlayerEncounter
Dependencies: models.base.db, datetime
"""

from datetime import datetime
from models.base import db
from sqlalchemy.orm import backref


class Classification(db.Model):
    """
    Tournament overall classification tracking.

    Tracks the overall performance of players across all provas in a tournament,
    maintaining total wins, point differences, and final rankings.
    """

    __tablename__ = "classification"

    id = db.Column(db.Integer, primary_key=True)
    tournament_id = db.Column(
        db.Integer, db.ForeignKey("tournament.id", ondelete="CASCADE"), nullable=False
    )
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    position = db.Column(db.Integer)
    total_matches_won = db.Column(db.Integer, default=0)
    total_point_difference = db.Column(db.Integer, default=0)
    provas_played = db.Column(db.Integer, default=0)

    # Relations
    tournament = db.relationship(
        "Tournament",
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
    Dynamic classification after each round for Amalfi algorithm.

    Tracks player standings after each round of play, enabling the Amalfi
    pairing system to create balanced matches based on current performance.
    """

    __tablename__ = "round_classification"

    id = db.Column(db.Integer, primary_key=True)
    prova_id = db.Column(
        db.Integer, db.ForeignKey("prova.id", ondelete="CASCADE"), nullable=False
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
    prova = db.relationship(
        "Prova",
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
            "prova_id", "round_number", "user_id", name="unique_round_classification"
        ),
    )

    @staticmethod
    def calculate_classification_after_round(prova_id, round_number):
        """
        Calculate classification after a specific round.

        This method aggregates match results up to the specified round
        and creates/updates RoundClassification entries for all players.

        Args:
            prova_id: ID of the prova
            round_number: Round number to calculate classification for

        Returns:
            List of (player_id, stats) tuples sorted by classification
        """
        from models.match.models import Match

        # Get all completed matches up to this round
        completed_matches = db.session.query(Match).filter(
            Match.prova_id == prova_id,
            Match.round_number <= round_number,
            Match.status == "completed",  # type: ignore[operator]
            Match.is_bye.is_(False),
        ).all()

        # Calculate stats per player
        player_stats = {}
        for match in completed_matches:
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

        # Sort players by classification criteria
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
            previous_classification = db.session.query(RoundClassification).filter_by(
                prova_id=prova_id,
                round_number=round_number - 1,
                user_id=player_id,
            ).first()
            previous_position = (
                previous_classification.position if previous_classification else None
            )

            # Create or update classification
            classification = db.session.query(RoundClassification).filter_by(
                prova_id=prova_id,
                round_number=round_number,
                user_id=player_id,
            ).first()

            if classification:
                # Update existing
                classification.position = position
                classification.matches_won = stats["matches_won"]
                classification.rack_difference = stats["rack_difference"]
                classification.previous_position = previous_position
            else:
                # Create new
                classification = RoundClassification(
                    prova_id=prova_id,
                    round_number=round_number,
                    user_id=player_id,
                    position=position,
                    matches_won=stats["matches_won"],
                    rack_difference=stats["rack_difference"],
                    previous_position=previous_position,
                )
                db.session.add(classification)

        db.session.commit()
        return sorted_players

    def __repr__(self):
        return (
            f"<RoundClassification {self.user_id} -> {self.position} "
            f"(Round {self.round_number})>"
        )


class PlayerEncounter(db.Model):
    """
    Player encounter tracking for anti-reincontro logic.

    Tracks which players have already faced each other in a prova,
    enabling the Amalfi algorithm to avoid repeat pairings when possible.
    """

    __tablename__ = "player_encounter"

    id = db.Column(db.Integer, primary_key=True)
    prova_id = db.Column(
        db.Integer, db.ForeignKey("prova.id", ondelete="CASCADE"), nullable=False
    )
    player1_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    player2_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    round_number = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relations
    prova = db.relationship(
        "Prova",
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
            "prova_id",
            "player1_id",
            "player2_id",
            name="unique_encounter_per_prova",
        ),
    )

    @staticmethod
    def have_played(prova_id, player1_id, player2_id):
        """
        Check if two players have already played against each other.

        Args:
            prova_id: ID of the prova
            player1_id: ID of first player
            player2_id: ID of second player

        Returns:
            Boolean indicating if players have met
        """
        # Ensure consistent ordering
        p1, p2 = min(player1_id, player2_id), max(player1_id, player2_id)

        encounter = db.session.query(PlayerEncounter).filter_by(
            prova_id=prova_id, player1_id=p1, player2_id=p2
        ).first()

        return encounter is not None

    @staticmethod
    def record_encounter(prova_id, player1_id, player2_id, round_number):
        """
        Record that two players have played against each other.

        Args:
            prova_id: ID of the prova
            player1_id: ID of first player
            player2_id: ID of second player
            round_number: Round when they played

        Returns:
            Created PlayerEncounter instance
        """
        # Ensure consistent ordering
        p1, p2 = min(player1_id, player2_id), max(player1_id, player2_id)

        encounter = PlayerEncounter(
            prova_id=prova_id,
            player1_id=p1,
            player2_id=p2,
            round_number=round_number,
        )
        db.session.add(encounter)
        db.session.commit()
        return encounter

    def __repr__(self):
        return (
            f"<PlayerEncounter {self.player1_id} vs {self.player2_id} "
            f"(Round {self.round_number})>"
        )
