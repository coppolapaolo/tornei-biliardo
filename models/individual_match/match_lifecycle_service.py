"""
Module: models/individual_match/match_lifecycle_service.py
Purpose: Match lifecycle management service (extracted from IndividualMatchService)
Sprint 13: IndividualMatchService decomposition
"""

from __future__ import annotations

from datetime import timedelta
from typing import Optional, List

from ..base import db, utc_now
from ..transaction.manager import transactional
from ..status_enum import MatchStatus
from .models import IndividualMatch


class MatchLifecycleService:
    """Service for individual match lifecycle management."""

    @staticmethod
    @transactional(domain="individual_match")
    def start_match(match_id: int, user_id: int) -> IndividualMatch:
        """Start an individual match (must be one of the players)."""
        match = db.session.get(IndividualMatch, match_id)
        if match is None:
            raise ValueError("Match non trovato")

        if user_id not in [match.player1_id, match.player2_id]:
            raise ValueError("Only match players can start the match")

        match.start_match()
        return match

    @staticmethod
    @transactional(domain="individual_match")
    def confirm_match_result(match_id: int, user_id: int) -> IndividualMatch:
        """Confirm match result by a player (new UX)."""
        match = db.session.get(IndividualMatch, match_id)
        if match is None:
            raise ValueError("Match non trovato")

        if user_id not in [match.player1_id, match.player2_id]:
            raise ValueError("Only match players can confirm the result")

        if not match.is_ready_for_validation():
            raise ValueError("Match is not ready for validation")

        match.confirm_result(user_id)
        return match

    @staticmethod
    @transactional(domain="individual_match")
    def reject_match_result(match_id: int, user_id: int) -> IndividualMatch:
        """Reject match result - removes last rack (new UX)."""
        match = db.session.get(IndividualMatch, match_id)
        if match is None:
            raise ValueError("Match non trovato")

        if user_id not in [match.player1_id, match.player2_id]:
            raise ValueError("Only match players can reject the result")

        if not match.is_ready_for_validation():
            raise ValueError("Match is not ready for validation")

        match.reject_result(user_id)
        return match

    @staticmethod
    @transactional(domain="individual_match")
    def complete_match(match_id: int, winner_id: int, user_id: int) -> IndividualMatch:
        """Complete a match - legacy method for backward compatibility."""
        match = db.session.get(IndividualMatch, match_id)
        if match is None:
            raise ValueError("Match non trovato")

        if user_id not in [match.player1_id, match.player2_id]:
            raise ValueError("Only match players can complete the match")

        match.complete_match(winner_id)
        return match

    @staticmethod
    @transactional(domain="individual_match")
    def complete_individual_match(
        match_id: int, winner_id: int, user_id: int
    ) -> IndividualMatch:
        """Complete an individual match - alias for complete_match."""
        return MatchLifecycleService.complete_match(match_id, winner_id, user_id)

    @staticmethod
    @transactional(domain="individual_match")
    def cancel_match(
        match_id: int, user_id: int, reason: Optional[str] = None
    ) -> IndividualMatch:
        """Cancel a match (must be one of the players)."""
        match = db.session.get(IndividualMatch, match_id)
        if match is None:
            raise ValueError("Match non trovato")

        if user_id not in [match.player1_id, match.player2_id]:
            raise ValueError("Only match players can cancel the match")

        match.cancel_match(reason)
        return match

    @staticmethod
    @transactional(domain="individual_match")
    def forfeit_match(match_id: int, user_id: int) -> IndividualMatch:
        """Forfeit an individual match - user loses, opponent wins.

        The forfeiting player keeps their current score (racks already won).
        The opponent receives the winning score (distance).

        Args:
            match_id: ID of the match
            user_id: ID of player forfeiting

        Returns:
            The updated IndividualMatch object

        Raises:
            ValueError: If invalid forfeit conditions
        """
        match = db.session.get(IndividualMatch, match_id)
        if match is None:
            raise ValueError("Match non trovato")

        # Delegate to model method which handles all validation and logic
        match.forfeit_match(user_id)
        return match

    @staticmethod
    def send_match_reminders(
        hours_before: int = 2, window_minutes: int = 15
    ) -> List[int]:
        """Send reminder notifications for upcoming matches.

        Finds matches scheduled within a time window and sends reminders
        to both players. Designed to be called periodically (e.g., every 15 min).

        Args:
            hours_before: Hours before match to send reminder (default 2)
            window_minutes: Time window in minutes to check (default 15)

        Returns:
            List of match IDs that received reminders
        """
        from flask_babel import _
        from ..notification.factory import NotificationFactory
        from ..notification.models import NotificationType, NotificationPriority

        now = utc_now()
        window_start = now + timedelta(hours=hours_before)
        window_end = window_start + timedelta(minutes=window_minutes)

        # Find matches in the reminder window with status SCHEDULED
        upcoming_matches = IndividualMatch.query.filter(
            IndividualMatch.scheduled_at.between(window_start, window_end),
            IndividualMatch.status == MatchStatus.SCHEDULED.value,
        ).all()

        reminded_match_ids: List[int] = []

        for match in upcoming_matches:
            # Get both player IDs
            player_ids = [match.player1_id, match.player2_id]

            # Format time for message
            time_str = match.scheduled_at.strftime("%H:%M")
            location_text = match.location or ""

            try:
                NotificationFactory.create_bulk_notification(
                    user_ids=player_ids,
                    notification_type=NotificationType.MATCH_REMINDER,
                    title=_("Match tra 2 ore"),
                    message=_(
                        "Il tuo match è programmato per le %(time)s%(location)s",
                        time=time_str,
                        location=f" presso {location_text}" if location_text else "",
                    ),
                    priority=NotificationPriority.HIGH,
                    action_url=f"/match/matches/{match.id}",
                    action_text=_("Visualizza"),
                    continue_on_error=True,
                )
                reminded_match_ids.append(match.id)
            except Exception:
                # Log but don't fail on notification errors
                pass

        return reminded_match_ids
