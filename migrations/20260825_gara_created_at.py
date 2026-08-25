"""Aggiunge `gara.created_at` e la ricostruisce dove si può.

`Gara` estende `db.Model` e non `BaseModel`: le due colonne di timestamp che il
mixin mette a quasi tutte le entità qui non sono mai arrivate. Non se n'era
accorto nessuno perché nessuna schermata chiedeva *quando* una gara fosse nata
— finché la dashboard adattiva non ha avuto bisogno di sapere se l'ultima cosa
fatta dal direttore fosse creare una gara o giocare una partita.

`date` non risponde a quella domanda: è il giorno in cui **si gioca**, e può
stare mesi nel futuro. Usarla al posto della creazione farebbe risultare come
«appena fatto» un torneo di ottobre programmato a maggio.

RICOSTRUZIONE DELLE RIGHE ESISTENTI
-----------------------------------
La data vera non c'è più, quindi non la si inventa: si usa la traccia più
antica che il database conserva davvero, in quest'ordine.

1. **La prima iscrizione alla gara** (`MIN(inscription.created_at)`). È una
   prova diretta: al momento in cui qualcuno si è iscritto, la gara esisteva
   già. Sbaglia per difetto — la gara è nata prima — e sbagliare per difetto è
   la direzione giusta: al massimo un fatto da direttore sembra più vecchio di
   quanto sia.
2. **Il giorno della gara, non oltre adesso** (`MIN(date, CURRENT_TIMESTAMP)`).
   Ripiego per le gare senza nessuna iscrizione. Il tetto a «adesso» è la parte
   che conta: senza, una gara programmata per il prossimo autunno avrebbe una
   data di creazione nel futuro, e per la dashboard sarebbe per sempre l'ultima
   cosa fatta dal direttore — cioè il difetto che questa colonna serve a
   correggere, riscritto al contrario.

Le gare nuove non passano di qui: prendono `utc_now()` dal default del modello.

Idempotente: se la colonna c'è già è un no-op dichiarato.
"""

import sqlite3

migration_name = "20260825_gara_created_at"

TABELLA = "gara"
COLONNA = "created_at"


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
            print(f"  ⏭️  {TABELLA}.{COLONNA} c'e' gia'")
            return

        # Senza DEFAULT: SQLite rifiuta un default non costante in ADD COLUMN,
        # e le righe esistenti le riempie la UPDATE qui sotto.
        cursor.execute(f"ALTER TABLE {TABELLA} ADD COLUMN {COLONNA} DATETIME")

        cursor.execute("""
            UPDATE gara
               SET created_at = COALESCE(
                   (SELECT MIN(i.created_at) FROM inscription i
                     WHERE i.gara_id = gara.id),
                   MIN(datetime(gara.date), CURRENT_TIMESTAMP)
               )
             WHERE created_at IS NULL
            """)
        riparate = cursor.rowcount
        conn.commit()
        print(f"  ✓ {TABELLA}.{COLONNA} aggiunta ({riparate} gare ricostruite)")
    finally:
        conn.close()


if __name__ == "__main__":
    upgrade_sqlite()
