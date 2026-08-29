"""L'esercizio giocato al posto della X lo sceglie il direttore.

Con `odd_number_policy = "bye_with_challenge"` chi resta senza avversario gioca
un esercizio, e il punteggio diventa la sua differenza triangoli in quel turno
(`SPECIFICHE.md` riga 65). **Quale** esercizio, però, finora non lo decideva
nessuno: `get_challenge_for_x_replacement` pescava dal catalogo globale il meno
usato fra quelli attivi e a punteggio (issue #267).

Non è un problema di comodità ma di equità: in una gara a numero dispari riposa
una persona diversa a ogni turno, e se l'esercizio cambia da un turno all'altro
due giocatori ricevono prove di difficoltà diversa il cui punteggio finisce
nella stessa classifica, con lo stesso peso.

Da qui la colonna, e da qui il fatto che stia sulla **gara** e non sul turno: un
esercizio solo per tutte le X è l'unica configurazione in cui la X è la stessa
prova per tutti.

NULL resta legittimo e significa «scegli tu»: è il comportamento storico, ed è
quello che vale per ogni gara creata prima di oggi. Togliere il ripiego
automatico romperebbe le gare esistenti.

Idempotente: dove la colonna c'è già è un no-op dichiarato.
"""

import sqlite3

migration_name = "20260829_esercizio_della_x"

TABELLA = "gara"
COLONNA = "x_challenge_id"


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
            print(f"  ⏭️  {TABELLA} non esiste: niente da fare")
            return

        if _column_exists(cursor, TABELLA, COLONNA):
            print(f"  ⏭️  {TABELLA}.{COLONNA} già presente")
            return

        # Nessun vincolo di chiave esterna: aggiungerne uno in SQLite vuol dire
        # ricostruire la tabella, e `gara` è la più referenziata del database.
        # Il vincolo lo tiene l'ORM, e un esercizio cancellato lascia qui un id
        # orfano che `get_challenge_for_x_replacement` gestisce già come
        # «nessuna scelta»: ricade sul ripiego automatico invece di rompere.
        cursor.execute(f"ALTER TABLE {TABELLA} ADD COLUMN {COLONNA} INTEGER")
        conn.commit()
        print(f"  ✓ {TABELLA}: aggiunta {COLONNA}")
    finally:
        conn.close()
