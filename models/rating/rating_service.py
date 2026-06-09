"""
Module: models/rating/rating_service.py
Purpose: Core rating management and player category services
"""

from __future__ import annotations

from typing import Optional, Dict, Any
from datetime import datetime

from ..base import db, utc_now
from ..transaction.manager import transactional
from .models import (
    PlayerCategory,
    PlayerRating,
    HandicapRule,
    CategoryLevel,
    RatingSystem,
)


class RatingService:
    """Service for rating and handicap management."""

    @staticmethod
    def get_user_rating_profile(user_id: int) -> Dict[str, Any]:
        """Get comprehensive rating profile for user."""
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
        """Get all ratings for a user organized by system."""
        ratings = PlayerRating.query.filter_by(user_id=user_id).all()

        organized = {}
        for rating in ratings:
            organized[rating.rating_system.value] = {
                "rating": rating,
                "category_equivalent": rating.get_category_equivalent(),
                "last_updated": rating.last_updated,
            }

        # Add missing systems with None
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
        """Update user rating (unverified by default)."""
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
        """Verify or unverify a player's rating."""
        rating = db.session.get(PlayerRating, rating_id)
        if rating is None:
            raise ValueError("Rating non trovato")

        rating.verified = verified
        rating.verified_by_id = verified_by_id if verified else None

        return rating

    @staticmethod
    def get_management_overview() -> Dict[str, Any]:
        """Get overview data for rating management."""
        # Unverified ratings needing review
        unverified_ratings = (
            PlayerRating.query.filter_by(verified=False)
            .order_by(PlayerRating.last_updated.desc())  # type: ignore[attr-defined]
            .all()
        )

        # Players without categories
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

        # Recent rating updates
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
        """Get system-wide rating statistics."""
        stats = {}

        # Statistics per rating system
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
                        [r for r in ratings if (utc_now() - r.last_updated).days <= 30]
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

        # Category distribution
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
        """Get public leaderboard data."""
        leaderboards = {}

        # Create leaderboard for each rating system
        for system in RatingSystem:
            top_players = (
                PlayerRating.query.filter_by(rating_system=system, verified=True)
                .order_by(PlayerRating.rating_value.desc())  # type: ignore[attr-defined] # noqa: E501
                .limit(20)
                .all()
            )

            leaderboards[system.value] = top_players

        # Category-based leaderboard (by number of campionato wins, etc.)
        # This would need integration with campionato results
        category_leaders = {}
        for category in CategoryLevel:
            # For now, just show most recent assignments
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
            "last_updated": utc_now(),
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
        """Assign a category to a player."""

        # Deactivate existing categories
        existing_categories = PlayerCategory.query.filter_by(
            user_id=user_id, is_active=True
        ).all()

        for existing in existing_categories:
            existing.expire_category()

        # Create new category
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
        """Update or create a player's rating."""

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
        """Get player's effective category (assigned or derived from rating)."""

        # First try assigned category
        assigned_category = PlayerCategory.get_user_current_category(user_id)
        if assigned_category:
            return assigned_category.category

        # Fall back to rating-derived category
        # Try Fargo first, then ELO, then internal
        for rating_system in [
            RatingSystem.FARGO,
            RatingSystem.ELO,
            RatingSystem.INTERNAL,
        ]:
            rating = PlayerRating.get_user_rating(user_id, rating_system)
            if rating:
                return rating.get_category_equivalent()

        # Default to lowest category if no data
        return CategoryLevel.D

    @staticmethod
    def calculate_match_handicap(
        player1_id: int, player2_id: int, handicap_rule_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Calculate handicap for a match between two players."""
        from .handicap_service import HandicapService

        # Get default handicap rule if not specified
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
            raise ValueError("Regola handicap non trovata")

        # Try category-based handicap first
        category_result = HandicapService._calculate_category_handicap(
            player1_id, player2_id, rule
        )

        if category_result["handicap"] > 0:
            return category_result

        # Fall back to rating-based handicap
        rating_result = HandicapService._calculate_rating_handicap(
            player1_id, player2_id, rule
        )

        return rating_result


class CategoryService:
    """Service for player category management."""

    @staticmethod
    def get_user_category_info(user_id: int) -> Dict[str, Any]:
        """Get comprehensive category information for user."""
        current_category = PlayerCategory.get_user_current_category(user_id)
        category_history = (
            PlayerCategory.query.filter_by(user_id=user_id)
            .order_by(PlayerCategory.assigned_at.desc())
            .all()
        )

        # Get effective category (including rating-derived)
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
        """Assign category to player."""
        return RatingService.assign_player_category(
            user_id=user_id,
            category=category,
            assigned_by_id=assigned_by_id,
            reason=reason,
            expires_at=expires_at,
        )

    @staticmethod
    def get_user_current_category(user_id: int) -> Optional[PlayerCategory]:
        """Get user's current active category."""
        return PlayerCategory.get_user_current_category(user_id)

    @staticmethod
    @transactional(domain="rating")
    def expire_category(category_id: int) -> None:
        """Manually expire a category assignment."""
        category = db.session.get(PlayerCategory, category_id)
        if category is None:
            raise ValueError("Categoria non trovata")
        category.expire_category()
