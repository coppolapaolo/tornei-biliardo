"""Il tavolo su cui si è giocato resta scritto sulla partita.

`match.table_assignment` risponde alla domanda «quale tavolo è occupato
adesso»: alla chiusura di una partita torna a NULL, perché è così che il
tavolo rientra in circolo e viene riassegnato a chi sta aspettando.

Il fatto storico «questa partita si è giocata al tavolo 3» spariva insieme
all'occupazione, e nella tabella dei turni le partite concluse potevano solo
mostrare un trattino (issue #154). Sono due domande diverse, e vogliono due
colonne: `played_on_table` non si azzera mai.

Il backfill copia il tavolo delle partite **ancora in corso**, che è l'unico
dato superstite: per le partite già concluse prima di oggi il tavolo non
esiste più da nessuna parte, e resteranno col trattino. Non è recuperabile e
non vale la pena fingere il contrario.

Idempotente: dove la colonna c'è già è un no-op dichiarato.
"""

import sqlite3

migration_name = "20260830_tavolo_giocato"

TABELLA = "match"
COLONNA = "played_on_table"


def _table_exists(cursor: sqlite3.Cursor, table: str) -> bool:
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    )
    return cursor.fetchone() is not None


def _column_exists(cursor: sqlite3.Cursor, table: str, column: str) -> bool:
    cursor.execute(f"PRAGMA table_info(`{table}`)")
    return any(row[1] == column for row in cursor.fetchall())


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db"):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        if not _table_exists(cursor, TABELLA):
            print(f"  ⏭️  {TABELLA} non esiste: niente da fare")
            return

        if _column_exists(cursor, TABELLA, COLONNA):
            print(f"  ⏭️  {TABELLA}.{COLONNA} già presente")
            return

        cursor.execute(f"ALTER TABLE `{TABELLA}` ADD COLUMN {COLONNA} VARCHAR(10)")
        cursor.execute(
            f"UPDATE `{TABELLA}` SET {COLONNA} = table_assignment "
            "WHERE table_assignment IS NOT NULL"
        )
        recuperate = cursor.rowcount
        conn.commit()
        print(f"  ✓ {TABELLA}: aggiunta {COLONNA} ({recuperate} partite in corso)")
    finally:
        conn.close()
