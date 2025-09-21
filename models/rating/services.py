"""
Module: models/rating/services.py
Purpose: Rating domain services for handicap calculation
Requirements: SPECIFICHE.md - Handicap system management
"""

from __future__ import annotations

from typing import List, Optional, Dict, Any
from datetime import datetime

from ..base import db
from ..transaction.manager import transactional
from .models import (
    PlayerCategory,
    PlayerRating,
    HandicapRule,
    CategoryHandicapRule,
    RatingHandicapRule,
    CategoryLevel,
    RatingSystem,
)


class RatingService:
    """Service for player rating management and handicap calculation.

    Handles the complete rating ecosystem including:
    - Multiple rating systems (Fargo, ELO, Internal)
    - Category management (A, B, C, D levels)
    - Handicap rule creation and calculation
    - Rating verification and administrative oversight
    - System statistics and public leaderboards

    Business Logic:
    - Category levels determine player classification (A=highest, D=lowest)
    - Effective category can be assigned or derived from best available rating
    - Handicap calculation prioritizes category-based over rating-based differences
    - All rating updates go through verification workflow for data integrity
    """

    @staticmethod
    def get_user_rating_profile(user_id: int) -> Dict[str, Any]:
        """Get comprehensive rating profile for user.

        Provides complete view of player's rating ecosystem including:
        - Current assigned category (manually assigned by admin/director)
        - Effective category (assigned or derived from best rating)
        - All rating systems data (Fargo, ELO, Internal)
        - Category assignment history for tracking progress
        - Verification status across all rating systems

        Args:
            user_id: Target player's user ID

        Returns:
            Dictionary containing complete rating profile for dashboard display
        """
        # Get current category
        current_category = PlayerCategory.get_user_current_category(user_id)

        # Get all ratings
        ratings = PlayerRating.query.filter_by(user_id=user_id).all()

        # Get effective category
        effective_category = RatingService.get_player_effective_category(user_id)

        # Get category history
        category_history = (
            PlayerCategory.query.filter_by(user_id=user_id)
            .order_by(PlayerCategory.assigned_at.desc())
            .all()
        )

        return {
            "user_id": user_id,
            "current_category": current_category,
            "effective_category": effective_category,
            "ratings": ratings,
            "category_history": category_history,
            "has_verified_rating": any(r.verified for r in ratings),
        }

    @staticmethod
    def get_user_all_ratings(user_id: int) -> Dict[str, Any]:
        """Get all ratings for a user organized by rating system.

        Organizes player ratings by system type for administrative overview.
        Shows category equivalents to help understand relative skill levels
        across different rating systems.

        Args:
            user_id: Target player's user ID

        Returns:
            Dictionary with ratings organized by system, including category
            equivalents and verification counts for administrative review
        """
        ratings = PlayerRating.query.filter_by(user_id=user_id).all()

        organized = {}
        for rating in ratings:
            organized[rating.rating_system.value] = {
                "rating": rating,
                "category_equivalent": rating.get_category_equivalent(),
                "last_updated": rating.last_updated,
            }

        # Ensure all rating systems are represented (even if no data)
        for system in RatingSystem:
            if system.value not in organized:
                organized[system.value] = None

        return {
            "ratings_by_system": organized,
            "total_systems": len([r for r in organized.values() if r is not None]),
            "verified_count": len([r for r in ratings if r.verified]),
        }

    @staticmethod
    def update_user_rating(
        user_id: int,
        rating_system: RatingSystem,
        rating_value: int,
        external_id: Optional[str] = None,
        confidence: float = 0.5,
    ) -> PlayerRating:
        """Update user rating (unverified by default).

        Convenience method for updating ratings without administrative verification.
        Used for player self-reported ratings or automated imports that require
        subsequent manual verification.

        Args:
            user_id: Player to update
            rating_system: Which rating system (Fargo, ELO, Internal)
            rating_value: New rating value
            external_id: External system identifier (e.g., Fargo player ID)
            confidence: Rating confidence level (currently unused)

        Returns:
            PlayerRating: Updated or created rating record (unverified)
        """
        return RatingService.update_player_rating(
            user_id=user_id,
            rating_system=rating_system,
            new_rating=rating_value,
            verified=False,
            external_id=external_id,
        )

    @staticmethod
    @transactional(domain="rating")
    def verify_rating(
        rating_id: int, verified_by_id: int, verified: bool = True
    ) -> PlayerRating:
        """Verify or unverify a player's rating.

        Administrative function for rating verification workflow.
        Verified ratings carry more weight in handicap calculations and
        tournament seeding. Only admins/directors can verify ratings.

        Transaction Safety:
        Uses @transactional(domain="rating") for data consistency

        Args:
            rating_id: Rating record to verify/unverify
            verified_by_id: Admin/Director performing verification
            verified: True to verify, False to unverify

        Returns:
            PlayerRating: Updated rating with new verification status
        """
        rating = db.session.get(PlayerRating, rating_id)
        if rating is None:
            from flask import abort

            abort(404)

        rating.verified = verified
        rating.verified_by_id = verified_by_id if verified else None

        return rating

    @staticmethod
    def get_management_overview() -> Dict[str, Any]:
        """Get overview data for rating management dashboard.

        Provides administrative overview of rating system health:
        - Unverified ratings requiring admin review
        - Players without category assignments (need classification)
        - Recent rating activity for monitoring system usage

        Used by admin dashboard to prioritize rating management tasks.

        Returns:
            Dictionary with management metrics and pending tasks
        """
        # Get unverified ratings that need administrative review
        unverified_ratings = (
            PlayerRating.query.filter_by(verified=False)
            .order_by(PlayerRating.last_updated.desc())  # type: ignore[attr-defined]
            .all()
        )

        # Find players with ratings but no assigned categories
        users_without_categories = (
            db.session.query(PlayerRating.user_id)
            .outerjoin(
                PlayerCategory,
                db.and_(
                    PlayerCategory.user_id == PlayerRating.user_id,
                    PlayerCategory.is_active.is_(True),  # type: ignore[attr-defined]
                ),
            )
            .filter(PlayerCategory.id.is_(None))
            .distinct()
            .all()
        )

        # Get recent rating activity for monitoring
        recent_updates = (
            PlayerRating.query.order_by(
                PlayerRating.last_updated.desc()  # type: ignore[attr-defined]
            )
            .limit(20)
            .all()
        )

        return {
            "unverified_ratings": unverified_ratings,
            "users_without_categories": [uid[0] for uid in users_without_categories],
            "recent_updates": recent_updates,
            "total_unverified": len(unverified_ratings),
        }

    @staticmethod
    def get_system_statistics() -> Dict[str, Any]:
        """Get system-wide rating statistics for administrative monitoring.

        Provides comprehensive statistics across all rating systems:
        - Player distribution per rating system
        - Verification rates and data quality metrics
        - Rating ranges and averages for system health
        - Recent activity levels for engagement tracking
        - Category distribution for community balance

        Used for system monitoring and community growth analysis.

        Returns:
            Dictionary with detailed statistics for each rating system
        """
        stats = {}

        # Calculate statistics for each rating system
        for system in RatingSystem:
            ratings = PlayerRating.query.filter_by(rating_system=system).all()

            if ratings:
                values = [r.rating_value for r in ratings]
                stats[system.value] = {
                    "total_players": len(ratings),
                    "verified_players": len([r for r in ratings if r.verified]),
                    "average_rating": sum(values) / len(values),
                    "min_rating": min(values),
                    "max_rating": max(values),
                    "recent_updates": len(
                        [
                            r
                            for r in ratings
                            if (datetime.utcnow() - r.last_updated).days <= 30
                        ]
                    ),
                }
            else:
                stats[system.value] = {
                    "total_players": 0,
                    "verified_players": 0,
                    "average_rating": 0,
                    "min_rating": 0,
                    "max_rating": 0,
                    "recent_updates": 0,
                }

        # Calculate category distribution across active players
        category_counts = {}
        for category in CategoryLevel:
            count = PlayerCategory.query.filter_by(
                category=category, is_active=True
            ).count()
            category_counts[category.value] = count

        return {
            "rating_systems": stats,
            "category_distribution": category_counts,
            "total_active_categories": sum(category_counts.values()),
            "total_handicap_rules": HandicapRule.query.filter_by(
                is_active=True
            ).count(),
        }

    @staticmethod
    def get_public_leaderboard() -> Dict[str, Any]:
        """Get public leaderboard data for community engagement.

        Creates public-facing leaderboards to showcase top players and
        encourage community participation. Only includes verified ratings
        to ensure data integrity and fair representation.

        Business Logic:
        - Only verified ratings are included in public leaderboards
        - Separate leaderboard for each rating system
        - Category leaders show most recently assigned (placeholder for tournament wins)
        - Future enhancement: integrate with campionato results for category leaders

        Returns:
            Dictionary with leaderboards for public display
        """
        leaderboards = {}

        # Generate verified player leaderboards for each rating system
        for system in RatingSystem:
            top_players = (
                PlayerRating.query.filter_by(rating_system=system, verified=True)
                .order_by(PlayerRating.rating_value.desc())  # type: ignore[attr-defined]
                .limit(20)
                .all()
            )

            leaderboards[system.value] = top_players

        # Category-based leaders (placeholder - future integration with tournament results)
        category_leaders = {}
        for category in CategoryLevel:
            # Currently shows recent category assignments (TODO: integrate tournament wins)
            leaders = (
                PlayerCategory.query.filter_by(category=category, is_active=True)
                .order_by(PlayerCategory.assigned_at.desc())
                .limit(10)
                .all()
            )
            category_leaders[category.value] = leaders

        return {
            "rating_leaderboards": leaderboards,
            "category_leaders": category_leaders,
            "last_updated": datetime.utcnow(),
        }

    @staticmethod
    @transactional(domain="rating")
    def assign_player_category(
        user_id: int,
        category: CategoryLevel,
        assigned_by_id: Optional[int] = None,
        reason: Optional[str] = None,
        expires_at: Optional[datetime] = None,
    ) -> PlayerCategory:
        """Assign a category to a player.

        Administrative function for manual category assignment.
        Deactivates any existing active categories before assigning new one
        to maintain data integrity (only one active category per player).

        Transaction Safety:
        Uses @transactional(domain="rating") to ensure atomic category updates

        Business Logic:
        - Categories represent skill levels: A (highest) to D (lowest)
        - Manual assignments override rating-derived categories
        - Assignment history is preserved for tracking player progression
        - Optional expiration for temporary category adjustments

        Args:
            user_id: Player to assign category to
            category: Category level (A, B, C, D)
            assigned_by_id: Admin/Director making assignment (optional for system)
            reason: Reason for assignment (tournament performance, etc.)
            expires_at: Optional expiration date for temporary assignments

        Returns:
            PlayerCategory: New active category assignment
        """

        # Deactivate any existing active categories (only one active per player)
        existing_categories = PlayerCategory.query.filter_by(
            user_id=user_id, is_active=True
        ).all()

        for existing in existing_categories:
            existing.expire_category()

        # Create new active category assignment
        new_category = PlayerCategory(
            user_id=user_id,
            category=category,
            assigned_by_id=assigned_by_id,
            reason=reason,
            expires_at=expires_at,
        )

        db.session.add(new_category)
        return new_category

    @staticmethod
    @transactional(domain="rating")
    def update_player_rating(
        user_id: int,
        rating_system: RatingSystem,
        new_rating: int,
        verified: bool = False,
        verified_by_id: Optional[int] = None,
        external_id: Optional[str] = None,
    ) -> PlayerRating:
        """Update or create a player's rating.

        Core rating management function that handles both updates and creation.
        Used by both administrative verification and automated rating updates.

        Transaction Safety:
        Uses @transactional(domain="rating") for atomic rating operations

        Business Logic:
        - Updates existing rating or creates new one if none exists
        - Preserves rating history through update_rating() method
        - Verification status and external IDs can be set during update
        - Each player can have one rating per system (Fargo, ELO, Internal)

        Args:
            user_id: Player to update
            rating_system: Which rating system (Fargo, ELO, Internal)
            new_rating: New rating value
            verified: Whether rating is verified (default False)
            verified_by_id: Admin/Director who verified (if verified=True)
            external_id: External system identifier (e.g., Fargo player ID)

        Returns:
            PlayerRating: Updated or newly created rating record
        """

        rating = PlayerRating.get_user_rating(user_id, rating_system)

        if rating:
            rating.update_rating(new_rating)
            if verified:
                rating.verified = True
                rating.verified_by_id = verified_by_id
            if external_id:
                rating.external_id = external_id
        else:
            rating = PlayerRating(
                user_id=user_id,
                rating_system=rating_system,
                rating_value=new_rating,
                verified=verified,
                verified_by_id=verified_by_id,
                external_id=external_id,
            )
            db.session.add(rating)

        return rating

    @staticmethod
    def get_player_effective_category(user_id: int) -> Optional[CategoryLevel]:
        """Get player's effective category (assigned or derived from rating).

        Determines the category to use for handicap calculations and tournament seeding.
        Follows a specific priority order to ensure fair and consistent classification.

        Business Logic Priority:
        1. Assigned category (manual admin/director assignment)
        2. Rating-derived category from best available rating system:
           - Fargo (preferred for accuracy)
           - ELO (secondary choice)
           - Internal (fallback system)
        3. Default to category D if no data available

        Args:
            user_id: Player to evaluate

        Returns:
            CategoryLevel: Effective category for competition purposes
        """

        # Priority 1: Use manually assigned category if available
        assigned_category = PlayerCategory.get_user_current_category(user_id)
        if assigned_category:
            return assigned_category.category

        # Priority 2: Derive category from best available rating
        # Priority order: Fargo (most accurate) > ELO > Internal
        for rating_system in [
            RatingSystem.FARGO,
            RatingSystem.ELO,
            RatingSystem.INTERNAL,
        ]:
            rating = PlayerRating.get_user_rating(user_id, rating_system)
            if rating:
                return rating.get_category_equivalent()

        # Priority 3: Default to lowest category for new players
        return CategoryLevel.D

    @staticmethod
    def calculate_match_handicap(
        player1_id: int, player2_id: int, handicap_rule_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Calculate handicap for a match between two players.

        Core handicap calculation engine that ensures fair play between
        players of different skill levels. Uses a hierarchical approach
        to determine appropriate handicap values.

        Business Logic:
        1. Category-based handicap (preferred for simplicity)
        2. Rating-based handicap (fallback for precision)
        3. No handicap if insufficient data

        The result includes detailed explanation for transparency and
        debugging purposes.

        Args:
            player1_id: First player
            player2_id: Second player
            handicap_rule_id: Specific rule to use (uses default if None)

        Returns:
            Dictionary with handicap values and calculation method explanation
        """

        # Use default active handicap rule if none specified
        if not handicap_rule_id:
            default_rule = HandicapRule.query.filter_by(is_active=True).first()
            if not default_rule:
                return {
                    "player1_handicap": 0,
                    "player2_handicap": 0,
                    "method": "no_rule",
                    "explanation": "No handicap rule available",
                }
            handicap_rule_id = default_rule.id

        rule = db.session.get(HandicapRule, handicap_rule_id)
        if rule is None:
            from flask import abort

            abort(404)

        # Priority 1: Category-based handicap (simpler, more stable)
        category_result = HandicapService._calculate_category_handicap(
            player1_id, player2_id, rule
        )

        if category_result["handicap"] > 0:
            return category_result

        # Priority 2: Rating-based handicap (more precise, complex)
        rating_result = HandicapService._calculate_rating_handicap(
            player1_id, player2_id, rule
        )

        return rating_result


class CategoryService:
    """Service for player category management and classification.

    Handles category assignments and provides convenient access to
    category-related information. Categories represent skill levels
    from A (highest) to D (lowest) and can be manually assigned
    or derived from rating systems.

    Business Logic:
    - Only one active category per player at any time
    - Manual assignments take precedence over rating-derived categories
    - Category history is preserved for tracking player progression
    - Effective category calculation includes fallback to rating systems
    """

    @staticmethod
    def get_user_category_info(user_id: int) -> Dict[str, Any]:
        """Get comprehensive category information for user.

        Provides complete category view including assignment history
        and whether the current category is manually assigned or
        derived from rating systems.

        Args:
            user_id: Player to analyze

        Returns:
            Dictionary with current, effective, and historical category data
        """
        current_category = PlayerCategory.get_user_current_category(user_id)
        category_history = (
            PlayerCategory.query.filter_by(user_id=user_id)
            .order_by(PlayerCategory.assigned_at.desc())
            .all()
        )

        # Calculate effective category (manual assignment or rating-derived)
        effective_category = RatingService.get_player_effective_category(user_id)

        return {
            "current_category": current_category,
            "effective_category": effective_category,
            "category_history": category_history,
            "is_rating_derived": current_category is None,
            "has_category_history": len(category_history) > 0,
        }

    @staticmethod
    def assign_category(
        user_id: int,
        category: CategoryLevel,
        assigned_by_id: int,
        reason: Optional[str] = None,
        expires_at: Optional[datetime] = None,
    ) -> PlayerCategory:
        """Assign category to player.

        Convenience wrapper for RatingService.assign_player_category
        with enforced assigned_by_id requirement for accountability.

        Args:
            user_id: Player to assign category to
            category: Category level (A, B, C, D)
            assigned_by_id: Admin/Director making assignment (required)
            reason: Reason for assignment
            expires_at: Optional expiration date

        Returns:
            PlayerCategory: New category assignment
        """
        return RatingService.assign_player_category(
            user_id=user_id,
            category=category,
            assigned_by_id=assigned_by_id,
            reason=reason,
            expires_at=expires_at,
        )

    @staticmethod
    def get_user_current_category(user_id: int) -> Optional[PlayerCategory]:
        """Get user's current active category.

        Returns the manually assigned category if one exists.
        Returns None if player only has rating-derived category.

        Args:
            user_id: Player to check

        Returns:
            PlayerCategory: Active assigned category or None
        """
        return PlayerCategory.get_user_current_category(user_id)

    @staticmethod
    @transactional(domain="rating")
    def expire_category(category_id: int) -> None:
        """Manually expire a category assignment.

        Administrative function to deactivate a category assignment.
        After expiration, player's effective category will fall back
        to rating-derived category or default.

        Transaction Safety:
        Uses @transactional(domain="rating") for data consistency

        Args:
            category_id: Category assignment to expire
        """
        category = db.session.get(PlayerCategory, category_id)
        if category is None:
            from flask import abort

            abort(404)
        category.expire_category()


class HandicapService:
    """Service for handicap calculation and rule management.

    Manages the handicap system that ensures fair play between players
    of different skill levels. Supports both category-based and rating-based
    handicap calculations with configurable rules.

    Handicap Calculation Logic:
    1. Category-based: Simple lookup table (A vs D = 3 handicap)
    2. Rating-based: Mathematical calculation based on rating differences
    3. Hierarchical fallback: Category preferred, rating as backup

    Rule Management:
    - Multiple handicap rules can exist (tournament-specific)
    - Rules define both category and rating calculation parameters
    - Active/inactive status allows rule versioning
    """

    @staticmethod
    def calculate_handicap(
        player1_id: int, player2_id: int, rule_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Calculate handicap between two players.

        Convenience wrapper for RatingService.calculate_match_handicap.
        Provides consistent interface for handicap calculations.

        Args:
            player1_id: First player
            player2_id: Second player
            rule_id: Handicap rule to use (default if None)

        Returns:
            Dictionary with handicap calculation results
        """
        return RatingService.calculate_match_handicap(player1_id, player2_id, rule_id)

    @staticmethod
    def get_all_rules() -> Dict[str, Any]:
        """Get all handicap rules for administrative management.

        Provides complete overview of handicap rules for admin dashboard.
        Separates active and inactive rules for better organization.

        Returns:
            Dictionary with active/inactive rules and totals
        """
        active_rules = HandicapRule.query.filter_by(is_active=True).all()
        inactive_rules = HandicapRule.query.filter_by(is_active=False).all()

        return {
            "active_rules": active_rules,
            "inactive_rules": inactive_rules,
            "total_rules": len(active_rules) + len(inactive_rules),
        }

    @staticmethod
    @transactional(domain="rating")
    def create_handicap_rule(
        name: str,
        description: Optional[str] = None,
        applies_to_campionatos: bool = True,
        applies_to_individual_matches: bool = True,
        category_rules: Optional[List[Dict[str, Any]]] = None,
        rating_rules: Optional[List[Dict[str, Any]]] = None,
    ) -> HandicapRule:
        """Create new handicap rule with associated category and rating rules.

        Creates a complete handicap rule with both category-based and
        rating-based calculation parameters. Used for tournament-specific
        or system-wide handicap configurations.

        Transaction Safety:
        Uses @transactional(domain="rating") to ensure atomic rule creation
        with all associated category and rating rules.

        Args:
            name: Rule name for identification
            description: Optional detailed description
            applies_to_campionatos: Whether rule applies to tournaments
            applies_to_individual_matches: Whether rule applies to casual matches
            category_rules: List of category-based handicap configurations
            rating_rules: List of rating-based handicap configurations

        Returns:
            HandicapRule: Newly created handicap rule with all sub-rules
        """

        rule = HandicapRule(
            name=name,
            description=description,
            applies_to_campionatos=applies_to_campionatos,
            applies_to_individual_matches=applies_to_individual_matches,
        )

        db.session.add(rule)
        db.session.flush()  # Flush to get rule ID for sub-rule creation

        # Create category-based handicap rules
        if category_rules:
            for cat_rule_data in category_rules:
                cat_rule = CategoryHandicapRule(
                    rule_id=rule.id,
                    higher_category=CategoryLevel(cat_rule_data["higher_category"]),
                    lower_category=CategoryLevel(cat_rule_data["lower_category"]),
                    handicap_value=cat_rule_data["handicap_value"],
                )
                db.session.add(cat_rule)

        # Create rating-based handicap rules
        if rating_rules:
            for rating_rule_data in rating_rules:
                rating_rule = RatingHandicapRule(
                    rule_id=rule.id,
                    rating_system=RatingSystem(rating_rule_data["rating_system"]),
                    rating_difference_threshold=rating_rule_data[
                        "rating_difference_threshold"
                    ],
                    handicap_per_point=rating_rule_data["handicap_per_point"],
                    max_handicap=rating_rule_data.get("max_handicap"),
                )
                db.session.add(rating_rule)

        return rule

    @staticmethod
    @transactional(domain="rating")
    def update_rule_status(rule_id: int, is_active: bool) -> HandicapRule:
        """Update handicap rule active status.

        Administrative function to activate/deactivate handicap rules.
        Allows for rule versioning and tournament-specific configurations.

        Transaction Safety:
        Uses @transactional(domain="rating") for data consistency

        Args:
            rule_id: Rule to update
            is_active: New active status

        Returns:
            HandicapRule: Updated rule
        """
        rule = db.session.get(HandicapRule, rule_id)
        if rule is None:
            from flask import abort

            abort(404)
        rule.is_active = is_active
        return rule

    @staticmethod
    def _calculate_category_handicap(
        player1_id: int, player2_id: int, rule: HandicapRule
    ) -> Dict[str, Any]:
        """Calculate handicap based on player categories.

        Uses simple lookup table for category-based handicaps.
        Preferred method due to simplicity and consistency.

        Business Logic:
        - Category order: A(4) > B(3) > C(2) > D(1)
        - Higher category player gives handicap to lower category player
        - Same category = no handicap
        - Missing categories = no handicap

        Args:
            player1_id: First player
            player2_id: Second player
            rule: Handicap rule containing category lookup table

        Returns:
            Dictionary with handicap calculation and explanation
        """

        cat1 = RatingService.get_player_effective_category(player1_id)
        cat2 = RatingService.get_player_effective_category(player2_id)

        if not cat1 or not cat2:
            return {
                "player1_handicap": 0,
                "player2_handicap": 0,
                "handicap": 0,
                "method": "no_categories",
                "explanation": "Category information not available",
            }

        # Establish category hierarchy for handicap calculation
        category_order = {
            CategoryLevel.A: 4,
            CategoryLevel.B: 3,
            CategoryLevel.C: 2,
            CategoryLevel.D: 1,
        }

        if category_order[cat1] == category_order[cat2]:
            return {
                "player1_handicap": 0,
                "player2_handicap": 0,
                "handicap": 0,
                "method": "same_category",
                "explanation": f"Both players are category {cat1.value}",
            }

        if category_order[cat1] > category_order[cat2]:
            # Player 1 is higher category
            handicap = rule.calculate_category_handicap(cat1, cat2)
            return {
                "player1_handicap": 0,
                "player2_handicap": handicap,
                "handicap": handicap,
                "method": "category",
                "explanation": f"Player 2 ({cat2.value}) gets +{handicap} vs Player 1 ({cat1.value})",
            }
        else:
            # Player 2 is higher category
            handicap = rule.calculate_category_handicap(cat2, cat1)
            return {
                "player1_handicap": handicap,
                "player2_handicap": 0,
                "handicap": handicap,
                "method": "category",
                "explanation": f"Player 1 ({cat1.value}) gets +{handicap} vs Player 2 ({cat2.value})",
            }

    @staticmethod
    def _calculate_rating_handicap(
        player1_id: int, player2_id: int, rule: HandicapRule
    ) -> Dict[str, Any]:
        """Calculate handicap based on player ratings.

        Mathematical handicap calculation using rating differences.
        More precise than category-based but requires verified ratings.

        Business Logic:
        - Tries rating systems in priority order: Fargo > ELO > Internal
        - Uses first system where both players have ratings
        - Higher rated player gives handicap to lower rated player
        - Handicap calculated per rule's mathematical formula

        Args:
            player1_id: First player
            player2_id: Second player
            rule: Handicap rule containing rating calculation parameters

        Returns:
            Dictionary with handicap calculation and explanation
        """

        # Try rating systems in priority order until both players have ratings
        for rating_system in [
            RatingSystem.FARGO,
            RatingSystem.ELO,
            RatingSystem.INTERNAL,
        ]:
            rating1 = PlayerRating.get_user_rating(player1_id, rating_system)
            rating2 = PlayerRating.get_user_rating(player2_id, rating_system)

            if rating1 and rating2:
                if rating1.rating_value == rating2.rating_value:
                    return {
                        "player1_handicap": 0,
                        "player2_handicap": 0,
                        "handicap": 0,
                        "method": "same_rating",
                        "explanation": f"Both players have same {rating_system.value} rating",
                    }

                if rating1.rating_value > rating2.rating_value:
                    # Player 1 has higher rating
                    handicap = rule.calculate_rating_handicap(
                        rating1.rating_value, rating2.rating_value, rating_system
                    )
                    return {
                        "player1_handicap": 0,
                        "player2_handicap": handicap,
                        "handicap": handicap,
                        "method": f"rating_{rating_system.value}",
                        "explanation": f"Player 2 ({rating2.rating_value}) gets +{handicap} vs Player 1 ({rating1.rating_value})",
                    }
                else:
                    # Player 2 has higher rating
                    handicap = rule.calculate_rating_handicap(
                        rating2.rating_value, rating1.rating_value, rating_system
                    )
                    return {
                        "player1_handicap": handicap,
                        "player2_handicap": 0,
                        "handicap": handicap,
                        "method": f"rating_{rating_system.value}",
                        "explanation": f"Player 1 ({rating1.rating_value}) gets +{handicap} vs Player 2 ({rating2.rating_value})",
                    }

        # Fallback when no rating system has data for both players
        return {
            "player1_handicap": 0,
            "player2_handicap": 0,
            "handicap": 0,
            "method": "no_ratings",
            "explanation": "No rating information available",
        }

    @staticmethod
    @transactional(domain="rating")
    def create_standard_handicap_rule() -> HandicapRule:
        """Create a standard handicap rule with typical category differences.

        Creates a default handicap rule suitable for most tournament situations.
        Includes both category-based and rating-based calculations with
        commonly accepted handicap values.

        Transaction Safety:
        Uses @transactional(domain="rating") for atomic rule creation
        with all associated category and rating rules.

        Standard Category Handicaps:
        - A vs B: 1 point
        - A vs C: 2 points
        - A vs D: 3 points
        - B vs C: 1 point
        - B vs D: 2 points
        - C vs D: 1 point

        Standard Rating Handicaps:
        - Fargo: 50-point minimum difference, 1 handicap per 100 points
        - ELO: 100-point minimum difference, 1 handicap per 200 points
        - Internal: 10-point minimum difference, 1 handicap per 20 points

        Returns:
            HandicapRule: Created standard rule with all configurations
        """

        rule = HandicapRule(
            name="Standard Category Handicap",
            description="Standard handicap based on category differences",
            is_active=True,
        )

        db.session.add(rule)
        db.session.flush()  # Flush to get rule ID for sub-rule creation

        # Create standard category-based handicap lookup table
        category_rules = [
            # A vs others
            (CategoryLevel.A, CategoryLevel.B, 1),
            (CategoryLevel.A, CategoryLevel.C, 2),
            (CategoryLevel.A, CategoryLevel.D, 3),
            # B vs others
            (CategoryLevel.B, CategoryLevel.C, 1),
            (CategoryLevel.B, CategoryLevel.D, 2),
            # C vs D
            (CategoryLevel.C, CategoryLevel.D, 1),
        ]

        for higher, lower, handicap in category_rules:
            category_rule = CategoryHandicapRule(
                rule_id=rule.id,
                higher_category=higher,
                lower_category=lower,
                handicap_value=handicap,
            )
            db.session.add(category_rule)

        # Create standard rating-based handicap formulas
        rating_rules = [
            (RatingSystem.FARGO, 50, 500, 100, 5),
            (RatingSystem.ELO, 100, 800, 200, 4),
            (RatingSystem.INTERNAL, 10, 60, 20, 3),
        ]

        for rating_system, min_diff, max_diff, points_per, max_handicap in rating_rules:
            rating_rule = RatingHandicapRule(
                rule_id=rule.id,
                rating_system=rating_system,
                min_difference=min_diff,
                max_difference=max_diff,
                points_per_handicap=points_per,
                max_handicap=max_handicap,
            )
            db.session.add(rating_rule)

        return rule

    @staticmethod
    def get_player_ratings_summary(user_id: int) -> Dict[str, Any]:
        """Get comprehensive rating summary for a player.

        Provides complete player rating profile for display purposes.
        Includes both assigned and derived categories plus all rating
        system data with verification status.

        Args:
            user_id: Player to summarize

        Returns:
            Dictionary with complete rating profile for UI display
        """
        ratings = PlayerRating.query.filter_by(user_id=user_id).all()
        category = PlayerCategory.get_user_current_category(user_id)
        effective_category = RatingService.get_player_effective_category(user_id)

        return {
            "assigned_category": category.category.value if category else None,
            "effective_category": (
                effective_category.value if effective_category else None
            ),
            "ratings": {
                rating.rating_system.value: {
                    "value": rating.rating_value,
                    "games_played": rating.games_played,
                    "verified": rating.verified,
                    "last_updated": rating.last_updated,
                    "category_equivalent": rating.get_category_equivalent().value,
                }
                for rating in ratings
            },
        }

    @staticmethod
    def bulk_import_fargo_ratings(fargo_data: List[Dict[str, Any]]) -> int:
        """Bulk import Fargo ratings from external data.

        Administrative utility for importing Fargo ratings from external
        sources. All imported ratings are marked as verified since they
        come from official Fargo system.

        Data Format Expected:
        - user_id: Internal user ID
        - fargo_rating: Fargo rating value
        - fargo_id: External Fargo player ID

        Args:
            fargo_data: List of dictionaries with Fargo rating data

        Returns:
            int: Number of successfully imported ratings
        """
        imported_count = 0

        for data in fargo_data:
            try:
                user_id = data.get("user_id")
                fargo_rating = data.get("fargo_rating")
                external_id = data.get("fargo_id")

                if user_id and fargo_rating:
                    RatingService.update_player_rating(
                        user_id=user_id,
                        rating_system=RatingSystem.FARGO,
                        new_rating=fargo_rating,
                        verified=True,
                        external_id=external_id,
                    )
                    imported_count += 1

            except Exception as e:
                print(
                    f"Failed to import Fargo rating for user {data.get('user_id')}: {e}"
                )

        return imported_count

    @staticmethod
    def auto_assign_categories_from_ratings() -> int:
        """Auto-assign categories based on existing ratings.

        Administrative utility to automatically assign categories to players
        who have ratings but no manual category assignments. Uses the same
        priority logic as get_player_effective_category.

        Business Logic:
        - Only assigns to players without existing categories
        - Uses best available rating system (Fargo > ELO > Internal)
        - Categories derived from rating equivalents
        - Assignment reason includes rating system and value for audit trail

        Returns:
            int: Number of categories automatically assigned
        """
        assigned_count = 0

        # Find all users who have ratings but no manual category assignment
        users_with_ratings = db.session.query(PlayerRating.user_id).distinct().all()

        for (user_id,) in users_with_ratings:
            existing_category = PlayerCategory.get_user_current_category(user_id)
            if existing_category:
                continue  # Skip users who already have assigned categories

            # Use best available rating system to derive category
            for rating_system in [
                RatingSystem.FARGO,
                RatingSystem.ELO,
                RatingSystem.INTERNAL,
            ]:
                rating = PlayerRating.get_user_rating(user_id, rating_system)
                if rating:
                    category = rating.get_category_equivalent()
                    RatingService.assign_player_category(
                        user_id=user_id,
                        category=category,
                        reason=f"Auto-assigned from {rating_system.value} rating ({rating.rating_value})",
                    )
                    assigned_count += 1
                    break

        return assigned_count
