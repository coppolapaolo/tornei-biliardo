"""
Module: models/classification/models.py
Purpose: Classification domain models
(Classification, RoundClassification, GaraClassification, PlayerEncounter)
Data Structures: Classification, RoundClassification, GaraClassification, PlayerEncounter
Dependencies: models.base.db, datetime

Phase 5 Refactor Notes:
- GaraClassification added for final gara rankings
- Strategy pattern implemented in strategies/ subdirectory
- StrategyBasedClassificationService is the new recommended API
- Legacy static methods preserved for backward compatibility
"""

from datetime import datetime
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
    rack_difference = db.Column(db.Integer, default=0)  # rack_vinti - rack_persi
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

    @staticmethod
    @transactional(domain="classification")
    def calculate_classification_after_round(gara_id, round_number):
        """
        Calculate classification after a specific round.

        .. deprecated::
            Use StrategyBasedClassificationService.calculate_round_classification()
            instead. This method is preserved for backward compatibility.

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

        # Get all finished matches up to this round (including bye matches)
        # Include both 'completed' (admin) and 'validated' (bilateral player confirmation)
        completed_matches = (
            db.session.query(Match)
            .filter(
                Match.gara_id == gara_id,
                Match.round_number <= round_number,
                Match.status.in_(["completed", "validated"]),  # type: ignore[union-attr]
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
            elif match.is_trio and match.trio_match:
                # Handle trio matches using round-robin format (ADR-005)
                # Bonus racks added to equalize with normal matches
                trio = match.trio_match
                player_ids = [trio.player1_id, trio.player2_id, trio.player3_id]
                racks = [trio.player1_racks, trio.player2_racks, trio.player3_racks]

                # Calculate bonus racks (1 if distance is odd, 0 otherwise)
                distance = gara.distance
                bonus_racks = distance % 2  # 1 for distance 3,5; 0 for distance 2,4

                # Initialize all three players if not seen
                for pid in player_ids:
                    if pid and pid not in player_stats:
                        player_stats[pid] = {
                            "matches_won": 0,
                            "rack_won": 0,
                            "rack_lost": 0,
                        }

                # Process each player
                winner_id = match.winner_id
                for i, pid in enumerate(player_ids):
                    if not pid:
                        continue

                    player_racks = racks[i]
                    # Opponent racks = sum of other two players' racks
                    opponent_racks = sum(r for j, r in enumerate(racks) if j != i)

                    # Add bonus racks to each player (equalization)
                    player_stats[pid]["rack_won"] += player_racks + bonus_racks
                    player_stats[pid]["rack_lost"] += opponent_racks

                    # Winner exists: winner gets match_won
                    # No winner (tie): no one gets match_won
                    if winner_id and pid == winner_id:
                        player_stats[pid]["matches_won"] += 1
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
                # FIX: Handle ties correctly - neither player wins
                if match.player1_score > match.player2_score:
                    player_stats[match.player1_id]["matches_won"] += 1
                elif match.player2_score > match.player1_score:
                    player_stats[match.player2_id]["matches_won"] += 1
                # else: tie - neither player gets a win

                # Calculate rack stats
                # FIX: Handle multi-set matches by summing racks from all sets
                if match.is_multi_set:
                    # Multi-set: player1_score/player2_score are SETS won, not racks
                    # We need to sum racks from all sets
                    for set_obj in match.sets:
                        player_stats[match.player1_id]["rack_won"] += set_obj.player1_racks
                        player_stats[match.player1_id]["rack_lost"] += set_obj.player2_racks
                        player_stats[match.player2_id]["rack_won"] += set_obj.player2_racks
                        player_stats[match.player2_id]["rack_lost"] += set_obj.player1_racks
                else:
                    # Single-set: player1_score/player2_score are racks won
                    player_stats[match.player1_id]["rack_won"] += match.player1_score
                    player_stats[match.player1_id]["rack_lost"] += match.player2_score
                    player_stats[match.player2_id]["rack_won"] += match.player2_score
                    player_stats[match.player2_id]["rack_lost"] += match.player1_score

        # Calculate rack difference
        for player_id, stats in player_stats.items():
            stats["rack_difference"] = stats["rack_won"] - stats["rack_lost"]

        # Load SSR scores from GaraClassification if available (for tiebreaking)
        ssr_scores: dict[int, int] = {}
        if gara.matchmaking_strategy == "random":
            existing_gara_class = (
                db.session.query(GaraClassification)
                .filter_by(gara_id=gara_id)
                .all()
            )
            for gc in existing_gara_class:
                if gc.spot_shot_wins is not None:
                    ssr_scores[gc.user_id] = gc.spot_shot_wins

        # Sort players by classification criteria based on strategy
        if gara.matchmaking_strategy == "random":
            # For Random strategy: order by total racks won, then SSR score, then rack difference
            # SSR score of -1 means not entered (sorts last among same racks)
            sorted_players = sorted(
                player_stats.items(),
                key=lambda x: (
                    -x[1]["rack_won"],  # Primary: total racks won
                    -ssr_scores.get(x[0], -1),  # Secondary: SSR score (tiebreaker)
                    -x[1]["rack_difference"],  # Tertiary: rack difference
                    x[0],  # Quaternary: player ID for stability
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
    tied_with_player_ids = db.Column(db.JSON, nullable=True)  # IDs of originally tied players
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
        return f"<GaraClassification {self.user_id} -> {self.position} (Gara {self.gara_id})>"


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
    def delete_encounter(gara_id: int, player1_id: int, player2_id: int) -> bool:
        """
        Delete the encounter record between two players.

        Used when a match is reset to clear stale anti-rematch data.

        Args:
            gara_id: ID of the gara
            player1_id: ID of first player
            player2_id: ID of second player

        Returns:
            True if deleted, False if not found
        """
        # Ensure consistent ordering
        p1, p2 = min(player1_id, player2_id), max(player1_id, player2_id)

        deleted = (
            db.session.query(PlayerEncounter)
            .filter_by(gara_id=gara_id, player1_id=p1, player2_id=p2)
            .delete()
        )

        return deleted > 0

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
