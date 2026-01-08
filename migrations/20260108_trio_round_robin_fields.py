# migrations/20260108_trio_round_robin_fields.py
"""
Add round-robin tracking fields to trio_match table.

These fields support the new trio round-robin system where trios play
multiple "gironi" (rounds) based on the gara distance.

See ADR-005 for full specification.
"""


def upgrade_sqlite(db_path: str):
    """Add new columns to trio_match for round-robin tracking (SQLite)."""
    import sqlite3

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get existing columns
    cursor.execute("PRAGMA table_info(trio_match)")
    columns = [col[1] for col in cursor.fetchall()]

    if "current_round" not in columns:
        cursor.execute(
            "ALTER TABLE trio_match ADD COLUMN current_round INTEGER DEFAULT 1"
        )
        print("  Added: current_round")

    if "current_rack_in_round" not in columns:
        cursor.execute(
            "ALTER TABLE trio_match ADD COLUMN current_rack_in_round INTEGER DEFAULT 0"
        )
        print("  Added: current_rack_in_round")

    if "total_racks_played" not in columns:
        cursor.execute(
            "ALTER TABLE trio_match ADD COLUMN total_racks_played INTEGER DEFAULT 0"
        )
        print("  Added: total_racks_played")

    if "bonus_applied" not in columns:
        cursor.execute(
            "ALTER TABLE trio_match ADD COLUMN bonus_applied INTEGER DEFAULT 0"
        )
        print("  Added: bonus_applied")

    conn.commit()
    conn.close()
    print("Migration 20260108_trio_round_robin_fields: Added round-robin fields")
