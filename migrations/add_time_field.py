#!/usr/bin/env python3
"""
Migration script to add time field to the Gara table.
"""

import sqlite3
import sys
from pathlib import Path

# Database path
DB_PATH = Path(__file__).parent.parent / "instance" / "billiard_campionato.db"


def migrate():
    """Add time column to the gara table."""

    if not DB_PATH.exists():
        print(f"Database not found at {DB_PATH}")
        return False

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Check if column already exists
        cursor.execute("PRAGMA table_info(gara)")
        columns = [col[1] for col in cursor.fetchall()]

        if "time" not in columns:
            print("Adding time column...")
            cursor.execute("ALTER TABLE gara ADD COLUMN time TIME")
            conn.commit()
            print("Successfully added time column to gara table")
        else:
            print("Time column already exists, no migration needed")

        return True

    except Exception as e:
        print(f"Error during migration: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


if __name__ == "__main__":
    success = migrate()
    sys.exit(0 if success else 1)
