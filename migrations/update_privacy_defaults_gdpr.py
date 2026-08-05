"""Database migration: Update privacy defaults to False for GDPR compliance.

Date: 2025-12-29

This migration changes the default values for privacy settings from True (visible)
to False (private) for GDPR compliance. The GDPR requires opt-in consent for
sharing personal data, meaning data should be private by default.

Changes:
- show_email: DEFAULT 1 -> DEFAULT 0
- show_phone: DEFAULT 1 -> DEFAULT 0
- show_statistics: DEFAULT 1 -> DEFAULT 0
- show_recent_matches: DEFAULT 1 -> DEFAULT 0
- show_classifications: DEFAULT 1 -> DEFAULT 0
- show_challenge_stats: DEFAULT 1 -> DEFAULT 0

Note: This migration does NOT modify existing records. Users who have already
configured their privacy settings will retain their choices. Only new records
will use the new (private) defaults.
"""

import sqlite3
from pathlib import Path


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db") -> None:
    """Run migration for SQLite (development).

    SQLite doesn't support ALTER COLUMN for changing defaults, so we need to:
    1. Create a new table with correct defaults
    2. Copy existing data
    3. Drop old table
    4. Rename new table
    """
    db_file = Path(db_path)
    if not db_file.exists():
        print(f"Database not found: {db_path}")
        print("   Run application first to create database")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print(f"Migrating SQLite database: {db_path}")
    print("   Updating privacy defaults to False for GDPR compliance...")

    try:
        # Check if table exists
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='user_privacy_setting'
        """)
        if not cursor.fetchone():
            print(
                "   Table 'user_privacy_setting' doesn't exist yet - skipping migration"
            )
            return

        # 1. Create new table with correct defaults (0 = False)
        print("   Creating temporary table with new defaults...")
        cursor.execute("""
            CREATE TABLE user_privacy_setting_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL UNIQUE,
                show_email BOOLEAN NOT NULL DEFAULT 0,
                show_phone BOOLEAN NOT NULL DEFAULT 0,
                show_statistics BOOLEAN NOT NULL DEFAULT 0,
                show_recent_matches BOOLEAN NOT NULL DEFAULT 0,
                show_classifications BOOLEAN NOT NULL DEFAULT 0,
                show_challenge_stats BOOLEAN NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES user(id) ON DELETE CASCADE
            )
        """)

        # 2. Copy existing data (preserving user choices)
        print("   Copying existing user privacy settings...")
        cursor.execute("""
            INSERT INTO user_privacy_setting_new
                (id, user_id, show_email, show_phone, show_statistics,
                 show_recent_matches, show_classifications, show_challenge_stats,
                 created_at, updated_at)
            SELECT
                id, user_id, show_email, show_phone, show_statistics,
                show_recent_matches, show_classifications, show_challenge_stats,
                created_at, updated_at
            FROM user_privacy_setting
        """)

        # 3. Drop old table
        print("   Removing old table...")
        cursor.execute("DROP TABLE user_privacy_setting")

        # 4. Rename new table
        print("   Renaming new table...")
        cursor.execute(
            "ALTER TABLE user_privacy_setting_new RENAME TO user_privacy_setting"
        )

        # 5. Recreate index
        print("   Recreating index...")
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_privacy_user_id
            ON user_privacy_setting(user_id)
        """)

        conn.commit()
        print("Migration completed successfully!")
        print("   Privacy defaults changed from True to False (GDPR compliance)")
        print("   Existing user settings preserved")

    except sqlite3.OperationalError as e:
        conn.rollback()
        if "no such table" in str(e).lower():
            print(f"   Table doesn't exist yet, migration not needed: {e}")
        else:
            print(f"   Migration failed: {e}")
            raise
    finally:
        conn.close()


def downgrade_sqlite(db_path: str = "instance/billiard_campionato.db") -> None:
    """Rollback migration - restore defaults to True.

    Note: This reverts the table structure but does NOT change existing data.
    """
    db_file = Path(db_path)
    if not db_file.exists():
        print(f"Database not found: {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print("Rolling back privacy defaults migration...")

    try:
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='user_privacy_setting'
        """)
        if not cursor.fetchone():
            print("   Table doesn't exist - nothing to rollback")
            return

        # Recreate with old defaults (1 = True)
        cursor.execute("""
            CREATE TABLE user_privacy_setting_old (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL UNIQUE,
                show_email BOOLEAN NOT NULL DEFAULT 1,
                show_phone BOOLEAN NOT NULL DEFAULT 1,
                show_statistics BOOLEAN NOT NULL DEFAULT 1,
                show_recent_matches BOOLEAN NOT NULL DEFAULT 1,
                show_classifications BOOLEAN NOT NULL DEFAULT 1,
                show_challenge_stats BOOLEAN NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES user(id) ON DELETE CASCADE
            )
        """)

        cursor.execute("""
            INSERT INTO user_privacy_setting_old
                (id, user_id, show_email, show_phone, show_statistics,
                 show_recent_matches, show_classifications, show_challenge_stats,
                 created_at, updated_at)
            SELECT
                id, user_id, show_email, show_phone, show_statistics,
                show_recent_matches, show_classifications, show_challenge_stats,
                created_at, updated_at
            FROM user_privacy_setting
        """)

        cursor.execute("DROP TABLE user_privacy_setting")
        cursor.execute(
            "ALTER TABLE user_privacy_setting_old RENAME TO user_privacy_setting"
        )
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_privacy_user_id
            ON user_privacy_setting(user_id)
        """)

        conn.commit()
        print("Rollback completed!")

    except sqlite3.OperationalError as e:
        conn.rollback()
        print(f"   Rollback failed: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "downgrade":
        downgrade_sqlite()
    else:
        upgrade_sqlite()
