# migrations/20260109_trio_player_confirmations.py
"""
Add individual player confirmation fields to trio_match table.

This supports the 3-player confirmation workflow:
- All 3 players must confirm before a trio match is completed
- OR an admin/director can bypass and validate directly

Fields added:
- player1_confirmed: Boolean, default False
- player2_confirmed: Boolean, default False
- player3_confirmed: Boolean, default False
"""


def upgrade_sqlite(db_path: str):
    """Add player confirmation columns to trio_match (SQLite)."""
    import sqlite3

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get existing columns
    cursor.execute("PRAGMA table_info(trio_match)")
    columns = [col[1] for col in cursor.fetchall()]

    added = []

    if "player1_confirmed" not in columns:
        cursor.execute(
            "ALTER TABLE trio_match ADD COLUMN player1_confirmed INTEGER DEFAULT 0"
        )
        added.append("player1_confirmed")

    if "player2_confirmed" not in columns:
        cursor.execute(
            "ALTER TABLE trio_match ADD COLUMN player2_confirmed INTEGER DEFAULT 0"
        )
        added.append("player2_confirmed")

    if "player3_confirmed" not in columns:
        cursor.execute(
            "ALTER TABLE trio_match ADD COLUMN player3_confirmed INTEGER DEFAULT 0"
        )
        added.append("player3_confirmed")

    conn.commit()
    conn.close()

    if added:
        print(f"  Added: {', '.join(added)}")
    else:
        print("  No changes needed (columns already exist)")

    print(
        "Migration 20260109_trio_player_confirmations: Added player confirmation fields"
    )
