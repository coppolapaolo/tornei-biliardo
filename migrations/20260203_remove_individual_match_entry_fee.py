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

    SQLite < 3.35.0 doesn't support DROP COLUMN, so we recreate tables.
    """
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = OFF")
    cursor = conn.cursor()

    # === match_proposal table ===
    cursor.execute("PRAGMA table_info(match_proposal)")
    columns_info = cursor.fetchall()
    columns = [row[1] for row in columns_info]

    if "entry_fee" in columns:
        # Get all columns except entry_fee
        keep_columns = [col for col in columns if col != "entry_fee"]
        columns_str = ", ".join(keep_columns)

        cursor.execute(f"""
            CREATE TABLE match_proposal_new AS
            SELECT {columns_str} FROM match_proposal
        """)
        cursor.execute("DROP TABLE match_proposal")
        cursor.execute("ALTER TABLE match_proposal_new RENAME TO match_proposal")
        print("  Dropped entry_fee column from match_proposal table")
    else:
        print("  entry_fee column already removed from match_proposal")

    # === individual_match table ===
    cursor.execute("PRAGMA table_info(individual_match)")
    columns_info = cursor.fetchall()
    columns = [row[1] for row in columns_info]

    if "entry_fee" in columns:
        # Get all columns except entry_fee
        keep_columns = [col for col in columns if col != "entry_fee"]
        columns_str = ", ".join(keep_columns)

        cursor.execute(f"""
            CREATE TABLE individual_match_new AS
            SELECT {columns_str} FROM individual_match
        """)
        cursor.execute("DROP TABLE individual_match")
        cursor.execute("ALTER TABLE individual_match_new RENAME TO individual_match")
        print("  Dropped entry_fee column from individual_match table")
    else:
        print("  entry_fee column already removed from individual_match")

    conn.execute("PRAGMA foreign_keys = ON")
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
