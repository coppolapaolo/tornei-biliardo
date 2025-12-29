"""Database migration: Update notification template_params to use raw keys.

Date: 2025-12-29

Updates existing notifications to use raw keys for i18n at display time:
- difficulty_key instead of difficulty (for achievements)
- type_key instead of type (for streaks and quests)

This enables proper translation when user changes language.
"""

import sqlite3
import json
from pathlib import Path


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db") -> None:
    """Run migration for SQLite (development)."""
    db_file = Path(db_path)
    if not db_file.exists():
        print(f"Database not found: {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print(f"Migrating SQLite database: {db_path}")
    print("   Updating notification template_params to use raw keys...")

    # Mapping of translated difficulty labels back to keys
    difficulty_label_to_key = {
        "Livello Comune": "common",
        "Livello Non Comune": "uncommon",
        "Livello Raro": "rare",
        "Livello Epico": "epic",
        "Livello Leggendario": "legendary",
        # Also handle old format without "Livello" prefix
        "Comune": "common",
        "Non Comune": "uncommon",
        "Raro": "rare",
        "Epico": "epic",
        "Leggendario": "legendary",
    }

    # Mapping of translated streak type labels back to keys
    streak_label_to_key = {
        "attività": "weekly_activity",
        "partite": "weekly_match",
        "tornei": "weekly_tournament",
        "allenamenti": "weekly_drill",
    }

    # Mapping of translated quest type labels back to keys
    quest_label_to_key = {
        "Settimanale": "weekly",
        "Mensile": "monthly",
        "Evento Speciale": "special_event",
    }

    try:
        # Get all notifications with template_key set
        cursor.execute("""
            SELECT id, template_key, template_params
            FROM notification
            WHERE template_key IS NOT NULL AND template_params IS NOT NULL
        """)
        notifications = cursor.fetchall()

        updated_count = 0

        for notif_id, template_key, template_params_str in notifications:
            try:
                params = json.loads(template_params_str)
            except (json.JSONDecodeError, TypeError):
                continue

            modified = False

            # Handle achievement notifications
            if template_key == "achievement.unlocked":
                if "difficulty" in params and "difficulty_key" not in params:
                    difficulty_label = params.pop("difficulty")
                    # Try to reverse-map to key
                    difficulty_key = difficulty_label_to_key.get(
                        difficulty_label, difficulty_label
                    )
                    params["difficulty_key"] = difficulty_key
                    modified = True

            # Handle streak milestone notifications
            elif template_key == "gamification.streak_milestone":
                if "type" in params and "type_key" not in params:
                    type_label = params.pop("type")
                    # Try to reverse-map to key
                    type_key = streak_label_to_key.get(type_label, type_label)
                    params["type_key"] = type_key
                    modified = True

            # Handle quest completed notifications
            elif template_key == "gamification.quest_completed":
                if "type" in params and "type_key" not in params:
                    type_label = params.pop("type")
                    # Try to reverse-map to key
                    type_key = quest_label_to_key.get(type_label, type_label)
                    params["type_key"] = type_key
                    modified = True

            if modified:
                cursor.execute(
                    "UPDATE notification SET template_params = ? WHERE id = ?",
                    (json.dumps(params), notif_id)
                )
                updated_count += 1

        conn.commit()
        print(f"Migration completed successfully!")
        print(f"   Updated {updated_count} notifications with raw key format")

    except sqlite3.OperationalError as e:
        conn.rollback()
        print(f"   Migration failed: {e}")
        raise
    finally:
        conn.close()


def downgrade_sqlite(db_path: str = "instance/billiard_campionato.db") -> None:
    """Rollback migration - convert keys back to translated labels."""
    print("Downgrade not implemented - keys remain as raw values")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "downgrade":
        downgrade_sqlite()
    else:
        upgrade_sqlite()
