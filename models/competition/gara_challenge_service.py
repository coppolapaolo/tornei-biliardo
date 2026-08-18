"""
Module: models/competition/gara_challenge_service.py
Purpose: Service layer for managing challenges within tournament competitions (Gara)
Requirements: Support for challenge integration in Random tournament type competitions
Data Operations: Challenge management, attempt tracking, classification calculation

Design Note (Sprint 11 - December 2025):
    This service was moved from models/challenge/ to models/competition/ to properly
    establish domain boundaries. The Competition domain owns the integration logic
    between tournaments and challenges. The Challenge domain remains pure.

    See ADR-004-challenge-gara-decoupling.md for rationale.
"""

from __future__ import annotations

import logging
from typing import List, Dict, Any, Optional

from ..base import db
from ..challenge.models import Challenge
from .gara_challenge import (
    GaraChallenge,
    GaraChallengeAttempt,
    GaraChallengeClassification,
)
from ..exceptions import ConflictError, NotFoundError
from ..transaction.manager import transactional

logger = logging.getLogger(__name__)


class GaraChallengeService:
    """Service for managing challenges within competitions.

    This service lives in the Competition domain because it orchestrates
    the integration between Gara (competition) and Challenge entities.
    The Challenge domain remains unaware of competitions.
    """

    @staticmethod
    @transactional(domain="competition")
    def add_challenge_to_gara(
        gara_id: int,
        challenge_id: int,
        round_number: int,
        added_by_id: int,
        max_attempts: int = 1,
    ) -> GaraChallenge:
        """
        Add a challenge to a gara.

        Args:
            gara_id: ID of the gara
            challenge_id: ID of the challenge to add
            round_number: After which round to execute the challenge
            added_by_id: chi la sta aggiungendo. Obbligatorio: la colonna e'
                ``nullable=False``, e la firma con default ``None`` prometteva
                il contrario — l'unico modo di scoprirlo era
                ``NOT NULL constraint failed`` da SQLite (GlitchTip
                TORNEI-BILIARDO-5U), a transazione gia' avviata.
            max_attempts: Maximum attempts per player (default 1)

        Returns:
            GaraChallenge: The created gara challenge link

        Raises:
            ConflictError: la challenge c'e' gia' per questa gara e questo turno
            NotFoundError: la challenge non esiste
        """
        # Check if challenge already exists for this gara and round
        existing = GaraChallenge.query.filter_by(
            gara_id=gara_id, challenge_id=challenge_id, round_number=round_number
        ).first()

        if existing:
            raise ConflictError("Challenge già presente per questo round della gara")

        # Verify challenge exists
        challenge = Challenge.query.get(challenge_id)
        if not challenge:
            raise NotFoundError("Challenge non trovata")

        # Create the gara challenge link
        gara_challenge = GaraChallenge(
            gara_id=gara_id,
            challenge_id=challenge_id,
            round_number=round_number,
            max_attempts=max_attempts,
            added_by_id=added_by_id,
            is_active=True,
        )

        db.session.add(gara_challenge)
        # Transaction managed by @transactional decorator
        return gara_challenge

    @staticmethod
    @transactional(domain="competition")
    def remove_challenge_from_gara(
        gara_id: int, challenge_id: int, round_number: int
    ) -> bool:
        """
        Remove a challenge from a gara.

        Args:
            gara_id: ID of the gara
            challenge_id: ID of the challenge to remove
            round_number: Round number for the challenge

        Returns:
            bool: True if removed successfully, False if not found
        """
        gara_challenge = GaraChallenge.query.filter_by(
            gara_id=gara_id, challenge_id=challenge_id, round_number=round_number
        ).first()

        if not gara_challenge:
            return False

        # Check if there are any attempts - if so, just deactivate
        has_attempts = GaraChallengeAttempt.query.filter_by(
            gara_challenge_id=gara_challenge.id
        ).first()

        if has_attempts:
            gara_challenge.is_active = False
        else:
            db.session.delete(gara_challenge)

        # Transaction managed by @transactional decorator
        return True

    @staticmethod
    def get_gara_challenges(
        gara_id: int, round_number: Optional[int] = None
    ) -> List[GaraChallenge]:
        """
        Get all active challenges for a gara.

        Args:
            gara_id: ID of the gara
            round_number: Optional filter by round number

        Returns:
            List[GaraChallenge]: List of gara challenges
        """
        query = GaraChallenge.query.filter_by(gara_id=gara_id, is_active=True)

        if round_number is not None:
            query = query.filter_by(round_number=round_number)

        return query.order_by(
            GaraChallenge.round_number, GaraChallenge.created_at
        ).all()

    @staticmethod
    def get_available_challenges_for_round(
        gara_id: int, current_round: int
    ) -> List[GaraChallenge]:
        """
        Get challenges that should be available for the current round.

        Args:
            gara_id: ID of the gara
            current_round: Current round number

        Returns:
            List[GaraChallenge]: Challenges available for this round
        """
        return (
            GaraChallenge.query.filter(
                GaraChallenge.gara_id == gara_id,
                GaraChallenge.round_number <= current_round,
                GaraChallenge.is_active == True,  # noqa: E712
            )
            .order_by(GaraChallenge.round_number)
            .all()
        )

    @staticmethod
    @transactional(domain="competition")
    def record_challenge_attempt(
        gara_challenge_id: int,
        user_id: int,
        score: Optional[int] = None,
        passed: Optional[bool] = None,
        notes: Optional[str] = None,
        round_when_attempted: Optional[int] = None,
    ) -> GaraChallengeAttempt:
        """
        Record a challenge attempt for a user in a gara.

        Args:
            gara_challenge_id: ID of the gara challenge
            user_id: ID of the user making the attempt
            score: Score achieved (for numeric challenges)
            passed: Pass/fail result (for pass/fail challenges)
            notes: Optional notes about the attempt
            round_when_attempted: Round when attempt was made

        Returns:
            GaraChallengeAttempt: The recorded attempt

        Raises:
            ValueError: If user has reached max attempts or other validation errors
        """
        gara_challenge = GaraChallenge.query.get(gara_challenge_id)
        if not gara_challenge:
            raise ValueError("Gara challenge non trovata")

        # Check if user can make another attempt
        if not gara_challenge.can_user_attempt(user_id):
            raise ValueError(
                (
                    f"Utente ha già raggiunto il massimo numero di tentativi "
                    f"({gara_challenge.max_attempts})"
                )
            )

        # Get next attempt number for this user
        attempt_number = gara_challenge.get_user_attempts_count(user_id) + 1

        # Create the attempt
        attempt = GaraChallengeAttempt(
            gara_challenge_id=gara_challenge_id,
            user_id=user_id,
            attempt_number=attempt_number,
            notes=notes,
            round_when_attempted=round_when_attempted,
        )

        # Complete the attempt with the provided score/result
        attempt.complete_attempt(
            score=score, passed=passed, gara_challenge=gara_challenge
        )

        db.session.add(attempt)
        # Transaction managed by @transactional decorator

        # Update the gara challenge classification
        GaraChallengeService.update_gara_classification(gara_challenge.gara_id)

        GaraChallengeService._publish_attempt_completed(attempt, gara_challenge)

        return attempt

    @staticmethod
    def _publish_attempt_completed(
        attempt: GaraChallengeAttempt, gara_challenge: GaraChallenge
    ) -> None:
        """Annuncia il drill di gara completato, per XP e streak.

        Best-effort: la gamification non deve mai far perdere un punteggio già
        registrato. ``attempt_number`` viaggia con l'evento perché in gara la
        stessa prova si ripete fino a ``max_attempts``, e chi ascolta deve
        poter distinguere un allenamento nuovo da un secondo tiro.
        """
        from models.challenge.events import (
            ChallengeAttemptCompletedEvent,
            DrillOrigin,
        )
        from models.events.base import EventBus

        try:
            challenge = gara_challenge.challenge
            EventBus.publish(
                ChallengeAttemptCompletedEvent(
                    attempt_id=attempt.id,
                    challenge_id=gara_challenge.challenge_id,
                    challenge_name=(challenge.get_display_name() if challenge else ""),
                    user_id=attempt.user_id,
                    origin=DrillOrigin.GARA.value,
                    score=attempt.score,
                    passed=attempt.passed,
                    gara_id=gara_challenge.gara_id,
                    attempt_number=attempt.attempt_number,
                )
            )
        except Exception:  # pragma: no cover - la gamification non blocca mai
            logger.warning("Evento di drill di gara non pubblicato", exc_info=True)

    @staticmethod
    @transactional(domain="competition")
    def record_multiple_attempts(
        attempts_data: List[Dict[str, Any]],
        round_when_attempted: Optional[int] = None,
    ) -> List[GaraChallengeAttempt]:
        """
        Record multiple challenge attempts at once (useful for match result input).

        Args:
            attempts_data: List of attempt data dictionaries
            round_when_attempted: Round when attempts were made

        Returns:
            List[GaraChallengeAttempt]: List of recorded attempts
        """
        recorded_attempts = []

        for attempt_data in attempts_data:
            attempt = GaraChallengeService.record_challenge_attempt(
                gara_challenge_id=attempt_data["gara_challenge_id"],
                user_id=attempt_data["user_id"],
                score=attempt_data.get("score"),
                passed=attempt_data.get("passed"),
                notes=attempt_data.get("notes"),
                round_when_attempted=round_when_attempted,
            )
            recorded_attempts.append(attempt)

        # Update classification once after all attempts
        if attempts_data:
            first_attempt = attempts_data[0]
            gara_challenge = GaraChallenge.query.get(first_attempt["gara_challenge_id"])
            if gara_challenge:
                GaraChallengeService.update_gara_classification(gara_challenge.gara_id)

        return recorded_attempts

    @staticmethod
    def update_gara_classification(gara_id: int) -> List[GaraChallengeClassification]:
        """
        Update the challenge classification for a gara.

        Args:
            gara_id: ID of the gara

        Returns:
            List[GaraChallengeClassification]: Updated classification
        """
        return GaraChallengeClassification.calculate_for_gara(gara_id)

    @staticmethod
    def get_gara_challenge_classification(
        gara_id: int,
    ) -> List[GaraChallengeClassification]:
        """
        Get the current challenge classification for a gara.

        Args:
            gara_id: ID of the gara

        Returns:
            List[GaraChallengeClassification]: Current classification ordered by
                position
        """
        return (
            GaraChallengeClassification.query.filter_by(gara_id=gara_id)
            .order_by(GaraChallengeClassification.position)
            .all()
        )

    @staticmethod
    def get_user_gara_challenge_progress(gara_id: int, user_id: int) -> Dict[str, Any]:
        """
        Get a user's progress across all challenges in a gara.

        Args:
            gara_id: ID of the gara
            user_id: ID of the user

        Returns:
            Dict containing user's challenge progress
        """
        gara_challenges = GaraChallengeService.get_gara_challenges(gara_id)
        progress = {
            "challenges": [],
            "total_best_score": 0,
            "total_all_attempts": 0,
            "challenges_attempted": 0,
        }

        for gara_challenge in gara_challenges:
            attempts = gara_challenge.get_user_attempts(user_id)
            completed_attempts = [a for a in attempts if a.completed]

            challenge_progress = {
                "gara_challenge": gara_challenge,
                "challenge": gara_challenge.challenge,
                "attempts": completed_attempts,
                "attempts_count": len(completed_attempts),
                "max_attempts": gara_challenge.max_attempts,
                "can_attempt": gara_challenge.can_user_attempt(user_id),
                "best_score": 0,
                "total_score": 0,
            }

            if completed_attempts:
                progress["challenges_attempted"] += 1
                scores = [a.score or 0 for a in completed_attempts]
                challenge_progress["best_score"] = max(scores)
                challenge_progress["total_score"] = sum(scores)

                progress["total_best_score"] += challenge_progress["best_score"]
                progress["total_all_attempts"] += challenge_progress["total_score"]

            progress["challenges"].append(challenge_progress)

        # Get user's position in classification
        classification = GaraChallengeClassification.query.filter_by(
            gara_id=gara_id, user_id=user_id
        ).first()

        if classification:
            progress["position"] = classification.position
            progress["total_players"] = GaraChallengeClassification.query.filter_by(
                gara_id=gara_id
            ).count()

        return progress

    @staticmethod
    def has_active_challenges(gara_id: int) -> bool:
        """
        Check if a gara has any active challenges.

        Args:
            gara_id: ID of the gara

        Returns:
            bool: True if gara has active challenges
        """
        return (
            GaraChallenge.query.filter_by(gara_id=gara_id, is_active=True).first()
            is not None
        )

    @staticmethod
    def get_challenge_statistics(gara_id: int) -> Dict[str, Any]:
        """
        Get overall challenge statistics for a gara.

        Args:
            gara_id: ID of the gara

        Returns:
            Dict containing challenge statistics
        """
        gara_challenges = GaraChallengeService.get_gara_challenges(gara_id)
        total_challenges = len(gara_challenges)

        if total_challenges == 0:
            return {
                "total_challenges": 0,
                "total_attempts": 0,
                "participating_players": 0,
                "challenges": [],
            }

        total_attempts = 0
        participating_players = set()
        challenge_stats = []

        for gara_challenge in gara_challenges:
            attempts = gara_challenge.attempts.filter_by(completed=True).all()
            challenge_attempts = len(attempts)
            total_attempts += challenge_attempts

            challenge_players = set(a.user_id for a in attempts)
            participating_players.update(challenge_players)

            if attempts:
                scores = [a.score or 0 for a in attempts]
                avg_score = sum(scores) / len(scores)
                max_score = max(scores)
                min_score = min(scores)
            else:
                avg_score = max_score = min_score = 0

            challenge_stats.append(
                {
                    "gara_challenge": gara_challenge,
                    "challenge": gara_challenge.challenge,
                    "attempts": challenge_attempts,
                    "participating_players": len(challenge_players),
                    "avg_score": round(avg_score, 1),
                    "max_score": max_score,
                    "min_score": min_score,
                }
            )

        return {
            "total_challenges": total_challenges,
            "total_attempts": total_attempts,
            "participating_players": len(participating_players),
            "challenges": challenge_stats,
        }
