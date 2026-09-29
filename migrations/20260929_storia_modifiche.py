"""La storia delle modifiche alle impostazioni (ADR-075).

Due tabelle nuove, nessuna colonna toccata:

* `settings_change` — una voce per salvataggio: di cosa parla (gara,
  campionato o configurazione dei playoff), chi ha agito e con che ruolo, da
  dove, che cosa è successo, il motivo facoltativo, da che turno vale;
* `settings_change_field` — le righe della voce: campo, prima, dopo.

Le chiavi verso gara, campionato e configurazione dei playoff sono `ON DELETE
CASCADE`: la storia appartiene a ciò che descrive. L'autore è `SET NULL`: la
voce resta anche se l'utente sparisce, perché la modifica è avvenuta.

Nessun backfill: per le modifiche di prima non c'è storia, e la pagina lo dice.

Idempotente: CREATE TABLE/INDEX IF NOT EXISTS. Le tabelle nascono con
`created_at` e `updated_at`, che `BaseModel` pretende (incidente `categoria`,
2026-08-19).
"""

import sqlite3

migration_name = "20260929_storia_modifiche"


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db"):
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings_change (
                id INTEGER NOT NULL PRIMARY KEY,
                gara_id INTEGER REFERENCES gara(id) ON DELETE CASCADE,
                campionato_id INTEGER REFERENCES campionato(id) ON DELETE CASCADE,
                playoff_config_id INTEGER
                    REFERENCES playoff_configuration(id) ON DELETE CASCADE,
                author_id INTEGER REFERENCES user(id) ON DELETE SET NULL,
                author_role VARCHAR(20),
                source VARCHAR(20) NOT NULL,
                action VARCHAR(30) NOT NULL,
                reason TEXT,
                from_round INTEGER,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            )
            """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings_change_field (
                id INTEGER NOT NULL PRIMARY KEY,
                change_id INTEGER NOT NULL
                    REFERENCES settings_change(id) ON DELETE CASCADE,
                field VARCHAR(50) NOT NULL,
                old_value TEXT,
                new_value TEXT,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            )
            """)
        for nome, tabella, colonna in (
            ("ix_settings_change_gara_id", "settings_change", "gara_id"),
            ("ix_settings_change_campionato_id", "settings_change", "campionato_id"),
            (
                "ix_settings_change_playoff_config_id",
                "settings_change",
                "playoff_config_id",
            ),
            (
                "ix_settings_change_field_change_id",
                "settings_change_field",
                "change_id",
            ),
        ):
            cursor.execute(
                f"CREATE INDEX IF NOT EXISTS {nome} ON {tabella} ({colonna})"
            )
        print("  ✓ Tabelle settings_change e settings_change_field")
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    upgrade_sqlite()
