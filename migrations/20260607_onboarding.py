"""Onboarding obbligatorio (ADR-035).

Aggiunge a ``user``:
- ``onboarding_completed`` (BOOLEAN NOT NULL DEFAULT 0) — flag one-time;
  default 0 per tutti gli account esistenti (backfill) → eseguono l'onboarding
  al primo login successivo.
- ``onboarding_interests`` (VARCHAR nullable) — CSV di interessi dichiarati.

Idempotente: aggiunge ogni colonna solo se assente.
"""

import sqlite3

migration_name = "20260607_onboarding"


def _table_exists(cursor: sqlite3.Cursor, table: str) -> bool:
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    )
    return cursor.fetchone() is not None


def _column_exists(cursor: sqlite3.Cursor, table: str, column: str) -> bool:
    cursor.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cursor.fetchall())


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db"):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    if not _table_exists(cursor, "user"):
        print("  ⏭️  tabella user assente, skip")
        conn.close()
        return

    if not _column_exists(cursor, "user", "onboarding_completed"):
        cursor.execute(
            'ALTER TABLE "user" ADD COLUMN onboarding_completed '
            "BOOLEAN NOT NULL DEFAULT 0"
        )
        print("  ✓ aggiunta colonna user.onboarding_completed (default 0)")
    else:
        print("  ⏭️  user.onboarding_completed già presente")

    if not _column_exists(cursor, "user", "onboarding_interests"):
        cursor.execute(
            'ALTER TABLE "user" ADD COLUMN onboarding_interests VARCHAR(100)'
        )
        print("  ✓ aggiunta colonna user.onboarding_interests")
    else:
        print("  ⏭️  user.onboarding_interests già presente")

    conn.commit()
    conn.close()
