# migrations/20260109_trio_awaiting_confirmation.py
"""
Add awaiting_confirmation field to trio_match table.

This field supports a two-phase completion flow:
1. After all racks are played, trio enters awaiting_confirmation state
2. User must confirm the result before match is marked completed
"""


def upgrade_sqlite(db_path: str):
    """Add awaiting_confirmation column to trio_match (SQLite)."""
    import sqlite3

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get existing columns
    cursor.execute("PRAGMA table_info(trio_match)")
    columns = [col[1] for col in cursor.fetchall()]

    if "awaiting_confirmation" not in columns:
        cursor.execute(
            "ALTER TABLE trio_match ADD COLUMN awaiting_confirmation INTEGER DEFAULT 0"
        )
        print("  Added: awaiting_confirmation")

    conn.commit()
    conn.close()
    print("Migration 20260109_trio_awaiting_confirmation: Added confirmation field")
