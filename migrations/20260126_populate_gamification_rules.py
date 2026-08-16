"""Database migration: Populate Gamification Rules.
2026-01-26

This migration populates the feature_config table with:
1. Legacy level-based unlocks (converted to Rules)
2. New complex ABAC rules (create_match, manage_availability, etc.)
"""

import sqlite3
import json
from pathlib import Path

# Legacy Defaults (from models.gamification.config_models)
DEFAULT_LEVEL_UNLOCKS = [
    (
        5,
        "match_proposals",
        "Proposte Partita",
        "Sblocca la possibilità di inviare e ricevere proposte di partita",
    ),
    (
        10,
        "tournament_creation",
        "Creazione Tornei",
        "Sblocca la creazione di tornei amichevoli",
    ),
    (
        15,
        "priority_invites",
        "Inviti Prioritari",
        "I tuoi inviti appaiono in cima alla lista",
    ),
    (
        20,
        "custom_badge_display",
        "Bacheca Personalizzata",
        "Scegli quali badge mostrare nel profilo",
    ),
    (25, "venue_suggestion", "Suggerisci Location", "Proponi nuove sale da biliardo"),
    (
        30,
        "challenge_creation",
        "Crea Sfide",
        "Crea sfide personalizzate per la community",
    ),
    (
        40,
        "director_fast_track",
        "Director Fast Track",
        "Accesso prioritario al corso direttori",
    ),
    (
        50,
        "legend_status",
        "Status Leggenda",
        "Icona speciale e riconoscimento nella community",
    ),
]

# New Complex Rules
COMPLEX_FEATURES = [
    # === CORE & SOCIAL ===
    {
        "code": "view_other_profiles",
        "name": "View Other Profiles",
        "rules": [
            {
                "description": "Played at least 1 match",
                "conditions": [
                    {
                        "type": "METRIC",
                        "metric": "total_matches",
                        "operator": "gte",
                        "value": 1,
                    }
                ],
            }
        ],
    },
    {
        "code": "view_global_stats",
        "name": "View Global Statistics",
        "rules": [
            {
                "description": "Level 1 (always unlocked)",
                "conditions": [{"type": "LEVEL", "operator": "gte", "value": 1}],
            }
        ],
    },
    # === MATCHMAKING ===
    {
        "code": "create_match_direct",
        "name": "Create Direct Match",
        "rules": [
            {
                "description": "5+ matches AND 1+ score inserted",
                "conditions": [
                    {
                        "type": "METRIC",
                        "metric": "total_matches",
                        "operator": "gte",
                        "value": 5,
                    },
                    {
                        "type": "METRIC",
                        "metric": "scores_inserted",
                        "operator": "gte",
                        "value": 1,
                    },
                ],
            }
        ],
    },
    {
        "code": "create_match_community",
        "name": "Create Community Match",
        "rules": [
            {
                "description": "15+ total matches",
                "conditions": [
                    {
                        "type": "METRIC",
                        "metric": "total_matches",
                        "operator": "gte",
                        "value": 15,
                    }
                ],
            }
        ],
    },
    {
        "code": "manage_availability",
        "name": "Manage Availability",
        "rules": [
            # OR logic: 3 rule sets
            {
                "description": "Venue Manager Role",
                "conditions": [{"type": "ROLE", "value": "VENUE_MANAGER"}],
            },
            {
                "description": "20+ matches in location",
                "conditions": [
                    {
                        "type": "METRIC",
                        "metric": "matches_in_location",
                        "operator": "gte",
                        "value": 20,
                    }
                ],
            },
            {
                "description": "5+ tournaments in location",
                "conditions": [
                    {
                        "type": "METRIC",
                        "metric": "tournaments_in_location",
                        "operator": "gte",
                        "value": 5,
                    }
                ],
            },
        ],
    },
    # === VENUE MANAGEMENT ===
    {
        "code": "request_venue_manager",
        "name": "Request Venue Manager",
        "rules": [
            {
                "description": "Level 5 AND 50+ matches in location",
                "conditions": [
                    {"type": "LEVEL", "operator": "gte", "value": 5},
                    {
                        "type": "METRIC",
                        "metric": "matches_in_location",
                        "operator": "gte",
                        "value": 50,
                    },
                ],
            }
        ],
    },
    {
        "code": "venue_dashboard",
        "name": "Access Venue Dashboard",
        "rules": [
            {
                "description": "Venue Manager Role",
                "conditions": [{"type": "ROLE", "value": "VENUE_MANAGER"}],
            }
        ],
    },
    # === COMPETITION DIRECTOR ===
    {
        "code": "request_director",
        "name": "Request Director Role",
        "rules": [
            {
                "description": "Level 3 AND 1+ tournament played",
                "conditions": [
                    {"type": "LEVEL", "operator": "gte", "value": 3},
                    {
                        "type": "METRIC",
                        "metric": "tournaments_played",
                        "operator": "gte",
                        "value": 1,
                    },
                ],
            }
        ],
    },
    {
        "code": "create_gara",
        "name": "Create Standalone Tournament",
        "rules": [
            {
                "description": "Director Role",
                "conditions": [{"type": "ROLE", "value": "DIRECTOR"}],
            }
        ],
    },
    {
        "code": "create_campionato",
        "name": "Create Championship",
        "rules": [
            {
                "description": "Director + 3 tournaments organized",
                "conditions": [
                    {"type": "ROLE", "value": "DIRECTOR"},
                    {
                        "type": "METRIC",
                        "metric": "tournaments_organized",
                        "operator": "gte",
                        "value": 3,
                    },
                ],
            },
            {
                "description": "Legend Level (50+)",
                "conditions": [{"type": "LEVEL", "operator": "gte", "value": 50}],
            },
        ],
    },
    # === CHALLENGES (DRILLS) ===
    {
        "code": "do_challenge",
        "name": "Participate in Challenges",
        "rules": [
            # OR logic
            {
                "description": "Level 5+",
                "conditions": [{"type": "LEVEL", "operator": "gte", "value": 5}],
            },
            {
                "description": "Completed 1+ tournament drill",
                "conditions": [
                    {
                        "type": "METRIC",
                        "metric": "tournament_drills_completed",
                        "operator": "gte",
                        "value": 1,
                    }
                ],
            },
        ],
    },
    {
        "code": "create_challenge",
        "name": "Create New Challenge",
        "rules": [
            {
                "description": "Level 5 AND 5+ challenges completed",
                "conditions": [
                    {"type": "LEVEL", "operator": "gte", "value": 5},
                    {
                        "type": "METRIC",
                        "metric": "challenges_completed",
                        "operator": "gte",
                        "value": 5,
                    },
                ],
            }
        ],
    },
]


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db") -> None:
    """Run data migration for SQLite."""
    db_file = Path(db_path)
    if not db_file.exists():
        # Fallback logic
        alt_path = "instance/tornei_biliardo.db"
        if Path(alt_path).exists():
            db_path = alt_path
            db_file = Path(db_path)

    if not db_file.exists():
        print(f"Database not found: {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print(f"Migrating Data (Gamification Rules): {db_path}")

    try:
        # 1. Migrate Legacy Levels
        for level, code, name, description in DEFAULT_LEVEL_UNLOCKS:
            # Create Rule: Level >= X
            rule_set = {
                "description": f"Requires Level {level}",
                "conditions": [{"type": "LEVEL", "operator": "gte", "value": level}],
            }
            rules_json = json.dumps([rule_set])

            # Insert or Ignore
            cursor.execute(
                """
                INSERT
                    OR IGNORE INTO feature_config (code, name, description, rules,
                    is_active, created_at, updated_at)
                VALUES (?, ?, ?, ?, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
                (code, name, description, rules_json),
            )

        print(f"   Processed {len(DEFAULT_LEVEL_UNLOCKS)} legacy level rules.")

        # 2. Migrate Complex Features
        for cf in COMPLEX_FEATURES:
            code = cf["code"]
            name = cf["name"]
            rules_json = json.dumps(cf["rules"])
            description = "Complex rule migrated from system defaults"

            # Upsert (Replace if exists)
            # Note: REPLACE INTO deletes and re-inserts, effectively updating but
            # resetting creation time.
            # For migration purposes this is acceptable.
            cursor.execute(
                """
                INSERT
                    OR REPLACE INTO feature_config (code, name, description, rules,
                    is_active, created_at, updated_at)
                VALUES (?, ?, ?, ?, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
                (code, name, description, rules_json),
            )

        print(f"   Processed {len(COMPLEX_FEATURES)} complex rules.")

        conn.commit()
        print("Data migration completed successfully!")

    except Exception as e:
        conn.rollback()
        print(f"Data migration failed: {e}")
        raise
    finally:
        conn.close()
