"""Rinomina «challenge»/«drill» in «esercizio» nelle etichette gia' scritte a DB.

Il resto della rinomina vive nei template e nelle stringhe `_()`, dove basta
cambiare il sorgente. Queste no: sono testi **persistiti** — nome e descrizione
dei traguardi, e i nomi delle funzioni sbloccate per livello — e i seed che li
hanno creati sono insert-only (`seed_achievements` salta le righe esistenti,
`config_service` scrive i `level_unlock` una volta sola). Cambiare il seed
lascerebbe la produzione a mostrare «Maestro dei Drill» per sempre.

Idempotente per costruzione: ogni UPDATE ha in WHERE il testo vecchio, quindi
una seconda esecuzione non tocca nulla. Non si aggiorna per `slug`/`code` con
un valore fisso, cosi' un testo gia' ritoccato a mano non viene sovrascritto.

Niente rename di tabelle, colonne o codici feature: `do_challenge`,
`create_challenge`, `challenge_master` restano quello che sono. Sono chiavi
tecniche, l'utente non le legge, e rinominarle romperebbe i gate che le citano.
"""

import sqlite3

migration_name = "20260818_esercizi_nelle_etichette_persistite"

# (tabella, colonna-chiave, valore-chiave, colonna-testo, vecchio, nuovo)
_UPDATES = [
    (
        "achievement",
        "slug",
        "challenge_master",
        "name",
        "Maestro dei Drill",
        "Maestro degli Esercizi",
    ),
    (
        "achievement",
        "slug",
        "challenge_master",
        "description",
        "Completa 10 drill di allenamento",
        "Completa 10 esercizi di allenamento",
    ),
    (
        "achievement",
        "slug",
        "perfectionist",
        "description",
        "Supera 5 drill pass/fail diversi",
        "Supera 5 esercizi superato/non superato diversi",
    ),
    (
        "achievement",
        "slug",
        "drill_addict",
        "name",
        "Dipendente dal Drill",
        "Dipendente dagli Esercizi",
    ),
    (
        "achievement",
        "slug",
        "drill_addict",
        "description",
        "Completa 100 drill di allenamento",
        "Completa 100 esercizi di allenamento",
    ),
    (
        "achievement",
        "slug",
        "open_player",
        "description",
        "Condividi almeno un dato di gioco pubblicamente "
        "(statistiche, partite, classifiche o challenge)",
        "Condividi almeno un dato di gioco pubblicamente "
        "(statistiche, partite, classifiche o esercizi)",
    ),
    (
        "level_unlock",
        "feature_code",
        "challenge_creation",
        "feature_name",
        "Creazione Challenge",
        "Creazione esercizi",
    ),
    (
        "level_unlock",
        "feature_code",
        "challenge_creation",
        "description",
        "Puoi creare challenge per altri",
        "Puoi creare esercizi per altri",
    ),
    (
        "level_unlock",
        "feature_code",
        "match_proposals",
        "feature_name",
        "Proposte Match",
        "Proposte di sfida",
    ),
    (
        "level_unlock",
        "feature_code",
        "match_proposals",
        "description",
        "Puoi proporre match individuali",
        "Puoi proporre sfide individuali",
    ),
]


def _table_exists(cursor: sqlite3.Cursor, table: str) -> bool:
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    )
    return cursor.fetchone() is not None


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db"):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    total = 0
    for table, key_col, key_val, text_col, old, new in _UPDATES:
        if not _table_exists(cursor, table):
            print(f"  ⏭️  tabella {table} assente, salto")
            continue
        cursor.execute(
            f"UPDATE {table} SET {text_col} = ? WHERE {key_col} = ? AND {text_col} = ?",
            (new, key_val, old),
        )
        if cursor.rowcount:
            total += cursor.rowcount
            print(f"  ✓ {table}.{text_col} ({key_val}): {cursor.rowcount} riga/e")

    if total == 0:
        print("  ⏭️  nessuna etichetta da rinominare (gia' aggiornate o assenti)")
    else:
        print(f"  ✓ {total} etichette rinominate in «esercizio»")

    conn.commit()
    conn.close()
