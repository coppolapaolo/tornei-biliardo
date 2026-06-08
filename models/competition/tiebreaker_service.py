"""
Tiebreaker service for handling end-of-gara ties.

This service detects tied positions in the final classification and manages
the tiebreaker process (playoff match or challenge) based on gara configuration.
"""

from typing import List, Dict, Tuple
from dataclasses import dataclass
from sqlalchemy import func

from models.base import db
from models.match.models import Match
from models.status_enum import MatchStatus
from models.transaction.manager import transactional


@dataclass
class TiedPosition:
    """Represents a tie at a specific position."""

    position: int
    player_ids: List[int]
    matches_won: int
    rack_difference: int


class TiebreakerService:
    """Service for managing end-of-gara tiebreakers."""

    @staticmethod
    def detect_ties(gara_id: int) -> List[TiedPosition]:
        """Detect tied positions in the final classification.

        Returns list of TiedPosition objects for positions that need tiebreakers.
        Only returns ties up to tiebreaker_until_position.

        Args:
            gara_id: ID of the gara to check

        Returns:
            List of TiedPosition objects, sorted by position
        """
        from models.competition.models import Gara
        from models.classification.models import RoundClassification

        gara = db.session.get(Gara, gara_id)
        if not gara:
            raise ValueError(f"Gara {gara_id} not found")

        if not gara.tiebreaker_enabled:
            return []

        # Get final round classification - use max(Match.round_number) to handle
        # Random strategy where all rounds are created at startup
        final_round = (
            db.session.query(func.max(Match.round_number))
            .filter(Match.gara_id == gara_id)
            .scalar()
            or gara.current_round
        )
        if final_round == 0:
            return []

        classifications = (
            RoundClassification.query.filter_by(
                gara_id=gara_id, round_number=final_round
            )
            .order_by(RoundClassification.position)
            .all()
        )

        if not classifications:
            return []

        # Group by (matches_won, rack_difference) to find ties
        groups: Dict[Tuple[int, int], List[int]] = {}
        position_map: Dict[Tuple[int, int], int] = {}

        for c in classifications:
            key = (c.matches_won, c.rack_difference)
            if key not in groups:
                groups[key] = []
                position_map[key] = c.position
            groups[key].append(c.user_id)

        # Find ties within tiebreaker_until_position
        ties = []
        for key, player_ids in groups.items():
            if len(player_ids) > 1:
                position = position_map[key]
                # Only include if any tied position is <= tiebreaker_until_position
                # (`or 3`: guardia NULL coerente con gli altri siti — un record
                # legacy con tiebreaker_until_position=NULL darebbe int <= None)
                if position <= (gara.tiebreaker_until_position or 3):
                    ties.append(
                        TiedPosition(
                            position=position,
                            player_ids=player_ids,
                            matches_won=key[0],
                            rack_difference=key[1],
                        )
                    )

        # Sort by position
        ties.sort(key=lambda t: t.position)
        return ties

    @staticmethod
    def needs_tiebreaker(gara_id: int) -> bool:
        """Check if gara needs any tiebreakers.

        Args:
            gara_id: ID of the gara to check

        Returns:
            True if there are ties that need resolution
        """
        ties = TiebreakerService.detect_ties(gara_id)
        return len(ties) > 0

    @staticmethod
    def get_tiebreaker_config(gara_id: int) -> Dict:
        """Get tiebreaker configuration for a gara.

        Args:
            gara_id: ID of the gara

        Returns:
            Dict with tiebreaker configuration
        """
        from models.competition.models import Gara

        gara = db.session.get(Gara, gara_id)
        if not gara:
            raise ValueError(f"Gara {gara_id} not found")

        config = {
            "enabled": gara.tiebreaker_enabled,
            "until_position": gara.tiebreaker_until_position,
            "mode": gara.tiebreaker_mode,
            "challenge_id": gara.tiebreaker_challenge_id,
            "challenge": None,
        }

        if gara.tiebreaker_challenge:
            config["challenge"] = {
                "id": gara.tiebreaker_challenge.id,
                "description": gara.tiebreaker_challenge.description,
            }

        return config

    @staticmethod
    @transactional(domain="competition")
    def create_playoff_match(
        gara_id: int, player1_id: int, player2_id: int, for_position: int
    ):
        """Create a playoff match for tiebreaker.

        Creates a single-rack match (race to 1) between tied players.

        Args:
            gara_id: ID of the gara
            player1_id: First player ID
            player2_id: Second player ID
            for_position: Position being contested

        Returns:
            Created Match object
        """
        from models.competition.models import Gara
        from models.match.models import Match

        gara = db.session.get(Gara, gara_id)
        if not gara:
            raise ValueError(f"Gara {gara_id} not found")

        # Create playoff match as "extra round"
        # Use round_number = rounds_count + 1 to indicate tiebreaker
        tiebreaker_round = gara.rounds_count + 1

        match = Match(
            gara_id=gara_id,
            round_number=tiebreaker_round,
            player1_id=player1_id,
            player2_id=player2_id,
            is_bye=False,
            is_trio=False,
            status="pending",
            # Tiebreaker is always single rack (race to 1)
            discipline=gara.discipline,
        )

        db.session.add(match)
        return match

    @staticmethod
    @transactional(domain="competition")
    def create_challenge_tiebreaker(
        gara_id: int, player_ids: List[int], for_position: int
    ) -> List:
        """Create challenge attempts for all tied players.

        Each tied player will attempt the configured challenge.
        Winner determined by highest score (or best time, etc).

        Args:
            gara_id: ID of the gara
            player_ids: List of tied player IDs
            for_position: Position being contested

        Returns:
            List of created ChallengeAttempt objects
        """
        from models.competition.models import Gara
        from models.challenge.models import ChallengeAttempt

        gara = db.session.get(Gara, gara_id)
        if not gara:
            raise ValueError(f"Gara {gara_id} not found")

        if not gara.tiebreaker_challenge_id:
            raise ValueError("No challenge configured for tiebreaker")

        attempts = []
        for player_id in player_ids:
            attempt = ChallengeAttempt(
                challenge_id=gara.tiebreaker_challenge_id,
                user_id=player_id,
                gara_id=gara_id,
                round_number=gara.rounds_count + 1,  # Tiebreaker "round"
                completed=False,
            )
            db.session.add(attempt)
            attempts.append(attempt)

        return attempts

    @staticmethod
    def get_tiebreaker_status(gara_id: int) -> Dict:
        """Get current tiebreaker status for a gara.

        Returns comprehensive status including:
        - Whether tiebreakers are needed
        - List of ties requiring resolution
        - Current tiebreaker matches/attempts
        - Resolution status

        Args:
            gara_id: ID of the gara

        Returns:
            Dict with tiebreaker status
        """
        from models.competition.models import Gara
        from models.match.models import Match
        from models.challenge.models import ChallengeAttempt

        gara = db.session.get(Gara, gara_id)
        if not gara:
            raise ValueError(f"Gara {gara_id} not found")

        ties = TiebreakerService.detect_ties(gara_id)
        config = TiebreakerService.get_tiebreaker_config(gara_id)

        # Check for existing tiebreaker matches
        tiebreaker_round = gara.rounds_count + 1
        tiebreaker_matches = Match.query.filter_by(
            gara_id=gara_id, round_number=tiebreaker_round
        ).all()

        # Check for existing tiebreaker challenge attempts
        tiebreaker_attempts = ChallengeAttempt.query.filter_by(
            gara_id=gara_id, round_number=tiebreaker_round
        ).all()

        # Calculate resolution status (VALIDATED also counts as finished)
        all_matches_completed = all(
            MatchStatus.is_finished(m.status) for m in tiebreaker_matches
        )
        all_attempts_completed = all(a.completed for a in tiebreaker_attempts)

        return {
            "needs_tiebreaker": len(ties) > 0,
            "ties": [
                {
                    "position": t.position,
                    "player_ids": t.player_ids,
                    "matches_won": t.matches_won,
                    "rack_difference": t.rack_difference,
                }
                for t in ties
            ],
            "config": config,
            "tiebreaker_matches": [
                {
                    "id": m.id,
                    "player1_id": m.player1_id,
                    "player2_id": m.player2_id,
                    "status": m.status,
                    "winner_id": m.winner_id,
                }
                for m in tiebreaker_matches
            ],
            "tiebreaker_attempts": [
                {
                    "id": a.id,
                    "user_id": a.user_id,
                    "completed": a.completed,
                    "score": a.score,
                }
                for a in tiebreaker_attempts
            ],
            "resolved": (
                (len(ties) == 0)
                or (len(tiebreaker_matches) > 0 and all_matches_completed)
                or (len(tiebreaker_attempts) > 0 and all_attempts_completed)
            ),
        }
