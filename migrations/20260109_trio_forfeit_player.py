"""Add forfeit_player_id to trio_match table.

This migration adds support for forfeit handling in trio matches.
When a player forfeits, their remaining racks are auto-assigned to opponents.
"""

import sqlite3
from pathlib import Path


def upgrade_sqlite(db_path: str):
    """Add forfeit_player_id column to trio_match table."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check if column already exists
    cursor.execute("PRAGMA table_info(trio_match)")
    columns = [col[1] for col in cursor.fetchall()]

    if "forfeit_player_id" not in columns:
        cursor.execute(
            (
                "ALTER TABLE trio_match ADD COLUMN forfeit_player_id INTEGER "
                "REFERENCES user(id)"
            )
        )
        print("  Added forfeit_player_id column to trio_match")

    conn.commit()
    conn.close()


def downgrade_sqlite(db_path: str):
    """Remove forfeit_player_id column (SQLite doesn't support DROP COLUMN easily)."""
    print("  Note: SQLite doesn't easily support DROP COLUMN. Column will remain.")


if __name__ == "__main__":
    db_path = Path(__file__).parent.parent / "instance" / "billiard_campionato.db"
    upgrade_sqlite(str(db_path))
