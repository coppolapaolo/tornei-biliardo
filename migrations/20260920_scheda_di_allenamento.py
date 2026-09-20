"""La scheda di allenamento: voci, lettori, sedute, registro (ADR-067, #172).

Cinque tabelle nuove, nessuna colonna toccata: la scheda non cambia niente di
quello che c'era.

* `training_sheet` — la scheda; livello, soglia, giorni e durata sono NULL per
  chi non li usa, e NULL vuol dire «non si è detto», mai uno zero inventato;
* `training_sheet_item` — la voce: quale esercizio, quanto farne, come si
  segna. `is_active` perché una voce con registrazioni **si ritira**;
* `training_sheet_reader` — chi legge la scheda, da quando a quando (D11);
* `training_session` — la seduta, con la **versione** della scheda di allora;
* `training_entry` — la casella: il numero, e la misura e il «su quanto» che
  quella sera erano veri.

Due indici unici **parziali**, che in SQLite si possono fare e servono:
la posizione è unica fra le voci attive, e la casella è una per (seduta, voce,
variante) — con un UNIQUE pieno due caselle senza variante passerebbero
entrambe, perché in SQL NULL non è uguale a NULL.

Idempotente: CREATE TABLE/INDEX IF NOT EXISTS. Le tabelle nascono con
`created_at` e `updated_at`, che `BaseModel` pretende (incidente `categoria`,
2026-08-19).
"""

import os
import sqlite3
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

migration_name = "20260920_scheda_di_allenamento"


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db"):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS training_sheet (
            id INTEGER NOT NULL PRIMARY KEY,
            name VARCHAR(120) NOT NULL,
            owner_id INTEGER NOT NULL REFERENCES user(id) ON DELETE CASCADE,
            level INTEGER,
            threshold INTEGER,
            threshold_streak INTEGER NOT NULL DEFAULT 1,
            weeks INTEGER,
            uses_days BOOLEAN NOT NULL DEFAULT 0,
            version INTEGER NOT NULL DEFAULT 1,
            is_active BOOLEAN NOT NULL DEFAULT 1,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL
        )
        """)
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS ix_training_sheet_owner_id "
        "ON training_sheet (owner_id)"
    )
    print("  ✓ Tabella training_sheet")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS training_sheet_item (
            id INTEGER NOT NULL PRIMARY KEY,
            sheet_id INTEGER NOT NULL
                REFERENCES training_sheet(id) ON DELETE CASCADE,
            challenge_id INTEGER NOT NULL
                REFERENCES challenge(id) ON DELETE CASCADE,
            position INTEGER NOT NULL,
            section VARCHAR(60),
            day VARCHAR(12),
            measure VARCHAR(20) NOT NULL DEFAULT 'made',
            amount INTEGER,
            per_variant BOOLEAN NOT NULL DEFAULT 0,
            is_active BOOLEAN NOT NULL DEFAULT 1,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL
        )
        """)
    cursor.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_training_sheet_item_position "
        "ON training_sheet_item (sheet_id, position) WHERE is_active = 1"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS ix_training_sheet_item_sheet_id "
        "ON training_sheet_item (sheet_id)"
    )
    print("  ✓ Tabella training_sheet_item")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS training_sheet_reader (
            id INTEGER NOT NULL PRIMARY KEY,
            sheet_id INTEGER NOT NULL
                REFERENCES training_sheet(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES user(id) ON DELETE CASCADE,
            granted_at DATETIME NOT NULL,
            revoked_at DATETIME,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL
        )
        """)
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS ix_training_sheet_reader_user_id "
        "ON training_sheet_reader (user_id)"
    )
    print("  ✓ Tabella training_sheet_reader")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS training_session (
            id INTEGER NOT NULL PRIMARY KEY,
            sheet_id INTEGER NOT NULL
                REFERENCES training_sheet(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES user(id) ON DELETE CASCADE,
            sheet_version INTEGER NOT NULL DEFAULT 1,
            day VARCHAR(12),
            started_at DATETIME NOT NULL,
            ended_at DATETIME,
            notes TEXT,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL
        )
        """)
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS ix_training_session_sheet_user "
        "ON training_session (sheet_id, user_id)"
    )
    print("  ✓ Tabella training_session")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS training_entry (
            id INTEGER NOT NULL PRIMARY KEY,
            session_id INTEGER NOT NULL
                REFERENCES training_session(id) ON DELETE CASCADE,
            item_id INTEGER NOT NULL
                REFERENCES training_sheet_item(id) ON DELETE CASCADE,
            variant_id INTEGER
                REFERENCES challenge_variant(id) ON DELETE CASCADE,
            value INTEGER,
            done BOOLEAN,
            marks VARCHAR(200),
            measure VARCHAR(20) NOT NULL,
            target_amount INTEGER,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL
        )
        """)
    cursor.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_training_entry_variant "
        "ON training_entry (session_id, item_id, variant_id) "
        "WHERE variant_id IS NOT NULL"
    )
    cursor.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_training_entry_plain "
        "ON training_entry (session_id, item_id) WHERE variant_id IS NULL"
    )
    print("  ✓ Tabella training_entry")

    conn.commit()
    conn.close()


if __name__ == "__main__":
    upgrade_sqlite()
