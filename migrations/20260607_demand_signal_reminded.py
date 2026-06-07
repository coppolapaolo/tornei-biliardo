"""Ciclo di vita scadenza segnali-domanda (ADR-036 open item 3).

Aggiunge ``demand_signal.reminded_at`` (DATETIME nullable): traccia l'invio del
prompt di riconferma pre-scadenza, per non re-inviarlo in continuazione.

Idempotente: aggiunge la colonna solo se assente.
"""

import sqlite3

migration_name = "20260607_demand_signal_reminded"


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

    if _table_exists(cursor, "demand_signal") and not _column_exists(
        cursor, "demand_signal", "reminded_at"
    ):
        cursor.execute("ALTER TABLE demand_signal ADD COLUMN reminded_at DATETIME")
        print("  ✓ aggiunta colonna demand_signal.reminded_at")
    else:
        print("  ⏭️  demand_signal.reminded_at già presente (o tabella assente)")

    conn.commit()
    conn.close()
