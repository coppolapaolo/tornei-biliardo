"""
Add province field to billiard_hall table for geographic matching.

Migration: 20260201_add_province_to_billiard_hall
"""

import sqlite3
from pathlib import Path

migration_name = "20260201_add_province_to_billiard_hall"


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db") -> None:
    """Add province column to billiard_hall table (SQLite)."""
    db_file = Path(db_path)
    if not db_file.exists():
        print(f"Database not found: {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        cursor.execute(
            "ALTER TABLE billiard_hall ADD COLUMN province VARCHAR(2) NULL"
        )
        conn.commit()
        print("  Added 'province' column to billiard_hall table")
    except sqlite3.OperationalError as e:
        if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
            print("  Column 'province' already exists, skipping")
        else:
            raise
    finally:
        conn.close()


def downgrade_sqlite(db_path: str = "instance/billiard_campionato.db") -> None:
    """Remove province column from billiard_hall table (SQLite)."""
    # SQLite doesn't support DROP COLUMN easily, but we can ignore for now
    print("  Downgrade: province column will remain (SQLite limitation)")
