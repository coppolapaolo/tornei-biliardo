"""I preset di configurazione dei direttori (ADR-082).

Una tabella nuova, nessuna colonna toccata altrove:

* `config_preset` — di chi è, come si chiama, che modulo precompila (`kind`),
  i valori in JSON (`payload`) con la forma in cui sono scritti
  (`schema_version`), e — solo sulle copie ricevute — da chi arrivano e quando.

Il nome è unico per proprietario, e lo dice il database con un indice unico:
è il nome con cui il direttore ritrova il preset, e la copia ricevuta prende
un suffisso proprio per non scontrarsi.

Nessun legame fra gare e preset: il preset precompila e basta.

Idempotente: CREATE TABLE/INDEX IF NOT EXISTS. La tabella nasce con
`created_at` e `updated_at`, che `BaseModel` pretende (incidente `categoria`,
2026-08-19).
"""

import os
import sqlite3
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

migration_name = "20261012_preset_dei_direttori"


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db"):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS config_preset (
            id INTEGER NOT NULL PRIMARY KEY,
            owner_id INTEGER NOT NULL REFERENCES user(id) ON DELETE CASCADE,
            name VARCHAR(100) NOT NULL,
            kind VARCHAR(20) NOT NULL,
            payload TEXT NOT NULL,
            schema_version INTEGER NOT NULL,
            received_from_user_id INTEGER
                REFERENCES user(id) ON DELETE SET NULL,
            received_at DATETIME,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL,
            CONSTRAINT uq_config_preset_owner_name UNIQUE (owner_id, name)
        )
        """)
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS ix_config_preset_owner_id "
        "ON config_preset (owner_id)"
    )
    print("  ✓ Tabella config_preset")

    conn.commit()
    conn.close()


if __name__ == "__main__":
    upgrade_sqlite()
