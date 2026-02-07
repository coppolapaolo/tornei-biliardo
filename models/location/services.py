"""
Module: models/location/services.py
Purpose: Location domain services for billiard hall management
Requirements: SPECIFICHE.md - Location-based match organization
"""

from __future__ import annotations

from typing import List, Optional, Dict, Any
from datetime import datetime

from ..base import db, utc_now
from ..transaction.manager import transactional
from .models import BilliardHall, UserLocationAvailability, DayOfWeek


class LocationService:
    """Service for location and availability management."""

    @staticmethod
    @transactional(domain="location")
    def create_billiard_hall(
        name: str,
        address: Optional[str] = None,
        city: Optional[str] = None,
        postal_code: Optional[str] = None,
        country: str = "Italy",
        phone: Optional[str] = None,
        email: Optional[str] = None,
        website: Optional[str] = None,
        number_of_tables: Optional[int] = None,
        table_types: Optional[List[str]] = None,
        amenities: Optional[List[str]] = None,
        hourly_rate: Optional[float] = None,
        added_by_id: Optional[int] = None,
        business_hours: Optional[str] = None,
    ) -> BilliardHall:
        """Create a new billiard hall."""

        hall = BilliardHall(
            name=name,
            address=address,
            city=city,
            postal_code=postal_code,
            country=country,
            phone=phone,
            email=email,
            website=website,
            number_of_tables=number_of_tables,
            hourly_rate=hourly_rate,
            added_by_id=added_by_id,
        )

        if business_hours:
            hall.business_hours = business_hours

        if table_types:
            hall.set_table_types(table_types)

        if amenities:
            hall.set_amenities(amenities)

        db.session.add(hall)

        return hall

    @staticmethod
    def get_nearby_halls(
        city: Optional[str] = None, country: str = "Italy", verified_only: bool = False
    ) -> List[BilliardHall]:
        """Get billiard halls in a specific area."""

        query = BilliardHall.query.filter_by(is_active=True)

        if city:
            query = query.filter(BilliardHall.city.ilike(f"%{city}%"))

        if country:
            query = query.filter_by(country=country)

        if verified_only:
            query = query.filter_by(verified=True)

        return query.order_by(BilliardHall.name).all()

    @staticmethod
    @transactional(domain="location")
    def set_user_availability(
        user_id: int,
        billiard_hall_id: int,
        is_available: bool = True,
        available_days: Optional[List[DayOfWeek]] = None,
        preferred_time_start: Optional[str] = None,
        preferred_time_end: Optional[str] = None,
        advance_notice_hours: int = 24,
        notify_on_proposals: bool = True,
    ) -> UserLocationAvailability:
        """Set or update user availability for a billiard hall."""

        availability = UserLocationAvailability.query.filter_by(
            user_id=user_id, billiard_hall_id=billiard_hall_id
        ).first()

        if availability:
            availability.is_available = is_available
            availability.advance_notice_hours = advance_notice_hours
            availability.notify_on_proposals = notify_on_proposals
        else:
            availability = UserLocationAvailability(
                user_id=user_id,
                billiard_hall_id=billiard_hall_id,
                is_available=is_available,
                advance_notice_hours=advance_notice_hours,
                notify_on_proposals=notify_on_proposals,
            )
            db.session.add(availability)

        # Set available days
        if available_days:
            availability.set_available_days(available_days)

        # Parse time preferences
        if preferred_time_start:
            try:
                availability.preferred_time_start = datetime.strptime(
                    preferred_time_start, "%H:%M"
                ).time()
            except ValueError:
                pass

        if preferred_time_end:
            try:
                availability.preferred_time_end = datetime.strptime(
                    preferred_time_end, "%H:%M"
                ).time()
            except ValueError:
                pass

        return availability

    @staticmethod
    def get_user_locations(user_id: int) -> List[Dict[str, Any]]:
        """Get all locations where user is available."""

        availabilities = (
            UserLocationAvailability.query.filter_by(user_id=user_id, is_available=True)
            .join(BilliardHall)
            .filter(BilliardHall.is_active.is_(True))
            .all()
        )

        locations = []
        for availability in availabilities:
            locations.append(
                {
                    "billiard_hall": availability.billiard_hall,
                    "availability": availability.get_availability_summary(),
                }
            )

        return locations

    @staticmethod
    def find_available_players(
        billiard_hall_id: int,
        proposed_datetime: datetime,
        exclude_user_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Find players available at a specific hall and time."""

        availabilities = (
            UserLocationAvailability.query.filter_by(
                billiard_hall_id=billiard_hall_id, is_available=True
            )
            .join(BilliardHall)
            .filter(BilliardHall.is_active.is_(True))
            .all()
        )

        available_players = []

        for availability in availabilities:
            if exclude_user_id and availability.user_id == exclude_user_id:
                continue

            if availability.is_available_at(proposed_datetime):
                available_players.append(
                    {
                        "user": availability.user,
                        "availability": availability,
                        "matches_played_here": availability.matches_played_here,
                        "last_played_at": availability.last_played_at,
                    }
                )

        # Sort by experience at this location (more experienced first)
        available_players.sort(key=lambda x: x["matches_played_here"], reverse=True)

        return available_players

    @staticmethod
    def get_location_statistics(billiard_hall_id: int) -> Dict[str, Any]:
        """Get statistics for a billiard hall."""

        hall = db.session.get(BilliardHall, billiard_hall_id)
        if hall is None:
            from flask import abort

            abort(404)

        # Count active users
        active_users_count = UserLocationAvailability.query.filter_by(
            billiard_hall_id=billiard_hall_id, is_available=True
        ).count()

        # Count total matches played (from individual matches)
        from ..individual_match.models import IndividualMatch

        total_matches = IndividualMatch.query.filter_by(location=hall.name).count()

        return {
            "billiard_hall": hall,
            "active_users_count": active_users_count,
            "total_matches_played": total_matches,
            "table_types": hall.get_table_types(),
            "amenities": hall.get_amenities(),
        }

    @staticmethod
    def suggest_locations_for_match(
        user_id: int,
        opponent_id: Optional[int] = None,
        preferred_city: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Suggest billiard halls for a match between users."""

        suggestions = []

        # Get user's available locations
        user_locations = LocationService.get_user_locations(user_id)
        user_hall_ids = {loc["billiard_hall"].id for loc in user_locations}

        # Get opponent's available locations if specified
        opponent_hall_ids = set()
        if opponent_id:
            opponent_locations = LocationService.get_user_locations(opponent_id)
            opponent_hall_ids = {loc["billiard_hall"].id for loc in opponent_locations}

        # Find common locations
        common_hall_ids = (
            user_hall_ids.intersection(opponent_hall_ids)
            if opponent_id
            else user_hall_ids
        )

        for location_data in user_locations:
            hall = location_data["billiard_hall"]

            # Calculate suitability score
            score = 0

            # Bonus for common locations
            if hall.id in common_hall_ids:
                score += 10

            # Bonus for preferred city
            if (
                preferred_city
                and hall.city
                and preferred_city.lower() in hall.city.lower()
            ):
                score += 5

            # Bonus for user experience at location
            user_availability = next(
                (
                    loc["availability"]
                    for loc in user_locations
                    if loc["billiard_hall"].id == hall.id
                ),
                {},
            )
            matches_played = user_availability.get("matches_played_here", 0)
            score += min(matches_played, 5)  # Max 5 bonus points

            # Bonus for verified halls
            if hall.verified:
                score += 2

            suggestions.append(
                {
                    "billiard_hall": hall,
                    "suitability_score": score,
                    "is_common_location": hall.id in common_hall_ids,
                    "user_matches_played": matches_played,
                    "statistics": LocationService.get_location_statistics(hall.id),
                }
            )

        # Sort by suitability score
        suggestions.sort(key=lambda x: x["suitability_score"], reverse=True)

        return suggestions

    @staticmethod
    @transactional(domain="location")
    def record_match_at_location(user_id: int, location_name: str) -> None:
        """Record that a user played a match at a location."""

        # Find billiard hall by name (fuzzy matching)
        hall = BilliardHall.query.filter(
            BilliardHall.name.ilike(f"%{location_name}%")
        ).first()

        if not hall:
            return

        # Update or create availability record
        availability = UserLocationAvailability.query.filter_by(
            user_id=user_id, billiard_hall_id=hall.id
        ).first()

        if availability:
            availability.record_match_played()
        else:
            # Create new availability record
            availability = UserLocationAvailability(
                user_id=user_id,
                billiard_hall_id=hall.id,
                is_available=True,
                matches_played_here=1,
                last_played_at=utc_now(),
            )
            db.session.add(availability)

    @staticmethod
    @transactional(domain="location")
    def update_billiard_hall(hall_id: int, **kwargs) -> BilliardHall:
        """Update billiard hall information."""

        hall = db.session.get(BilliardHall, hall_id)
        if hall is None:
            from flask import abort

            abort(404)

        # Update simple fields
        simple_fields = [
            "name",
            "address",
            "city",
            "postal_code",
            "country",
            "phone",
            "email",
            "website",
            "number_of_tables",
            "hourly_rate",
            "is_active",
            "verified",
        ]

        for field in simple_fields:
            if field in kwargs:
                setattr(hall, field, kwargs[field])

        # Update complex fields
        if "table_types" in kwargs:
            hall.set_table_types(kwargs["table_types"])

        if "amenities" in kwargs:
            hall.set_amenities(kwargs["amenities"])

        if "business_hours" in kwargs:
            hall.set_business_hours(kwargs["business_hours"])

        return hall

    @staticmethod
    def search_billiard_halls(
        query: str,
        city: Optional[str] = None,
        country: str = "Italy",
        verified_only: bool = False,
    ) -> List[BilliardHall]:
        """Search billiard halls by name or location."""

        search_query = BilliardHall.query.filter(
            BilliardHall.is_active.is_(True),
            db.or_(
                BilliardHall.name.ilike(f"%{query}%"),
                BilliardHall.address.ilike(f"%{query}%"),
                BilliardHall.city.ilike(f"%{query}%"),
            ),
        )

        if city:
            search_query = search_query.filter(BilliardHall.city.ilike(f"%{city}%"))

        if country:
            search_query = search_query.filter_by(country=country)

        if verified_only:
            search_query = search_query.filter_by(verified=True)

        return search_query.order_by(BilliardHall.name).all()

    @staticmethod
    @transactional(domain="location")
    def set_venue_active(venue_id: int, active: bool) -> BilliardHall:
        """Activate or deactivate a venue."""
        venue = db.session.get(BilliardHall, venue_id)
        if not venue:
            raise ValueError(f"Sala con id {venue_id} non trovata")
        venue.is_active = active
        return venue

    @staticmethod
    @transactional(domain="location")
    def set_venue_verified(venue_id: int, verified: bool) -> BilliardHall:
        """Set venue verification status."""
        venue = db.session.get(BilliardHall, venue_id)
        if not venue:
            raise ValueError(f"Sala con id {venue_id} non trovata")
        venue.verified = verified
        return venue

    @staticmethod
    @transactional(domain="location")
    def update_venue_table_numbers(
        venue_id: int, table_numbers: str
    ) -> BilliardHall:
        """Update venue table numbers stored in amenities."""
        venue = db.session.get(BilliardHall, venue_id)
        if not venue:
            raise ValueError(f"Sala con id {venue_id} non trovata")

        current_amenities = venue.get_amenities()
        # Remove existing table number entries
        current_amenities = [
            a for a in current_amenities if not a.startswith("Tavoli:")
        ]
        # Add new table numbers
        if table_numbers.strip():
            current_amenities.append(f"Tavoli: {table_numbers}")
        venue.set_amenities(current_amenities)
        return venue

    @staticmethod
    @transactional(domain="location")
    def update_venue_photo(venue_id: int, photo_db_path: str) -> BilliardHall:
        """Update venue photo path in amenities."""
        venue = db.session.get(BilliardHall, venue_id)
        if not venue:
            raise ValueError(f"Sala con id {venue_id} non trovata")

        current_amenities = venue.get_amenities()
        # Remove existing photo entries
        current_amenities = [
            a for a in current_amenities if not a.startswith("Foto:")
        ]
        current_amenities.append(f"Foto: {photo_db_path}")
        venue.set_amenities(current_amenities)
        return venue
