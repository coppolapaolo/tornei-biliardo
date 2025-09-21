"""
Module: models/tiebreaker/services.py
Purpose: Tiebreaker domain services for resolving tied match situations

This module provides comprehensive business logic for handling different types of tiebreakers
in the American Pool community platform. It supports three primary tiebreaker mechanisms:

1. **Spot Shots** (8-ball/9-ball): Round-based elimination with sudden death capabilities
2. **Rallies** (Straight Pool): Score-based continuous play with target thresholds
3. **Playoff Matches** (Campionato): Best-of series for position-based ties

All service methods use @transactional(domain="tiebreaker") for consistent transaction
boundaries and automatic rollback on failures. The domain-specific tagging enables
proper monitoring and performance tracking of tiebreaker operations.

Key Features:
- Automatic completion detection based on discipline-specific rules
- Configurable scoring systems per pool discipline
- Real-time score tracking and validation
- Integration with main match system for seamless tie resolution
- Support for both tournament and casual match tie resolution

Business Rules:
- All tiebreakers must have exactly two participants (player1, player2)
- Winner determination follows discipline-specific completion criteria
- Automatic state transitions from pending → in_progress → completed
- Configuration-driven rules allow customization per competition/venue

Requirements: SPECIFICHE.md - Tiebreaker system management
"""

from __future__ import annotations

from typing import Dict, Any, Optional, cast
from datetime import datetime

from ..base import db
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
from ..transaction.manager import transactional


class TiebreakerService:
    """
    Primary service for managing tiebreaker situations and resolution workflows.

    This service handles the complete lifecycle of tiebreaker resolution including:
    - Creation of discipline-specific tiebreakers with appropriate configurations
    - Recording of individual attempts/shots/matches within tiebreakers
    - Automatic completion detection based on business rules
    - Winner determination and status management

    All methods are transactional with domain="tiebreaker" tagging for proper
    transaction isolation and monitoring. The service integrates with the
    TiebreakerConfiguration system to apply venue/competition-specific rules.

    Transaction Boundaries:
    Each public method represents a complete business operation that either
    succeeds entirely or rolls back completely, ensuring data consistency
    across all related entities (Tiebreaker, SpotShot, RallyAttempt, PlayoffMatch).
    """

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
        """
        Create a spot shot tiebreaker for tied 8-ball or 9-ball matches.

        Spot shots are the traditional method for resolving tied matches in 8-ball
        and 9-ball pool. Players alternate shooting at the designated ball(s)
        until one player makes a shot and the other misses in the same round.

        Business Rules:
        - Each round consists of both players shooting once
        - Winner determined when one player makes and opponent misses in same round
        - After max_rounds, sudden death mode may be triggered
        - Supports both 8-ball (object ball on spot) and 9-ball (9-ball on spot)

        Transaction Boundary:
        Creates the tiebreaker entity with proper configuration and initial status.
        All related validation and setup operations are atomic.

        Args:
            match_id: The tied match requiring resolution
            player1_id: First player participant
            player2_id: Second player participant
            campionato_id: Optional tournament context
            gara_id: Optional competition context
            configuration: Custom rules overriding defaults

        Returns:
            Newly created Tiebreaker entity in PENDING status

        Configuration Options:
            - max_rounds: Maximum rounds before sudden death (default: 5)
            - sudden_death_after: Round number to switch to sudden death (default: 5)
            - ball_type: "8_ball" or "9_ball" (default: "8_ball")
        """

        # Default configuration for spot shots following traditional pool rules
        default_config = {
            "max_rounds": 5,  # Maximum rounds before sudden death (standard tournament rule)
            "sudden_death_after": 5,  # Switch to sudden death after this many tied rounds
            "ball_type": "8_ball",  # Target ball type: "8_ball" or "9_ball"
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
        """
        Create a rally tiebreaker for tied straight pool matches.

        Rally tiebreakers are used in straight pool (14.1 continuous) where
        players alternate shooting continuously until they miss, then the
        next player shoots. The first player to reach the target score wins.

        Business Rules:
        - Players shoot until they miss, then opponent shoots
        - Points accumulated across multiple attempts
        - Winner determined when target_score reached AND leading opponent
        - Limited attempts per player to prevent indefinite games

        Transaction Boundary:
        Creates the tiebreaker entity with straight pool specific configuration.
        Sets up the scoring system for cumulative point tracking.

        Args:
            match_id: The tied straight pool match requiring resolution
            player1_id: First player participant
            player2_id: Second player participant
            campionato_id: Optional tournament context
            gara_id: Optional competition context
            target_score: Points needed to win (default: 15)

        Returns:
            Newly created Tiebreaker entity configured for rally scoring

        Configuration:
            - target_score: Points required to win the tiebreaker
            - max_attempts_per_player: Limit to prevent infinite games (default: 3)
            - discipline: Set to "straight_pool" for proper scoring
        """

        configuration = {
            "target_score": target_score,  # Points needed to win the tiebreaker
            "max_attempts_per_player": 3,  # Prevents indefinite rallies
            "discipline": "straight_pool",  # Ensures proper scoring logic
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
        """
        Create a playoff match series tiebreaker for campionato position ties.

        Playoff tiebreakers are used when players are tied in campionato standings
        and need to determine final positions. This involves playing a series of
        short matches (typically race-to-3) in a best-of format.

        Business Rules:
        - Best-of series (e.g., best of 3 = first to win 2 matches)
        - Each playoff match is a short race (typically 3 games)
        - Winner determined when they win majority of matches in series
        - Used primarily for final standings determination in tournaments

        Transaction Boundary:
        Creates the tiebreaker entity with playoff series configuration.
        Sets up the framework for multiple PlayoffMatch entities.

        Args:
            match_id: The tied match requiring position resolution
            player1_id: First player participant
            player2_id: Second player participant
            campionato_id: Optional tournament context (usually required for playoffs)
            gara_id: Optional competition context
            best_of: Number of matches in series (default: 3, meaning first to 2 wins)

        Returns:
            Newly created Tiebreaker entity configured for playoff series

        Configuration:
            - best_of: Total matches in series (winner needs (best_of//2)+1 wins)
            - match_distance: Race length for each individual playoff match (default: 3)
            - discipline: Pool discipline for playoff matches (default: "palla_8")
        """

        configuration = {
            "best_of": best_of,  # Total matches in series (first to majority wins)
            "match_distance": 3,  # Race length for each individual playoff match
            "discipline": "palla_8",  # Pool discipline for all matches in series
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
        """
        Record an individual spot shot attempt and check for tiebreaker completion.

        This method handles the core spot shot workflow including validation,
        recording the attempt, and automatic completion detection. Each shot
        is recorded with its round context and shooting order.

        Business Logic:
        - Validates tiebreaker is in progress and player is participant
        - Records shot with result (MADE, MISSED, FOUL, SCRATCH)
        - Automatically checks if tiebreaker is complete after each shot
        - Completion occurs when one player makes and opponent misses in same round

        Transaction Boundary:
        Records the shot attempt and performs completion check atomically.
        If completion is detected, the tiebreaker status is updated to COMPLETED
        with winner assignment in the same transaction.

        Args:
            tiebreaker_id: The spot shot tiebreaker to record against
            player_id: Player making the shot (must be participant)
            round_number: Which round of spot shots (starts at 1)
            order_in_round: Shooting order within round (1 or 2)
            result: Outcome of the shot attempt
            notes: Optional notes about the shot

        Returns:
            Newly created SpotShot record

        Raises:
            ValueError: If tiebreaker not in progress or player not participant

        Side Effects:
            May complete the tiebreaker if winning condition is met
        """

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

        # Automatically check for completion after recording shot
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
        """
        Record a rally attempt in straight pool tiebreaker and check completion.

        Records a continuous shooting attempt by a player, tracking points scored
        and whether the rally continues or ends. The system automatically tracks
        cumulative scores and determines when the target score is reached.

        Business Logic:
        - Validates tiebreaker is in progress
        - Assigns sequence number for attempt ordering
        - Marks attempt as successful if points > 0
        - Automatically checks for completion after each attempt
        - Winner determined when target_score reached AND leading opponent

        Transaction Boundary:
        Records the rally attempt and performs completion check atomically.
        Calculates cumulative scores and updates tiebreaker status if winner
        is determined based on target score achievement.

        Args:
            tiebreaker_id: The rally tiebreaker to record against
            player_id: Player making the attempt
            points_scored: Points accumulated in this attempt
            balls_pocketed: Number of balls pocketed (for statistics)
            ended_rally: Whether this attempt ended the continuous rally
            notes: Optional notes about the attempt

        Returns:
            Newly created RallyAttempt record with sequence number

        Side Effects:
            May complete the tiebreaker if target score reached with lead
        """

        tiebreaker = db.session.get(Tiebreaker, tiebreaker_id)
        if tiebreaker is None:
            from flask import abort

            abort(404)

        if str(tiebreaker.status) != TiebreakerStatus.IN_PROGRESS.value:
            raise ValueError("Tiebreaker must be in progress to record attempts")

        # Get sequence number for proper attempt ordering
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
            completed_at=datetime.utcnow(),
        )

        db.session.add(rally_attempt)

        # Automatically check for completion after recording attempt
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
        """
        Create an individual playoff match within a playoff series tiebreaker.

        Creates one match in the best-of series, inheriting players from the
        parent tiebreaker. Each playoff match is a short race designed to
        quickly determine a winner for that game in the series.

        Business Logic:
        - Inherits player1_id and player2_id from parent tiebreaker
        - Creates match with specified race distance (typically 3-5 games)
        - Match starts in PENDING status awaiting execution
        - Part of larger best-of series managed by parent tiebreaker

        Transaction Boundary:
        Creates the playoff match entity as part of the series structure.
        Links to parent tiebreaker for proper relationship management.

        Args:
            tiebreaker_id: Parent playoff tiebreaker
            match_number: Sequence number in the series (1, 2, 3, etc.)
            distance: Race length for this match (default: 3)
            discipline: Pool discipline (default: "palla_8")

        Returns:
            Newly created PlayoffMatch in PENDING status

        Note:
            This creates the match structure but does not execute it.
            Use complete_playoff_match() to record results.
        """

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
        """
        Complete an individual playoff match and check overall series status.

        Records the result of one match in the playoff series and automatically
        determines if the entire tiebreaker is complete based on best-of rules.
        The series winner is determined when they reach majority wins.

        Business Logic:
        - Validates winner is one of the two participants
        - Records final scores for the individual match
        - Updates match status to COMPLETED
        - Checks if series winner has been determined
        - Completes parent tiebreaker if majority wins achieved

        Transaction Boundary:
        Updates the playoff match result and potentially completes the entire
        tiebreaker series atomically. All scoring and status updates are
        performed in a single transaction.

        Args:
            playoff_match_id: The specific playoff match to complete
            winner_id: Winner of this individual match
            p1_score: Final score for player 1
            p2_score: Final score for player 2

        Returns:
            Updated PlayoffMatch with completion details

        Side Effects:
            May complete the parent tiebreaker if series winner determined

        Example:
            In best-of-3 series, completing the 2nd match with same winner
            as the 1st match will complete the entire tiebreaker.
        """

        playoff_match = db.session.get(PlayoffMatch, playoff_match_id)
        if playoff_match is None:
            from flask import abort

            abort(404)
        playoff_match.complete_match(winner_id, p1_score, p2_score)

        # Check if completing this match determines the series winner
        TiebreakerService._check_playoff_completion(playoff_match.tiebreaker)

        return playoff_match

    @staticmethod
    def get_tiebreaker_status(tiebreaker_id: int) -> Dict[str, Any]:
        """
        Get comprehensive status and detailed information for a tiebreaker.

        Provides complete status information including current scores, attempt
        history, and type-specific details. This is a read-only operation that
        compiles all relevant data for display or API responses.

        Returns different detail structures based on tiebreaker type:
        - Spot Shot: Round-by-round shot history with results
        - Rally: Sequence of attempts with points and rally status
        - Playoff: Individual match results and series progress

        Transaction Note:
        This is a read-only operation that does not require transaction
        management as it only queries existing data.

        Args:
            tiebreaker_id: The tiebreaker to get status for

        Returns:
            Dictionary containing:
            - Basic tiebreaker info (id, type, status, players, winner)
            - Current scores calculated from attempts/shots/matches
            - Timestamps for creation, start, completion
            - Configuration details
            - Type-specific attempt/shot/match history

        Type-Specific Details:
            - spot_shots: List of shots with round, order, result, timing
            - rally_attempts: List of attempts with sequence, points, rally status
            - playoff_matches: List of matches with scores and winners
        """

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
        """
        Check if spot shot tiebreaker meets completion criteria and update status.

        Implements the core business logic for spot shot completion:
        1. Groups shots by round number
        2. For each completed round (both players shot), determines round winner
        3. If one player makes and opponent misses in same round, declares winner
        4. Handles sudden death rules after maximum rounds

        Completion Rules:
        - Both players must shoot in a round for it to be considered complete
        - Winner determined when one makes and one misses in the same round
        - If both make or both miss, continue to next round
        - After max_rounds, sudden death logic may apply (implementation specific)

        SQLAlchemy Type Safety:
        Uses cast(int, ...) for player IDs to ensure type compatibility
        with SQLAlchemy nullable foreign key relationships.

        Args:
            tiebreaker: The spot shot tiebreaker to check

        Side Effects:
            May call tiebreaker.complete(winner_id) if completion criteria met
        """

        # Group shots by round number for round-by-round analysis
        rounds = {}
        for shot in tiebreaker.spot_shots:
            if shot.round_number not in rounds:
                rounds[shot.round_number] = []
            rounds[shot.round_number].append(shot)

        # Check each completed round for winner determination
        for round_num, shots in rounds.items():
            if len(shots) == 2:  # Both players have completed their shots
                # Store player IDs as local variables to avoid SQLAlchemy type issues
                player1_id = cast(int, tiebreaker.player1_id)
                player2_id = cast(int, tiebreaker.player2_id)

                p1_shots = [s for s in shots if s.player_id == player1_id]
                p2_shots = [s for s in shots if s.player_id == player2_id]

                if len(p1_shots) == 1 and len(p2_shots) == 1:
                    p1_made = p1_shots[0].result == SpotShotResult.MADE.value
                    p2_made = p2_shots[0].result == SpotShotResult.MADE.value

                    # Apply spot shot completion rule: one makes, one misses = winner
                    if p1_made and not p2_made:
                        tiebreaker.complete(player1_id)
                        return
                    elif p2_made and not p1_made:
                        tiebreaker.complete(player2_id)
                        return
                    # If both made or both missed, continue to next round (no winner yet)

        # Check for sudden death mode after maximum regular rounds
        max_rounds = tiebreaker.configuration.get("max_rounds", 5)
        if len(rounds) >= max_rounds:
            # TODO: Implement sudden death logic (immediate elimination on next make/miss)
            # For now, continue with regular rules
            pass

    @staticmethod
    def _check_rally_completion(tiebreaker: Tiebreaker) -> None:
        """
        Check if rally tiebreaker meets completion criteria and update status.

        Implements straight pool rally completion logic:
        1. Calculates cumulative points for each player across all attempts
        2. Checks if any player has reached target_score
        3. Ensures winner has both reached target AND is leading opponent
        4. Declares winner only when both conditions are satisfied

        Completion Rules:
        - Player must reach configured target_score (default: 15)
        - Player must be leading their opponent when target is reached
        - If both players reach target simultaneously, higher score wins
        - Prevents ties by requiring clear lead at target achievement

        SQLAlchemy Type Safety:
        Uses cast(int, ...) for player IDs and attempt attributes to ensure
        proper type handling with nullable database fields.

        Args:
            tiebreaker: The rally tiebreaker to check

        Side Effects:
            May call tiebreaker.complete(winner_id) if target reached with lead
        """

        target_score = tiebreaker.configuration.get("target_score", 15)

        # Store player IDs as local variables to avoid SQLAlchemy type issues
        player1_id = cast(int, tiebreaker.player1_id)
        player2_id = cast(int, tiebreaker.player2_id)

        # Calculate cumulative scores across all rally attempts
        p1_score: int = 0
        p2_score: int = 0
        for attempt in tiebreaker.rally_attempts:
            attempt_player_id = cast(int, attempt.player_id)
            if attempt_player_id == player1_id:
                p1_score += cast(int, attempt.points_scored)
            elif attempt_player_id == player2_id:
                p2_score += cast(int, attempt.points_scored)

        # Check for winner: must reach target AND be leading opponent
        if p1_score >= target_score and p1_score > p2_score:
            tiebreaker.complete(player1_id)
        elif p2_score >= target_score and p2_score > p1_score:
            tiebreaker.complete(player2_id)

    @staticmethod
    def _check_playoff_completion(tiebreaker: Tiebreaker) -> None:
        """
        Check if playoff series tiebreaker meets completion criteria and update status.

        Implements best-of series completion logic:
        1. Counts completed match wins for each player
        2. Calculates wins_needed based on best_of configuration
        3. Declares winner when majority wins achieved
        4. Ensures series ends as soon as winner is mathematically determined

        Completion Rules:
        - Winner needs majority of matches: (best_of // 2) + 1 wins
        - Series ends immediately when winner reaches required wins
        - Only counts matches with completed status and declared winner
        - Example: In best-of-5, first to 3 wins takes the series

        SQLAlchemy Type Safety:
        Uses cast(int, ...) for nullable winner_id fields to ensure proper
        type handling when checking match results.

        Args:
            tiebreaker: The playoff tiebreaker to check

        Side Effects:
            May call tiebreaker.complete(winner_id) if series winner determined
        """

        best_of = tiebreaker.configuration.get("best_of", 3)
        wins_needed = (best_of // 2) + 1  # Majority wins required

        # Store player IDs as local variables to avoid SQLAlchemy type issues
        player1_id = cast(int, tiebreaker.player1_id)
        player2_id = cast(int, tiebreaker.player2_id)

        # Count completed match wins for each player
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

        # Check for series winner: first to majority wins
        if p1_wins >= wins_needed:
            tiebreaker.complete(player1_id)
        elif p2_wins >= wins_needed:
            tiebreaker.complete(player2_id)


class TiebreakerConfigurationService:
    """
    Configuration management service for discipline-specific tiebreaker rules.

    This service manages the configuration system that determines how tiebreakers
    should be resolved based on:
    - Pool discipline (8-ball, 9-ball, straight pool, etc.)
    - Competition/venue-specific rules
    - Default fallback configurations

    The configuration hierarchy follows:
    1. Gara-specific configuration (most specific)
    2. Campionato-specific configuration
    3. Default system configuration (fallback)

    Configuration Structure:
    - JSON-based rules defining type, scoring, and completion criteria
    - Support for custom parameters per discipline
    - Backward compatibility with legacy rule formats
    """

    @staticmethod
    @transactional(domain="tiebreaker")
    def create_default_configuration(
        campionato_id: Optional[int] = None, gara_id: Optional[int] = None
    ) -> TiebreakerConfiguration:
        """
        Create a default tiebreaker configuration with standard rules for all disciplines.

        Establishes baseline tiebreaker rules that can be applied system-wide or
        to specific competitions. The configuration defines how ties should be
        resolved for each supported pool discipline.

        Default Rules by Discipline:
        - palla_8: Spot shot with 5 rounds, sudden death after 5
        - palla_9: Spot shot with 3 rounds, sudden death after 3
        - straight_pool: Rally to 15 points, max 3 attempts per player
        - default: Playoff matches, best of 3, race to 3

        Transaction Boundary:
        Creates the configuration record atomically with all rule definitions.

        Args:
            campionato_id: Optional tournament to scope configuration to
            gara_id: Optional competition to scope configuration to

        Returns:
            Newly created TiebreakerConfiguration marked as default

        Note:
            If both campionato_id and gara_id are None, creates system-wide default.
            Configuration hierarchy: gara-specific > campionato-specific > system default
        """

        # Standard tiebreaker rules following pool community practices
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
        """
        Retrieve the most specific tiebreaker configuration applicable to a match.

        Implements the configuration hierarchy to find the most appropriate
        tiebreaker rules for a given match and discipline combination.

        Configuration Resolution Order:
        1. Gara-specific configuration (highest priority)
        2. Campionato-specific configuration (medium priority)
        3. System default configuration (fallback)
        4. None if no applicable configuration supports the discipline

        Business Logic:
        - Must support the requested discipline or have default rules
        - Must be marked as active (is_active=True)
        - Inherits competition context from the match entity

        Args:
            match_id: The match requiring tiebreaker resolution
            discipline: Pool discipline ("palla_8", "palla_9", "straight_pool", etc.)

        Returns:
            Most specific applicable TiebreakerConfiguration or None

        Note:
            This is a read-only operation that queries the configuration hierarchy
            without modifying any data.
        """

        from ..match.models import Match

        match = db.session.get(Match, match_id)
        if match is None:
            from flask import abort

            abort(404)

        # Search configuration hierarchy: gara -> campionato -> system default
        config = None

        # First try gara-specific configuration (highest priority)
        if match.gara_id:
            config = TiebreakerConfiguration.query.filter_by(
                gara_id=match.gara_id, is_active=True
            ).first()

        # Then try campionato-specific configuration (medium priority)
        if not config and match.gara and match.gara.campionato_id:
            config = TiebreakerConfiguration.query.filter_by(
                campionato_id=match.gara.campionato_id, is_active=True
            ).first()

        # Finally try system default configuration (fallback)
        if not config:
            config = TiebreakerConfiguration.query.filter_by(
                campionato_id=None, gara_id=None, is_default=True, is_active=True
            ).first()

        return config if config and config.supports_discipline(discipline) else None

    @staticmethod
    def get_tiebreaker_type_for_discipline(
        discipline: str, configuration: Optional[TiebreakerConfiguration] = None
    ) -> TiebreakerType:
        """
        Determine the appropriate tiebreaker type for a pool discipline.

        Maps pool disciplines to their traditional tiebreaker methods, with
        optional override via configuration. Uses pool community standards
        for tiebreaker selection when no specific configuration is provided.

        Standard Discipline Mappings:
        - palla_8, palla_9: SPOT_SHOT (traditional for pocket billiards)
        - straight_pool: RALLY (continuous play format)
        - others: PLAYOFF_MATCH (safe default for unknown disciplines)

        Configuration Override:
        If a TiebreakerConfiguration is provided, its discipline-specific
        rules take precedence over the default mappings.

        Args:
            discipline: Pool discipline name
            configuration: Optional configuration to override defaults

        Returns:
            TiebreakerType enum value for the discipline

        Note:
            This method encapsulates the business logic for tiebreaker type
            selection and can be extended to support new disciplines.
        """

        if configuration:
            rule = configuration.get_rule_for_discipline(discipline)
            if rule and "type" in rule:
                return TiebreakerType(rule["type"])

        # Default mappings based on pool community standards
        if discipline in ["palla_8", "palla_9"]:
            return TiebreakerType.SPOT_SHOT  # Traditional for pocket billiards
        elif discipline == "straight_pool":
            return TiebreakerType.RALLY  # Continuous play format
        else:
            return TiebreakerType.PLAYOFF_MATCH  # Safe default for unknown disciplines
