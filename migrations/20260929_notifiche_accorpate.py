"""Le notifiche delle modifiche a una gara, accorpate (ADR-075).

Una tabella nuova, `settings_notice`: la notifica in attesa per una gara, al
più una per gara (`gara_id` unico). Tiene i valori di partenza dei campi
modificati, quando è cambiato qualcosa la prima e l'ultima volta, e — dopo un
invio parziale per le ore di silenzio — chi manca ancora. La manda lo
scheduled task orario `send_match_reminders.py`.

`ON DELETE CASCADE` sulla gara: la notifica appartiene a lei.

Idempotente: CREATE TABLE/INDEX IF NOT EXISTS. La tabella nasce con
`created_at` e `updated_at`, che `BaseModel` pretende.
"""

import sqlite3

migration_name = "20260929_notifiche_accorpate"


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db"):
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings_notice (
                id INTEGER NOT NULL PRIMARY KEY,
                gara_id INTEGER NOT NULL UNIQUE
                    REFERENCES gara(id) ON DELETE CASCADE,
                initial_values TEXT NOT NULL,
                pending_user_ids TEXT,
                first_change_at DATETIME NOT NULL,
                last_change_at DATETIME NOT NULL,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            )
            """)
        print("  ✓ Tabella settings_notice")
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    upgrade_sqlite()
