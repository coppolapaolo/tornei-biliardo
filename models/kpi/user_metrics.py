"""
User Metric Service - Centralized Provider for Gamification Metrics

This service aggregates various user statistics from different domains (Match, Tournament, etc.)
to provide a unified interface for the Gamification Rule Engine.

It allows the Rule Engine to ask questions like:
- "How many tournaments has this user organized?"
- "How many matches has this user played in Location X?"
"""

from __future__ import annotations
from typing import Dict, Any, Optional
from sqlalchemy import func, or_

from models.base import db
from models.match.models import Match
from models.competition.models import Inscription, Gara
from models.user.models import User, DirectorAssignment, VenueManagement
from models.gamification.models import StreakTracker, UserAchievement, QuestParticipation
from models.user.role_enum import UserRole

class UserMetricService:
    """
    Aggregates user metrics for gamification.
    """

    @staticmethod
    def get_metric(user_id: int, metric_name: str, context: Optional[Dict[str, Any]] = None) -> Any:
        """
        Get value for a specific metric.
        
        Args:
            user_id: ID of the user
            metric_name: Name of the metric (e.g., 'total_matches')
            context: Optional context filter (e.g., {'location_id': 5})
            
        Returns:
            The metric value (usually int, bool, or float)
        """
        handler = getattr(UserMetricService, f"_get_{metric_name}", None)
        if handler:
            return handler(user_id, context)
        return 0

    @staticmethod
    def _get_total_matches(user_id: int, context: Optional[Dict[str, Any]] = None) -> int:
        """Count total completed matches."""
        query = Match.query.filter(
            or_(Match.player1_id == user_id, Match.player2_id == user_id),
            Match.status == 'completed'
        )
        return query.count()

    @staticmethod
    def _get_scores_inserted(user_id: int, context: Optional[Dict[str, Any]] = None) -> int:
        """
        Count matches where the user has updated the score/result.
        Note: Currently we might verify this by checking if they are the winner or loser
        in a confirmed match, or if we have a specific 'updated_by' log. 
        For now, we assume participation in a completed match counts as inserting score 
        if we don't track 'who clicked the button'.
        
        TODO: Improve this if we add a robust audit log for score entry.
        For now, alias to total_matches to allow progress.
        """
        return UserMetricService._get_total_matches(user_id, context)

    @staticmethod
    def _get_tournaments_played(user_id: int, context: Optional[Dict[str, Any]] = None) -> int:
        """Count tournaments participated in."""
        query = Inscription.query.filter_by(user_id=user_id)
        
        # If filtering by location
        if context and 'location_id' in context:
            # Join Gara to check location
            query = query.join(Gara).filter(Gara.venue_id == context['location_id'])
            
        return query.count()

    @staticmethod
    def _get_tournaments_organized(user_id: int, context: Optional[Dict[str, Any]] = None) -> int:
        """Count tournaments organized or co-organized."""
        # Check DirectorAssignment
        assignments = DirectorAssignment.query.filter_by(
            user_id=user_id, 
            entity_type='gara'
        ).count()
        # Admin implies all? No, metric should be specific action.
        return assignments

    @staticmethod
    def _get_matches_in_location(user_id: int, context: Optional[Dict[str, Any]] = None) -> int:
        """Count matches played in a specific location."""
        if not context or 'location_id' not in context:
            return 0
            
        location_id = context['location_id']
        query = Match.query.filter(
            or_(Match.player1_id == user_id, Match.player2_id == user_id),
            Match.status == 'completed',
            Match.venue_id == location_id
        )
        return query.count()

    @staticmethod
    def _get_roles(user_id: int, context: Optional[Dict[str, Any]] = None) -> int:
        """Check for specific roles (Venue Manager, Director)."""
        # This is a bit tricky as the engine expects a value comparison.
        # But usually roles are checked via "has_role" condition type, not "metric".
        # If needed as metric, return bitmask or similar?
        # For now, this might be unused if we use separate ConditionType.ROLE
        return 0 

    @staticmethod
    def _get_challenges_completed(user_id: int, context: Optional[Dict[str, Any]] = None) -> int:
        """Count completed challenge sessions (drills)."""
        # Assuming we have a way to track completed drills.
        # This might need to query a dedicated ChallengeResult model if it exists,
        # or QuestParticipation for 'drills' type.
        # Placeholder for now until Challenge domain is fully implemented.
        return 0

    @staticmethod
    def _get_distinct_opponents(user_id: int, context: Optional[Dict[str, Any]] = None) -> int:
        """Count unique players played against."""
        p1_query = db.session.query(Match.player2_id).filter(
            Match.player1_id == user_id, Match.status == 'completed'
        )
        p2_query = db.session.query(Match.player1_id).filter(
            Match.player2_id == user_id, Match.status == 'completed'
        )
        
        opponents = set([r[0] for r in p1_query.all()] + [r[0] for r in p2_query.all()])
        return len(opponents)

    @staticmethod
    def _get_tournaments_in_location(user_id: int, context: Optional[Dict[str, Any]] = None) -> int:
        """Count tournaments played in a specific location."""
        return UserMetricService._get_tournaments_played(user_id, context)

    @staticmethod
    def _get_tournament_drills_completed(user_id: int, context: Optional[Dict[str, Any]] = None) -> int:
        """Count drills completed during a tournament context."""
        # Placeholder
        return 0
