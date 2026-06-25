"""
User Metric Service - Centralized Provider for Gamification Metrics

This service aggregates various user statistics from different domains
(Match, Tournament, etc.)
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
from models.status_enum import MatchStatus
from models.user.models import DirectorAssignment


class UserMetricService:
    """
    Aggregates user metrics for gamification.
    """

    @staticmethod
    def get_metric(
        user_id: int,
        metric_name: str,
        context: Optional[Dict[str, Any]] = None,
        cache: Optional[Dict[Any, Any]] = None,
    ) -> Any:
        """
        Get value for a specific metric.

        Args:
            user_id: ID of the user
            metric_name: Name of the metric (e.g., 'total_matches')
            context: Optional context filter (e.g., {'location_id': 5})
            cache: Optional memoization dict. Quando fornito, il valore viene
                cachato per (user_id, metric_name, context) e riusato. DA USARE
                SOLO da path di SOLA LETTURA dove le metriche sono stabili (es.
                il render della dashboard "cosa posso sbloccare", issue #9). I
                flussi che mutano le metriche (completamento match → check
                achievement) NON devono passare la cache, altrimenti
                servirebbero valori stale e assegnerebbero award sbagliati.

        Returns:
            The metric value (usually int, bool, or float)
        """
        if cache is not None:
            key = (user_id, metric_name, UserMetricService._context_key(context))
            if key in cache:
                return cache[key]

        handler = getattr(UserMetricService, f"_get_{metric_name}", None)
        value = handler(user_id, context) if handler else 0

        if cache is not None:
            cache[key] = value
        return value

    @staticmethod
    def _context_key(context: Optional[Dict[str, Any]]) -> Any:
        """Chiave hashable per il context (per la memoizzazione opt-in)."""
        if not context:
            return None
        return tuple(sorted(context.items()))

    @staticmethod
    def _get_total_matches(
        user_id: int, context: Optional[Dict[str, Any]] = None
    ) -> int:
        """Count total completed matches."""
        query = Match.query.filter(
            or_(Match.player1_id == user_id, Match.player2_id == user_id),
            Match.status == MatchStatus.COMPLETED.value,
        )
        return query.count()

    @staticmethod
    def _get_scores_inserted(
        user_id: int, context: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        Count distinct matches where the user has inserted at least one rack.

        Uses the added_by_id field in Rack, IndividualRack, and TrioRack tables
        to accurately track who actually entered scores (vs just being a player).

        Returns count of distinct matches across all match types.
        """
        from models.match.models import Rack, TrioRack
        from models.individual_match.models import IndividualRack

        # Tournament matches (regular 1v1)
        tournament_count = (
            db.session.query(func.count(func.distinct(Rack.match_id)))
            .filter(Rack.added_by_id == user_id, Rack.is_deleted == False)  # noqa: E712
            .scalar()
            or 0
        )

        # Individual matches (casual 1v1)
        individual_count = (
            db.session.query(func.count(func.distinct(IndividualRack.match_id)))
            .filter(
                IndividualRack.added_by_id == user_id,
                IndividualRack.is_deleted == False,  # noqa: E712
            )
            .scalar()
            or 0
        )

        # Trio matches
        trio_count = (
            db.session.query(func.count(func.distinct(TrioRack.trio_match_id)))
            .filter(
                TrioRack.added_by_id == user_id,
                TrioRack.is_deleted == False,  # noqa: E712
            )
            .scalar()
            or 0
        )

        return tournament_count + individual_count + trio_count

    @staticmethod
    def _get_tournaments_played(
        user_id: int, context: Optional[Dict[str, Any]] = None
    ) -> int:
        """Count tournaments participated in."""
        query = Inscription.query.filter_by(user_id=user_id)

        # If filtering by location
        if context and "location_id" in context:
            # Join Gara to check location
            query = query.join(Gara).filter(Gara.venue_id == context["location_id"])

        return query.count()

    @staticmethod
    def _get_tournaments_organized(
        user_id: int, context: Optional[Dict[str, Any]] = None
    ) -> int:
        """Count tournaments organized or co-organized."""
        # Check DirectorAssignment
        assignments = DirectorAssignment.query.filter_by(
            user_id=user_id, entity_type="gara"
        ).count()
        # Admin implies all? No, metric should be specific action.
        return assignments

    @staticmethod
    def _get_matches_in_location(
        user_id: int, context: Optional[Dict[str, Any]] = None
    ) -> int:
        """Count matches played in a specific location."""
        if not context or "location_id" not in context:
            return 0

        location_id = context["location_id"]
        query = Match.query.filter(
            or_(Match.player1_id == user_id, Match.player2_id == user_id),
            Match.status == MatchStatus.COMPLETED.value,
            Match.venue_id == location_id,
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
    def _get_challenges_completed(
        user_id: int, context: Optional[Dict[str, Any]] = None
    ) -> int:
        """Count completed challenge attempts (drills)."""
        from models.challenge.models import ChallengeAttempt

        return ChallengeAttempt.query.filter(
            ChallengeAttempt.user_id == user_id,
            ChallengeAttempt.completed == True,  # noqa: E712
        ).count()

    @staticmethod
    def _get_distinct_opponents(
        user_id: int, context: Optional[Dict[str, Any]] = None
    ) -> int:
        """Count unique players played against."""
        p1_query = db.session.query(Match.player2_id).filter(
            Match.player1_id == user_id, Match.status == MatchStatus.COMPLETED.value
        )
        p2_query = db.session.query(Match.player1_id).filter(
            Match.player2_id == user_id, Match.status == MatchStatus.COMPLETED.value
        )

        opponents = set([r[0] for r in p1_query.all()] + [r[0] for r in p2_query.all()])
        return len(opponents)

    @staticmethod
    def _get_tournaments_in_location(
        user_id: int, context: Optional[Dict[str, Any]] = None
    ) -> int:
        """Count tournaments played in a specific location."""
        return UserMetricService._get_tournaments_played(user_id, context)

    @staticmethod
    def _get_tournament_drills_completed(
        user_id: int, context: Optional[Dict[str, Any]] = None
    ) -> int:
        """Count drills completed during a tournament context (with gara_id set)."""
        from models.challenge.models import ChallengeAttempt

        return ChallengeAttempt.query.filter(
            ChallengeAttempt.user_id == user_id,
            ChallengeAttempt.completed == True,  # noqa: E712
            ChallengeAttempt.gara_id.isnot(None),  # Has tournament context
        ).count()

    @staticmethod
    def _get_gare_with_drill_played(
        user_id: int, context: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        Count distinct gare where user completed at least one challenge/drill.

        This metric is used for feature gating: users who have experienced
        drills in a tournament context can unlock standalone drill features.
        """
        from models.challenge.models import ChallengeAttempt

        return (
            db.session.query(func.count(func.distinct(ChallengeAttempt.gara_id)))
            .filter(
                ChallengeAttempt.user_id == user_id,
                ChallengeAttempt.completed == True,  # noqa: E712
                ChallengeAttempt.gara_id.isnot(None),
            )
            .scalar()
            or 0
        )
