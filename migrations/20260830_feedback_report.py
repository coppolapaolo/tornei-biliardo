"""Le tabelle delle segnalazioni degli utenti (issue #255).

`feedback_report` è la segnalazione; `feedback_sync_state` è la riga sola
in cui il job giornaliero ricorda dove era arrivato — il processo nasce e
muore ogni notte, e senza quella riga rileggerebbe da capo ogni volta.

`created_at`/`updated_at` sono scritte a mano nel `CREATE TABLE` perché
`BaseModel` le aggiunge a ogni entità: una migration che le dimentica fa
morire l'ORM in produzione con «no such column», e i test di comportamento non
possono accorgersene — costruiscono lo schema con `db.create_all()`, che legge
i modelli e non questo file (incidente `categoria`, 2026-08-19; presidio in
`tests/new/unit/test_migrations_timestamps.py`).

Idempotente: `CREATE TABLE IF NOT EXISTS`, e gli indici pure.
"""

import sqlite3

migration_name = "20260830_feedback_report"

TABELLA = "feedback_report"
TABELLA_STATO = "feedback_sync_state"


def _table_exists(cursor: sqlite3.Cursor, table: str) -> bool:
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    )
    return cursor.fetchone() is not None


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db"):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        if _table_exists(cursor, TABELLA) and _table_exists(cursor, TABELLA_STATO):
            print(f"  ⏭️  {TABELLA} e {TABELLA_STATO} già presenti")
            return

        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS `{TABELLA}` (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL
                    REFERENCES user(id) ON DELETE CASCADE,
                tipo VARCHAR(20) NOT NULL,
                titolo VARCHAR(200) NOT NULL,
                corpo TEXT NOT NULL,
                contesto TEXT,
                stato VARCHAR(20) NOT NULL DEFAULT 'ricevuta',
                stato_cambiato_il DATETIME,
                nota_pubblica TEXT,
                issue_number INTEGER,
                tentativi_invio INTEGER NOT NULL DEFAULT 0,
                ultimo_errore VARCHAR(500),
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            )
            """)
        cursor.execute(
            f"CREATE INDEX IF NOT EXISTS ix_feedback_report_user "
            f"ON `{TABELLA}` (user_id)"
        )
        cursor.execute(
            f"CREATE INDEX IF NOT EXISTS ix_feedback_report_issue "
            f"ON `{TABELLA}` (issue_number)"
        )
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS `{TABELLA_STATO}` (
                id INTEGER PRIMARY KEY,
                ultimo_controllo DATETIME,
                etag VARCHAR(200),
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            )
            """)
        conn.commit()
        print(f"  ✓ create {TABELLA} (con due indici) e {TABELLA_STATO}")
    finally:
        conn.close()
