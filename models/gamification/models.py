"""
Gamification Domain Models - XP, Levels, Achievements, Streaks, Leaderboards

Database models for the gamification system including:
- UserLevel: Player XP and level progression
- XPTransaction: Audit log for all XP awards
- Achievement: Predefined achievements with requirements
- UserAchievement: Player progress on achievements
- StreakTracker: Weekly streak tracking with freeze mechanics
- LeaderboardEntry: Cached leaderboard rankings
- Quest: Weekly/monthly goals
- QuestParticipation: Player progress on quests
"""

from __future__ import annotations
from enum import Enum

from ..base import db, BaseModel, TimestampMixin, utc_now

# ========================================
# Enums
# ========================================


class XPTransactionType(Enum):
    """Types of XP transactions for audit trail."""

    MATCH_WIN = "match_win"
    MATCH_LOSS = "match_loss"
    CASUAL_MATCH_WIN = "casual_match_win"  # Match individuale (ridotto vs torneo)
    CASUAL_MATCH_LOSS = "casual_match_loss"
    TOURNAMENT_INSCRIPTION = "tournament_inscription"
    TOURNAMENT_COMPLETION = "tournament_completion"
    TOURNAMENT_PODIUM = "tournament_podium"
    TOURNAMENT_WIN = "tournament_win"
    STREAK_BONUS = "streak_bonus"
    ACHIEVEMENT_UNLOCK = "achievement_unlock"
    CHALLENGE_COMPLETION = "challenge_completion"
    GARA_CREATION = "gara_creation"
    CAMPIONATO_CREATION = "campionato_creation"
    ADMIN_ADJUSTMENT = "admin_adjustment"
    ADMIN_GRANT = "admin_grant"  # Bonus XP granted by admin


class AchievementCategory(Enum):
    """Achievement categorization for UI organization."""

    MATCH = "match"
    TOURNAMENT = "tournament"
    SOCIAL = "social"
    SKILL = "skill"
    CONSISTENCY = "consistency"
    EXPLORATION = "exploration"
    MILESTONE = "milestone"


class AchievementDifficulty(Enum):
    """Achievement rarity levels affecting XP rewards."""

    COMMON = "common"  # 50%+ of players earn
    UNCOMMON = "uncommon"  # 25-50%
    RARE = "rare"  # 10-25%
    EPIC = "epic"  # 5-10%
    LEGENDARY = "legendary"  # <5%


class StreakType(Enum):
    """Types of weekly streak tracking."""

    WEEKLY_ACTIVITY = "weekly_activity"  # Any activity 1x/week
    WEEKLY_MATCH = "weekly_match"  # At least 1 match/week
    WEEKLY_TOURNAMENT = "weekly_tournament"  # At least 1 tournament/week
    WEEKLY_DRILL = "weekly_drill"  # At least 1 drill (Challenge)/week


class LeaderboardType(Enum):
    """Types of leaderboards with different time periods."""

    XP_ALL_TIME = "xp_all_time"
    XP_WEEKLY = "xp_weekly"
    XP_MONTHLY = "xp_monthly"
    LEVEL_HIGHEST = "level_highest"
    STREAK_CURRENT = "streak_current"
    STREAK_LONGEST = "streak_longest"
    WIN_RATE_30_DAYS = "win_rate_30_days"
    ELO_RATING = "elo_rating"
    ELO_GLOBAL_RATING = "elo_global"  # Dual ELO: tornei + casual (display)


class QuestType(Enum):
    """Quest duration types."""

    WEEKLY = "weekly"
    MONTHLY = "monthly"
    SPECIAL_EVENT = "special_event"


class QuestStatus(Enum):
    """Quest lifecycle status."""

    UPCOMING = "upcoming"
    ACTIVE = "active"
    COMPLETED = "completed"
    EXPIRED = "expired"


# ========================================
# Core XP & Level Models
# ========================================


class UserLevel(BaseModel):
    """
    Player XP and level progression tracking.

    Tracks current level, XP in current level, and lifetime total XP.
    Levels unlock features at thresholds (e.g., tournament creation at level 10).
    """

    __tablename__ = "user_level"

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    current_level = db.Column(db.Integer, nullable=False, default=1)
    current_xp = db.Column(db.Integer, nullable=False, default=0)  # XP in current level
    total_xp = db.Column(db.Integer, nullable=False, default=0)  # Lifetime XP
    highest_level_reached = db.Column(db.Integer, nullable=False, default=1)

    # Relationships
    user = db.relationship("User", foreign_keys=[user_id], backref="level_stats")

    # Indexes for leaderboards
    __table_args__ = (
        db.Index("idx_user_level_total_xp", "total_xp"),
        db.Index("idx_user_level_current_level", "current_level"),
    )

    def __repr__(self) -> str:
        return (
            f"<UserLevel user_id={self.user_id} "
            f"level={self.current_level} xp={self.total_xp}>"
        )


class XPTransaction(db.Model, TimestampMixin):
    """
    Audit log for all XP awards.

    Tracks every XP gain/loss with reason, type, and level changes.
    Used for analytics and debugging XP economy.
    """

    __tablename__ = "xp_transaction"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )

    # Transaction Details
    transaction_type = db.Column(db.Enum(XPTransactionType), nullable=False)
    xp_amount = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.String(255), nullable=True)

    # Level Tracking
    level_before = db.Column(db.Integer, nullable=False)
    level_after = db.Column(db.Integer, nullable=False)

    # Related Entities (JSON)
    related_entities = db.Column(
        db.Text, nullable=True
    )  # {"match_id": 123, "gara_id": 456}

    # Relationships
    user = db.relationship("User", foreign_keys=[user_id])

    # Indexes
    __table_args__ = (
        db.Index("idx_xp_transaction_user_created", "user_id", "created_at"),
        db.Index("idx_xp_transaction_type", "transaction_type"),
    )

    def __repr__(self) -> str:
        return (
            f"<XPTransaction user_id={self.user_id} "
            f"type={self.transaction_type.value} amount={self.xp_amount}>"
        )


# ========================================
# Achievement Models
# ========================================


class Achievement(BaseModel):
    """
    Predefined achievements with requirements and rewards.

    Achievements are configured once and tracked per-user in UserAchievement.
    Requirements stored as JSON for flexibility
    (e.g., {"type": "match_wins", "count": 50}).
    """

    __tablename__ = "achievement"

    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(100), unique=True, nullable=False)  # "first_blood"
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    icon_path = db.Column(db.String(255), nullable=True)

    # Categorization
    category = db.Column(db.Enum(AchievementCategory), nullable=False)
    difficulty = db.Column(
        db.Enum(AchievementDifficulty),
        nullable=False,
        default=AchievementDifficulty.COMMON,
    )

    # Requirements (JSON flexible criteria)
    requirements = db.Column(
        db.Text, nullable=False
    )  # {"type": "match_wins", "count": 50}
    is_progressive = db.Column(
        db.Boolean, default=False
    )  # Track progress (e.g., 50/100)

    # Rewards
    xp_reward = db.Column(db.Integer, nullable=False, default=0)

    # Visibility
    is_hidden = db.Column(db.Boolean, default=False)  # Secret achievements
    is_active = db.Column(db.Boolean, default=True)

    # Relationships
    earned_by = db.relationship(
        "UserAchievement", cascade="all, delete-orphan", back_populates="achievement"
    )

    def __repr__(self) -> str:
        return f"<Achievement slug={self.slug} category={self.category.value}>"


class UserAchievement(db.Model, TimestampMixin):
    """
    Player progress on specific achievement.

    Junction table tracking user's progress toward achievement completion.
    Supports progressive achievements with progress tracking.
    """

    __tablename__ = "user_achievement"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    achievement_id = db.Column(
        db.Integer, db.ForeignKey("achievement.id", ondelete="CASCADE"), nullable=False
    )

    # Progress Tracking
    current_progress = db.Column(db.Integer, nullable=False, default=0)
    is_unlocked = db.Column(db.Boolean, nullable=False, default=False)
    unlocked_at = db.Column(db.DateTime, nullable=True)

    # Display
    is_displayed = db.Column(db.Boolean, default=True)  # Show in public profile

    # Relationships
    user = db.relationship("User", foreign_keys=[user_id])
    achievement = db.relationship(
        "Achievement", foreign_keys=[achievement_id], back_populates="earned_by"
    )

    # Constraints
    __table_args__ = (
        db.UniqueConstraint("user_id", "achievement_id", name="uq_user_achievement"),
    )

    def __repr__(self) -> str:
        return (
            f"<UserAchievement user_id={self.user_id} "
            f"achievement_id={self.achievement_id} unlocked={self.is_unlocked}>"
        )


# ========================================
# Streak Tracking (WEEKLY)
# ========================================


class StreakTracker(db.Model, TimestampMixin):
    """
    Weekly streak tracking with freeze mechanics.

    Tracks activity streaks in WEEKS (not days) using ISO week numbers.
    Supports freeze mechanics earned at milestones (4/12/52 weeks).
    """

    __tablename__ = "streak_tracker"

    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), primary_key=True
    )
    streak_type = db.Column(db.Enum(StreakType), primary_key=True)

    # Streak Data (WEEKS, not days)
    current_streak = db.Column(
        db.Integer, nullable=False, default=0
    )  # Consecutive weeks
    longest_streak = db.Column(db.Integer, nullable=False, default=0)  # Longest weeks
    last_activity_week = db.Column(db.Integer, nullable=True)  # ISO week number (1-53)
    last_activity_year = db.Column(
        db.Integer, nullable=True
    )  # Year for year transitions

    # Freeze Mechanics
    freeze_count = db.Column(
        db.Integer, nullable=False, default=0
    )  # Available freezes (max 3)
    total_freeze_earned = db.Column(
        db.Integer, nullable=False, default=0
    )  # Lifetime count
    last_freeze_earned_at = db.Column(db.Date, nullable=True)
    last_freeze_used_at = db.Column(db.Date, nullable=True)

    # Milestone Tracking
    milestone_4_reached = db.Column(db.Boolean, default=False)
    milestone_12_reached = db.Column(db.Boolean, default=False)
    milestone_52_reached = db.Column(db.Boolean, default=False)

    # Relationships
    user = db.relationship("User", foreign_keys=[user_id])

    # Indexes
    __table_args__ = (
        db.Index("idx_streak_current", "current_streak"),
        db.Index("idx_streak_longest", "longest_streak"),
    )

    def __repr__(self) -> str:
        return (
            f"<StreakTracker user_id={self.user_id} "
            f"type={self.streak_type.value} current={self.current_streak}>"
        )


# ========================================
# Leaderboard Models
# ========================================


class LeaderboardEntry(db.Model, TimestampMixin):
    """
    Cached leaderboard rankings (materialized view pattern).

    Pre-calculated leaderboard entries with TTL-based invalidation.
    Optimizes expensive queries for multiple leaderboard types.
    """

    __tablename__ = "leaderboard_entry"

    id = db.Column(db.Integer, primary_key=True)
    leaderboard_type = db.Column(db.Enum(LeaderboardType), nullable=False)
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )

    # Ranking
    rank = db.Column(db.Integer, nullable=False)
    score = db.Column(
        db.Float, nullable=False
    )  # Generic score (XP, level, streak, win rate)

    # Period (for temporal leaderboards)
    period_start = db.Column(db.Date, nullable=True)
    period_end = db.Column(db.Date, nullable=True)

    # Cache Metadata
    calculated_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    is_stale = db.Column(db.Boolean, nullable=False, default=False)

    # Relationships
    user = db.relationship("User", foreign_keys=[user_id])

    # Indexes
    __table_args__ = (
        db.Index("idx_leaderboard_type_rank", "leaderboard_type", "rank"),
        db.Index("idx_leaderboard_type_score", "leaderboard_type", "score"),
    )

    def __repr__(self) -> str:
        return (
            f"<LeaderboardEntry type={self.leaderboard_type.value} "
            f"rank={self.rank} user_id={self.user_id}>"
        )


# ========================================
# Quest System (Weekly/Monthly Goals)
# ========================================


class Quest(BaseModel):
    """
    Weekly/monthly goals with objectives and rewards.

    Admin-created challenges for community engagement.
    NOT to be confused with Challenge (drill/training) domain.
    """

    __tablename__ = "quest"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)

    # Type & Status
    quest_type = db.Column(db.Enum(QuestType), nullable=False)
    status = db.Column(
        db.Enum(QuestStatus), nullable=False, default=QuestStatus.UPCOMING
    )

    # Timing
    start_date = db.Column(db.DateTime, nullable=False)
    end_date = db.Column(db.DateTime, nullable=False)

    # Requirements (JSON flexible)
    requirements = db.Column(
        db.Text, nullable=False
    )  # {"type": "matches_played", "target": 10}

    # Rewards
    xp_reward = db.Column(db.Integer, nullable=False, default=150)
    badge_icon = db.Column(db.String(255), nullable=True)

    # Statistics
    participant_count = db.Column(db.Integer, nullable=False, default=0)
    completion_count = db.Column(db.Integer, nullable=False, default=0)

    # Relationships
    participations = db.relationship(
        "QuestParticipation", back_populates="quest", cascade="all, delete-orphan"
    )

    @property
    def effective_status(self) -> "QuestStatus":
        """Status calcolato dalle date a runtime (niente cron necessario).

        `update_quest_statuses()` non è mai chiamato in produzione: il campo
        `status` precalcolato resta congelato sul valore di creazione (di norma
        UPCOMING). Questa property deriva lo stato reale da
        `start_date`/`end_date` con `utc_now()` alla lettura.

        Gli stati terminali/override impostati dall'admin
        (COMPLETED, EXPIRED) hanno la precedenza sul default temporale: in
        produzione l'unico modo per cui `status` vale COMPLETED/EXPIRED è
        un'azione admin (i flussi automatici non girano), quindi vanno
        rispettati come override manuali.
        """
        if self.status in (QuestStatus.COMPLETED, QuestStatus.EXPIRED):
            return self.status

        now = utc_now()
        if now < self.start_date:
            return QuestStatus.UPCOMING
        if now <= self.end_date:
            return QuestStatus.ACTIVE
        return QuestStatus.EXPIRED

    @property
    def is_currently_active(self) -> bool:
        """True se la quest è attiva ORA secondo le date (o override admin)."""
        return self.effective_status == QuestStatus.ACTIVE

    def __repr__(self) -> str:
        return f"<Quest id={self.id} name={self.name} type={self.quest_type.value}>"


class QuestParticipation(db.Model, TimestampMixin):
    """
    Player progress on specific quest.

    Tracks individual player's progress toward quest completion.
    """

    __tablename__ = "quest_participation"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    quest_id = db.Column(
        db.Integer, db.ForeignKey("quest.id", ondelete="CASCADE"), nullable=False
    )

    # Progress
    current_progress = db.Column(db.Integer, nullable=False, default=0)
    target_progress = db.Column(
        db.Integer, nullable=False
    )  # Copied from quest requirements

    # Completion
    is_completed = db.Column(db.Boolean, nullable=False, default=False)
    completed_at = db.Column(db.DateTime, nullable=True)
    xp_awarded = db.Column(db.Integer, nullable=False, default=0)

    # Relationships
    user = db.relationship("User", foreign_keys=[user_id])
    quest = db.relationship(
        "Quest", foreign_keys=[quest_id], back_populates="participations"
    )

    # Constraints
    __table_args__ = (db.UniqueConstraint("user_id", "quest_id", name="uq_user_quest"),)

    def __repr__(self) -> str:
        return (
            f"<QuestParticipation user_id={self.user_id} "
            f"quest_id={self.quest_id} "
            f"progress={self.current_progress}/{self.target_progress}>"
        )
