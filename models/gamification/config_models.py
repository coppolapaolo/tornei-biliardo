"""
Gamification Configuration Models - Database-backed configuration

These models replace hardcoded values in xp_config.py, allowing admin
to configure gamification rules via UI.

Models:
- GamificationConfig: Key-value store for XP rates, level curve params
- LevelUnlock: Feature unlocks at specific levels
- StreakMilestone: Streak milestone rewards configuration
"""

from __future__ import annotations
from datetime import datetime

from ..base import db, BaseModel, TimestampMixin


class GamificationConfig(db.Model, TimestampMixin):
    """
    Key-value configuration store for gamification settings.

    Replaces hardcoded values in xp_config.py for:
    - XP rates per transaction type (xp_match_win, xp_match_loss, etc.)
    - Level curve parameters (level_base_xp, level_power)
    - Max freeze tokens, etc.

    Categories:
    - "xp_rates": XP amounts per transaction type
    - "level_curve": Level progression parameters
    - "streak": Streak-related configuration
    - "general": Other general settings
    """
    __tablename__ = "gamification_config"

    key = db.Column(db.String(50), primary_key=True)
    value = db.Column(db.Integer, nullable=False)
    description = db.Column(db.String(255), nullable=True)
    category = db.Column(db.String(50), nullable=False, default="general")

    # Audit
    updated_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)

    def __repr__(self) -> str:
        return f"<GamificationConfig {self.key}={self.value}>"


class LevelUnlock(db.Model, TimestampMixin):
    """
    Feature unlocks at specific levels.

    Replaces LEVEL_UNLOCKS dict in xp_config.py.
    Allows admin to configure which features unlock at which levels.

    Example unlocks:
    - Level 5: match_proposals
    - Level 10: tournament_creation
    - Level 40: director_fast_track
    """
    __tablename__ = "level_unlock"

    id = db.Column(db.Integer, primary_key=True)
    level = db.Column(db.Integer, nullable=False, unique=True)
    feature_code = db.Column(db.String(50), nullable=False)
    feature_name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(255), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    def __repr__(self) -> str:
        return f"<LevelUnlock Lv{self.level}: {self.feature_code}>"


class StreakMilestone(db.Model, TimestampMixin):
    """
    Streak milestone rewards configuration.

    Replaces FREEZE_MILESTONES_WEEKLY dict in xp_config.py.
    Allows admin to configure freeze token rewards at streak milestones.

    Example milestones:
    - 4 weeks: 1 freeze token
    - 12 weeks: 1 freeze token (recurring)
    - 52 weeks: 2 freeze tokens
    """
    __tablename__ = "streak_milestone"

    id = db.Column(db.Integer, primary_key=True)
    weeks = db.Column(db.Integer, nullable=False, unique=True)
    freeze_tokens = db.Column(db.Integer, nullable=False, default=1)
    xp_bonus_multiplier = db.Column(db.Integer, nullable=False, default=1)
    is_recurring = db.Column(db.Boolean, nullable=False, default=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    def __repr__(self) -> str:
        return f"<StreakMilestone {self.weeks}w: {self.freeze_tokens} freeze>"


# Default configuration values (used for initial seeding and fallback)
DEFAULT_XP_RATES = {
    "xp_match_win": (50, "XP awarded for winning a match"),
    "xp_match_loss": (20, "XP awarded for losing a match"),
    "xp_tournament_inscription": (25, "XP for registering to a tournament"),
    "xp_tournament_completion": (100, "XP for completing a tournament"),
    "xp_tournament_podium": (200, "Bonus XP for top 3 finish"),
    "xp_tournament_win": (500, "Bonus XP for winning a tournament"),
    "xp_streak_bonus": (30, "XP per week of streak"),
    "xp_challenge_completion": (150, "XP for completing a challenge"),
}

DEFAULT_LEVEL_PARAMS = {
    "level_base_xp": (100, "Base XP for level 1"),
    "level_power": (150, "Level curve power (divided by 100, so 150 = 1.5)"),
}

DEFAULT_STREAK_CONFIG = {
    "max_freeze_count": (3, "Maximum freeze tokens a user can hold"),
}

DEFAULT_LEVEL_UNLOCKS = [
    (5, "match_proposals", "Proposte Match", "Puoi proporre match individuali"),
    (10, "tournament_creation", "Creazione Tornei", "Accesso all'assistente creazione tornei"),
    (15, "priority_invites", "Inviti Prioritari", "Ricevi inviti prioritari ai tornei"),
    (20, "custom_badge_display", "Badge Personalizzati", "Puoi scegliere quali badge mostrare"),
    (25, "venue_suggestion", "Suggerimenti Venue", "Puoi suggerire nuove venue"),
    (30, "challenge_creation", "Creazione Challenge", "Puoi creare challenge per altri"),
    (40, "director_fast_track", "Direttore Fast-Track", "Richiesta direttore auto-approvata"),
    (50, "legend_status", "Status Leggenda", "Accesso alla Hall of Fame"),
]

DEFAULT_STREAK_MILESTONES = [
    (4, 1, 1, False, "Prima milestone: 1 freeze token"),
    (12, 1, 1, True, "Milestone trimestrale: 1 freeze (ricorrente)"),
    (52, 2, 1, False, "Milestone annuale: 2 freeze tokens"),
]
