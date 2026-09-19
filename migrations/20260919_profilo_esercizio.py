"""Il profilo dell'esercizio: abilità, gesti, livello, varianti, voto (ADR-065).

Quattro colonne su `challenge`, una su `challenge_attempt`, tre tabelle nuove:

* `challenge.declared_level`, `family`, `family_step`, `cue_ball_reset`;
* `challenge_attempt.variant_id` — con quale variante è stata fatta la prova;
* `challenge_category` — le voci dei due vocabolari (asse + valore);
* `challenge_variant` — le etichette dx/sx, A/B di uno stesso esercizio;
* `challenge_rating` — il voto da 1 a 5, uno per giocatore per esercizio.

**Nessun backfill, ed è deliberato.** Gli esercizi che ci sono restano senza
categoria e senza livello finché l'autore non glieli dà: «non lo so» e un valore
messo d'ufficio sono cose diverse, e il catalogo filtrerebbe il secondo come
vero. Le prove già registrate restano senza variante per lo stesso motivo.

Idempotente: ALTER preceduto da PRAGMA table_info, CREATE TABLE/INDEX IF NOT
EXISTS. Le tabelle nascono con `created_at` e `updated_at`, che `BaseModel`
pretende (incidente `categoria`, 2026-08-19).
"""

import os
import sqlite3
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

migration_name = "20260919_profilo_esercizio"


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

    _add_column(cursor, "challenge", "declared_level", "INTEGER")
    _add_column(cursor, "challenge", "family", "VARCHAR(80)")
    _add_column(cursor, "challenge", "family_step", "INTEGER")
    _add_column(cursor, "challenge", "cue_ball_reset", "BOOLEAN")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS challenge_category (
            id INTEGER NOT NULL PRIMARY KEY,
            challenge_id INTEGER NOT NULL
                REFERENCES challenge(id) ON DELETE CASCADE,
            axis VARCHAR(20) NOT NULL,
            value VARCHAR(30) NOT NULL,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL,
            CONSTRAINT uq_challenge_category UNIQUE (challenge_id, axis, value)
        )
        """)
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS ix_challenge_category_axis_value "
        "ON challenge_category (axis, value)"
    )
    print("  ✓ Tabella challenge_category")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS challenge_variant (
            id INTEGER NOT NULL PRIMARY KEY,
            challenge_id INTEGER NOT NULL
                REFERENCES challenge(id) ON DELETE CASCADE,
            label VARCHAR(40) NOT NULL,
            position INTEGER NOT NULL DEFAULT 1,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL,
            CONSTRAINT uq_challenge_variant UNIQUE (challenge_id, label)
        )
        """)
    print("  ✓ Tabella challenge_variant")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS challenge_rating (
            id INTEGER NOT NULL PRIMARY KEY,
            challenge_id INTEGER NOT NULL
                REFERENCES challenge(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES user(id) ON DELETE CASCADE,
            rating INTEGER NOT NULL,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL,
            CONSTRAINT uq_challenge_rating UNIQUE (challenge_id, user_id),
            CONSTRAINT ck_challenge_rating_range CHECK (rating BETWEEN 1 AND 5)
        )
        """)
    print("  ✓ Tabella challenge_rating")

    # Dopo `challenge_variant`: la colonna la cita. In SQLite un ADD COLUMN con
    # REFERENCES è ammesso purché il default sia NULL, ed è il nostro caso.
    _add_column(
        cursor,
        "challenge_attempt",
        "variant_id",
        "INTEGER REFERENCES challenge_variant(id) ON DELETE SET NULL",
    )

    conn.commit()
    conn.close()


if __name__ == "__main__":
    upgrade_sqlite()
