"""Supporto al modello di prossimità (ADR-034).

1. Aggiunge `user.home_city` (VARCHAR nullable, opt-in) — città "home"
   auto-dichiarata usata come fallback quando il GPS del browser non è
   disponibile. Nessuna coordinata utente è memorizzata.
2. Crea un indice su `billiard_hall(latitude, longitude)` per il pre-filtro
   bounding-box delle query di prossimità.

Idempotente: aggiunge la colonna solo se assente; l'indice usa IF NOT EXISTS.
"""

import sqlite3

migration_name = "20260606_geo_proximity"


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
        cursor, "user", "home_city"
    ):
        cursor.execute('ALTER TABLE "user" ADD COLUMN home_city VARCHAR(100)')
        print("  ✓ aggiunta colonna user.home_city")
    else:
        print("  ⏭️  user.home_city già presente (o tabella user assente)")

    if _table_exists(cursor, "billiard_hall"):
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS ix_billiard_hall_lat_lng "
            "ON billiard_hall (latitude, longitude)"
        )
        print("  ✓ indice ix_billiard_hall_lat_lng garantito")

    conn.commit()
    conn.close()
