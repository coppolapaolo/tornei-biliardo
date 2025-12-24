# Gamification Domain Documentation

## Purpose

The Gamification domain implements a comprehensive engagement system to create habits and encourage community participation through XP, levels, achievements, streaks, quests, and leaderboards.

**Core Responsibilities:**
- XP and level progression with tangible unlocks
- Achievement system with 20+ categorized badges
- Weekly streak tracking with freeze mechanics
- Multiple leaderboards with caching
- Weekly/monthly quest system
- Event-driven integration with other domains

**Related Domains:**
- See [../match/CLAUDE.md](../match/CLAUDE.md) for match completion events
- See [../competition/CLAUDE.md](../competition/CLAUDE.md) for inscription/completion events
- See [../challenge/](../challenge/) for drill/training integration
- See [../notification/CLAUDE.md](../notification/CLAUDE.md) for gamification notifications

---

## Quick Reference

### Most-Used Classes

```python
from models.gamification.level_service import LevelService
from models.gamification.achievement_service import AchievementService
from models.gamification.streak_service import StreakService
from models.gamification.quest_service import QuestService
from models.gamification.models import (
    UserLevel, XPTransaction, XPTransactionType,
    Achievement, UserAchievement,
    StreakTracker, StreakType,
    Quest, QuestParticipation, QuestType
)

# Award XP
LevelService.award_xp(
    user_id=user.id,
    xp_amount=50,
    transaction_type=XPTransactionType.MATCH_WIN,
    reason="Won match"
)

# Record streak activity
StreakService.record_activity(
    user_id=user.id,
    streak_type=StreakType.WEEKLY_MATCH
)

# Check achievement
AchievementService.check_and_award_achievement(
    user_id=user.id,
    achievement_code="first_blood"
)
```

---

## Architecture Overview

### Event-Driven Integration

The gamification system is **completely decoupled** from other domains through the EventBus pattern:

```
Domain Events                    Gamification Handlers
─────────────────────────────────────────────────────────
MatchCompletedEvent      ──→     handle_match_completed_for_xp()
                                 - Award XP (winner/loser)
                                 - Check achievements
                                 - Record WEEKLY_MATCH streak
                                 - Update quest progress

InscriptionCreatedEvent  ──→     handle_inscription_for_xp()
                                 - Award inscription XP
                                 - Record WEEKLY_TOURNAMENT streak
                                 - Update quest progress

CompetitionCompletedEvent ──→    handle_competition_completed_for_xp()
                                 - Award completion XP (all)
                                 - Award winner bonus
                                 - Award podium bonus
                                 - Update quest progress
```

### Handler Registration

Handlers auto-register on app startup via import in `app.py`:

```python
# app.py
from models.gamification import event_handlers  # noqa: F401
```

---

## Key Services

### LevelService (`level_service.py`)

**Purpose**: XP award logic with automatic level-up detection.

**Key Methods:**

```python
@transactional(domain="gamification")
def award_xp(
    user_id: int,
    xp_amount: int,
    transaction_type: XPTransactionType,
    reason: str = "",
    related_entities: Optional[Dict] = None
) -> Tuple[UserLevel, Optional[int]]:
    """Award XP and check for level up.

    Returns:
        Tuple of (UserLevel, new_level_if_leveled_up)

    Side Effects:
        - Creates XPTransaction record
        - Emits XPGainedEvent
        - Emits LevelUpEvent if level increased
    """

def get_user_level(user_id: int) -> UserLevel:
    """Get or create user level record."""

def get_xp_progress(user_id: int) -> Dict[str, Any]:
    """Get XP progress for display.

    Returns:
        {
            "current_level": int,
            "current_xp": int,
            "xp_for_next_level": int,
            "progress_percentage": float,
            "total_xp": int
        }
    """
```

**XP Rates** (from `xp_config.py`):

| Transaction Type | XP Amount |
|-----------------|-----------|
| MATCH_WIN | 50 |
| MATCH_LOSS | 20 |
| TOURNAMENT_INSCRIPTION | 25 |
| TOURNAMENT_COMPLETION | 100 |
| TOURNAMENT_WIN | 500 |
| TOURNAMENT_PODIUM | 200 |
| STREAK_BONUS | 30 per week |
| CHALLENGE_COMPLETION | 75 |

---

### StreakService (`streak_service.py`)

**Purpose**: Weekly streak tracking with freeze mechanics.

**Key Concepts:**
- Streaks track WEEKLY (not daily) engagement
- ISO week numbering (1-53)
- Freeze tokens protect against missing 1 week
- Missing 2+ weeks breaks the streak

**Streak Types:**

| Type | Tracked By |
|------|-----------|
| WEEKLY_ACTIVITY | Any activity per week |
| WEEKLY_MATCH | At least 1 match per week |
| WEEKLY_TOURNAMENT | At least 1 tournament registration per week |
| WEEKLY_DRILL | At least 1 drill/challenge per week |

**Milestone Rewards:**

| Weeks | Freeze Tokens | XP Bonus |
|-------|--------------|----------|
| 4 | 1 (one-time) | 120 |
| 12 | 1 (recurring) | 360 |
| 52 | 2 (one-time) | 1560 |

**Key Methods:**

```python
@transactional(domain="gamification")
def record_activity(
    user_id: int,
    streak_type: StreakType,
    activity_date: Optional[date] = None
) -> Tuple[StreakTracker, Dict[str, Any]]:
    """Record weekly activity and update streak.

    Returns:
        Tuple of (StreakTracker, result_info)

    Result info:
        - "action": "continued" | "incremented" | "freeze_used" | "broken" | "started"
        - "current_streak": int
        - "milestone_reached": Optional[int]
        - "freeze_earned": int
        - "xp_bonus": int
    """

def get_streak_info(user_id: int, streak_type: StreakType) -> Dict[str, Any]:
    """Get streak info for display.

    Returns:
        {
            "current_streak": int,
            "longest_streak": int,
            "freeze_count": int,
            "is_at_risk": bool,
            "weeks_until_break": int,
            "next_milestone": int or None,
            "milestones_reached": List[int]
        }
    """

def get_all_streaks(user_id: int) -> Dict[str, Dict[str, Any]]:
    """Get all streak types for user."""
```

---

### AchievementService (`achievement_service.py`)

**Purpose**: Achievement eligibility checking and unlock logic.

**Achievement Categories:**
- BEGINNER: First steps
- COMPETITION: Tournament achievements
- SKILL: Match wins, streaks
- SOCIAL: Community engagement
- DEDICATION: Long-term engagement
- SPECIAL: Limited-time events

**Key Methods:**

```python
def check_and_award_achievement(
    user_id: int,
    achievement_code: str,
    progress_increment: int = 0
) -> Optional[UserAchievement]:
    """Check and award achievement if eligible.

    For simple achievements: checks if already unlocked
    For progress achievements: increments progress

    Returns:
        UserAchievement if just unlocked, None otherwise
    """

def get_achievement_progress(
    user_id: int,
    achievement_code: str
) -> Dict[str, Any]:
    """Get achievement progress for display."""

def get_user_achievements(user_id: int) -> List[Dict[str, Any]]:
    """Get all achievements for user with unlock status."""
```

---

### QuestService (`quest_service.py`)

**Purpose**: Weekly/monthly community goal management.

**Quest Types:**
- WEEKLY: 7-day goals
- MONTHLY: 30-day goals
- SPECIAL_EVENT: Limited-time events

**Quest Lifecycle:**
```
UPCOMING ──→ ACTIVE ──→ COMPLETED
                   └──→ EXPIRED
```

**Key Methods:**

```python
@transactional(domain="gamification")
def record_activity_for_quests(
    user_id: int,
    activity_type: str,
    activity_count: int = 1
) -> List[Tuple[Quest, bool]]:
    """Record activity that may progress multiple quests.

    Activity types:
    - "matches_played": Any match completed
    - "matches_won": Match won
    - "tournaments_registered": Inscribed to tournament
    - "tournaments_completed": Finished tournament

    Auto-joins user to matching active quests.

    Returns:
        List of (Quest, just_completed) tuples
    """

def get_user_quests(
    user_id: int,
    include_completed: bool = True,
    active_only: bool = False
) -> List[Dict[str, Any]]:
    """Get quests with participation status."""
```

---

## Event Handlers (`event_handlers.py`)

**Purpose**: Connect gamification to domain events.

### Match Completed Handler

```python
def handle_match_completed_for_xp(event: MatchCompletedEvent):
    """
    Triggered by: MatchService.to_completed()

    Actions:
    1. Award 50 XP to winner (MATCH_WIN)
    2. Award 20 XP to loser (MATCH_LOSS)
    3. Check achievements: first_blood, veteran_player, etc.
    4. Record WEEKLY_MATCH streak for both players
    5. Record WEEKLY_ACTIVITY streak for both players
    6. Update quest progress ("matches_played", "matches_won")
    """
```

### Inscription Handler

```python
def handle_inscription_for_xp(event: InscriptionCreatedEvent):
    """
    Triggered by: InscriptionService.inscribe_user()

    Actions:
    1. Award 25 XP (TOURNAMENT_INSCRIPTION)
    2. Check achievements: tournament_debut, tournament_regular
    3. Record WEEKLY_TOURNAMENT streak
    4. Record WEEKLY_ACTIVITY streak
    5. Update quest progress ("tournaments_registered")
    """
```

### Competition Completed Handler

```python
def handle_competition_completed_for_xp(event: CompetitionCompletedEvent):
    """
    Triggered by: StateService.complete()

    Actions:
    1. Award 100 XP to all participants (TOURNAMENT_COMPLETION)
    2. Award 500 XP bonus to winner (TOURNAMENT_WIN)
    3. Award 200 XP bonus to podium (TOURNAMENT_PODIUM)
    4. Check achievements: champion, podium_finish
    5. Update quest progress ("tournaments_completed")
    """
```

---

## Models Reference

### UserLevel

```python
id: int (PK)
user_id: int (FK, unique)
current_level: int = 1
current_xp: int = 0
total_xp_earned: int = 0
created_at: datetime
updated_at: datetime
```

### XPTransaction

```python
id: int (PK)
user_id: int (FK)
xp_amount: int
transaction_type: XPTransactionType (enum)
reason: str(255)
related_entities: JSON
created_at: datetime
```

### StreakTracker

```python
id: int (PK)
user_id: int (FK)
streak_type: StreakType (enum)
current_streak: int = 0
longest_streak: int = 0
freeze_count: int = 0
total_freeze_earned: int = 0
last_activity_week: int
last_activity_year: int
last_freeze_used_at: date
last_freeze_earned_at: date
milestone_4_reached: bool = False
milestone_12_reached: bool = False
milestone_52_reached: bool = False
```

### Achievement / UserAchievement

```python
# Achievement (definition)
id: int (PK)
code: str(50) - unique
name: str(100)
description: text
category: AchievementCategory (enum)
difficulty: AchievementDifficulty (enum)
icon: str(50)
xp_reward: int
is_hidden: bool = False
requirement_type: str(50)  # "instant" or "progress"
requirement_value: int = 1  # Target for progress achievements

# UserAchievement (user's progress/unlock)
id: int (PK)
user_id: int (FK)
achievement_id: int (FK)
unlocked_at: datetime
progress: int = 0
is_notified: bool = False
```

### Quest / QuestParticipation

```python
# Quest
id: int (PK)
name: str(100)
description: text
quest_type: QuestType (enum)
status: QuestStatus (enum)
start_date: datetime
end_date: datetime
requirements: JSON  # {"type": "matches_played", "target": 10}
xp_reward: int
participant_count: int = 0
completion_count: int = 0

# QuestParticipation
id: int (PK)
user_id: int (FK)
quest_id: int (FK)
current_progress: int = 0
target_progress: int
is_completed: bool = False
completed_at: datetime
xp_awarded: int = 0
```

---

## Common Patterns

### Automatic XP Award on Match

When a match completes, the event chain triggers:

```python
# 1. MatchService.to_completed() emits event
MatchCompletedEvent(match_id=123, winner_id=10, ...)

# 2. Event handler processes
handle_match_completed_for_xp(event)
  → LevelService.award_xp(winner_id, 50, MATCH_WIN)
  → LevelService.award_xp(loser_id, 20, MATCH_LOSS)
  → StreakService.record_activity(player1_id, WEEKLY_MATCH)
  → StreakService.record_activity(player2_id, WEEKLY_MATCH)
  → QuestService.record_activity_for_quests(winner_id, "matches_won")
```

### Streak Milestone Reward

```python
# When streak reaches milestone
tracker, result = StreakService.record_activity(user_id, WEEKLY_MATCH)

if result["milestone_reached"]:
    # 4-week: +1 freeze, +120 XP
    # 12-week: +1 freeze, +360 XP
    # 52-week: +2 freezes, +1560 XP
    print(f"Milestone {result['milestone_reached']} weeks!")
    print(f"Earned {result['freeze_earned']} freeze(s)")
    print(f"+{result['xp_bonus']} XP")
```

---

## File Structure

```
models/gamification/
├── __init__.py              # Package exports
├── CLAUDE.md                # This documentation
├── models.py                # All model classes and enums
├── xp_config.py             # XP rates, level curve, constants
├── level_service.py         # XP and level management
├── achievement_service.py   # Achievement logic
├── achievement_seeds.py     # Default achievement definitions
├── streak_service.py        # Weekly streak tracking
├── quest_service.py         # Quest management
├── leaderboard_service.py   # Leaderboard calculations
├── events.py                # Gamification domain events
├── event_handlers.py        # Handlers for domain events
└── notification_handlers.py # Notification integration
```

---

## Cross-References

- **Match Events**: [../match/CLAUDE.md](../match/CLAUDE.md)
- **Competition Events**: [../competition/CLAUDE.md](../competition/CLAUDE.md)
- **Event System**: [../events/](../events/)
- **Root Architecture**: [../CLAUDE.md](../CLAUDE.md)
