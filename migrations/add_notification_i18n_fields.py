"""Database migration: Add i18n fields to notification table.

Date: 2025-12-29

This migration adds template-based i18n support for notifications:
- template_key: Reference to translatable template (e.g., "achievement.unlocked")
- template_params: JSON parameters for template substitution

This enables notifications to be translated at display time instead of
creation time, allowing proper language switching.

Backward Compatibility:
- Existing notifications keep their static title/message fields
- New notifications can use template_key + template_params
- get_translated_content() method falls back to static fields if template_key is null
"""

import sqlite3
from pathlib import Path


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db") -> None:
    """Run migration for SQLite (development)."""
    db_file = Path(db_path)
    if not db_file.exists():
        print(f"Database not found: {db_path}")
        print("   Run application first to create database")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print(f"Migrating SQLite database: {db_path}")
    print("   Adding i18n fields to notification table...")

    try:
        # Check if table exists
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='notification'
        """)
        if not cursor.fetchone():
            print("   Table 'notification' doesn't exist yet - skipping migration")
            return

        # Check if columns already exist
        cursor.execute("PRAGMA table_info(notification)")
        columns = [col[1] for col in cursor.fetchall()]

        if "template_key" in columns:
            print("   Column 'template_key' already exists - skipping migration")
            return

        # Add template_key column
        print("   Adding 'template_key' column...")
        cursor.execute("""
            ALTER TABLE notification
            ADD COLUMN template_key VARCHAR(100) DEFAULT NULL
        """)

        # Add template_params column
        print("   Adding 'template_params' column...")
        cursor.execute("""
            ALTER TABLE notification
            ADD COLUMN template_params TEXT DEFAULT NULL
        """)

        # Create index for template_key lookups
        print("   Creating index on template_key...")
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_notification_template_key
            ON notification(template_key)
        """)

        conn.commit()
        print("Migration completed successfully!")
        print("   Added columns: template_key, template_params")

    except sqlite3.OperationalError as e:
        conn.rollback()
        if "duplicate column" in str(e).lower():
            print(f"   Columns already exist: {e}")
        else:
            print(f"   Migration failed: {e}")
            raise
    finally:
        conn.close()


def downgrade_sqlite(db_path: str = "instance/billiard_campionato.db") -> None:
    """Rollback migration.

    Note: SQLite doesn't support DROP COLUMN easily.
    This creates a new table without the columns and migrates data.
    """
    db_file = Path(db_path)
    if not db_file.exists():
        print(f"Database not found: {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print("Rolling back notification i18n migration...")
    print("   Note: This will remove template_key and template_params columns")

    try:
        # Get current table structure (without new columns)
        cursor.execute("PRAGMA table_info(notification)")
        columns = cursor.fetchall()

        # Filter out the new columns
        old_columns = [
            col[1]
            for col in columns
            if col[1] not in ("template_key", "template_params")
        ]

        if len(old_columns) == len(columns):
            print("   Columns don't exist - nothing to rollback")
            return

        columns_str = ", ".join(old_columns)

        # Create temporary table without new columns
        cursor.execute(f"""
            CREATE TABLE notification_backup AS
            SELECT {columns_str} FROM notification
        """)

        # Drop original table
        cursor.execute("DROP TABLE notification")

        # Rename backup to original
        cursor.execute("ALTER TABLE notification_backup RENAME TO notification")

        # Drop the index
        cursor.execute("DROP INDEX IF EXISTS idx_notification_template_key")

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
