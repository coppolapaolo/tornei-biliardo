"""Tracciamento attività utente (ADR-036 open item 3 — auto-refresh).

Aggiunge ``user.last_active_at`` (DATETIME nullable): ultimo accesso "attivo"
dell'utente, aggiornato (throttled) a ogni richiesta autenticata. Usato dal job
di scadenza dei segnali-domanda per auto-rinnovare le richieste degli utenti
attivi invece di inviare il prompt di riconferma.

Idempotente: aggiunge la colonna solo se assente.
"""

import sqlite3

migration_name = "20260607_user_last_active"


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

    if _table_exists(cursor, "user") and not _column_exists(
        cursor, "user", "last_active_at"
    ):
        cursor.execute('ALTER TABLE "user" ADD COLUMN last_active_at DATETIME')
        print("  ✓ aggiunta colonna user.last_active_at")
    else:
        print("  ⏭️  user.last_active_at già presente (o tabella user assente)")

    conn.commit()
    conn.close()
