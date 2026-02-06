"""
Module: models/tiebreaker/services.py
Purpose: Tiebreaker domain services for business logic
Requirements: SPECIFICHE.md - Tiebreaker system management
"""

from __future__ import annotations

from typing import Dict, Any, Optional, cast
from datetime import datetime

from ..base import db, utc_now
from ..transaction.manager import transactional
from .models import (
    Tiebreaker,
    SpotShot,
    RallyAttempt,
    PlayoffMatch,
    TiebreakerConfiguration,
    TiebreakerType,
    TiebreakerStatus,
    SpotShotResult,
)


class TiebreakerService:
    """Service for managing tiebreaker situations and resolution."""

    @staticmethod
    @transactional(domain="tiebreaker")
    def create_spot_shot_tiebreaker(
        match_id: int,
        player1_id: int,
        player2_id: int,
        campionato_id: Optional[int] = None,
        gara_id: Optional[int] = None,
        configuration: Optional[Dict[str, Any]] = None,
    ) -> Tiebreaker:
        """Create a spot shot tiebreaker for tied matches."""

        # Default configuration for spot shots
        default_config = {
            "max_rounds": 5,  # Maximum rounds before sudden death
            "sudden_death_after": 5,  # Switch to sudden death after tied rounds
            "ball_type": "8_ball",  # or "9_ball"
        }

        if configuration:
            default_config.update(configuration)

        tiebreaker = Tiebreaker(
            match_id=match_id,
            campionato_id=campionato_id,
            gara_id=gara_id,
            tiebreaker_type=TiebreakerType.SPOT_SHOT.value,
            player1_id=player1_id,
            player2_id=player2_id,
            configuration=default_config,
        )

        db.session.add(tiebreaker)
        return tiebreaker

    @staticmethod
    @transactional(domain="tiebreaker")
    def create_rally_tiebreaker(
        match_id: int,
        player1_id: int,
        player2_id: int,
        campionato_id: Optional[int] = None,
        gara_id: Optional[int] = None,
        target_score: int = 15,
    ) -> Tiebreaker:
        """Create a rally tiebreaker for straight pool ties."""

        configuration = {
            "target_score": target_score,
            "max_attempts_per_player": 3,
            "discipline": "straight_pool",
        }

        tiebreaker = Tiebreaker(
            match_id=match_id,
            campionato_id=campionato_id,
            gara_id=gara_id,
            tiebreaker_type=TiebreakerType.RALLY.value,
            player1_id=player1_id,
            player2_id=player2_id,
            configuration=configuration,
        )

        db.session.add(tiebreaker)
        return tiebreaker

    @staticmethod
    @transactional(domain="tiebreaker")
    def create_playoff_tiebreaker(
        match_id: int,
        player1_id: int,
        player2_id: int,
        campionato_id: Optional[int] = None,
        gara_id: Optional[int] = None,
        best_of: int = 3,
    ) -> Tiebreaker:
        """Create a playoff match tiebreaker for campionato position ties."""

        configuration = {
            "best_of": best_of,
            "match_distance": 3,  # Race to 3
            "discipline": "palla_8",
        }

        tiebreaker = Tiebreaker(
            match_id=match_id,
            campionato_id=campionato_id,
            gara_id=gara_id,
            tiebreaker_type=TiebreakerType.PLAYOFF_MATCH.value,
            player1_id=player1_id,
            player2_id=player2_id,
            configuration=configuration,
        )

        db.session.add(tiebreaker)
        return tiebreaker

    @staticmethod
    @transactional(domain="tiebreaker")
    def record_spot_shot(
        tiebreaker_id: int,
        player_id: int,
        round_number: int,
        order_in_round: int,
        result: SpotShotResult,
        notes: Optional[str] = None,
    ) -> SpotShot:
        """Record a spot shot attempt."""

        tiebreaker = db.session.get(Tiebreaker, tiebreaker_id)
        if tiebreaker is None:
            from flask import abort

            abort(404)

        if str(tiebreaker.status) != TiebreakerStatus.IN_PROGRESS.value:
            raise ValueError("Tiebreaker must be in progress to record shots")

        if player_id not in [
            cast(int, tiebreaker.player1_id),
            cast(int, tiebreaker.player2_id),
        ]:
            raise ValueError("Player must be one of the tiebreaker participants")

        spot_shot = SpotShot(
            tiebreaker_id=tiebreaker_id,
            player_id=player_id,
            round_number=round_number,
            order_in_round=order_in_round,
            result=result.value,
            notes=notes,
        )

        db.session.add(spot_shot)

        # Check if tiebreaker is complete
        TiebreakerService._check_spot_shot_completion(tiebreaker)

        return spot_shot

    @staticmethod
    @transactional(domain="tiebreaker")
    def record_rally_attempt(
        tiebreaker_id: int,
        player_id: int,
        points_scored: int,
        balls_pocketed: int,
        ended_rally: bool = False,
        notes: Optional[str] = None,
    ) -> RallyAttempt:
        """Record a rally attempt."""

        tiebreaker = db.session.get(Tiebreaker, tiebreaker_id)
        if tiebreaker is None:
            from flask import abort

            abort(404)

        if str(tiebreaker.status) != TiebreakerStatus.IN_PROGRESS.value:
            raise ValueError("Tiebreaker must be in progress to record attempts")

        # Get sequence number
        sequence_number = len(tiebreaker.rally_attempts) + 1

        rally_attempt = RallyAttempt(
            tiebreaker_id=tiebreaker_id,
            player_id=player_id,
            sequence_number=sequence_number,
            points_scored=points_scored,
            balls_pocketed=balls_pocketed,
            was_successful=bool(points_scored > 0),
            ended_rally=ended_rally,
            notes=notes,
            completed_at=utc_now(),
        )

        db.session.add(rally_attempt)

        # Check if tiebreaker is complete
        TiebreakerService._check_rally_completion(tiebreaker)

        return rally_attempt

    @staticmethod
    @transactional(domain="tiebreaker")
    def create_playoff_match(
        tiebreaker_id: int,
        match_number: int,
        distance: int = 3,
        discipline: str = "palla_8",
    ) -> PlayoffMatch:
        """Create a playoff match within a tiebreaker."""

        tiebreaker = db.session.get(Tiebreaker, tiebreaker_id)
        if tiebreaker is None:
            from flask import abort

            abort(404)

        playoff_match = PlayoffMatch(
            tiebreaker_id=tiebreaker_id,
            match_number=match_number,
            player1_id=tiebreaker.player1_id,
            player2_id=tiebreaker.player2_id,
            distance=distance,
            discipline=discipline,
        )

        db.session.add(playoff_match)
        return playoff_match

    @staticmethod
    @transactional(domain="tiebreaker")
    def complete_playoff_match(
        playoff_match_id: int, winner_id: int, p1_score: int, p2_score: int
    ) -> PlayoffMatch:
        """Complete a playoff match and check tiebreaker status."""

        playoff_match = db.session.get(PlayoffMatch, playoff_match_id)
        if playoff_match is None:
            from flask import abort

            abort(404)
        playoff_match.complete_match(winner_id, p1_score, p2_score)

        # Check if entire tiebreaker is complete
        TiebreakerService._check_playoff_completion(playoff_match.tiebreaker)

        return playoff_match

    @staticmethod
    def get_tiebreaker_status(tiebreaker_id: int) -> Dict[str, Any]:
        """Get comprehensive status of a tiebreaker."""

        tiebreaker = db.session.get(Tiebreaker, tiebreaker_id)
        if tiebreaker is None:
            from flask import abort

            abort(404)
        score_summary = tiebreaker.get_score_summary()

        status = {
            "id": tiebreaker.id,
            "type": tiebreaker.tiebreaker_type,
            "status": tiebreaker.status,
            "players": {
                "player1": {
                    "id": tiebreaker.player1_id,
                    "username": tiebreaker.player1.username,
                    "score": score_summary.get("player1_score", 0),
                },
                "player2": {
                    "id": tiebreaker.player2_id,
                    "username": tiebreaker.player2.username,
                    "score": score_summary.get("player2_score", 0),
                },
            },
            "winner_id": tiebreaker.winner_id,
            "created_at": tiebreaker.created_at,
            "started_at": tiebreaker.started_at,
            "completed_at": tiebreaker.completed_at,
            "configuration": tiebreaker.configuration,
        }

        # Add type-specific details
        if str(tiebreaker.tiebreaker_type) == TiebreakerType.SPOT_SHOT.value:
            status["spot_shots"] = [
                {
                    "round": shot.round_number,
                    "player_id": shot.player_id,
                    "order": shot.order_in_round,
                    "result": shot.result,
                    "attempted_at": shot.attempted_at,
                }
                for shot in tiebreaker.spot_shots
            ]
        elif str(tiebreaker.tiebreaker_type) == TiebreakerType.RALLY.value:
            status["rally_attempts"] = [
                {
                    "sequence": attempt.sequence_number,
                    "player_id": attempt.player_id,
                    "points": attempt.points_scored,
                    "balls": attempt.balls_pocketed,
                    "ended_rally": attempt.ended_rally,
                }
                for attempt in tiebreaker.rally_attempts
            ]
        elif str(tiebreaker.tiebreaker_type) == TiebreakerType.PLAYOFF_MATCH.value:
            status["playoff_matches"] = [
                {
                    "match_number": match.match_number,
                    "status": match.status,
                    "p1_score": match.player1_score,
                    "p2_score": match.player2_score,
                    "winner_id": match.winner_id,
                }
                for match in tiebreaker.playoff_matches
            ]

        return status

    @staticmethod
    def _check_spot_shot_completion(tiebreaker: Tiebreaker) -> None:
        """Check if spot shot tiebreaker is complete."""

        # Group shots by round
        rounds = {}
        for shot in tiebreaker.spot_shots:
            if shot.round_number not in rounds:
                rounds[shot.round_number] = []
            rounds[shot.round_number].append(shot)

        # Check each completed round
        for round_num, shots in rounds.items():
            if len(shots) == 2:  # Both players shot
                # Store player IDs as local variables to avoid SQLAlchemy type issues
                player1_id = cast(int, tiebreaker.player1_id)
                player2_id = cast(int, tiebreaker.player2_id)

                p1_shots = [s for s in shots if s.player_id == player1_id]
                p2_shots = [s for s in shots if s.player_id == player2_id]

                if len(p1_shots) == 1 and len(p2_shots) == 1:
                    p1_made = p1_shots[0].result == SpotShotResult.MADE.value
                    p2_made = p2_shots[0].result == SpotShotResult.MADE.value

                    # Check for winner
                    if p1_made and not p2_made:
                        tiebreaker.complete(player1_id)
                        return
                    elif p2_made and not p1_made:
                        tiebreaker.complete(player2_id)
                        return
                    # If both made or both missed, continue to next round

        # Check for sudden death after max rounds
        max_rounds = tiebreaker.configuration.get("max_rounds", 5)
        if len(rounds) >= max_rounds:
            # Implement sudden death logic if needed
            pass

    @staticmethod
    def _check_rally_completion(tiebreaker: Tiebreaker) -> None:
        """Check if rally tiebreaker is complete."""

        target_score = tiebreaker.configuration.get("target_score", 15)

        # Store player IDs as local variables to avoid SQLAlchemy type issues
        player1_id = cast(int, tiebreaker.player1_id)
        player2_id = cast(int, tiebreaker.player2_id)

        # Calculate current scores
        p1_score: int = 0
        p2_score: int = 0
        for attempt in tiebreaker.rally_attempts:
            attempt_player_id = cast(int, attempt.player_id)
            if attempt_player_id == player1_id:
                p1_score += cast(int, attempt.points_scored)
            elif attempt_player_id == player2_id:
                p2_score += cast(int, attempt.points_scored)

        # Check for winner
        if p1_score >= target_score and p1_score > p2_score:
            tiebreaker.complete(player1_id)
        elif p2_score >= target_score and p2_score > p1_score:
            tiebreaker.complete(player2_id)

    @staticmethod
    def _check_playoff_completion(tiebreaker: Tiebreaker) -> None:
        """Check if playoff tiebreaker is complete."""

        best_of = tiebreaker.configuration.get("best_of", 3)
        wins_needed = (best_of // 2) + 1

        # Store player IDs as local variables to avoid SQLAlchemy type issues
        player1_id = cast(int, tiebreaker.player1_id)
        player2_id = cast(int, tiebreaker.player2_id)

        # Count wins
        p1_wins = 0
        p2_wins = 0
        for match in tiebreaker.playoff_matches:
            match_winner_id = (
                cast(int, match.winner_id) if match.winner_id is not None else None
            )
            if match_winner_id == player1_id:
                p1_wins += 1
            elif match_winner_id == player2_id:
                p2_wins += 1

        # Check for winner
        if p1_wins >= wins_needed:
            tiebreaker.complete(player1_id)
        elif p2_wins >= wins_needed:
            tiebreaker.complete(player2_id)


class TiebreakerConfigurationService:
    """Service for managing tiebreaker configurations."""

    @staticmethod
    @transactional(domain="tiebreaker")
    def create_default_configuration(
        campionato_id: Optional[int] = None, gara_id: Optional[int] = None
    ) -> TiebreakerConfiguration:
        """Create default tiebreaker configuration."""

        default_rules = {
            "palla_8": {"type": "spot_shot", "max_rounds": 5, "sudden_death_after": 5},
            "palla_9": {"type": "spot_shot", "max_rounds": 3, "sudden_death_after": 3},
            "straight_pool": {
                "type": "rally",
                "target_score": 15,
                "max_attempts_per_player": 3,
            },
            "default": {"type": "playoff_match", "best_of": 3, "match_distance": 3},
        }

        config = TiebreakerConfiguration(
            campionato_id=campionato_id,
            gara_id=gara_id,
            name="Default Tiebreaker Rules",
            description="Standard tiebreaker rules for all disciplines",
            rules=default_rules,
            is_default=True,
        )

        db.session.add(config)
        return config

    @staticmethod
    def get_configuration_for_match(
        match_id: int, discipline: str
    ) -> Optional[TiebreakerConfiguration]:
        """Get the appropriate tiebreaker configuration for a match."""

        from ..match.models import Match

        match = db.session.get(Match, match_id)
        if match is None:
            from flask import abort

            abort(404)

        # Try to find specific configuration
        config = None

        # First try gara-specific
        if match.gara_id:
            config = TiebreakerConfiguration.query.filter_by(
                gara_id=match.gara_id, is_active=True
            ).first()

        # Then try campionato-specific
        if not config and match.gara and match.gara.campionato_id:
            config = TiebreakerConfiguration.query.filter_by(
                campionato_id=match.gara.campionato_id, is_active=True
            ).first()

        # Finally try default
        if not config:
            config = TiebreakerConfiguration.query.filter_by(
                campionato_id=None, gara_id=None, is_default=True, is_active=True
            ).first()

        return config if config and config.supports_discipline(discipline) else None

    @staticmethod
    def get_tiebreaker_type_for_discipline(
        discipline: str, configuration: Optional[TiebreakerConfiguration] = None
    ) -> TiebreakerType:
        """Determine the appropriate tiebreaker type for a discipline."""

        if configuration:
            rule = configuration.get_rule_for_discipline(discipline)
            if rule and "type" in rule:
                return TiebreakerType(rule["type"])

        # Default mappings
        if discipline in ["palla_8", "palla_9"]:
            return TiebreakerType.SPOT_SHOT
        elif discipline == "straight_pool":
            return TiebreakerType.RALLY
        else:
            return TiebreakerType.PLAYOFF_MATCH
