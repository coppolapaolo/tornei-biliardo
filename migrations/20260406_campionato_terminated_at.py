"""Add terminated_at column to campionato table.

Supports manual termination of a campionato even when not all gare
are completed. Idempotent: checks column existence before ALTER.
"""

import sqlite3

migration_name = "20260406_campionato_terminated_at"


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db"):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("PRAGMA table_info(campionato)")
    cols = {row[1] for row in cursor.fetchall()}

    if "terminated_at" not in cols:
        cursor.execute(
            "ALTER TABLE campionato ADD COLUMN terminated_at DATETIME DEFAULT NULL"
        )
        print("  ✓ campionato.terminated_at added")
    else:
        print("  ⏭️  campionato.terminated_at already exists")

    conn.commit()
    conn.close()
