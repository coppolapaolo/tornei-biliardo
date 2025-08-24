"""
Module: models/rating/services.py
Purpose: Rating domain services for handicap calculation
Requirements: SPECIFICHE.md - Handicap system management
"""

from __future__ import annotations

from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime

from ..base import db
from .models import (
    PlayerCategory, PlayerRating, HandicapRule, CategoryHandicapRule,
    RatingHandicapRule, CategoryLevel, RatingSystem
)


class RatingService:
    """Service for rating and handicap management."""
    
    @staticmethod
    def assign_player_category(
        user_id: int,
        category: CategoryLevel,
        assigned_by_id: Optional[int] = None,
        reason: Optional[str] = None,
        expires_at: Optional[datetime] = None
    ) -> PlayerCategory:
        """Assign a category to a player."""
        
        # Deactivate existing categories
        existing_categories = PlayerCategory.query.filter_by(
            user_id=user_id,
            is_active=True
        ).all()
        
        for existing in existing_categories:
            existing.expire_category()
        
        # Create new category
        new_category = PlayerCategory(
            user_id=user_id,
            category=category,
            assigned_by_id=assigned_by_id,
            reason=reason,
            expires_at=expires_at
        )
        
        db.session.add(new_category)
        db.session.commit()
        
        return new_category
    
    @staticmethod
    def update_player_rating(
        user_id: int,
        rating_system: RatingSystem,
        new_rating: int,
        verified: bool = False,
        verified_by_id: Optional[int] = None,
        external_id: Optional[str] = None
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
                external_id=external_id
            )
            db.session.add(rating)
        
        db.session.commit()
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
        for rating_system in [RatingSystem.FARGO, RatingSystem.ELO, RatingSystem.INTERNAL]:
            rating = PlayerRating.get_user_rating(user_id, rating_system)
            if rating:
                return rating.get_category_equivalent()
        
        # Default to lowest category if no data
        return CategoryLevel.D
    
    @staticmethod
    def calculate_match_handicap(
        player1_id: int,
        player2_id: int,
        handicap_rule_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Calculate handicap for a match between two players."""
        
        # Get default handicap rule if not specified
        if not handicap_rule_id:
            default_rule = HandicapRule.query.filter_by(is_active=True).first()
            if not default_rule:
                return {
                    "player1_handicap": 0,
                    "player2_handicap": 0,
                    "method": "no_rule",
                    "explanation": "No handicap rule available"
                }
            handicap_rule_id = default_rule.id
        
        rule = HandicapRule.query.get_or_404(handicap_rule_id)
        
        # Try category-based handicap first
        category_result = RatingService._calculate_category_handicap(
            player1_id, player2_id, rule
        )
        
        if category_result["handicap"] > 0:
            return category_result
        
        # Fall back to rating-based handicap
        rating_result = RatingService._calculate_rating_handicap(
            player1_id, player2_id, rule
        )
        
        return rating_result
    
    @staticmethod
    def _calculate_category_handicap(
        player1_id: int,
        player2_id: int,
        rule: HandicapRule
    ) -> Dict[str, Any]:
        """Calculate handicap based on categories."""
        
        cat1 = RatingService.get_player_effective_category(player1_id)
        cat2 = RatingService.get_player_effective_category(player2_id)
        
        if not cat1 or not cat2:
            return {
                "player1_handicap": 0,
                "player2_handicap": 0,
                "handicap": 0,
                "method": "no_categories",
                "explanation": "Category information not available"
            }
        
        # Determine higher and lower categories
        category_order = {CategoryLevel.A: 4, CategoryLevel.B: 3, CategoryLevel.C: 2, CategoryLevel.D: 1}
        
        if category_order[cat1] == category_order[cat2]:
            return {
                "player1_handicap": 0,
                "player2_handicap": 0,
                "handicap": 0,
                "method": "same_category",
                "explanation": f"Both players are category {cat1.value}"
            }
        
        if category_order[cat1] > category_order[cat2]:
            # Player 1 is higher category
            handicap = rule.calculate_category_handicap(cat1, cat2)
            return {
                "player1_handicap": 0,
                "player2_handicap": handicap,
                "handicap": handicap,
                "method": "category",
                "explanation": f"Player 2 ({cat2.value}) gets +{handicap} vs Player 1 ({cat1.value})"
            }
        else:
            # Player 2 is higher category
            handicap = rule.calculate_category_handicap(cat2, cat1)
            return {
                "player1_handicap": handicap,
                "player2_handicap": 0,
                "handicap": handicap,
                "method": "category",
                "explanation": f"Player 1 ({cat1.value}) gets +{handicap} vs Player 2 ({cat2.value})"
            }
    
    @staticmethod
    def _calculate_rating_handicap(
        player1_id: int,
        player2_id: int,
        rule: HandicapRule
    ) -> Dict[str, Any]:
        """Calculate handicap based on ratings."""
        
        # Try each rating system
        for rating_system in [RatingSystem.FARGO, RatingSystem.ELO, RatingSystem.INTERNAL]:
            rating1 = PlayerRating.get_user_rating(player1_id, rating_system)
            rating2 = PlayerRating.get_user_rating(player2_id, rating_system)
            
            if rating1 and rating2:
                if rating1.rating_value == rating2.rating_value:
                    return {
                        "player1_handicap": 0,
                        "player2_handicap": 0,
                        "handicap": 0,
                        "method": "same_rating",
                        "explanation": f"Both players have same {rating_system.value} rating"
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
                        "explanation": f"Player 2 ({rating2.rating_value}) gets +{handicap} vs Player 1 ({rating1.rating_value})"
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
                        "explanation": f"Player 1 ({rating1.rating_value}) gets +{handicap} vs Player 2 ({rating2.rating_value})"
                    }
        
        # No ratings available
        return {
            "player1_handicap": 0,
            "player2_handicap": 0,
            "handicap": 0,
            "method": "no_ratings",
            "explanation": "No rating information available"
        }
    
    @staticmethod
    def create_standard_handicap_rule() -> HandicapRule:
        """Create a standard handicap rule with typical category differences."""
        
        rule = HandicapRule(
            name="Standard Category Handicap",
            description="Standard handicap based on category differences",
            is_active=True
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
                handicap_value=handicap
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
                max_handicap=max_handicap
            )
            db.session.add(rating_rule)
        
        db.session.commit()
        return rule
    
    @staticmethod
    def get_player_ratings_summary(user_id: int) -> Dict[str, Any]:
        """Get comprehensive rating summary for a player."""
        ratings = PlayerRating.query.filter_by(user_id=user_id).all()
        category = PlayerCategory.get_user_current_category(user_id)
        effective_category = RatingService.get_player_effective_category(user_id)
        
        return {
            "assigned_category": category.category.value if category else None,
            "effective_category": effective_category.value if effective_category else None,
            "ratings": {
                rating.rating_system.value: {
                    "value": rating.rating_value,
                    "games_played": rating.games_played,
                    "verified": rating.verified,
                    "last_updated": rating.last_updated,
                    "category_equivalent": rating.get_category_equivalent().value
                }
                for rating in ratings
            }
        }
    
    @staticmethod
    def bulk_import_fargo_ratings(fargo_data: List[Dict[str, Any]]) -> int:
        """Bulk import Fargo ratings from external data."""
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
                        external_id=external_id
                    )
                    imported_count += 1
                    
            except Exception as e:
                print(f"Failed to import Fargo rating for user {data.get('user_id')}: {e}")
        
        return imported_count
    
    @staticmethod
    def auto_assign_categories_from_ratings() -> int:
        """Auto-assign categories based on existing ratings."""
        assigned_count = 0
        
        # Get all users with ratings but no assigned category
        users_with_ratings = db.session.query(PlayerRating.user_id).distinct().all()
        
        for (user_id,) in users_with_ratings:
            existing_category = PlayerCategory.get_user_current_category(user_id)
            if existing_category:
                continue  # Skip users who already have assigned categories
            
            # Get best available rating
            for rating_system in [RatingSystem.FARGO, RatingSystem.ELO, RatingSystem.INTERNAL]:
                rating = PlayerRating.get_user_rating(user_id, rating_system)
                if rating:
                    category = rating.get_category_equivalent()
                    RatingService.assign_player_category(
                        user_id=user_id,
                        category=category,
                        reason=f"Auto-assigned from {rating_system.value} rating ({rating.rating_value})"
                    )
                    assigned_count += 1
                    break
        
        return assigned_count