"""Elimina il rating Fargo: colonna, sistema di rating e regole di handicap.

Il Fargo era **predisposto e mai alimentato**: la colonna `user.fargo_rating`
esisteva dal principio, nessuna riga di codice ci ha mai scritto dentro, e il
valore compariva comunque nel profilo e nell'elenco utenti come un trattino
perenne. Un dato che non arriva mai non e' una funzione a meta': e' una
promessa che l'interfaccia continua a fare per conto di nessuno.

Questa migration:
  1. elimina la colonna `user.fargo_rating`;
  2. elimina le righe di `player_rating` con `rating_system = 'fargo'`;
  3. elimina le regole di handicap costruite su quel sistema
     (`rating_handicap_rule`).

Idempotente: ogni passo controlla prima se c'e' qualcosa da fare.

NOTA SQLite: `ALTER TABLE ... DROP COLUMN` richiede SQLite 3.35 (2021). Se la
versione e' precedente la migration si ferma con un messaggio esplicito invece
di ricostruire la tabella a mano: su un dato che nessuno ha mai scritto, il
rischio di una ricostruzione non vale il guadagno.
"""

import os
import sqlite3
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

migration_name = "20260816_drop_fargo_rating"


def _column_exists(cursor: sqlite3.Cursor, table: str, column: str) -> bool:
    cursor.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cursor.fetchall())


def _table_exists(cursor: sqlite3.Cursor, table: str) -> bool:
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    )
    return cursor.fetchone() is not None


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db"):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 1. Le regole di handicap sul sistema Fargo, prima delle righe di rating:
    #    sono le uniche che potrebbero riferirsi a un rating inesistente.
    if _table_exists(cursor, "rating_handicap_rule"):
        cursor.execute("DELETE FROM rating_handicap_rule WHERE rating_system = 'fargo'")
        print(f"  ✓ Regole di handicap Fargo rimosse: {cursor.rowcount}")

    # 2. I rating Fargo eventualmente importati.
    if _table_exists(cursor, "player_rating"):
        cursor.execute("DELETE FROM player_rating WHERE rating_system = 'fargo'")
        print(f"  ✓ Righe player_rating Fargo rimosse: {cursor.rowcount}")

    # 3. La colonna.
    if _column_exists(cursor, "user", "fargo_rating"):
        if sqlite3.sqlite_version_info < (3, 35, 0):
            conn.close()
            raise RuntimeError(
                "SQLite "
                f"{sqlite3.sqlite_version} non supporta ALTER TABLE DROP COLUMN "
                "(serve la 3.35). La colonna user.fargo_rating resta: e' vuota e "
                "inerte, nessun codice la legge piu'."
            )
        cursor.execute("ALTER TABLE user DROP COLUMN fargo_rating")
        print("  ✓ Colonna user.fargo_rating eliminata")
    else:
        print("  ⏭️  user.fargo_rating già assente")

    conn.commit()
    conn.close()


if __name__ == "__main__":
    upgrade_sqlite()
