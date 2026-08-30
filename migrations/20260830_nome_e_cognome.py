"""Nome e cognome, facoltativi, accanto allo username.

Lo username è un soprannome, e in una sala dove tre persone si chiamano
`marco`, `marco_b` e `marcob` il direttore che iscrive qualcuno non ha modo di
sapere quale sia quello giusto (issue #156). L'email lo direbbe, ma non si
mostra a nessuno: nome e cognome sono il dato che l'interessato sceglie di
dare per farsi riconoscere.

Cifrati come il telefono (`EncryptedString`): sono dati personali e la chiave
sta fuori dal database. Per questo la colonna è TEXT e non ha indici — il
testo cifrato non è né ordinabile né cercabile in SQL, e va bene così: qui non
si cerca per cognome, si legge un elenco di iscritti.

Nessun backfill possibile né sensato: chi vorrà comparire col proprio nome lo
scriverà nel profilo.

Idempotente: dove le colonne ci sono già è un no-op dichiarato.
"""

import sqlite3

migration_name = "20260830_nome_e_cognome"

TABELLA = "user"
COLONNE = ("first_name", "last_name")


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

        aggiunte = 0
        for colonna in COLONNE:
            if _column_exists(cursor, TABELLA, colonna):
                print(f"  ⏭️  {TABELLA}.{colonna} già presente")
                continue
            cursor.execute(f"ALTER TABLE `{TABELLA}` ADD COLUMN {colonna} VARCHAR(100)")
            aggiunte += 1

        conn.commit()
        print(f"  ✓ {TABELLA}: {aggiunte} colonne aggiunte")
    finally:
        conn.close()
