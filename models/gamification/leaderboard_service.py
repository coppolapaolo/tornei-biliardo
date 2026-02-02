"""
Leaderboard Service - Ranking Calculation and Caching

Manages leaderboard data with a caching strategy:
- Checks materialized view (LeaderboardEntry) first
- Recalculates if data is stale or missing
- optimizing performance for expensive ranking queries
"""

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from sqlalchemy import func, desc, and_

from models.base import db
from models.user.models import User
from models.gamification.models import (
    UserLevel,
    StreakTracker,
    LeaderboardEntry,
    LeaderboardType,
    StreakType
)
from models.gamification.xp_config import LEADERBOARD_CACHE_TTL

logger = logging.getLogger(__name__)


class LeaderboardService:
    """Service for managing game leaderboards."""

    @staticmethod
    def get_leaderboard(
        leaderboard_type: LeaderboardType,
        limit: int = 50,
        force_refresh: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Get leaderboard rankings.
        
        Args:
            leaderboard_type: Type of leaderboard to retrieve
            limit: Max number of entries
            force_refresh: Force recalculation ignoring cache
            
        Returns:
            List of dicts with rank, user, score, etc.
        """
        if force_refresh or LeaderboardService._is_cache_stale(leaderboard_type):
            logger.info(f"Refresing leaderboard: {leaderboard_type.value}")
            LeaderboardService._refresh_leaderboard(leaderboard_type)

        # Query cached entries
        entries = (
            LeaderboardEntry.query
            .filter_by(leaderboard_type=leaderboard_type)
            .order_by(LeaderboardEntry.rank)
            .limit(limit)
            .all()
        )

        # Transform to rich objects with user data
        results = []
        for entry in entries:
            results.append({
                "rank": entry.rank,
                "user": entry.user,
                "score": entry.score,
                "trend": 0,  # Placeholder for trend (up/down)
                "metadata": {}  # Placeholder for extra data
            })
            
        return results

    @staticmethod
    def _is_cache_stale(leaderboard_type: LeaderboardType) -> bool:
        """Check if leaderboard cache needs refresh."""
        last_entry = (
            LeaderboardEntry.query
            .filter_by(leaderboard_type=leaderboard_type)
            .order_by(desc(LeaderboardEntry.calculated_at))
            .first()
        )
        
        if not last_entry:
            return True
            
        ttl = LEADERBOARD_CACHE_TTL.get(leaderboard_type.name, 3600)
        age = (datetime.utcnow() - last_entry.calculated_at).total_seconds()
        
        return age > ttl

    @staticmethod
    def _refresh_leaderboard(leaderboard_type: LeaderboardType) -> None:
        """Recalculate and cache leaderboard data."""
        try:
            # Delete old entries
            LeaderboardEntry.query.filter_by(leaderboard_type=leaderboard_type).delete()
            
            # Calculate new entries
            new_entries = []
            
            if leaderboard_type == LeaderboardType.XP_ALL_TIME:
                new_entries = LeaderboardService._calculate_xp_all_time()
            elif leaderboard_type == LeaderboardType.LEVEL_HIGHEST:
                new_entries = LeaderboardService._calculate_level_highest()
            elif leaderboard_type == LeaderboardType.STREAK_CURRENT:
                new_entries = LeaderboardService._calculate_streak_current()
            elif leaderboard_type == LeaderboardType.STREAK_LONGEST:
                new_entries = LeaderboardService._calculate_streak_longest()
            elif leaderboard_type == LeaderboardType.ELO_RATING:
                new_entries = LeaderboardService._calculate_elo_rating()
            # Add other types here
            
            # Save to DB
            if new_entries:
                db.session.add_all(new_entries)
                db.session.commit()
                logger.info(f"Updated {leaderboard_type.value} with {len(new_entries)} entries")
                
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error refreshing leaderboard {leaderboard_type.value}: {e}", exc_info=True)

    @staticmethod
    def _calculate_xp_all_time() -> List[LeaderboardEntry]:
        """Calculate All-Time XP Ranking."""
        results = (
            db.session.query(UserLevel)
            .order_by(desc(UserLevel.total_xp))
            .limit(100)
            .all()
        )
        
        entries = []
        for rank, user_level in enumerate(results, 1):
            entries.append(LeaderboardEntry(
                leaderboard_type=LeaderboardType.XP_ALL_TIME,
                user_id=user_level.user_id,
                rank=rank,
                score=user_level.total_xp,
                calculated_at=datetime.utcnow()
            ))
        return entries

    @staticmethod
    def _calculate_level_highest() -> List[LeaderboardEntry]:
        """Calculate Highest Level Ranking."""
        # Order by Level DESC, then XP DESC (within level)
        results = (
            db.session.query(UserLevel)
            .order_by(desc(UserLevel.current_level), desc(UserLevel.current_xp))
            .limit(100)
            .all()
        )
        
        entries = []
        for rank, user_level in enumerate(results, 1):
            entries.append(LeaderboardEntry(
                leaderboard_type=LeaderboardType.LEVEL_HIGHEST,
                user_id=user_level.user_id,
                rank=rank,
                score=user_level.current_level,
                calculated_at=datetime.utcnow()
            ))
        return entries

    @staticmethod
    def _calculate_streak_current() -> List[LeaderboardEntry]:
        """Calculate Current Active Streak Ranking."""
        # Use WEEKLY_ACTIVITY as the main metric
        results = (
            db.session.query(StreakTracker)
            .filter(StreakTracker.streak_type == StreakType.WEEKLY_ACTIVITY)
            .order_by(desc(StreakTracker.current_streak))
            .limit(100)
            .all()
        )
        
        entries = []
        for rank, streak in enumerate(results, 1):
            # Only count significant streaks (>0)
            if streak.current_streak > 0:
                entries.append(LeaderboardEntry(
                    leaderboard_type=LeaderboardType.STREAK_CURRENT,
                    user_id=streak.user_id,
                    rank=rank,
                    score=streak.current_streak,
                    calculated_at=datetime.utcnow()
                ))
        return entries

    @staticmethod
    def _calculate_streak_longest() -> List[LeaderboardEntry]:
        """Calculate Longest Ever Streak Ranking."""
        results = (
            db.session.query(StreakTracker)
            .filter(StreakTracker.streak_type == StreakType.WEEKLY_ACTIVITY)
            .order_by(desc(StreakTracker.longest_streak))
            .limit(100)
            .all()
        )
        
        entries = []
        for rank, streak in enumerate(results, 1):
            if streak.longest_streak > 0:
                entries.append(LeaderboardEntry(
                    leaderboard_type=LeaderboardType.STREAK_LONGEST,
                    user_id=streak.user_id,
                    rank=rank,
                ))
        return entries

    @staticmethod
    def _calculate_elo_rating() -> List[LeaderboardEntry]:
        """Calculate Elo Rating Ranking."""
        from models.rating.models import PlayerRating, RatingSystem
        
        results = (
            db.session.query(PlayerRating)
            .filter_by(rating_system=RatingSystem.ELO)
            .order_by(desc(PlayerRating.rating_value))
            .limit(100)
            .all()
        )
        
        entries = []
        for rank, pr in enumerate(results, 1):
            entries.append(LeaderboardEntry(
                leaderboard_type=LeaderboardType.ELO_RATING,
                user_id=pr.user_id,
                rank=rank,
                score=pr.rating_value,
                calculated_at=datetime.utcnow()
            ))
        return entries
