# ADR-019: Gamification ABAC (Attribute-Based Access Control) Migration

## Status
Accepted

## Date
2026-01-26

## Context
The platform started with a simple Level accumulation system where features were unlocked purely based on User Level (integer).
Start-up requirements evolved to include more complex "Rule-based" logic, such as:
- Unlocking features based on number of matches played.
- Role-based overrides (Directors always have access).
- "Nudge" system to encourage users to try newly unlocked features.

The hardcoded checks (`if user.level >= 10:`) were becoming unmanageable and inflexible.

## Decision
We migrated to an **Attribute-Based Access Control (ABAC)** system for gamification features.

### 1. New Data Models
- **FeatureConfig**: Stores the definition of a restricted features and its access rules in JSON format.
  - `code`: Unique string identifier (e.g. `create_match_direct`).
  - `rules`: JSON list of "Rule Sets".
- **UserFeatureUsage**: Tracks if/when a user utilized a specific feature. used for the Nudge system.

### 2. UnlockEngine
A central `UnlockEngine` replaces direct level checks. It evaluates the JSON rules against the user's current context (User Metrics, Roles, Levels).

Rule Logic:
- **OR** between Rule Sets (if *any* set passes, access is granted).
- **AND** between Conditions within a set (all conditions in a set must be met).

Condition Types supported:
- `LEVEL` (Legacy level check)
- `METRIC` (e.g., `total_matches`, `tournaments_organized`)
- `ROLE` (e.g., `DIRECTOR`, `VENUE_MANAGER`)
- `ACHIEVEMENT` (e.g., has specific badge)

### 3. User Override
Added `gamification_override` column to User table to allow Admin bypassing of all gamification rules for specific users (e.g., testing or VIPs).

### 4. Migration Strategy
- **Schema**: Created new tables via standard migration.
- **Data**: Script `scripts/migrate_gamification_rules.py` converts old `DEFAULT_LEVEL_UNLOCKS` into `LEVEL` condition rules in the new system.
- **Code**: Updated `LevelService.check_unlock_eligibility` to delegate to `UnlockEngine`.

## Consequences

### Positive
- **Flexibility**: Can add complex rules (e.g. "Level 5 OR 10 Matches") without code changes.
- **Granularity**: Can gate features by specific metrics, encouraging specific behaviors (e.g. "Play 5 matches to unlock direct creation").
- **Nudge**: Tracking usage allows us to guide users to features they earned but haven't touched.

### Negative
- **Complexity**: Evaluating JSON rules is slightly heavier than a simple integer compare (though negligible for this scale).
- **DB Queries**: Requires fetching FeatureConfig; however, caching can be implemented if needed.

## References
- `models/gamification/unlock_engine.py`
- `models/gamification/feature_models.py`
- `scripts/migrate_gamification_rules.py`
