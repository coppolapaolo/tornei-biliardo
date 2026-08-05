"""Aggiunge gara.assign_tables_by_ranking (tavoli assegnati per classifica).

Feature (2026-06): per le gare con strategia random il direttore può attivare
l'assegnazione dei tavoli "a ondate" in base alla classifica provvisoria:
dal secondo turno in poi si attende la fine di tutte le partite del turno
precedente, poi il primo tavolo della lista (ordine di pregio) viene assegnato
al match con il giocatore meglio piazzato, e così via.

    Gara.assign_tables_by_ranking  (BOOLEAN NOT NULL, default 0)

Idempotente: l'ALTER è preceduto da un PRAGMA table_info check.
"""

import sqlite3

migration_name = "20260611_assign_tables_by_ranking"


def _column_exists(cursor: sqlite3.Cursor, table: str, column: str) -> bool:
    cursor.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cursor.fetchall())


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db"):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    if not _column_exists(cursor, "gara", "assign_tables_by_ranking"):
        cursor.execute(
            "ALTER TABLE gara ADD COLUMN assign_tables_by_ranking "
            "BOOLEAN NOT NULL DEFAULT 0"
        )
        print("  ✓ Aggiunta colonna gara.assign_tables_by_ranking")
    else:
        print("  ⏭️  gara.assign_tables_by_ranking già esistente")

    conn.commit()
    conn.close()
