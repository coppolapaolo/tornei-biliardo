"""La prova giocata al posto della X va validata dal direttore.

Il punteggio dell'esercizio diventa la differenza triangoli di quel turno
(`SPECIFICHE.md` riga 65), cioè entra dritto in classifica. A dichiararlo però è
il **giocatore stesso**, e qui manca il controllo che una partita normale ha per
costruzione: l'avversario. Una partita si chiude con la doppia conferma o con la
mano del direttore; una prova giocata da soli non ha nessuno che possa smentirla.

Da qui le due colonne: il punteggio si registra subito, ma arriva sul match —
e quindi in classifica — solo quando il direttore lo valida. `validated_by_id`
dice chi, `validated_at` quando. Finché sono NULL la prova è giocata ma non
conta, ed è uno stato legittimo, non un dato mancante.

Idempotente: dove le colonne ci sono già è un no-op dichiarato. Nessun backfill
possibile né voluto — le prove registrate prima di oggi non sono mai arrivate
in classifica (issue #221), quindi non c'è nessuna validazione storica da
inventare, e marcarle valide retroattivamente cambierebbe classifiche già
pubblicate senza che nessuno l'abbia deciso.
"""

import sqlite3

migration_name = "20260829_validazione_prova_al_posto_della_x"

TABELLA = "gara_bye_challenge"

#: nome → definizione SQL. `validated_by_id` resta senza vincolo di chiave
#: esterna: aggiungerne uno in SQLite richiede di ricostruire la tabella, e su
#: una colonna che punta a `user` — dove le righe non si cancellano mai davvero
#: (soft delete) — il vincolo non difenderebbe da niente che possa accadere.
COLONNE = {
    "validated_by_id": "INTEGER",
    "validated_at": "DATETIME",
}


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
            # Non è un errore: dove la tabella non c'è ancora, nascerà completa
            # da `create_all()` o dalla migration che la crea. Sollevare qui
            # lascerebbe la migration non marcata, e `auto_deploy` la
            # ritenterebbe ogni notte disabilitando la web app per niente.
            print(f"  ⏭️  {TABELLA} non esiste: niente da fare")
            return

        aggiunte = []
        for colonna, tipo in COLONNE.items():
            if _column_exists(cursor, TABELLA, colonna):
                continue
            cursor.execute(f"ALTER TABLE {TABELLA} ADD COLUMN {colonna} {tipo}")
            aggiunte.append(colonna)

        conn.commit()
        if aggiunte:
            print(f"  ✓ {TABELLA}: aggiunte {', '.join(aggiunte)}")
        else:
            print(f"  ⏭️  {TABELLA} già a posto")
    finally:
        conn.close()
