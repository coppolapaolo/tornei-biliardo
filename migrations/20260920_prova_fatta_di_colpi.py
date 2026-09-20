"""La prova fatta di colpi: come si registra un esercizio, e i suoi colpi (ADR-066).

Due colonne su `challenge` e una tabella nuova:

* `challenge.recording_mode` — `total` (il punteggio scritto a fine prova,
  com'è sempre stato) o `shots` (colpo per colpo). NOT NULL con default
  `total`: **ogni esercizio che c'è resta com'era**, ed è un fatto, non un
  backfill inventato — finora esisteva un modo solo;
* `challenge.shots_count` — quanti colpi ha una prova; NULL col totale;
* `challenge_shot` — un colpo: ordine, esito, punti, e il punto in cui si è
  fermata la battente quando la bilia è entrata.

Idempotente: ALTER preceduto da PRAGMA table_info, CREATE TABLE/INDEX IF NOT
EXISTS. La tabella nasce con `created_at` e `updated_at`, che `BaseModel`
pretende (incidente `categoria`, 2026-08-19).
"""

import os
import sqlite3
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

migration_name = "20260920_prova_fatta_di_colpi"


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

    _add_column(
        cursor, "challenge", "recording_mode", "VARCHAR(20) NOT NULL DEFAULT 'total'"
    )
    _add_column(cursor, "challenge", "shots_count", "INTEGER")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS challenge_shot (
            id INTEGER NOT NULL PRIMARY KEY,
            attempt_id INTEGER NOT NULL
                REFERENCES challenge_attempt(id) ON DELETE CASCADE,
            position INTEGER NOT NULL,
            made BOOLEAN,
            points INTEGER NOT NULL DEFAULT 0,
            x FLOAT,
            y FLOAT,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL,
            CONSTRAINT uq_challenge_shot UNIQUE (attempt_id, position)
        )
        """)
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS ix_challenge_shot_attempt_id "
        "ON challenge_shot (attempt_id)"
    )
    print("  ✓ Tabella challenge_shot")

    conn.commit()
    conn.close()


if __name__ == "__main__":
    upgrade_sqlite()
