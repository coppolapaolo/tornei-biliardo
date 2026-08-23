"""Peso della prova, modalità di classifica finale, e chi ha risposto all'invito.

Tre aggiunte, tutte su tabelle esistenti:

* ``gara.weight`` — il moltiplicatore del punteggio della prova in classifica
  generale (issue #64). Default 1: con tutti i pesi a 1 la somma pesata è
  identica alla somma piatta di prima, quindi nessun campionato esistente
  cambia classifica per effetto di questa migration.
* ``playoff_configuration.final_ranking_mode`` / ``playoff_weight`` — come il
  playoff entra nella classifica finale, e quanto pesa quando i due punteggi si
  sommano. Il default è ``campionato_plus_playoff`` perché **è** il
  comportamento storico: la gara di playoff nasce con ``campionato_id``
  valorizzato, quindi l'aggregatore la contava già, con peso implicito 1.
* ``playoff_qualification.responded_by_id`` — chi ha materialmente risposto
  all'invito. NULL sulle righe storiche: di quelle non lo sappiamo, e scrivere
  l'``user_id`` per riempire il vuoto direbbe «ha risposto il giocatore» senza
  averlo verificato.

Idempotente: si guarda il PRAGMA invece di provare e sperare.
"""

import sqlite3

migration_name = "20260823_playoff_final_ranking_and_weight"

#: (tabella, colonna, definizione SQL)
COLONNE = (
    ("gara", "weight", "INTEGER NOT NULL DEFAULT 1"),
    (
        "playoff_configuration",
        "final_ranking_mode",
        "VARCHAR(32) NOT NULL DEFAULT 'campionato_plus_playoff'",
    ),
    ("playoff_configuration", "playoff_weight", "INTEGER NOT NULL DEFAULT 1"),
    (
        "playoff_qualification",
        "responded_by_id",
        "INTEGER REFERENCES user(id)",
    ),
)


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
        aggiunte = 0
        for tabella, colonna, definizione in COLONNE:
            if not _table_exists(cursor, tabella):
                # Dove la tabella non c'è ancora nascerà completa, da
                # `db.create_all()` o dalla migration che la crea.
                print(f"  ⏭️  {tabella} non esiste: niente da fare")
                continue
            if _column_exists(cursor, tabella, colonna):
                print(f"  ⏭️  {tabella}.{colonna} già presente")
                continue

            cursor.execute(f"ALTER TABLE {tabella} ADD COLUMN {colonna} {definizione}")
            aggiunte += 1
            print(f"  ✓ {tabella}.{colonna} aggiunta")

        conn.commit()
        print(f"  ✓ Colonne aggiunte: {aggiunte}")
    finally:
        conn.close()


if __name__ == "__main__":
    upgrade_sqlite()
