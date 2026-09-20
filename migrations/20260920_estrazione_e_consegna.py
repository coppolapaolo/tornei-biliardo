"""La componente estratta dall'app, e la consegna del colpo (#452, ADR-066).

Quattro colonne, tutte facoltative e tutte NULL su ogni esercizio che c'è:

* `challenge.draw_spec` — che cosa estrae l'app prima di ogni colpo, e con che
  scala si conta (JSON, convalidato da `models/challenge/draw_spec.py`);
* `challenge_attempt.pending_prompt` — la consegna del colpo che sta per essere
  giocato. Si persiste, o ricaricare la pagina sarebbe un modo di cambiarla
  finché non piace;
* `challenge_shot.prompt` e `.outcome_label` — la consegna che era uscita e il
  nome dell'esito scelto, scritti **sul colpo** come i punti: se domani l'autore
  riscrive le liste o la scala, il colpo giocato deve continuare a raccontare
  quello che è successo.

Nessun backfill: la modalità con estrazione nasce oggi, e non c'è un esercizio
al mondo che l'abbia già.

Idempotente: ogni ALTER è preceduto da PRAGMA table_info.
"""

import os
import sqlite3
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

migration_name = "20260920_estrazione_e_consegna"


def _column_exists(cursor: sqlite3.Cursor, table: str, column: str) -> bool:
    cursor.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cursor.fetchall())


def _add_column(cursor: sqlite3.Cursor, table: str, column: str, ddl: str) -> None:
    if _column_exists(cursor, table, column):
        print(f"  ⏭️  {table}.{column} già esistente")
        return
    cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
    print(f"  ✓ Aggiunta colonna {table}.{column}")


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db"):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    _add_column(cursor, "challenge", "draw_spec", "TEXT")
    _add_column(cursor, "challenge_attempt", "pending_prompt", "VARCHAR(200)")
    _add_column(cursor, "challenge_shot", "prompt", "VARCHAR(200)")
    _add_column(cursor, "challenge_shot", "outcome_label", "VARCHAR(60)")

    conn.commit()
    conn.close()


if __name__ == "__main__":
    upgrade_sqlite()
