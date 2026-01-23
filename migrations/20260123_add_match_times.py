"""Add started_at and ended_at fields to Match table.

Also rename IndividualMatch.completed_at to ended_at for consistency.

These fields track match duration for statistical purposes:
- started_at: auto-set when match status → "playing"
- ended_at: auto-set when match status → "completed"
"""

import sqlite3
from pathlib import Path


def upgrade_sqlite(db_path: str):
    """Add time tracking columns to match and individual_match tables."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 1. Add started_at and ended_at to match table
    cursor.execute("PRAGMA table_info(match)")
    match_columns = [col[1] for col in cursor.fetchall()]

    if "started_at" not in match_columns:
        cursor.execute("ALTER TABLE match ADD COLUMN started_at DATETIME")
        print("  Added started_at column to match")

    if "ended_at" not in match_columns:
        cursor.execute("ALTER TABLE match ADD COLUMN ended_at DATETIME")
        print("  Added ended_at column to match")

    # 2. Rename completed_at to ended_at in individual_match table
    # SQLite doesn't support ALTER COLUMN RENAME, so we need to:
    # - Check if completed_at exists and ended_at doesn't
    # - Create a new column ended_at
    # - Copy data from completed_at to ended_at
    # - Note: Can't drop completed_at in SQLite easily, leave it as is

    cursor.execute("PRAGMA table_info(individual_match)")
    indiv_columns = [col[1] for col in cursor.fetchall()]

    if "completed_at" in indiv_columns and "ended_at" not in indiv_columns:
        cursor.execute("ALTER TABLE individual_match ADD COLUMN ended_at DATETIME")
        cursor.execute("UPDATE individual_match SET ended_at = completed_at")
        print("  Added ended_at column to individual_match and copied data from completed_at")
    elif "ended_at" not in indiv_columns:
        # completed_at doesn't exist either, just add ended_at
        cursor.execute("ALTER TABLE individual_match ADD COLUMN ended_at DATETIME")
        print("  Added ended_at column to individual_match")

    conn.commit()
    conn.close()


def downgrade_sqlite(db_path: str):
    """SQLite doesn't support DROP COLUMN easily."""
    print("  Note: SQLite doesn't easily support DROP COLUMN. Columns will remain.")


if __name__ == "__main__":
    db_path = Path(__file__).parent.parent / "instance" / "billiard_campionato.db"
    upgrade_sqlite(str(db_path))
