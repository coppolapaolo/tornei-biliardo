"""Aggiunge `match_proposal.start_rule` (ADR-056).

La proposta di sfida porta già «come si gioca» — disciplina, distanza, chi
spacca — e lo copia sul match quando qualcuno accetta (`to_match_kwargs`). La
**regola di inizio** era rimasta fuori per un motivo solo: quando l'ADR-056 ha
aggiunto `IndividualMatch.start_rule` nessuna schermata lo impostava, quindi
non c'era niente da far viaggiare. Adesso c'è.

Viaggia con la proposta e non si deduce all'accettazione perché è parte di ciò
a cui l'altro sta dicendo di sì: una sfida che comincia con l'acchito si gioca
diversamente da una in cui apre il primo giocatore.

Il default è `first_player`, cioè il comportamento che le sfide hanno sempre
avuto: le proposte già in giro non cambiano di significato.

Idempotente: se la colonna c'è già è un no-op dichiarato.
"""

import sqlite3

migration_name = "20260828_proposal_start_rule"

TABELLA = "match_proposal"
COLONNA = "start_rule"
DDL = "VARCHAR(20) DEFAULT 'first_player'"


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

        cursor.execute(f"ALTER TABLE {TABELLA} ADD COLUMN {COLONNA} {DDL}")
        conn.commit()
        print(f"  ✓ {TABELLA}.{COLONNA} aggiunta")
    finally:
        conn.close()


if __name__ == "__main__":
    upgrade_sqlite()
