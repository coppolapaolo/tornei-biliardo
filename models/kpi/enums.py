"""
Module: models/kpi/enums.py
Purpose: Enums for KPI tracking system
"""

from enum import Enum


class FeatureName(Enum):
    """Tracked features in the platform."""

    # Gare (Competitions)
    GARA_INSCRIPTION = "gara_inscription"
    GARA_CREATE = "gara_create"
    GARA_VIEW_CLASSIFICATION = "gara_view_classification"

    # Match
    MATCH_GARA_PLAYED = "match_gara_played"
    MATCH_INDIVIDUAL_CREATE = "match_individual_create"
    MATCH_INDIVIDUAL_ACCEPT = "match_individual_accept"
    MATCH_RESULT_SUBMIT = "match_result_submit"

    # Social
    CHALLENGE_SEND = "challenge_send"
    CHALLENGE_ACCEPT = "challenge_accept"
    AVAILABILITY_SIGNAL = "availability_signal"

    # Gamification
    ACHIEVEMENT_VIEW = "achievement_view"
    LEADERBOARD_XP_VIEW = "leaderboard_xp_view"
    PROFILE_STATS_VIEW = "profile_stats_view"

    # Challenge Drill
    DRILL_COMPLETE = "drill_complete"
    DRILL_START = "drill_start"


class MilestoneType(Enum):
    """Types of milestones for notifications."""

    # User milestones
    USERS_TOTAL = "users_total"

    # Activity milestones
    MATCHES_TOTAL = "matches_total"
    GARE_COMPLETED = "gare_completed"


class AlertType(Enum):
    """Types of activity alerts."""

    NO_MATCH_3_DAYS = "no_match_3_days"
    NO_MATCH_7_DAYS = "no_match_7_days"
    NO_REGISTRATION_7_DAYS = "no_registration_7_days"


# Milestone thresholds
USER_MILESTONES = [10, 25, 50, 100, 250, 500, 1000]
MATCH_MILESTONES = [100, 500, 1000, 5000]
GARA_MILESTONES = [10, 50, 100]
