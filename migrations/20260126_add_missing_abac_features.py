"""Database migration: Add Missing ABAC Features.
2026-01-26

This migration adds the 8 missing features from the original ABAC plan:
- view_other_profiles
- view_global_stats
- request_venue_manager
- venue_dashboard
- request_director
- create_gara
- do_challenge
- create_challenge (updated version)
"""

import sqlite3
import json
from pathlib import Path

# Missing Features from Original Plan
MISSING_FEATURES = [
    {
        "code": "view_other_profiles",
        "name": "View Other Profiles",
        "description": "View profiles of other players",
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
        "description": "Access global statistics and leaderboards",
        "rules": [
            {
                "description": "Level 1 (always unlocked for authenticated users)",
                "conditions": [{"type": "LEVEL", "operator": "gte", "value": 1}],
            }
        ],
    },
    {
        "code": "request_venue_manager",
        "name": "Request Venue Manager",
        "description": "Request venue manager role",
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
        "description": "Access venue manager dashboard",
        "rules": [
            {
                "description": "Venue Manager Role",
                "conditions": [{"type": "ROLE", "value": "VENUE_MANAGER"}],
            }
        ],
    },
    {
        "code": "request_director",
        "name": "Request Director Role",
        "description": "Request tournament director role",
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
        "description": "Create standalone tournaments (gara)",
        "rules": [
            {
                "description": "Director Role",
                "conditions": [{"type": "ROLE", "value": "DIRECTOR"}],
            }
        ],
    },
    {
        "code": "do_challenge",
        "name": "Participate in Challenges",
        "description": "Participate in skill challenges",
        "rules": [
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
        "description": "Create new skill challenges for the community",
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

    print(f"Migrating Data (Missing ABAC Features): {db_path}")

    try:
        # Add missing features
        for feature in MISSING_FEATURES:
            code = feature["code"]
            name = feature["name"]
            description = feature.get("description", "")
            rules_json = json.dumps(feature["rules"])

            # Use INSERT OR REPLACE to update if exists
            cursor.execute(
                """
                INSERT
                    OR REPLACE INTO feature_config (code, name, description, rules,
                    is_active, created_at, updated_at)
                VALUES (?, ?, ?, ?, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
                (code, name, description, rules_json),
            )

        print(f"   Processed {len(MISSING_FEATURES)} missing features.")

        conn.commit()
        print("Data migration completed successfully!")

    except Exception as e:
        conn.rollback()
        print(f"Data migration failed: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    upgrade_sqlite()
