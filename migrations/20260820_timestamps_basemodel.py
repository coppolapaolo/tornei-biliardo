"""Ripara le tabelle a cui mancano `created_at` e `updated_at`.

GlitchTip, 2026-08-19:

    OperationalError: (sqlite3.OperationalError)
    table categoria has no column named created_at

`BaseModel` aggiunge quelle due colonne a **ogni** entità, quindi senza di esse
ogni tentativo di creare una categoria finisce in 500 — cioè la funzione
introdotta da ADR-049 è inerte in produzione, e lo è in silenzio: chi prova a
creare una categoria vede una pagina di errore, non un campo mancante.

La migration che crea la tabella (`20260819_categorie_competizione`) le colonne
ce le ha. Ma è `CREATE TABLE IF NOT EXISTS` e risulta **già applicata**: su un
DB dove la tabella è nata senza, non tornerà mai a sistemarla. È la proprietà
scomoda dell'idempotenza scritta così — protegge dal doppio passaggio, non
dallo schema sbagliato — e l'unico rimedio è una migration nuova.

Sui DB dove le colonne ci sono già (sviluppo, e ogni installazione futura) è un
no-op dichiarato: si guarda il PRAGMA, non si prova e si spera.
"""

import sqlite3

migration_name = "20260820_timestamps_basemodel"

COLONNE = ("created_at", "updated_at")

#: Le tabelle da controllare. `categoria` è quella che ha rotto in produzione;
#: le altre tre le ha trovate il presidio scritto insieme a questa migration
#: (`tests/new/unit/test_migrations_timestamps.py`) guardando **tutte** le
#: CREATE TABLE del repository. Sono di gennaio, e con ogni probabilità in
#: produzione stanno bene — le avrà create `db.create_all()` all'avvio, che le
#: colonne del modello ce le mette tutte. «Con ogni probabilità» non è una
#: verifica, e il controllo qui costa un PRAGMA: dove sono a posto è un no-op
#: che lo dice.
TABELLE = ("categoria", "user_token", "kpi_milestone", "feature_config")


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
        riparate = 0
        for tabella in TABELLE:
            if not _table_exists(cursor, tabella):
                # Non è un errore: dove la tabella non c'è ancora, nascerà
                # completa — dalla migration che la crea o da `create_all()`.
                print(f"  ⏭️  {tabella} non esiste: niente da riparare")
                continue

            aggiunte = []
            for colonna in COLONNE:
                if _column_exists(cursor, tabella, colonna):
                    continue
                # DATETIME senza DEFAULT: SQLite rifiuta un default non
                # costante in ADD COLUMN, e le righe esistenti si riempiono
                # subito sotto.
                cursor.execute(f"ALTER TABLE {tabella} ADD COLUMN {colonna} DATETIME")
                aggiunte.append(colonna)

            for colonna in aggiunte:
                # Le righe già create restano senza la data vera — non c'è modo
                # di ricostruirla. Si mette l'adesso: falso, ma ordinabile, e
                # meglio di un NULL su una colonna che il codice legge come data.
                cursor.execute(
                    f"UPDATE {tabella} SET {colonna} = CURRENT_TIMESTAMP "
                    f"WHERE {colonna} IS NULL"
                )

            if aggiunte:
                riparate += 1
                print(f"  ✓ {tabella}: aggiunte {', '.join(aggiunte)}")
            else:
                print(f"  ⏭️  {tabella} già a posto")

        conn.commit()
        print(f"  ✓ Tabelle riparate: {riparate}")
    finally:
        conn.close()


if __name__ == "__main__":
    upgrade_sqlite()
