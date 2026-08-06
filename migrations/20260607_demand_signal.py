"""Segnale-domanda → director (ADR-036).

1. Aggiunge a ``user``:
   - ``signal_radius_km`` (INTEGER NOT NULL DEFAULT 30) — raggio zona director.
   - ``signal_notified_at`` (DATETIME nullable) — cooldown anti-nag.
2. Crea la tabella ``demand_signal`` (richieste geolocalizzate) + indici.

Idempotente: colonne/tabella/indici aggiunti solo se assenti.
"""

import sqlite3

migration_name = "20260607_demand_signal"


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

    if _table_exists(cursor, "user"):
        if not _column_exists(cursor, "user", "signal_radius_km"):
            cursor.execute(
                'ALTER TABLE "user" ADD COLUMN signal_radius_km '
                "INTEGER NOT NULL DEFAULT 30"
            )
            print("  ✓ aggiunta colonna user.signal_radius_km (default 30)")
        else:
            print("  ⏭️  user.signal_radius_km già presente")

        if not _column_exists(cursor, "user", "signal_notified_at"):
            cursor.execute('ALTER TABLE "user" ADD COLUMN signal_notified_at DATETIME')
            print("  ✓ aggiunta colonna user.signal_notified_at")
        else:
            print("  ⏭️  user.signal_notified_at già presente")

    if not _table_exists(cursor, "demand_signal"):
        cursor.execute("""
            CREATE TABLE demand_signal (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
                latitude FLOAT NOT NULL,
                longitude FLOAT NOT NULL,
                city VARCHAR(100),
                status VARCHAR(20) NOT NULL DEFAULT 'active',
                expires_at DATETIME NOT NULL,
                consumed_by_gara_id INTEGER REFERENCES gara(id) ON DELETE SET NULL,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            )
            """)
        print("  ✓ creata tabella demand_signal")
    else:
        print("  ⏭️  tabella demand_signal già presente")

    cursor.execute(
        "CREATE INDEX IF NOT EXISTS ix_demand_signal_user_id "
        "ON demand_signal (user_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS ix_demand_signal_status "
        "ON demand_signal (status)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS ix_demand_signal_lat_lng "
        "ON demand_signal (latitude, longitude)"
    )
    print("  ✓ indici demand_signal garantiti")

    conn.commit()
    conn.close()
