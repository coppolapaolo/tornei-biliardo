"""
Module: models/location/services.py
Purpose: Location domain services for billiard hall and venue management
         + player availability tracking for community-driven match organization
Requirements: SPECIFICHE.md Use Cases 5, 7 - Location-based match coordination
Domain: Location management with transactional integrity

Business Context:
- Billiard hall registry for community venues
- Player availability tracking for location-based matchmaking
- Community-driven match suggestion algorithms
- Venue statistics and player activity coordination
- Cross-domain integration with individual match proposals (Use Case 7)

Architecture:
- Uses @transactional decorators from Task 1.1 Phase 17 migration
- Domain-specific transaction boundaries (domain="location")
- Community-focused algorithms for player discovery and venue management
"""

from __future__ import annotations

from typing import List, Optional, Dict, Any
from datetime import datetime

from ..base import db
from ..transaction.manager import transactional
from .models import BilliardHall, UserLocationAvailability, DayOfWeek


class LocationService:
    """
    Service for location domain business logic and community venue management.

    Core Responsibilities:
    - Billiard hall creation and management (community venue registry)
    - Player availability tracking at specific venues (Use Case 7)
    - Location-based player discovery algorithms for match suggestions
    - Venue statistics and activity tracking for community coordination
    - Cross-domain integration with individual match proposals

    Business Rules:
    - All venues default to Italy unless specified (community focus)
    - Player availability includes time preferences and advance notice requirements
    - Match experience at venues influences suggestion algorithms
    - Location matching uses fuzzy search for flexible venue identification

    Transaction Management:
    - Uses @transactional(domain="location") for data consistency
    - Leverages transaction rollback for error handling
    - Coordinates with individual match domain for activity tracking
    """

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
    ) -> BilliardHall:
        """
        Create a new billiard hall in the community venue registry.

        Business Logic:
        - Creates venue entry for community match coordination
        - Supports flexible venue information (address/contact optional)
        - Enables table types and amenities specification for player preferences
        - Tracks who added the venue for community management
        - Defaults to Italy for Italian pool community focus

        Args:
            name: Venue name (required for community identification)
            address/city/postal_code: Location details for player discovery
            country: Defaults to "Italy" for community focus
            contact info: phone/email/website for player coordination
            table_types: Pool table specifications (9ft, 8ft, etc.)
            amenities: Venue features (parking, bar, etc.)
            hourly_rate: Cost information for player planning
            added_by_id: User who registered the venue (audit trail)

        Returns:
            BilliardHall: Created venue entity with all specified attributes

        Transaction: @transactional(domain="location") ensures atomicity
        """

        # Create core venue entity with provided information
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

        # Configure table specifications if provided (used for player matching)
        if table_types:
            hall.set_table_types(table_types)

        # Configure venue amenities if provided (affects player preferences)
        if amenities:
            hall.set_amenities(amenities)

        # Persist to database within transaction boundary
        db.session.add(hall)

        return hall

    @staticmethod
    def get_nearby_halls(
        city: Optional[str] = None, country: str = "Italy", verified_only: bool = False
    ) -> List[BilliardHall]:
        """
        Discover billiard halls in a geographic area for community match coordination.

        Business Logic:
        - Filters active venues only (excludes closed/inactive halls)
        - Uses case-insensitive city matching for flexible search
        - Supports verification filter for trusted venues
        - Orders by name for consistent presentation
        - Defaults to Italy for community geographic focus

        Use Cases:
        - Use Case 7: Player availability - find nearby venues
        - Match proposal location suggestions
        - Community venue discovery for new players

        Args:
            city: Geographic filter (partial match supported)
            country: Country filter (defaults to Italy)
            verified_only: Include only admin-verified venues

        Returns:
            List[BilliardHall]: Active venues matching criteria, sorted by name

        Note: Read-only operation, no transaction needed
        """

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
                last_played_at=datetime.utcnow(),
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
        """
        Flexible venue search for community venue discovery.

        Search Algorithm:
        - Searches across venue name, address, and city fields
        - Uses case-insensitive partial matching for user-friendly search
        - Filters by geographic and quality criteria
        - Returns active venues only (excludes closed/inactive)

        Business Logic:
        - Supports player venue discovery workflows
        - Enables match proposal location search
        - Facilitates community venue exploration
        - Defaults to Italy for community geographic focus

        Use Cases:
        - Player: "Find venues named 'Centro Biliardo' near me"
        - Match proposal: "Search for venues in Milano"
        - Community: "Find verified venues in my area"

        Args:
            query: Search term for name/address/city matching
            city: Geographic filter (optional additional filter)
            country: Country filter (defaults to Italy)
            verified_only: Include only admin-verified venues

        Returns:
            List[BilliardHall]: Matching venues sorted by name

        Note: Read-only operation with complex filtering
        """

        # Build search query with multi-field text matching
        # Searches venue name, address, and city for comprehensive results
        search_query = BilliardHall.query.filter(
            BilliardHall.is_active.is_(True),
            db.or_(
                BilliardHall.name.ilike(f"%{query}%"),
                BilliardHall.address.ilike(f"%{query}%"),
                BilliardHall.city.ilike(f"%{query}%"),
            ),
        )

        # Apply additional city filter if specified (refines geographic search)
        if city:
            search_query = search_query.filter(BilliardHall.city.ilike(f"%{city}%"))

        # Apply country filter (defaults to Italy for community focus)
        if country:
            search_query = search_query.filter_by(country=country)

        # Filter to verified venues only if quality assurance requested
        if verified_only:
            search_query = search_query.filter_by(verified=True)

        # Return results sorted by name for consistent presentation
        return search_query.order_by(BilliardHall.name).all()
