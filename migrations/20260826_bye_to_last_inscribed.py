"""Aggiunge `gara.bye_to_last_inscribed`: a chi tocca la X del primo turno.

Nuova scelta del direttore all'avvio di una gara amalfi/casuale con giocatori
dispari gestiti dalla X: sorteggiarla come sempre, oppure assegnarla
all'ultimo iscritto. Il resto degli abbinamenti resta casuale in entrambi i
casi.

`DEFAULT 0` non è una preferenza neutra scelta a caso: è **il comportamento
storico**. Le gare già avviate hanno sorteggiato la X, e nascono con 0 senza
che nulla cambi per loro; le gare ancora da avviare riceveranno il valore vero
al momento dell'avvio, quando il direttore risponde.

Idempotente: se la colonna c'è già è un no-op dichiarato.
"""

import sqlite3

migration_name = "20260826_bye_to_last_inscribed"

TABELLA = "gara"
COLONNA = "bye_to_last_inscribed"


def _table_exists(cursor: sqlite3.Cursor, table: str) -> bool:
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    )
    return cursor.fetchone() is not None


def _column_exists(cursor: sqlite3.Cursor, table: str, column: str) -> bool:
    cursor.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cursor.fetchall())


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db"):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        if not _table_exists(cursor, TABELLA):
            # Dove la tabella non c'è ancora nascerà completa da `create_all()`.
            print(f"  ⏭️  {TABELLA} non esiste: niente da fare")
            return

        if _column_exists(cursor, TABELLA, COLONNA):
            print(f"  ⏭️  {TABELLA}.{COLONNA} c'è già")
            return

        cursor.execute(
            f"ALTER TABLE {TABELLA} ADD COLUMN {COLONNA} BOOLEAN NOT NULL DEFAULT 0"
        )
        # Il DEFAULT copre già le righe esistenti; l'UPDATE è la cintura oltre
        # alle bretelle, perché un NULL qui verrebbe letto come «non scelto» e
        # la colonna è dichiarata NOT NULL nel modello.
        cursor.execute(f"UPDATE {TABELLA} SET {COLONNA} = 0 WHERE {COLONNA} IS NULL")
        conn.commit()

        cursor.execute(f"SELECT COUNT(*) FROM {TABELLA}")
        print(f"  ✓ {TABELLA}.{COLONNA} aggiunta ({cursor.fetchone()[0]} gare a 0)")
    finally:
        conn.close()


if __name__ == "__main__":
    upgrade_sqlite()
