"""Aggiunge playoff_configuration.classification_system — il sistema della finale.

Il direttore sceglie ogni opzione della finale dei playoff, e fra queste il
sistema di classifica (WINS o RACK). Conta solo con «Solo i playoff»: con
«Campionato + gara di playoff» il punteggio della finale si somma a quello del
campionato e deve usare lo stesso sistema (SPECIFICHE.md riga 289).

Nessun backfill, ed è deliberato: NULL vuol dire «quello del campionato», che
è esattamente come nasce una finale da oggi. Le configurazioni esistenti non
cambiano comportamento, e le finali già create non vengono toccate.

Idempotente: ALTER preceduto da PRAGMA table_info.
"""

import os
import sqlite3
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

migration_name = "20260914_add_playoff_configuration_classification_system"


def _column_exists(cursor: sqlite3.Cursor, table: str, column: str) -> bool:
    cursor.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cursor.fetchall())


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db"):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    if not _column_exists(cursor, "playoff_configuration", "classification_system"):
        cursor.execute(
            "ALTER TABLE playoff_configuration "
            "ADD COLUMN classification_system VARCHAR(10)"
        )
        print("  ✓ Aggiunta colonna playoff_configuration.classification_system")
    else:
        print("  ⏭️  playoff_configuration.classification_system già esistente")

    conn.commit()
    conn.close()


if __name__ == "__main__":
    upgrade_sqlite()
