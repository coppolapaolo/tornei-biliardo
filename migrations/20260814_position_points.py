"""Punti per posizione dei campionati a tabellone (US-17).

Due colonne, entrambe al servizio del sistema di classifica POSITION:

1. ``campionato.position_points`` — tabella punti **configurabile**, come JSON
   ``{"1": 25, "2": 18, ...}``. NULL significa "usa il default della spec"
   (25 / 18 / 15 / 12, 8 dal 5° all'8°, 4 dal 9° al 16°), che è il caso
   normale: un campionato non deve configurare niente per funzionare, e i
   campionati esistenti non cambiano punteggio perché nessuno di loro usa
   POSITION.

2. ``classification.total_position_points`` — la somma di quei punti per
   giocatore. Senza questa colonna la classifica mostrerebbe solo la posizione
   finale, senza far vedere da dove viene.

Idempotente: ogni ALTER è preceduto da PRAGMA table_info.
"""

import os
import sqlite3
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

migration_name = "20260814_position_points"


def _column_exists(cursor: sqlite3.Cursor, table: str, column: str) -> bool:
    cursor.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cursor.fetchall())


def _add_column(cursor: sqlite3.Cursor, table: str, column: str, ddl: str) -> None:
    if _column_exists(cursor, table, column):
        print(f"  ⏭️  {table}.{column} già esistente")
        return
    cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
    print(f"  ✓ Aggiunta colonna {table}.{column}")


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db"):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    _add_column(cursor, "campionato", "position_points", "TEXT")
    _add_column(cursor, "classification", "total_position_points", "INTEGER DEFAULT 0")

    conn.commit()
    conn.close()
    print("  ✓ Migration completata")


if __name__ == "__main__":
    upgrade_sqlite()
