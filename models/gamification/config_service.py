"""
Gamification Configuration Service - Database-backed configuration reader

This service provides access to gamification configuration stored in the database,
with fallback to default values from xp_config.py for backward compatibility.

Features:
- In-memory caching for performance
- Cache invalidation on config updates
- Fallback to hardcoded defaults if DB not populated
- Thread-safe cache access
"""

from __future__ import annotations
from typing import Dict, Any, List, Optional, Tuple
import logging
from threading import Lock

from models.base import db
from models.transaction.manager import transactional
from models.gamification.config_models import (
    GamificationConfig,
    LevelUnlock,
    StreakMilestone,
    DEFAULT_XP_RATES,
    DEFAULT_LEVEL_PARAMS,
    DEFAULT_STREAK_CONFIG,
)
from models.gamification.models import XPTransactionType

logger = logging.getLogger(__name__)


class GamificationConfigService:
    """
    Service for reading gamification configuration from database.

    Uses in-memory caching for performance. Cache is invalidated
    when configuration is updated via admin interface.

    Usage:
        # Get XP rate for match win
        xp = GamificationConfigService.get_xp_rate(XPTransactionType.MATCH_WIN)

        # Get level curve parameters
        base, power = GamificationConfigService.get_level_curve_params()

        # After admin updates config
        GamificationConfigService.invalidate_cache()
    """

    _cache: Dict[str, Any] = {}
    _cache_lock = Lock()
    _cache_initialized = False

    @classmethod
    def _get_config(cls, key: str, default: int = 0) -> int:
        """
        Get a configuration value from cache or database.

        Falls back to default if not found in database.
        """
        with cls._cache_lock:
            if key in cls._cache:
                return cls._cache[key]

        # Try database
        try:
            config = db.session.get(GamificationConfig, key)
            if config:
                with cls._cache_lock:
                    cls._cache[key] = config.value
                return config.value
        except Exception as e:
            logger.warning(f"Error reading config {key}: {e}")

        # Fallback to default
        with cls._cache_lock:
            cls._cache[key] = default
        return default

    @classmethod
    def get_xp_rate(cls, transaction_type: XPTransactionType) -> int:
        """
        Get XP rate for a transaction type.

        Args:
            transaction_type: Type of XP transaction

        Returns:
            XP amount for this transaction type
        """
        key = f"xp_{transaction_type.value}"
        default_tuple = DEFAULT_XP_RATES.get(key, (50, ""))
        default = default_tuple[0] if isinstance(default_tuple, tuple) else default_tuple
        return cls._get_config(key, default)

    @classmethod
    def get_level_curve_params(cls) -> Tuple[int, float]:
        """
        Get level curve parameters.

        Returns:
            Tuple of (base_xp, power) for level calculation
            Formula: xp_for_level = base_xp * (level ** power)
        """
        base = cls._get_config("level_base_xp", DEFAULT_LEVEL_PARAMS["level_base_xp"][0])
        # Power is stored as int * 100 (e.g., 150 = 1.5)
        power_int = cls._get_config("level_power", DEFAULT_LEVEL_PARAMS["level_power"][0])
        power = power_int / 100.0
        return base, power

    @classmethod
    def get_max_freeze_count(cls) -> int:
        """Get maximum freeze tokens a user can hold."""
        return cls._get_config(
            "max_freeze_count",
            DEFAULT_STREAK_CONFIG["max_freeze_count"][0]
        )

    @classmethod
    def get_level_unlocks(cls) -> List[LevelUnlock]:
        """
        Get all active level unlocks ordered by level.

        Returns:
            List of LevelUnlock objects. Falls back to default values
            if database is not populated.

        Note: Objects are detached from session to allow safe caching.
        All attributes are pre-loaded before caching.
        """
        from models.gamification.config_models import DEFAULT_LEVEL_UNLOCKS

        cache_key = "_level_unlocks"
        with cls._cache_lock:
            if cache_key in cls._cache:
                return cls._cache[cache_key]

        try:
            unlocks = LevelUnlock.query.filter_by(is_active=True).order_by(
                LevelUnlock.level
            ).all()
            # If DB is empty, use defaults (for tests or initial setup)
            if not unlocks:
                # Create mock objects for fallback
                unlocks = cls._create_default_level_unlocks()
            else:
                # Pre-load all attributes while still in session context
                # to prevent DetachedInstanceError when accessed later
                for unlock in unlocks:
                    _ = unlock.level
                    _ = unlock.feature_code
                    _ = unlock.feature_name
                    _ = unlock.description
                    _ = unlock.is_active
                # Expunge from session to make them safe for caching
                for unlock in unlocks:
                    db.session.expunge(unlock)
            with cls._cache_lock:
                cls._cache[cache_key] = unlocks
            return unlocks
        except Exception as e:
            logger.warning(f"Error reading level unlocks: {e}, using defaults")
            unlocks = cls._create_default_level_unlocks()
            with cls._cache_lock:
                cls._cache[cache_key] = unlocks
            return unlocks

    @classmethod
    def _create_default_level_unlocks(cls) -> List[LevelUnlock]:
        """Create mock LevelUnlock objects from defaults (for fallback)."""
        from models.gamification.config_models import DEFAULT_LEVEL_UNLOCKS

        result = []
        for level, feature_code, feature_name, description in DEFAULT_LEVEL_UNLOCKS:
            # Create a detached object (not added to session)
            unlock = LevelUnlock(
                level=level,
                feature_code=feature_code,
                feature_name=feature_name,
                description=description,
                is_active=True
            )
            result.append(unlock)
        return result

    @classmethod
    def get_level_unlock_at(cls, level: int) -> Optional[LevelUnlock]:
        """
        Get unlock at specific level.

        Args:
            level: Level to check

        Returns:
            LevelUnlock if one exists at this level, None otherwise
        """
        unlocks = cls.get_level_unlocks()
        for unlock in unlocks:
            if unlock.level == level:
                return unlock
        return None

    @classmethod
    def is_feature_unlocked(cls, level: int, feature_code: str) -> bool:
        """
        Check if a feature is unlocked at given level.

        Args:
            level: User's current level
            feature_code: Feature code to check (e.g., "director_fast_track")

        Returns:
            True if feature is unlocked at this level
        """
        unlocks = cls.get_level_unlocks()
        for unlock in unlocks:
            if unlock.feature_code == feature_code and unlock.level <= level:
                return True
        return False

    @classmethod
    def get_next_unlock(cls, current_level: int) -> Optional[Dict[str, Any]]:
        """
        Get next feature unlock after current level.

        Args:
            current_level: User's current level

        Returns:
            Dict with unlock info or None if no more unlocks
        """
        unlocks = cls.get_level_unlocks()
        for unlock in unlocks:
            if unlock.level > current_level:
                return {
                    "level": unlock.level,
                    "feature_code": unlock.feature_code,
                    "feature_name": unlock.feature_name,
                    "description": unlock.description,
                }
        return None

    @classmethod
    def get_streak_milestones(cls) -> List[StreakMilestone]:
        """
        Get all active streak milestones ordered by weeks.

        Returns:
            List of StreakMilestone objects

        Note: Objects are detached from session to allow safe caching.
        """
        cache_key = "_streak_milestones"
        with cls._cache_lock:
            if cache_key in cls._cache:
                return cls._cache[cache_key]

        try:
            milestones = StreakMilestone.query.filter_by(is_active=True).order_by(
                StreakMilestone.weeks
            ).all()
            if milestones:
                # Pre-load all attributes while still in session context
                # to prevent DetachedInstanceError when accessed later
                for milestone in milestones:
                    _ = milestone.weeks
                    _ = milestone.freeze_tokens
                    _ = milestone.xp_bonus
                    _ = milestone.badge_name
                    _ = milestone.is_active
                # Expunge from session to make them safe for caching
                for milestone in milestones:
                    db.session.expunge(milestone)
            with cls._cache_lock:
                cls._cache[cache_key] = milestones
            return milestones
        except Exception as e:
            logger.warning(f"Error reading streak milestones: {e}")
            return []

    @classmethod
    def get_streak_milestone_at(cls, weeks: int) -> Optional[StreakMilestone]:
        """
        Get milestone at specific week count.

        Args:
            weeks: Number of weeks in streak

        Returns:
            StreakMilestone if one exists at this week, None otherwise
        """
        milestones = cls.get_streak_milestones()
        for milestone in milestones:
            if milestone.weeks == weeks:
                return milestone
        return None

    @classmethod
    def invalidate_cache(cls) -> None:
        """
        Invalidate all cached configuration.

        Call this after updating configuration via admin interface.
        """
        with cls._cache_lock:
            cls._cache.clear()
            cls._cache_initialized = False
        logger.info("Gamification config cache invalidated")

    @classmethod
    def get_all_xp_rates(cls) -> Dict[str, int]:
        """
        Get all XP rates as a dictionary.

        Returns:
            Dict mapping transaction type to XP amount
        """
        rates = {}
        for tx_type in XPTransactionType:
            rates[tx_type.value] = cls.get_xp_rate(tx_type)
        return rates

    @classmethod
    def get_all_config(cls) -> Dict[str, Any]:
        """
        Get all configuration for admin display.

        Returns:
            Dict with all configuration values grouped by category
        """
        try:
            configs = GamificationConfig.query.all()
            result: Dict[str, Dict[str, Any]] = {}

            for config in configs:
                category = config.category or "general"
                if category not in result:
                    result[category] = {}
                result[category][config.key] = {
                    "value": config.value,
                    "description": config.description,
                }

            return result
        except Exception as e:
            logger.error(f"Error reading all config: {e}")
            return {}

    # ========================================
    # Level Calculation Helpers
    # ========================================

    @classmethod
    def get_xp_for_level(cls, level: int) -> int:
        """
        Calculate total XP required to reach this level from level 1.

        Uses exponential curve: XP = base_xp * (level ** power)

        Args:
            level: Target level (1-based)

        Returns:
            Total XP needed to reach this level from level 1
        """
        if level <= 1:
            return 0
        base, power = cls.get_level_curve_params()
        return int(base * (level ** power))

    @classmethod
    def get_xp_for_next_level(cls, current_level: int) -> int:
        """
        Calculate XP needed to reach next level from current level.

        Args:
            current_level: Current player level

        Returns:
            XP required to level up
        """
        return cls.get_xp_for_level(current_level + 1) - cls.get_xp_for_level(current_level)

    @classmethod
    def get_level_from_total_xp(cls, total_xp: int) -> int:
        """
        Calculate level from total XP earned.

        Args:
            total_xp: Total lifetime XP

        Returns:
            Current level (1-based)
        """
        level = 1
        while cls.get_xp_for_level(level + 1) <= total_xp:
            level += 1
        return level

    @classmethod
    def get_level_unlock_dict(cls, level: int) -> Optional[Dict[str, str]]:
        """
        Get unlock info as dict for a specific level.

        Args:
            level: Level to check

        Returns:
            Dict with feature and description, or None
        """
        unlock = cls.get_level_unlock_at(level)
        if unlock:
            return {
                "feature": unlock.feature_code,
                "description": unlock.description or ""
            }
        return None

    @classmethod
    def get_all_level_unlocks_dict(cls) -> Dict[int, Dict[str, str]]:
        """
        Get all level unlocks as dict keyed by level.

        Returns:
            Dict mapping level -> {feature, description}
        """
        result = {}
        unlocks = cls.get_level_unlocks()
        for unlock in unlocks:
            result[unlock.level] = {
                "feature": unlock.feature_code,
                "description": unlock.description or ""
            }
        return result

    # ========================================
    # Admin Write Operations
    # ========================================

    @classmethod
    @transactional(domain="gamification")
    def update_config(cls, key: str, value: int, updated_by_id: int) -> GamificationConfig:
        """Update a configuration value. Invalidates cache.

        Raises:
            ValueError: If key empty, value negative, or config not found.
        """
        if not key:
            raise ValueError("Chiave configurazione mancante")
        if value < 0:
            raise ValueError("Il valore non può essere negativo")
        config = db.session.get(GamificationConfig, key)
        if not config:
            raise ValueError("Configurazione non trovata")
        config.value = value
        config.updated_by_id = updated_by_id
        cls.invalidate_cache()
        logger.info(f"Config '{key}' updated to {value} by user {updated_by_id}")
        return config

    @classmethod
    @transactional(domain="gamification")
    def add_level_unlock(
        cls, level: int, feature_code: str, feature_name: str, description: str
    ) -> LevelUnlock:
        """Add a new level unlock.

        Raises:
            ValueError: If validation fails or level already has unlock.
        """
        if level < 1:
            raise ValueError("Il livello deve essere almeno 1")
        if not feature_code or not feature_name:
            raise ValueError("Codice e nome feature sono obbligatori")
        if LevelUnlock.query.filter_by(level=level).first():
            raise ValueError(f"Il livello {level} ha già un unlock definito")
        unlock = LevelUnlock(
            level=level,
            feature_code=feature_code,
            feature_name=feature_name,
            description=description,
            is_active=True,
        )
        db.session.add(unlock)
        cls.invalidate_cache()
        logger.info(f"Added level unlock at level {level}: {feature_code}")
        return unlock

    @classmethod
    @transactional(domain="gamification")
    def update_level_unlock(
        cls, unlock_id: int, feature_name: str, description: str, is_active: bool
    ) -> LevelUnlock:
        """Update an existing level unlock.

        Raises:
            ValueError: If unlock not found or feature_name empty.
        """
        unlock = db.session.get(LevelUnlock, unlock_id)
        if not unlock:
            raise ValueError("Level unlock non trovato")
        if not feature_name:
            raise ValueError("Il nome feature è obbligatorio")
        unlock.feature_name = feature_name
        unlock.description = description
        unlock.is_active = is_active
        cls.invalidate_cache()
        logger.info(f"Updated level unlock {unlock_id}")
        return unlock

    @classmethod
    @transactional(domain="gamification")
    def delete_level_unlock(cls, unlock_id: int) -> None:
        """Delete a level unlock.

        Raises:
            ValueError: If unlock not found.
        """
        unlock = db.session.get(LevelUnlock, unlock_id)
        if not unlock:
            raise ValueError("Level unlock non trovato")
        level = unlock.level
        db.session.delete(unlock)
        cls.invalidate_cache()
        logger.info(f"Deleted level unlock at level {level}")

    @classmethod
    @transactional(domain="gamification")
    def add_streak_milestone(
        cls,
        weeks: int,
        freeze_tokens: int,
        xp_bonus_multiplier: int,
        is_recurring: bool,
    ) -> StreakMilestone:
        """Add a new streak milestone.

        Raises:
            ValueError: If validation fails or weeks already has milestone.
        """
        if weeks < 1:
            raise ValueError("Le settimane devono essere almeno 1")
        if freeze_tokens < 0:
            raise ValueError("I freeze token non possono essere negativi")
        if StreakMilestone.query.filter_by(weeks=weeks).first():
            raise ValueError(f"Milestone per {weeks} settimane già esistente")
        milestone = StreakMilestone(
            weeks=weeks,
            freeze_tokens=freeze_tokens,
            xp_bonus_multiplier=xp_bonus_multiplier,
            is_recurring=is_recurring,
            is_active=True,
        )
        db.session.add(milestone)
        cls.invalidate_cache()
        logger.info(f"Added streak milestone at {weeks} weeks")
        return milestone

    @classmethod
    @transactional(domain="gamification")
    def update_streak_milestone(
        cls,
        milestone_id: int,
        freeze_tokens: int,
        xp_bonus_multiplier: int,
        is_recurring: bool,
        is_active: bool,
    ) -> StreakMilestone:
        """Update an existing streak milestone.

        Raises:
            ValueError: If milestone not found or freeze_tokens negative.
        """
        milestone = db.session.get(StreakMilestone, milestone_id)
        if not milestone:
            raise ValueError("Milestone non trovato")
        if freeze_tokens < 0:
            raise ValueError("I freeze token non possono essere negativi")
        milestone.freeze_tokens = freeze_tokens
        milestone.xp_bonus_multiplier = xp_bonus_multiplier
        milestone.is_recurring = is_recurring
        milestone.is_active = is_active
        cls.invalidate_cache()
        logger.info(f"Updated streak milestone {milestone_id}")
        return milestone

    @classmethod
    @transactional(domain="gamification")
    def delete_streak_milestone(cls, milestone_id: int) -> None:
        """Delete a streak milestone.

        Raises:
            ValueError: If milestone not found.
        """
        milestone = db.session.get(StreakMilestone, milestone_id)
        if not milestone:
            raise ValueError("Milestone non trovato")
        weeks = milestone.weeks
        db.session.delete(milestone)
        cls.invalidate_cache()
        logger.info(f"Deleted streak milestone at {weeks} weeks")
