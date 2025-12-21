"""
Module: models/individual_match/availability_service.py
Purpose: Service layer for player availability and match request management
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any

from models.base import db, transactional
from models.individual_match.models import (
    PlayerAvailability,
    MatchProposal,
    ProposalInvitation,
)
from models.location.models import BilliardHall, UserLocationAvailability
from models.user.models import User
from models.notification.factory import NotificationFactory
from models.notification.models import NotificationType, NotificationPriority


class AvailabilityService:
    """Service for managing player availability and match requests."""

    @staticmethod
    @transactional(domain="individual_match")
    def set_player_availability(
        user_id: int,
        location: str,
        is_available: bool = True,
        preferred_days: Optional[List[int]] = None,
        preferred_times: Optional[str] = None,
    ) -> PlayerAvailability:
        """Set player availability preferences for a location."""
        # Check for existing availability
        existing = PlayerAvailability.query.filter_by(
            user_id=user_id, location=location
        ).first()

        if existing:
            existing.is_available = is_available
            existing.preferred_days = (
                json.dumps(preferred_days) if preferred_days else None
            )
            existing.preferred_times = preferred_times
            existing.updated_at = datetime.utcnow()
        else:
            existing = PlayerAvailability(
                user_id=user_id,
                location=location,
                is_available=is_available,
                preferred_days=json.dumps(preferred_days) if preferred_days else None,
                preferred_times=preferred_times,
            )
            db.session.add(existing)

        return existing

    @staticmethod
    @transactional(domain="individual_match")
    def set_venue_availability(
        user_id: int,
        billiard_hall_id: int,
        is_available: bool = True,
        available_days: Optional[List[int]] = None,
        preferred_times: Optional[str] = None,
    ) -> UserLocationAvailability:
        """Set player availability for a specific venue."""
        from datetime import time

        # Parse preferred_times if provided (format: "HH:MM-HH:MM"). TODO: bisogna assicurarsi che l'interfaccia forzi questo formato
        preferred_time_start = None
        preferred_time_end = None
        if preferred_times:
            try:
                start_str, end_str = preferred_times.split("-")
                start_hour, start_min = map(int, start_str.split(":"))
                end_hour, end_min = map(int, end_str.split(":"))
                preferred_time_start = time(start_hour, start_min)
                preferred_time_end = time(end_hour, end_min)
            except (ValueError, AttributeError):
                pass  # Invalid format, ignore

        # Check for existing availability
        existing = UserLocationAvailability.query.filter_by(
            user_id=user_id, billiard_hall_id=billiard_hall_id
        ).first()

        if existing:
            existing.is_available = is_available
            existing.available_days = (
                json.dumps(available_days) if available_days else None
            )
            existing.preferred_time_start = preferred_time_start
            existing.preferred_time_end = preferred_time_end
            existing.updated_at = datetime.utcnow()
        else:
            existing = UserLocationAvailability(
                user_id=user_id,
                billiard_hall_id=billiard_hall_id,
                is_available=is_available,
                available_days=json.dumps(available_days) if available_days else None,
                preferred_time_start=preferred_time_start,
                preferred_time_end=preferred_time_end,
            )
            db.session.add(existing)

        return existing

    @staticmethod
    def get_available_players_at_location(
        location: str, exclude_user_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Get players available at a specific location."""
        query = (
            db.session.query(PlayerAvailability, User)
            .join(User, PlayerAvailability.user_id == User.id)
            .filter(
                PlayerAvailability.location == location,
                PlayerAvailability.is_available == True,
            )
        )

        if exclude_user_id:
            query = query.filter(User.id != exclude_user_id)

        results = query.all()

        players = []
        for availability, user in results:
            preferred_days = None
            if availability.preferred_days:
                try:
                    preferred_days = json.loads(availability.preferred_days)
                except (json.JSONDecodeError, TypeError):
                    preferred_days = None

            players.append(
                {
                    "user_id": user.id,
                    "username": user.username,
                    "location": availability.location,
                    "preferred_days": preferred_days,
                    "preferred_times": availability.preferred_times,
                    "updated_at": availability.updated_at,
                }
            )

        return players

    @staticmethod
    def get_available_players_at_venue(
        billiard_hall_id: int, exclude_user_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Get players available at a specific venue."""
        query = (
            db.session.query(UserLocationAvailability, User, BilliardHall)
            .join(User, UserLocationAvailability.user_id == User.id)
            .join(
                BilliardHall,
                UserLocationAvailability.billiard_hall_id == BilliardHall.id,
            )
            .filter(
                UserLocationAvailability.billiard_hall_id == billiard_hall_id,
                UserLocationAvailability.is_available == True,
            )
        )

        if exclude_user_id:
            query = query.filter(User.id != exclude_user_id)

        results = query.all()

        players = []
        for availability, user, venue in results:
            available_days = None
            if availability.available_days:
                try:
                    available_days = json.loads(availability.available_days)
                except (json.JSONDecodeError, TypeError):
                    available_days = None

            # Format preferred times back to string format
            preferred_times_str = None
            if availability.preferred_time_start and availability.preferred_time_end:
                preferred_times_str = f"{availability.preferred_time_start.strftime('%H:%M')}-{availability.preferred_time_end.strftime('%H:%M')}"

            players.append(
                {
                    "user_id": user.id,
                    "username": user.username,
                    "venue_id": venue.id,
                    "venue_name": venue.name,
                    "available_days": available_days,
                    "preferred_times": preferred_times_str,
                    "updated_at": availability.updated_at,
                }
            )

        return players

    @staticmethod
    @transactional(domain="individual_match")
    def notify_players_of_availability(
        user_id: int, location: str, message: Optional[str] = None
    ) -> int:
        """Notify players who have played at this location about availability."""
        # Find users who have played at this location before
        from models.individual_match.models import IndividualMatch

        # Get users who have played individual matches at this location
        played_at_location = (
            db.session.query(User)
            .join(
                IndividualMatch,
                db.or_(
                    IndividualMatch.player1_id == User.id,
                    IndividualMatch.player2_id == User.id,
                ),
            )
            .filter(
                IndividualMatch.location == location,
                User.id != user_id,  # Exclude the user posting availability
                User.deleted_at.is_(None),  # Only active users
            )
            .distinct()
            .all()
        )

        # Create notification for each user
        notifications_sent = 0
        requesting_user = db.session.get(User, user_id)

        default_message = (
            f"{requesting_user.username} è disponibile a giocare presso {location}"
        )
        notification_message = message or default_message

        # Use NotificationFactory for bulk notification with error handling
        user_ids = [user.id for user in played_at_location]
        notifications = NotificationFactory.create_bulk_notification(
            user_ids=user_ids,
            notification_type=NotificationType.MATCH_PROPOSAL,
            title="Giocatore Disponibile",
            message=notification_message,
            priority=NotificationPriority.NORMAL,
            continue_on_error=True,
        )

        # Count successful notifications
        stats = NotificationFactory.get_notification_stats(notifications)
        notifications_sent = stats["successful"]

        return notifications_sent

    @staticmethod
    def get_user_availability_preferences(user_id: int) -> Dict[str, Any]:
        """Get all availability preferences for a user."""
        # Get location-based availability
        location_availabilities = PlayerAvailability.query.filter_by(
            user_id=user_id, is_available=True
        ).all()

        # Get venue-based availability
        venue_availabilities = (
            db.session.query(UserLocationAvailability, BilliardHall)
            .join(BilliardHall)
            .filter(
                UserLocationAvailability.user_id == user_id,
                UserLocationAvailability.is_available == True,
            )
            .all()
        )

        locations = []
        for availability in location_availabilities:
            preferred_days = None
            if availability.preferred_days:
                try:
                    preferred_days = json.loads(availability.preferred_days)
                except (json.JSONDecodeError, TypeError):
                    preferred_days = None

            locations.append(
                {
                    "id": availability.id,
                    "location": availability.location,
                    "preferred_days": preferred_days,
                    "preferred_times": availability.preferred_times,
                    "type": "location",
                }
            )

        venues = []
        for availability, venue in venue_availabilities:
            available_days = None
            if availability.available_days:
                try:
                    available_days = json.loads(availability.available_days)
                except (json.JSONDecodeError, TypeError):
                    available_days = None

            # Format preferred times back to string format
            preferred_times_str = None
            if availability.preferred_time_start and availability.preferred_time_end:
                preferred_times_str = f"{availability.preferred_time_start.strftime('%H:%M')}-{availability.preferred_time_end.strftime('%H:%M')}"

            venues.append(
                {
                    "id": availability.id,
                    "venue_id": venue.id,
                    "venue_name": venue.name,
                    "available_days": available_days,
                    "preferred_times": preferred_times_str,
                    "type": "venue",
                }
            )

        return {"locations": locations, "venues": venues}

    @staticmethod
    @transactional(domain="individual_match")
    def create_availability_based_match_request(
        requesting_user_id: int,
        target_user_id: int,
        location: str,
        proposed_datetime: Optional[datetime] = None,
        message: Optional[str] = None,
    ) -> MatchProposal:
        """Create a match request based on availability discovery."""
        from models.individual_match.services import IndividualMatchService
        from datetime import datetime, timedelta

        # Use a future datetime if none provided
        if proposed_datetime is None:
            proposed_datetime = datetime.now() + timedelta(days=1)

        # Create direct match proposal to target user
        proposal = IndividualMatchService.create_direct_proposal(
            proposer_id=requesting_user_id,
            invited_user_ids=[target_user_id],
            location=location,
            scheduled_at=proposed_datetime,
            description=message or "Richiesta di match basata su disponibilità",
            discipline="palla_8",  # Default
            distance=7,  # Default
            is_race_to=True,
            entry_fee=0.0,
        )

        return proposal
