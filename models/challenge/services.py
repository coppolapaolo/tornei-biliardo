"""
Module: models/challenge/services.py
Purpose: Challenge domain services for business logic
Requirements: SPECIFICHE.md - Challenge management and statistics
"""

from __future__ import annotations

from typing import List, Optional, Dict, Any
from sqlalchemy import desc

from ..base import db
from .models import Challenge, ChallengeAttempt, ChallengeFavorite


class ChallengeService:
    """Service for challenge management and business logic."""

    @staticmethod
    def create_challenge(
        name: str,
        description: str,
        min_score: int = 0,
        max_score: int = 100,
        pass_fail_only: bool = False,
        image_path: Optional[str] = None,
        created_by_id: Optional[int] = None,
    ) -> Challenge:
        """Create a new challenge."""
        challenge = Challenge(
            name=name,
            description=description,
            min_score=min_score,
            max_score=max_score,
            pass_fail_only=pass_fail_only,
            image_path=image_path,
            created_by_id=created_by_id,
        )

        db.session.add(challenge)
        db.session.commit()
        return challenge

    @staticmethod
    def get_all_challenges() -> List[Challenge]:
        """Get all challenges."""
        return db.session.query(Challenge).all()

    @staticmethod
    def get_active_challenges() -> List[Challenge]:
        """Get all active challenges."""
        return db.session.query(Challenge).filter_by(is_active=True).all()

    @staticmethod
    def get_user_challenges(user_id: int) -> Dict[str, List[Challenge]]:
        """Get challenges organized by user relationship."""
        # All active challenges
        all_challenges = ChallengeService.get_active_challenges()

        # User's favorites
        favorite_ids = {
            fav.challenge_id
            for fav in db.session.query(ChallengeFavorite)
            .filter_by(user_id=user_id)
            .all()
        }
        favorites = [c for c in all_challenges if c.id in favorite_ids]

        # Challenges user has attempted
        attempted_ids = {
            att.challenge_id
            for att in db.session.query(ChallengeAttempt)
            .filter_by(user_id=user_id)
            .all()
        }
        attempted = [c for c in all_challenges if c.id in attempted_ids]

        # General catalog (not attempted)
        general = [c for c in all_challenges if c.id not in attempted_ids]

        return {"favorites": favorites, "attempted": attempted, "general": general}

    @staticmethod
    def start_challenge_attempt(
        user_id: int,
        challenge_id: int,
        gara_id: Optional[int] = None,
        round_number: Optional[int] = None,
    ) -> ChallengeAttempt:
        """Start a new challenge attempt."""
        attempt = ChallengeAttempt(
            user_id=user_id,
            challenge_id=challenge_id,
            gara_id=gara_id,
            round_number=round_number,
        )

        db.session.add(attempt)
        db.session.commit()
        return attempt

    @staticmethod
    def complete_challenge_attempt(
        attempt_id: int,
        score: Optional[int] = None,
        passed: Optional[bool] = None,
        notes: Optional[str] = None,
    ) -> ChallengeAttempt:
        """Complete a challenge attempt with results."""
        attempt = db.session.get(ChallengeAttempt, attempt_id)
        if not attempt:
            from flask import abort

            abort(404)

        attempt.complete_attempt(score=score, passed=passed)
        if notes:
            attempt.notes = notes

        db.session.commit()
        return attempt

    @staticmethod
    def toggle_favorite(user_id: int, challenge_id: int) -> bool:
        """Toggle challenge as favorite for user. Returns True if added, False if removed."""
        favorite = (
            db.session.query(ChallengeFavorite)
            .filter_by(user_id=user_id, challenge_id=challenge_id)
            .first()
        )

        if favorite:
            db.session.delete(favorite)
            db.session.commit()
            return False
        else:
            favorite = ChallengeFavorite(user_id=user_id, challenge_id=challenge_id)
            db.session.add(favorite)
            db.session.commit()
            return True

    @staticmethod
    def get_challenge_for_x_replacement(gara_id: int) -> Optional[Challenge]:
        """Get a suitable challenge for X replacement in campionato."""
        # Find challenges that can be used for X replacement
        suitable_challenges = (
            db.session.query(Challenge)
            .filter_by(is_active=True, pass_fail_only=False)
            .all()
        )

        if not suitable_challenges:
            return None

        # Prefer challenges that haven't been used much in this gara
        challenge_usage = {}
        for challenge in suitable_challenges:
            usage_count = (
                db.session.query(ChallengeAttempt)
                .filter_by(challenge_id=challenge.id, gara_id=gara_id)
                .count()
            )
            challenge_usage[challenge.id] = usage_count

        # Return the least used challenge
        min_usage = min(challenge_usage.values())
        for challenge in suitable_challenges:
            if challenge_usage[challenge.id] == min_usage:
                return challenge

        return suitable_challenges[0]  # Fallback

    @staticmethod
    def create_x_replacement_attempt(
        user_id: int,
        gara_id: int,
        round_number: int,
        challenge_id: Optional[int] = None,
    ) -> ChallengeAttempt:
        """Create a challenge attempt to replace X in campionato."""

        final_challenge_id: int
        if challenge_id is None:
            challenge = ChallengeService.get_challenge_for_x_replacement(gara_id)
            if not challenge:
                raise ValueError("No suitable challenge available for X replacement")
            final_challenge_id = challenge.id
        else:
            final_challenge_id = challenge_id

        attempt = ChallengeService.start_challenge_attempt(
            user_id=user_id,
            challenge_id=final_challenge_id,
            gara_id=gara_id,
            round_number=round_number,
        )

        return attempt

    @staticmethod
    def complete_x_replacement_attempt(
        attempt_id: int, score: int, notes: Optional[str] = None
    ) -> ChallengeAttempt:
        """Complete X replacement challenge and return match-equivalent result."""

        attempt = db.session.get(ChallengeAttempt, attempt_id)
        if not attempt:
            from flask import abort

            abort(404)

        # Complete the attempt
        attempt.complete_attempt(score=score, passed=None)

        # Set notes separately if provided
        if notes:
            attempt.notes = notes

        # Create equivalent match result for campionato classification
        ChallengeService._create_x_replacement_match_result(attempt)

        return attempt

    @staticmethod
    def _create_x_replacement_match_result(attempt: ChallengeAttempt) -> None:
        """Create a match result equivalent for X replacement challenge."""
        from ..match.models import Match

        # Find or create a match for this X replacement
        match = (
            db.session.query(Match)
            .filter_by(
                gara_id=attempt.gara_id,
                round_number=attempt.round_number,
                player1_id=attempt.user_id,
                is_bye=True,
            )
            .first()
        )

        if not match:
            match = Match(
                gara_id=attempt.gara_id,
                round_number=attempt.round_number,
                player1_id=attempt.user_id,
                player2_id=None,
                is_bye=True,
                status="completed",
                winner_id=attempt.user_id,
            )
            db.session.add(match)

        # Set match scores based on challenge performance
        rack_difference = attempt.get_rack_difference_equivalent()
        match.player1_score = max(1, rack_difference)  # At least 1 for the win
        match.player2_score = 0  # X gets 0

        db.session.commit()

    @staticmethod
    def get_admin_statistics() -> List[Dict[str, Any]]:
        """Get statistics for all challenges (admin view)."""
        challenges = Challenge.query.all()
        return [
            {"challenge": challenge, "stats": challenge.get_statistics()}
            for challenge in challenges
        ]

    @staticmethod
    def get_user_challenge_history(user_id: int) -> List[ChallengeAttempt]:
        """Get user's complete challenge attempt history."""
        return (
            ChallengeAttempt.query.filter_by(user_id=user_id, completed=True)
            .order_by(desc("attempted_at"))
            .all()
        )

    @staticmethod
    def update_challenge(
        challenge_id: int,
        name: Optional[str] = None,
        description: Optional[str] = None,
        image_path: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> Challenge:
        """Update challenge details."""
        challenge = db.session.get(Challenge, challenge_id)
        if not challenge:
            from flask import abort

            abort(404)

        if name is not None:
            challenge.name = name
        if description is not None:
            challenge.description = description
        if image_path is not None:
            challenge.image_path = image_path
        if is_active is not None:
            challenge.is_active = is_active

        db.session.commit()
        return challenge

    @staticmethod
    def delete_challenge(challenge_id: int) -> None:
        """Delete a challenge (soft delete by marking inactive)."""
        challenge = db.session.get(Challenge, challenge_id)
        if not challenge:
            from flask import abort

            abort(404)
        challenge.is_active = False
        db.session.commit()
