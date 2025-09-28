"""
Module: models/matchmaking/amalfi_challenge_bye_service.py
Purpose: Service for integrating Amalfi challenge-bye scoring with match results
Requirements: Update bye match scores when challenges are completed for Amalfi strategy
"""

from __future__ import annotations

from typing import Optional
from ..base import db
from ..transaction.manager import transactional


class AmalfiChallengeByeService:
    """Service for managing Amalfi-specific challenge-bye scoring integration.

    Handles the logic of updating bye match scores when challenges are completed
    as part of the Amalfi strategy's approach to variable bye scoring.

    This service maintains separation of concerns:
    - Generic challenge system remains agnostic
    - Amalfi-specific logic is contained here
    - Match scoring is updated transparently for classification
    """

    @staticmethod
    @transactional(domain="matchmaking")
    def update_bye_match_from_challenge(attempt_id: int) -> bool:
        """Update corresponding bye match score from completed challenge attempt.

        For Amalfi strategy, completed challenges replace traditional bye scoring.
        This method finds the bye match corresponding to a challenge attempt and
        updates its score for proper classification integration.

        Args:
            attempt_id: ID of the completed GaraChallengeAttempt

        Returns:
            bool: True if bye match was found and updated, False otherwise
        """
        try:
            from models.challenge.gara_challenge_models import GaraChallengeAttempt
            from models.match.models import Match

            # Get the completed challenge attempt
            attempt = db.session.get(GaraChallengeAttempt, attempt_id)
            if not attempt or not attempt.completed or attempt.score is None:
                return False

            # Find the corresponding bye match for this user and round
            bye_match = Match.query.filter_by(
                gara_id=attempt.gara_challenge.gara_id,
                round_number=attempt.round_when_attempted or attempt.gara_challenge.round_number,
                player1_id=attempt.user_id,
                is_bye=True
            ).first()

            if not bye_match:
                # No corresponding bye match found - this might be a regular challenge
                return False

            # Update the bye match with challenge score
            bye_match.player1_score = attempt.score
            bye_match.status = "completed"

            # Ensure player2_score is 0 for bye matches (consistency)
            if bye_match.player2_score is None:
                bye_match.player2_score = 0

            db.session.add(bye_match)

            return True

        except Exception:
            # Graceful degradation - don't break challenge completion
            return False

    @staticmethod
    def is_challenge_bye_replacement(attempt_id: int) -> bool:
        """Check if a challenge attempt is being used as bye replacement.

        Args:
            attempt_id: ID of the GaraChallengeAttempt

        Returns:
            bool: True if this challenge is replacing a bye, False otherwise
        """
        try:
            from models.challenge.gara_challenge_models import GaraChallengeAttempt
            from models.match.models import Match

            attempt = db.session.get(GaraChallengeAttempt, attempt_id)
            if not attempt:
                return False

            # Check if there's a corresponding bye match
            bye_match = Match.query.filter_by(
                gara_id=attempt.gara_challenge.gara_id,
                round_number=attempt.round_when_attempted or attempt.gara_challenge.round_number,
                player1_id=attempt.user_id,
                is_bye=True
            ).first()

            return bye_match is not None

        except Exception:
            return False

    @staticmethod
    def get_challenge_bye_score(gara_id: int, round_number: int, user_id: int) -> Optional[int]:
        """Get the challenge score for a bye replacement if available.

        Args:
            gara_id: ID of the gara
            round_number: Round number
            user_id: Player ID

        Returns:
            Optional[int]: Challenge score if found, None otherwise
        """
        try:
            from models.challenge.gara_challenge_models import GaraChallengeAttempt, GaraChallenge

            # Find completed challenge attempt for this user/round
            attempt = (
                GaraChallengeAttempt.query
                .join(GaraChallenge)
                .filter(
                    GaraChallenge.gara_id == gara_id,
                    GaraChallengeAttempt.user_id == user_id,
                    GaraChallengeAttempt.round_when_attempted == round_number,
                    GaraChallengeAttempt.completed == True
                )
                .first()
            )

            if attempt and AmalfiChallengeByeService.is_challenge_bye_replacement(attempt.id):
                return attempt.score

            return None

        except Exception:
            return None