"""
Add total_racks_won column to classification table.

This column stores the total racks won for campionato classification,
which is the primary sort key for Random strategy campionatos.

Addresses ADR-017: Classification model missing racks_won field.
"""

import sqlite3
from pathlib import Path


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db") -> None:
    """Add total_racks_won column to classification table."""
    db_file = Path(db_path)
    if not db_file.exists():
        print(f"Database not found: {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print(f"Migrating SQLite database: {db_path}")

    try:
        print("   Adding 'total_racks_won' column to classification table...")
        try:
            cursor.execute(
                (
                    "ALTER TABLE classification ADD COLUMN total_racks_won INTEGER "
                    "DEFAULT 0"
                )
            )
            print("   Column added successfully.")
        except sqlite3.OperationalError as e:
            if (
                "duplicate column" in str(e).lower()
                or "already exists" in str(e).lower()
            ):
                print("   Column 'total_racks_won' already exists, skipping.")
            else:
                raise

        conn.commit()
        print("Migration completed successfully!")

    except Exception as e:
        conn.rollback()
        print(f"Migration failed: {e}")
        raise
    finally:
        conn.close()


def downgrade_sqlite(db_path: str = "instance/billiard_campionato.db") -> None:
    """Rollback migration - note SQLite limitation on DROP COLUMN."""
    print("Downgrade: Column total_racks_won will remain (SQLite limitation)")


if __name__ == "__main__":
    upgrade_sqlite()
