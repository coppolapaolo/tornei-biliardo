"""
Module: models/rating/handicap_service.py
Purpose: Handicap calculation and rule management services
"""

from __future__ import annotations

import logging
from typing import List, Optional, Dict, Any

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

logger = logging.getLogger(__name__)


class HandicapService:
    """Service for handicap calculation and rule management."""

    @staticmethod
    def calculate_handicap(
        player1_id: int, player2_id: int, rule_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Calculate handicap between two players."""
        from .rating_service import RatingService

        return RatingService.calculate_match_handicap(player1_id, player2_id, rule_id)

    @staticmethod
    def get_all_rules() -> Dict[str, Any]:
        """Get all handicap rules for management."""
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
        """Create new handicap rule with associated category and rating rules."""

        rule = HandicapRule(
            name=name,
            description=description,
            applies_to_campionatos=applies_to_campionatos,
            applies_to_individual_matches=applies_to_individual_matches,
        )

        db.session.add(rule)
        db.session.flush()  # Get the ID

        # Add category rules
        if category_rules:
            for cat_rule_data in category_rules:
                cat_rule = CategoryHandicapRule(
                    rule_id=rule.id,
                    higher_category=CategoryLevel(cat_rule_data["higher_category"]),
                    lower_category=CategoryLevel(cat_rule_data["lower_category"]),
                    handicap_value=cat_rule_data["handicap_value"],
                )
                db.session.add(cat_rule)

        # Add rating rules
        if rating_rules:
            for rating_rule_data in rating_rules:
                # Nomi campi allineati al modello RatingHandicapRule
                # (min_difference / max_difference / points_per_handicap /
                # max_handicap), come fa create_standard_handicap_rule. Prima
                # si usavano kwargs inesistenti (rating_difference_threshold,
                # handicap_per_point) → TypeError ad ogni creazione con
                # rating_rules. min_difference/points_per_handicap hanno
                # default NOT NULL nel modello (50/100): usali se assenti.
                rating_rule = RatingHandicapRule(
                    rule_id=rule.id,
                    rating_system=RatingSystem(rating_rule_data["rating_system"]),
                    min_difference=rating_rule_data.get("min_difference", 50),
                    max_difference=rating_rule_data.get("max_difference"),
                    points_per_handicap=rating_rule_data.get(
                        "points_per_handicap", 100
                    ),
                    max_handicap=rating_rule_data.get("max_handicap"),
                )
                db.session.add(rating_rule)

        return rule

    @staticmethod
    @transactional(domain="rating")
    def update_rule_status(rule_id: int, is_active: bool) -> HandicapRule:
        """Update handicap rule active status."""
        rule = db.session.get(HandicapRule, rule_id)
        if rule is None:
            raise ValueError("Regola handicap non trovata")
        rule.is_active = is_active
        return rule

    @staticmethod
    def _calculate_category_handicap(
        player1_id: int, player2_id: int, rule: HandicapRule
    ) -> Dict[str, Any]:
        """Calculate handicap based on categories."""
        from .rating_service import RatingService

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

        # Determine higher and lower categories
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
                "explanation": (
                    f"Player 2 ({cat2.value}) gets +{handicap} "
                    f"vs Player 1 ({cat1.value})"
                ),
            }
        else:
            # Player 2 is higher category
            handicap = rule.calculate_category_handicap(cat2, cat1)
            return {
                "player1_handicap": handicap,
                "player2_handicap": 0,
                "handicap": handicap,
                "method": "category",
                "explanation": (
                    f"Player 1 ({cat1.value}) gets +{handicap} "
                    f"vs Player 2 ({cat2.value})"
                ),
            }

    @staticmethod
    def _calculate_rating_handicap(
        player1_id: int, player2_id: int, rule: HandicapRule
    ) -> Dict[str, Any]:
        """Calculate handicap based on ratings."""

        # Try each rating system
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
                        "explanation": (
                            f"Both players have same {rating_system.value} rating"
                        ),
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
                        "explanation": (
                            f"Player 2 ({rating2.rating_value}) gets "
                            f"+{handicap} vs Player 1 ({rating1.rating_value})"
                        ),
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
                        "explanation": (
                            f"Player 1 ({rating1.rating_value}) gets "
                            f"+{handicap} vs Player 2 ({rating2.rating_value})"
                        ),
                    }

        # No ratings available
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
        """Create a standard handicap rule with typical category differences."""

        rule = HandicapRule(
            name="Standard Category Handicap",
            description="Standard handicap based on category differences",
            is_active=True,
        )

        db.session.add(rule)
        db.session.flush()  # Get the ID

        # Standard category handicap rules
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

        # Standard rating handicap rules
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
        """Get comprehensive rating summary for a player."""
        from .rating_service import RatingService

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
        """Bulk import Fargo ratings from external data."""
        from .rating_service import RatingService

        imported_count = 0

        for data in fargo_data:
            try:
                user_id = data.get("user_id")
                fargo_rating = data.get("fargo_rating")
                external_id = data.get("fargo_id")

                # is not None (non falsy): non saltare user_id==0/fargo==0.
                if user_id is not None and fargo_rating is not None:
                    RatingService.update_player_rating(
                        user_id=user_id,
                        rating_system=RatingSystem.FARGO,
                        new_rating=fargo_rating,
                        verified=True,
                        external_id=external_id,
                    )
                    imported_count += 1

            except Exception as e:
                # logger, non print: in produzione lo stdout va perso.
                logger.warning(
                    "Failed to import Fargo rating for user %s: %s",
                    data.get("user_id"),
                    e,
                )

        return imported_count

    @staticmethod
    def auto_assign_categories_from_ratings() -> int:
        """Auto-assign categories based on existing ratings."""
        from .rating_service import RatingService

        assigned_count = 0

        # Get all users with ratings but no assigned category
        users_with_ratings = db.session.query(PlayerRating.user_id).distinct().all()

        for (user_id,) in users_with_ratings:
            existing_category = PlayerCategory.get_user_current_category(user_id)
            if existing_category:
                continue  # Skip users who already have assigned categories

            # Get best available rating
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
                        reason=(
                            f"Auto-assigned from {rating_system.value} "
                            f"rating ({rating.rating_value})"
                        ),
                    )
                    assigned_count += 1
                    break

        return assigned_count
