"""
Migration: Remove entry_fee columns from individual match tables.

Individual matches are always free - entry_fee is not needed.
This removes the unused column from both match_proposal and individual_match tables.

Migration name: 20260203_remove_individual_match_entry_fee
"""

import sqlite3
from pathlib import Path

migration_name = "20260203_remove_individual_match_entry_fee"


def upgrade_sqlite(db_path: str):
    """Drop entry_fee columns from match_proposal and individual_match tables.

    SQLite 3.35.0+ (2021) supports DROP COLUMN directly.
    PythonAnywhere uses Python 3.10+ which has SQLite 3.37+.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # For match_proposal table
    cursor.execute("PRAGMA table_info(match_proposal)")
    columns = [row[1] for row in cursor.fetchall()]

    if "entry_fee" in columns:
        cursor.execute("ALTER TABLE match_proposal DROP COLUMN entry_fee")
        print("  Dropped entry_fee column from match_proposal table")
    else:
        print("  entry_fee column already removed from match_proposal")

    # For individual_match table
    cursor.execute("PRAGMA table_info(individual_match)")
    columns = [row[1] for row in cursor.fetchall()]

    if "entry_fee" in columns:
        cursor.execute("ALTER TABLE individual_match DROP COLUMN entry_fee")
        print("  Dropped entry_fee column from individual_match table")
    else:
        print("  entry_fee column already removed from individual_match")

    conn.commit()
    conn.close()


def downgrade_sqlite(db_path: str):
    """Re-add entry_fee columns (for rollback)."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        cursor.execute(
            "ALTER TABLE match_proposal ADD COLUMN entry_fee NUMERIC(10, 2) DEFAULT 0"
        )
        print("  Re-added entry_fee to match_proposal")
    except Exception:
        pass  # Column might already exist

    try:
        cursor.execute(
            "ALTER TABLE individual_match ADD COLUMN entry_fee NUMERIC(10, 2)"
        )
        print("  Re-added entry_fee to individual_match")
    except Exception:
        pass  # Column might already exist

    conn.commit()
    conn.close()


if __name__ == "__main__":
    db_path = Path(__file__).parent.parent / "instance" / "billiard_campionato.db"
    upgrade_sqlite(str(db_path))
