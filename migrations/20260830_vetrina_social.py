"""La vetrina da condividere sui social: banner, link esterno, indirizzo leggibile.

Il link pubblico di iscrizione (`/g/<token>`, issue #61) finisce su WhatsApp o
Facebook **nudo**: lo scraper non trova né immagine né titolo e ripiega sul
dominio. Perché ci sia qualcosa da mostrare servono tre cose che il database
non sa ancora dire.

**`banner_path`** — l'immagine della locandina, su gara *e* su campionato.
Le due colonne hanno lo stesso nome di proposito: non è un `default_` come
`default_venue_id`, perché il banner del campionato è il banner *del
campionato* (gli serve per la sua vetrina), e l'ereditarietà è un
comportamento della gara — `Gara.effective_banner_path` prende il proprio, e
se non c'è quello del campionato. Così un direttore carica una grafica sola e
tutte le gare di quel campionato si presentano allo stesso modo, ma la singola
gara può sempre scavalcarla.

**`external_url` / `external_label`** — un link fuori dall'applicazione:
regolamento, pagina Facebook della sala, modulo di pagamento. Stessa
ereditarietà del banner, per la stessa ragione: il regolamento di un
campionato vale per tutte le sue gare.

**`gara.slug`** — l'indirizzo leggibile, facoltativo, accanto al token.
`/g/6Ktw_bYq` sta su una locandina ma non si detta al telefono e non dice
niente; `/g/open-di-natale-2026` sì. Il token **resta** e continua a
funzionare: lo slug è un secondo nome per la stessa pagina, non un
rimpiazzo, e le locandine già stampate non diventano carta straccia.

L'indice è UNIQUE ma la colonna è nullable, e in SQLite due NULL sono
distinti: le gare che non scelgono un nome non si contendono nulla. Il
controllo che uno slug non collida con il *token* di un'altra gara non può
stare qui — è una regola di scrittura, e vive in `GaraService.set_slug`.

Idempotente: ogni colonna già presente è un no-op dichiarato.
"""

import sqlite3

migration_name = "20260830_vetrina_social"

# (tabella, colonna, tipo SQL)
COLONNE = [
    ("gara", "banner_path", "VARCHAR(255)"),
    ("gara", "external_url", "VARCHAR(500)"),
    ("gara", "external_label", "VARCHAR(60)"),
    ("gara", "slug", "VARCHAR(60)"),
    ("campionato", "banner_path", "VARCHAR(255)"),
    ("campionato", "external_url", "VARCHAR(500)"),
    ("campionato", "external_label", "VARCHAR(60)"),
]

INDICE_SLUG = "ix_gara_slug"


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
        aggiunte = 0
        for tabella, colonna, tipo in COLONNE:
            if not _table_exists(cursor, tabella):
                print(f"  ⏭️  {tabella} non esiste: niente da fare")
                continue
            if _column_exists(cursor, tabella, colonna):
                print(f"  ⏭️  {tabella}.{colonna} già presente")
                continue
            cursor.execute(f"ALTER TABLE `{tabella}` ADD COLUMN {colonna} {tipo}")
            aggiunte += 1
            print(f"  ✓ {tabella}.{colonna} aggiunta")

        if _table_exists(cursor, "gara") and not _index_exists(cursor, INDICE_SLUG):
            cursor.execute(f"CREATE UNIQUE INDEX {INDICE_SLUG} ON gara(slug)")
            print(f"  ✓ indice {INDICE_SLUG} creato")

        conn.commit()
        print(f"  ✓ vetrina social: {aggiunte} colonne aggiunte")
    finally:
        conn.close()


if __name__ == "__main__":
    upgrade_sqlite()
