"""La vetrina del campionato: descrizione e indirizzo pubblico proprio.

Secondo lotto della issue #235. Il primo ha dato a ogni **gara** una pagina da
condividere; questo la dà al **campionato**, che è ciò che un direttore
pubblicizza quando la stagione comincia — e che nel primo lotto non poteva
avere, per una ragione precisa: non aveva né una descrizione né un indirizzo.

**`description`** — la gara ce l'ha da sempre, il campionato no. Senza, la sua
vetrina sarebbe un calendario di date e nient'altro: mai una riga che dica di
cosa si tratta, a chi è aperto, come ci si iscrive. È il campo che rende la
pagina una presentazione invece di un tabellone.

**`public_token`** — l'indirizzo che nasce con l'oggetto e non cambia mai.
Stessa forma di `gara.public_token` e per la stessa ragione: una locandina
stampata o un messaggio già mandato devono continuare a funzionare per sempre.
Il default lo mette l'ORM sui campionati **nuovi**; quelli già in tabella lo
ricevono qui, uno per uno — un `UPDATE` unico darebbe a tutti lo stesso
valore, e la colonna è UNIQUE.

**`slug`** — la versione leggibile, facoltativa, che il direttore sceglie
dopo: `/c/sociale-2026` invece di `/c/9Kt2wbYq`. I due indirizzi restano
**entrambi** validi, come per le gare.

Gli indici sono UNIQUE ma le colonne sono nullable, e in SQLite due NULL sono
distinti: i campionati che non scelgono un nome non si contendono niente. Che
uno slug non collida con il *token* di un altro campionato è una regola di
scrittura e vive in `showcase_service`, non qui.

Idempotente: ogni colonna o indice già presente è un no-op dichiarato.
"""

import secrets
import sqlite3

migration_name = "20260830_vetrina_campionato"

COLONNE = [
    ("campionato", "description", "TEXT"),
    ("campionato", "public_token", "VARCHAR(32)"),
    ("campionato", "slug", "VARCHAR(60)"),
]

INDICI = [
    ("ix_campionato_slug", "campionato", "slug"),
    ("ix_campionato_public_token", "campionato", "public_token"),
]


def _table_exists(cursor: sqlite3.Cursor, table: str) -> bool:
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    )
    return cursor.fetchone() is not None


def _column_exists(cursor: sqlite3.Cursor, table: str, column: str) -> bool:
    cursor.execute(f"PRAGMA table_info(`{table}`)")
    return any(row[1] == column for row in cursor.fetchall())


def _index_exists(cursor: sqlite3.Cursor, index: str) -> bool:
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name=?", (index,)
    )
    return cursor.fetchone() is not None


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db"):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        if not _table_exists(cursor, "campionato"):
            print("  ⏭️  campionato non esiste: niente da fare")
            return

        aggiunte = 0
        for tabella, colonna, tipo in COLONNE:
            if _column_exists(cursor, tabella, colonna):
                print(f"  ⏭️  {tabella}.{colonna} già presente")
                continue
            cursor.execute(f"ALTER TABLE `{tabella}` ADD COLUMN {colonna} {tipo}")
            aggiunte += 1
            print(f"  ✓ {tabella}.{colonna} aggiunta")

        # Un token per ciascun campionato già esistente. Uno alla volta e non
        # con un solo UPDATE: la colonna è UNIQUE, e un'espressione costante
        # darebbe a tutti lo stesso valore facendo fallire l'indice.
        cursor.execute("SELECT id FROM campionato WHERE public_token IS NULL")
        orfani = [riga[0] for riga in cursor.fetchall()]
        for campionato_id in orfani:
            cursor.execute(
                "UPDATE campionato SET public_token = ? WHERE id = ?",
                (secrets.token_urlsafe(6), campionato_id),
            )
        if orfani:
            print(f"  ✓ token assegnato a {len(orfani)} campionati esistenti")

        for nome, tabella, colonna in INDICI:
            if _index_exists(cursor, nome):
                print(f"  ⏭️  indice {nome} già presente")
                continue
            cursor.execute(f"CREATE UNIQUE INDEX {nome} ON {tabella}({colonna})")
            print(f"  ✓ indice {nome} creato")

        conn.commit()
        print(f"  ✓ vetrina campionato: {aggiunte} colonne aggiunte")
    finally:
        conn.close()


if __name__ == "__main__":
    upgrade_sqlite()
