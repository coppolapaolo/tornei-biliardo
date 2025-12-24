"""
XP Configuration - Rates, Level Progression, and Feature Unlocks

Defines the gamification economy:
- XP award rates for different actions
- Level progression curve (exponential with diminishing returns)
- Feature unlocks at level thresholds
- Freeze earning milestones for weekly streaks

All values are tunable based on community engagement metrics.
"""

from typing import Dict, Optional
from models.gamification.models import XPTransactionType


# ========================================
# XP Award Rates
# ========================================

XP_RATES: Dict[XPTransactionType, int] = {
    XPTransactionType.MATCH_WIN: 50,
    XPTransactionType.MATCH_LOSS: 20,
    XPTransactionType.TOURNAMENT_INSCRIPTION: 25,
    XPTransactionType.TOURNAMENT_COMPLETION: 100,
    XPTransactionType.TOURNAMENT_PODIUM: 200,  # Top 3
    XPTransactionType.TOURNAMENT_WIN: 500,
    XPTransactionType.STREAK_BONUS: 30,  # Multiplied by (weeks / 7) for milestones
    XPTransactionType.CHALLENGE_COMPLETION: 150,
    # ACHIEVEMENT_UNLOCK: Variable (from achievement.xp_reward)
    # ADMIN_ADJUSTMENT: Manual adjustment (can be negative)
}


# ========================================
# Level Progression Curve
# ========================================

def get_xp_for_level(level: int) -> int:
    """
    Calculate total XP required to reach this level from level 1.
    
    Uses exponential curve with power 1.5 for diminishing returns:
    Level 1: 0 XP (starting point)
    Level 2: 100 XP
    Level 3: 285 XP
    Level 5: 1,118 XP
    Level 10: 6,324 XP
    Level 20: 27,568 XP
    Level 50: 176,777 XP
    
    Args:
        level: Target level (1-based)
        
    Returns:
        Total XP needed to reach this level from level 1
    """
    if level <= 1:
        return 0
    base_xp = 100
    return int(base_xp * (level ** 1.5))


def get_xp_for_next_level(current_level: int) -> int:
    """
    Calculate XP needed to reach next level from current level.
    
    Args:
        current_level: Current player level
        
    Returns:
        XP required to level up (difference between current and next level)
    """
    return get_xp_for_level(current_level + 1) - get_xp_for_level(current_level)


def get_level_from_total_xp(total_xp: int) -> int:
    """
    Calculate level from total XP earned.
    
    Reverse lookup: given total XP, determine current level.
    
    Args:
        total_xp: Total lifetime XP
        
    Returns:
        Current level (1-based)
    """
    level = 1
    while get_xp_for_level(level + 1) <= total_xp:
        level += 1
    return level


# ========================================
# Feature Unlocks
# ========================================

LEVEL_UNLOCKS: Dict[int, Dict[str, str]] = {
    5: {
        "feature": "match_proposals",
        "description": "Puoi proporre partite individuali"
    },
    10: {
        "feature": "tournament_creation",
        "description": "Puoi creare tornei standalone"
    },
    15: {
        "feature": "priority_invites",
        "description": "Ricevi notifiche prioritarie per nuovi tornei"
    },
    20: {
        "feature": "custom_badge_display",
        "description": "Personalizza la visualizzazione dei badge"
    },
    25: {
        "feature": "venue_suggestion",
        "description": "Puoi suggerire nuove sedi"
    },
    30: {
        "feature": "challenge_creation",
        "description": "Puoi creare challenge personalizzate"
    },
    40: {
        "feature": "director_fast_track",
        "description": "Richiesta direttore approvata automaticamente"
    },
    50: {
        "feature": "legend_status",
        "description": "Stato Leggenda con icona speciale"
    },
}


def get_next_unlock(current_level: int) -> Optional[Dict[str, any]]:
    """
    Get the next feature unlock above current level.
    
    Args:
        current_level: Player's current level
        
    Returns:
        Dict with level, feature, and description, or None if no more unlocks
    """
    next_unlock_level = None
    for level in sorted(LEVEL_UNLOCKS.keys()):
        if level > current_level:
            next_unlock_level = level
            break
    
    if next_unlock_level is None:
        return None
    
    return {
        "level": next_unlock_level,
        **LEVEL_UNLOCKS[next_unlock_level]
    }


def is_feature_unlocked(current_level: int, feature: str) -> bool:
    """
    Check if feature is unlocked at current level.
    
    Args:
        current_level: Player's current level
        feature: Feature identifier (e.g., "tournament_creation")
        
    Returns:
        True if feature is unlocked
    """
    for level, unlock_info in LEVEL_UNLOCKS.items():
        if unlock_info["feature"] == feature:
            return current_level >= level
    return False


# ========================================
# Weekly Streak Configuration
# ========================================

# Freeze earning milestones (WEEKS, not days)
FREEZE_MILESTONES_WEEKLY: Dict[int, Dict[str, any]] = {
    4: {"freezes": 1, "recurring": False},    # One-time at 4 weeks (1 month)
    12: {"freezes": 1, "recurring": True},    # First time + every 12 weeks (3 months) after
    52: {"freezes": 2, "recurring": False},   # One-time at 52 weeks (1 year)
}

MAX_FREEZE_COUNT = 3

# Week tracking: ISO week number (1-53) + year
# Streak continues if: (current_week - last_week == 1) OR (year transition handled)
# Miss 1 week: use freeze if available
# Miss 2+ weeks: streak breaks


# ========================================
# Quest System Configuration
# ========================================

# Default XP rewards for quest types
QUEST_XP_REWARDS: Dict[str, int] = {
    "WEEKLY": 150,
    "MONTHLY": 500,
    "SPECIAL_EVENT": 1000,
}


# ========================================
# Leaderboard Configuration
# ========================================

# Cache TTLs in seconds for leaderboard types
LEADERBOARD_CACHE_TTL: Dict[str, int] = {
    "XP_ALL_TIME": 3600,       # 1 hour
    "XP_WEEKLY": 1800,         # 30 min
    "XP_MONTHLY": 1800,        # 30 min
    "LEVEL_HIGHEST": 3600,     # 1 hour
    "STREAK_CURRENT": 300,     # 5 min (changes frequently)
    "STREAK_LONGEST": 3600,    # 1 hour
    "WIN_RATE_30_DAYS": 1800,  # 30 min
}
