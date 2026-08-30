"""La traccia dei risultati corretti dal direttore.

Il direttore inserisce un punteggio sbagliato e se ne accorge dopo. Correggerlo
si poteva già — annullando e reinserendo — ma i giocatori quel risultato
l'avevano visto, e una classifica che cambia senza dire perché sembra un
errore dell'applicazione, o un favore a qualcuno (issue #90).

La tabella tiene: chi ha corretto, quando, da quale punteggio a quale, lo stato
di prima e una nota facoltativa. Non è un registro amministrativo: è quello che
la pagina della partita mostra accanto al risultato, a chiunque la apra.

`created_at`/`updated_at` ci sono perché `TimestampMixin` le dichiara sul
modello, e una tabella creata senza le colonne che l'ORM si aspetta muore in
silenzio in produzione al primo INSERT (incidente `categoria`, 2026-08-19).

Idempotente: `CREATE TABLE IF NOT EXISTS`.
"""

import sqlite3

migration_name = "20260830_correzione_risultato"

TABELLA = "match_correction"


def _table_exists(cursor: sqlite3.Cursor, table: str) -> bool:
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    )
    return cursor.fetchone() is not None


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db"):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        if _table_exists(cursor, TABELLA):
            print(f"  ⏭️  {TABELLA} c'è già")
            return

        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {TABELLA} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                match_id INTEGER NOT NULL
                    REFERENCES `match`(id) ON DELETE CASCADE,
                corrected_by_id INTEGER NOT NULL REFERENCES user(id),
                previous_player1_score INTEGER,
                previous_player2_score INTEGER,
                previous_status VARCHAR(30),
                new_player1_score INTEGER NOT NULL,
                new_player2_score INTEGER NOT NULL,
                note VARCHAR(200),
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            )
            """)
        cursor.execute(
            f"CREATE INDEX IF NOT EXISTS ix_{TABELLA}_match_id "
            f"ON {TABELLA} (match_id)"
        )
        conn.commit()
        print(f"  ✓ creata {TABELLA}")
    finally:
        conn.close()
