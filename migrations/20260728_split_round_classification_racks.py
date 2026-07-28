"""Separa i rack totali dalla differenza in `round_classification`.

Finora la colonna `rack_difference` cambiava significato in base a una
configurazione di un'altra tabella (`gara.classification_system`):

- gare WINS/POSITION → differenza rack (vinti - persi)
- gare RACK          → totale dei rack vinti

Una colonna con due significati è una trappola: ogni nuovo punto di scrittura
deve ricordarsi la conversione, e chi se ne dimentica non rompe nulla di
visibile subito. È successo davvero — il fix "B14" era stato applicato a un solo
calcolatore su due, e ricalcolare una gara RACK per l'altra via ne falsava
classifica e spareggio.

Questa migration aggiunge `racks_won`, così che ogni colonna abbia un
significato fisso:

- `rack_difference` → SEMPRE la differenza
- `racks_won`       → SEMPRE il totale

Backfill: per le gare RACK il valore in `rack_difference` È il totale, quindi
viene copiato in `racks_won`. Per le gare WINS il totale non è ricostruibile
dalle colonne esistenti e resta NULL.

Le righe storiche non vengono "riparate" oltre a questo, di proposito:
`RoundClassification.ranking_rack_value` gestisce il fallback, e ogni
ricalcolo successivo (che avviene a ogni match completato) riscrive entrambe le
colonne con la semantica nuova. Nelle gare RACK già chiuse `rack_difference`
resta uguale a `racks_won` finché non viene ricalcolata: è un valore stantio ma
non letto, perché per quelle gare si guarda `racks_won`.

Idempotente: se `racks_won` esiste già, è un no-op.
"""

import os
import sqlite3
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

migration_name = "20260728_split_round_classification_racks"


def _column_exists(cursor: sqlite3.Cursor, table: str, column: str) -> bool:
    cursor.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cursor.fetchall())


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db"):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    if _column_exists(cursor, "round_classification", "racks_won"):
        print("  ⏭️  round_classification.racks_won già presente (no-op)")
        conn.close()
        return

    cursor.execute("ALTER TABLE round_classification ADD COLUMN racks_won INTEGER")

    # Solo le gare RACK: lì `rack_difference` conteneva il totale.
    cursor.execute("""
        UPDATE round_classification
           SET racks_won = rack_difference
         WHERE gara_id IN (
               SELECT id FROM gara
                WHERE UPPER(COALESCE(classification_system, 'WINS')) = 'RACK'
         )
        """)
    backfilled = cursor.rowcount

    conn.commit()
    conn.close()
    print(
        f"  ✓ round_classification.racks_won aggiunta "
        f"({backfilled} righe di gare RACK popolate dal valore preesistente)"
    )


if __name__ == "__main__":
    upgrade_sqlite()
