"""
Module: models/challenge/services.py
Purpose: Challenge domain services for business logic
Requirements: SPECIFICHE.md - Challenge management and statistics
"""

from __future__ import annotations

from typing import List, Optional, Dict, Any
from sqlalchemy import desc

from ..base import db
from ..transaction.manager import transactional
from .models import Challenge, ChallengeAttempt, ChallengeFavorite


class ChallengeService:
    """Service for challenge management and business logic.

    Handles the complete challenge ecosystem for skill development including:
    - Core challenge lifecycle (creation, attempts, completion)
    - Challenge catalog organization (favorites, user attempts, general)
    - X-replacement system for tournament bye substitution
    - Challenge statistics and administrative oversight
    - Smart deletion with usage history preservation

    Business Logic:
    - Challenges support both scoring (numeric) and pass/fail modes
    - X-replacement challenges substitute player absence in tournaments
    - Challenge scores convert to rack differences for tournament integration
    - Favorite system provides personalized challenge discovery
    - Soft deletion preserves historical data when challenges have been used
    """

    @staticmethod
    @transactional(domain="challenge")
    def create_challenge(
        description: str,
        image_path: str,
        pass_fail_only: bool = False,
        created_by_id: Optional[int] = None,
    ) -> Challenge:
        """Create a new challenge for the community skill development system.

        Creates a challenge that can be used for individual skill testing or
        as X-replacement in tournaments. All challenges are active by default.

        Args:
            description: Challenge description and instructions for players
            image_path: Path to challenge diagram or reference image
            pass_fail_only: True for binary pass/fail, False for numeric scoring
            created_by_id: Optional admin/director who created the challenge

        Returns:
            Newly created Challenge instance with active status

        Business Logic:
            - Numeric scoring challenges can be used for X-replacement
            - Pass/fail challenges are limited to individual skill testing
            - Created challenges are immediately available in catalog
        """
        challenge = Challenge(
            description=description,
            pass_fail_only=pass_fail_only,
            image_path=image_path,
            created_by_id=created_by_id,
        )

        db.session.add(challenge)
        return challenge

    @staticmethod
    def get_all_challenges() -> List[Challenge]:
        """Get all challenges including inactive ones (admin view only).

        Returns all challenges regardless of active status for administrative
        oversight and challenge management.
        """
        return db.session.query(Challenge).all()

    @staticmethod
    def get_active_challenges() -> List[Challenge]:
        """Get all active challenges visible to players.

        Returns only active challenges that appear in public catalogs
        and can be attempted by players or used for X-replacement.
        """
        return db.session.query(Challenge).filter_by(is_active=True).all()

    @staticmethod
    def get_user_challenges(user_id: int) -> Dict[str, List[Challenge]]:
        """Get challenges organized by user relationship for personalized experience.

        Organizes active challenges into categories based on user interaction:
        - favorites: User-marked preferred challenges for quick access
        - attempted: Challenges user has previously attempted (skill tracking)
        - general: New challenges user hasn't attempted yet (discovery)

        Args:
            user_id: Target player's user ID

        Returns:
            Dictionary with categorized challenge lists for UI organization

        Business Logic:
            - Only active challenges appear in any category
            - Attempted status is based on any previous attempt (completed or not)
            - General catalog excludes attempted challenges for clean discovery
        """
        # Get all active challenges as base dataset
        all_challenges = ChallengeService.get_active_challenges()

        # Build user's favorites set for quick lookup
        favorite_ids = {
            fav.challenge_id
            for fav in db.session.query(ChallengeFavorite)
            .filter_by(user_id=user_id)
            .all()
        }
        favorites = [c for c in all_challenges if c.id in favorite_ids]

        # Build attempted challenges set (any attempt regardless of completion)
        attempted_ids = {
            att.challenge_id
            for att in db.session.query(ChallengeAttempt)
            .filter_by(user_id=user_id)
            .all()
        }
        attempted = [c for c in all_challenges if c.id in attempted_ids]

        # General catalog shows undiscovered challenges only
        general = [c for c in all_challenges if c.id not in attempted_ids]

        return {"favorites": favorites, "attempted": attempted, "general": general}

    @staticmethod
    def get_catalog_data(user_id: Optional[int] = None) -> Dict[str, Any]:
        """Get complete challenge catalog data for UI rendering.

        Provides comprehensive challenge dataset for catalog pages including
        global challenge list and user-specific organization when authenticated.

        Args:
            user_id: Optional authenticated user for personalized data

        Returns:
            Complete catalog structure with active challenges and user context

        Business Logic:
            - Anonymous users see all active challenges only
            - Authenticated users get personalized organization and favorites
            - Only active challenges appear to maintain clean catalog
            - My challenges shows user-created active challenges only
        """
        # Base dataset: all active challenges for public catalog
        all_challenges = ChallengeService.get_active_challenges()

        # Initialize result with public data structure
        result = {
            "all_challenges": all_challenges,
            "my_challenges": [],
            "favorite_challenges": [],
            "user_favorites": set(),
        }

        # Add personalized data for authenticated users
        if user_id:
            # Get challenges created by this user (active only)
            my_challenges = (
                db.session.query(Challenge)
                .filter_by(created_by_id=user_id, is_active=True)
                .all()
            )
            result["my_challenges"] = my_challenges

            # Get user's favorited challenges (intersection with active challenges)
            favorite_ids = {
                fav.challenge_id
                for fav in db.session.query(ChallengeFavorite)
                .filter_by(user_id=user_id)
                .all()
            }
            result["user_favorites"] = favorite_ids
            result["favorite_challenges"] = [
                c for c in all_challenges if c.id in favorite_ids
            ]

        return result

    @staticmethod
    @transactional(domain="challenge")
    def start_challenge_attempt(
        user_id: int,
        challenge_id: int,
        gara_id: Optional[int] = None,
        round_number: Optional[int] = None,
    ) -> ChallengeAttempt:
        """Start a new challenge attempt for skill testing or tournament integration.

        Creates a challenge attempt record to track player performance against
        specific challenges. Can be used for individual skill development or
        as X-replacement in tournament contexts.

        Args:
            user_id: Player attempting the challenge
            challenge_id: Target challenge to attempt
            gara_id: Optional tournament context for X-replacement
            round_number: Optional round context for tournament integration

        Returns:
            New ChallengeAttempt in pending state (not yet completed)

        Business Logic:
            - Individual attempts have no gara_id/round_number
            - X-replacement attempts include tournament context
            - Multiple attempts per challenge per user are allowed
            - Attempt timing is tracked for performance analysis
        """
        attempt = ChallengeAttempt(
            user_id=user_id,
            challenge_id=challenge_id,
            gara_id=gara_id,
            round_number=round_number,
        )

        db.session.add(attempt)
        return attempt

    @staticmethod
    @transactional(domain="challenge")
    def complete_challenge_attempt(
        attempt_id: int,
        score: Optional[int] = None,
        passed: Optional[bool] = None,
        notes: Optional[str] = None,
    ) -> ChallengeAttempt:
        """Complete a challenge attempt with player performance results.

        Records the final results of a challenge attempt including score,
        pass/fail status, and optional notes for player feedback.

        Args:
            attempt_id: Target attempt to complete
            score: Numeric score for scoring challenges (0-100+ scale)
            passed: Boolean result for pass/fail challenges
            notes: Optional performance notes or feedback

        Returns:
            Completed ChallengeAttempt with results and completion timestamp

        Raises:
            404: Attempt not found

        Business Logic:
            - Scoring challenges use numeric score (passed calculated automatically)
            - Pass/fail challenges use boolean passed flag directly
            - Completion marks attempt as finished and timestamps it
            - Notes provide additional context for player improvement
        """
        attempt = db.session.get(ChallengeAttempt, attempt_id)
        if not attempt:
            from flask import abort

            abort(404)

        # Complete the attempt with performance data
        attempt.complete_attempt(score=score, passed=passed)

        # Add optional performance notes
        if notes:
            attempt.notes = notes

        return attempt

    @staticmethod
    @transactional(domain="challenge")
    def toggle_favorite(user_id: int, challenge_id: int) -> bool:
        """Toggle challenge favorite status for personalized challenge discovery.

        Manages user's favorite challenges for quick access and personalized
        challenge organization in the catalog interface.

        Args:
            user_id: Player managing favorites
            challenge_id: Challenge to toggle favorite status

        Returns:
            True if challenge was added to favorites, False if removed

        Business Logic:
            - Favorite status is per-user and independent of attempts
            - Favorites persist across challenge attempts and completions
            - Toggling removes existing favorites or creates new ones
            - Favorites enhance user experience but don't affect challenge logic
        """
        # Check for existing favorite relationship
        favorite = (
            db.session.query(ChallengeFavorite)
            .filter_by(user_id=user_id, challenge_id=challenge_id)
            .first()
        )

        if favorite:
            # Remove existing favorite
            db.session.delete(favorite)
            return False
        else:
            # Create new favorite relationship
            favorite = ChallengeFavorite(user_id=user_id, challenge_id=challenge_id)
            db.session.add(favorite)
            return True

    @staticmethod
    def get_challenge_for_x_replacement(gara_id: int) -> Optional[Challenge]:
        """Select optimal challenge for X-replacement in tournament context.

        Finds the most suitable challenge to substitute for player absence (X)
        in tournament rounds. Prioritizes challenges with least usage in the
        current tournament for fair distribution.

        Args:
            gara_id: Tournament context for usage analysis

        Returns:
            Best available challenge for X-replacement, None if none suitable

        Business Logic:
            - Only numeric scoring challenges can be used (not pass/fail)
            - Challenges must be active for tournament use
            - Algorithm minimizes repeated challenge usage per tournament
            - Fair distribution ensures varied skill testing across rounds
        """
        # Find challenges eligible for X-replacement (numeric scoring only)
        suitable_challenges = (
            db.session.query(Challenge)
            .filter_by(is_active=True, pass_fail_only=False)
            .all()
        )

        if not suitable_challenges:
            return None

        # Calculate usage frequency per challenge in this tournament
        challenge_usage = {}
        for challenge in suitable_challenges:
            usage_count = (
                db.session.query(ChallengeAttempt)
                .filter_by(challenge_id=challenge.id, gara_id=gara_id)
                .count()
            )
            challenge_usage[challenge.id] = usage_count

        # Select least used challenge for fair distribution
        min_usage = min(challenge_usage.values())
        for challenge in suitable_challenges:
            if challenge_usage[challenge.id] == min_usage:
                return challenge

        # Fallback to first available (should not reach here)
        return suitable_challenges[0]

    @staticmethod
    def create_x_replacement_attempt(
        user_id: int,
        gara_id: int,
        round_number: int,
        challenge_id: Optional[int] = None,
    ) -> ChallengeAttempt:
        """Create challenge attempt for X-replacement in tournament context.

        Initiates a challenge attempt to substitute for player absence (X) in
        tournament rounds. Automatically selects optimal challenge if none specified.

        Args:
            user_id: Player performing X-replacement
            gara_id: Tournament context
            round_number: Specific round for replacement
            challenge_id: Optional specific challenge, auto-selected if None

        Returns:
            New ChallengeAttempt ready for completion

        Raises:
            ValueError: No suitable challenges available for X-replacement

        Business Logic:
            - Auto-selection prioritizes least-used challenges in tournament
            - X-replacement attempts include tournament context for classification
            - Challenge must support numeric scoring for tournament integration
        """

        # Determine challenge to use (auto-select or use specified)
        final_challenge_id: int
        if challenge_id is None:
            # Auto-select optimal challenge for this tournament
            challenge = ChallengeService.get_challenge_for_x_replacement(gara_id)
            if not challenge:
                raise ValueError("No suitable challenge available for X replacement")
            final_challenge_id = challenge.id
        else:
            # Use explicitly specified challenge
            final_challenge_id = challenge_id

        # Create attempt with tournament context
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
        """Complete X-replacement challenge and create tournament classification entry.

        Finalizes an X-replacement challenge attempt and generates equivalent
        match result for tournament classification integration.

        Args:
            attempt_id: Target X-replacement attempt to complete
            score: Challenge performance score
            notes: Optional performance notes

        Returns:
            Completed attempt with tournament match result created

        Raises:
            404: Attempt not found

        Business Logic:
            - Challenge score converts to rack difference for tournament ranking
            - Creates bye match with player as automatic winner
            - Integration ensures X-replacement appears in tournament classification
            - Maintains tournament bracket integrity with challenge substitution
        """

        attempt = db.session.get(ChallengeAttempt, attempt_id)
        if not attempt:
            from flask import abort

            abort(404)

        # Complete the challenge attempt with score
        attempt.complete_attempt(score=score, passed=None)

        # Add optional performance notes
        if notes:
            attempt.notes = notes

        # Generate equivalent match result for tournament classification
        ChallengeService._create_x_replacement_match_result(attempt)

        return attempt

    @staticmethod
    @transactional(domain="challenge")
    def _create_x_replacement_match_result(attempt: ChallengeAttempt) -> None:
        """Create tournament match equivalent for X-replacement challenge integration.

        Generates a bye match record that integrates challenge performance into
        tournament classification system. Challenge score converts to rack
        difference for consistent tournament ranking.

        Args:
            attempt: Completed X-replacement challenge attempt

        Business Logic:
            - Creates bye match with challenge player as winner
            - Challenge score converts to rack difference via model method
            - Player1 gets challenge-derived score, X (player2) gets 0
            - Match marked as completed bye for classification integration
            - Ensures tournament bracket integrity with challenge substitution
        """
        from ..match.models import Match

        # Find existing X-replacement match or create new one
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
            # Create new bye match for X-replacement
            match = Match(
                gara_id=attempt.gara_id,
                round_number=attempt.round_number,
                player1_id=attempt.user_id,
                player2_id=None,  # X (absent player)
                is_bye=True,
                status="completed",
                winner_id=attempt.user_id,  # Challenge player wins by default
            )
            db.session.add(match)

        # Convert challenge score to tournament-compatible rack scores
        rack_difference = attempt.get_rack_difference_equivalent()
        match.player1_score = max(1, rack_difference)  # Minimum 1 rack for win
        match.player2_score = 0  # X (absent player) gets 0 racks

    @staticmethod
    def get_admin_statistics() -> List[Dict[str, Any]]:
        """Get comprehensive challenge statistics for administrative oversight.

        Provides detailed analytics for all challenges including usage patterns,
        performance metrics, and player engagement data for system administration.

        Returns:
            List of challenge statistics dictionaries for admin dashboard

        Business Logic:
            - Includes both active and inactive challenges for complete oversight
            - Statistics cover attempts, unique players, scores, and pass rates
            - Data supports challenge effectiveness evaluation and curation
        """
        challenges = Challenge.query.all()
        return [
            {"challenge": challenge, "stats": challenge.get_statistics()}
            for challenge in challenges
        ]

    @staticmethod
    def get_user_challenge_history(user_id: int) -> List[ChallengeAttempt]:
        """Get user's complete challenge attempt history for skill tracking.

        Retrieves chronological history of all completed challenge attempts
        for player skill development analysis and progress tracking.

        Args:
            user_id: Target player's user ID

        Returns:
            Completed attempts ordered by most recent first

        Business Logic:
            - Only completed attempts are included (not pending ones)
            - Chronological order supports skill progression analysis
            - Includes both individual and X-replacement attempts
        """
        return (
            ChallengeAttempt.query.filter_by(user_id=user_id, completed=True)
            .order_by(desc("attempted_at"))
            .all()
        )

    @staticmethod
    @transactional(domain="challenge")
    def delete_challenge(challenge_id: int) -> None:
        """Delete challenge with intelligent data preservation strategy.

        Implements smart deletion that preserves historical data integrity:
        - Hard deletion for unused challenges (complete removal)
        - Soft deletion for used challenges (hide but preserve history)

        Args:
            challenge_id: Challenge to delete

        Raises:
            404: Challenge not found

        Business Logic:
            - Hard delete: No attempts or tournament usage (safe removal)
            - Soft delete: Has attempts or tournament history (preserve data)
            - Soft deleted challenges disappear from catalogs but maintain history
            - Preserves player attempt records and tournament integrity
        """
        challenge = db.session.get(Challenge, challenge_id)
        if not challenge:
            from flask import abort

            abort(404)

        # Check for player attempt history
        has_attempts = (
            db.session.query(ChallengeAttempt)
            .filter_by(challenge_id=challenge_id)
            .first()
            is not None
        )

        # Check for tournament integration usage (if gara relationships exist)
        has_gara_usage = False
        try:
            from .gara_challenge_models import GaraChallenge

            has_gara_usage = (
                db.session.query(GaraChallenge)
                .filter_by(challenge_id=challenge_id)
                .first()
                is not None
            )
        except ImportError:
            # No tournament relationship model exists, skip check
            pass

        # Apply appropriate deletion strategy
        if not has_attempts and not has_gara_usage:
            # Hard delete: Challenge never used, safe to remove completely
            db.session.delete(challenge)
        else:
            # Soft delete: Challenge has history, preserve data but hide from catalogs
            challenge.is_active = False

    @staticmethod
    def record_attempt(
        user_id: int,
        challenge_id: int,
        score: int,
        max_score: int = 100,
        gara_id: Optional[int] = None,
        round_number: Optional[int] = None,
        notes: Optional[str] = None,
    ) -> ChallengeAttempt:
        """Convenience method for complete challenge attempt recording.

        Single-call interface that combines attempt creation and completion
        for streamlined challenge recording workflows.

        Args:
            user_id: Player attempting challenge
            challenge_id: Target challenge
            score: Performance score achieved
            max_score: Maximum possible score (default 100)
            gara_id: Optional tournament context
            round_number: Optional round context
            notes: Optional performance notes

        Returns:
            Completed ChallengeAttempt with results

        Business Logic:
            - Automatically calculates pass/fail based on 70% threshold
            - Combines start_challenge_attempt and complete_challenge_attempt
            - Useful for batch recording or simplified API endpoints
            - Transaction safety maintained through service method calls
        """
        # Create and start the challenge attempt
        attempt = ChallengeService.start_challenge_attempt(
            user_id=user_id,
            challenge_id=challenge_id,
            gara_id=gara_id,
            round_number=round_number,
        )

        # Calculate pass/fail status using 70% threshold
        passed = score >= (max_score * 0.7)

        # Complete the attempt with results
        completed_attempt = ChallengeService.complete_challenge_attempt(
            attempt_id=attempt.id,
            score=score,
            passed=passed,
            notes=notes,
        )

        return completed_attempt
