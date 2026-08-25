"""Aggiunge `user_privacy_setting.show_elo`, l'unica preferenza accesa di suo.

Le altre colonne della tabella nascono a 0 e si accendono per scelta: sono dati
che il giocatore ha dato di suo, o che raccontano come gioca. L'Elo no — e' il
numero con cui due avversari si misurano prima di cominciare, e sul tabellone
della partita serve a tutti e due. Quindi `DEFAULT 1`, e chi non lo vuole lo
spegne.

Due conseguenze pratiche di quel default, ed e' per loro che questa migration
esiste invece di lasciar fare a `db.create_all()`:

* le righe **gia' scritte** (chi ha salvato la pagina privacy prima d'oggi) non
  hanno espresso nessuna preferenza sull'Elo: `ADD COLUMN ... DEFAULT 1` le
  riempie con 1, che e' la risposta giusta — non hanno scelto di nasconderlo;
* le righe che **non esistono** (la stragrande maggioranza: la riga nasce al
  primo salvataggio) le decide `PrivacyService.can_view_field`, che per i campi
  di `OPT_OUT_FIELDS` risponde True anche senza riga. Lo schema da solo non
  basta a chiudere il caso.

Idempotente: se la colonna c'e' gia' e' un no-op dichiarato, non un tentativo.
"""

import sqlite3

migration_name = "20260825_privacy_show_elo"

TABELLA = "user_privacy_setting"
COLONNA = "show_elo"


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
            # Non e' un errore: dove la tabella non c'e' ancora, nascera'
            # completa da `create_all()`, che la colonna ce la mette.
            print(f"  ⏭️  {TABELLA} non esiste: niente da fare")
            return

        if _column_exists(cursor, TABELLA, COLONNA):
            print(f"  ⏭️  {TABELLA}.{COLONNA} c'e' gia'")
            return

        cursor.execute(
            f"ALTER TABLE {TABELLA} ADD COLUMN {COLONNA} BOOLEAN NOT NULL DEFAULT 1"
        )
        # Cintura oltre alle bretelle: il DEFAULT copre gia' le righe esistenti,
        # ma un NULL qui sarebbe letto come «nascosto» da chi legge il campo.
        cursor.execute(f"UPDATE {TABELLA} SET {COLONNA} = 1 WHERE {COLONNA} IS NULL")
        conn.commit()

        cursor.execute(f"SELECT COUNT(*) FROM {TABELLA}")
        print(f"  ✓ {TABELLA}.{COLONNA} aggiunta ({cursor.fetchone()[0]} righe a 1)")
    finally:
        conn.close()


if __name__ == "__main__":
    upgrade_sqlite()
