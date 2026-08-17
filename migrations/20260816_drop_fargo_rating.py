"""Elimina il rating Fargo: colonna, sistema di rating e regole di handicap.

Il Fargo era **predisposto e mai alimentato**: la colonna `user.fargo_rating`
esisteva dal principio, nessuna riga di codice ci ha mai scritto dentro, e il
valore compariva comunque nel profilo e nell'elenco utenti come un trattino
perenne. Un dato che non arriva mai non e' una funzione a meta': e' una
promessa che l'interfaccia continua a fare per conto di nessuno.

Questa migration:
  1. elimina le regole di handicap costruite su quel sistema
     (`rating_handicap_rule`);
  2. elimina le righe di `player_rating` con `rating_system = 'fargo'`;
  3. elimina la colonna `user.fargo_rating` **dove SQLite lo consente**.

Idempotente: ogni passo controlla prima se c'e' qualcosa da fare.

NOTA SQLite < 3.35 — perche' il passo 3 e' un no-op e non un errore
--------------------------------------------------------------------
`ALTER TABLE ... DROP COLUMN` esiste solo dalla 3.35 (2021). PythonAnywhere
sta alla 3.31.1, e la prima stesura di questa migration in quel caso
sollevava. L'effetto non era proteggere niente: il runner registrava
"Completed: 0/1", **non** marcava la migration come applicata, e
`auto_deploy.py` la ritentava ogni notte — disabilitando e riabilitando la web
app a ogni giro per un lavoro che non poteva riuscire mai. Un errore che si
ripete identico all'infinito non e' un allarme, e' rumore che nasconde gli
allarmi veri.

La scelta e' quindi il **no-op dichiarato**: dove la DROP COLUMN non c'e', la
colonna resta e la migration riesce lo stesso. E' onesto perche' l'esito e'
davvero accettabile — la colonna e' vuota, nullable e nessun codice la nomina
piu' (nemmeno il modello `User`) — e perche' l'alternativa, il pattern SQLite
di ricostruzione della tabella (create + copy + drop + rename), su `user`
significherebbe ricreare la tabella piu' referenziata dello schema, con i
suoi indici e le FK che le puntano contro, su uno storage NFS con i lock
inaffidabili (incidente 2026-06-10). Rischio reale, guadagno nullo.

Conseguenza da mettere agli atti: una volta marcata applicata, questa
migration non gira piu'. Se un domani PythonAnywhere passasse a SQLite >= 3.35
e si volesse davvero togliere la colonna, servirebbe una migration **nuova**,
non un nuovo tentativo di questa.
"""

import os
import sqlite3
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

migration_name = "20260816_drop_fargo_rating"

#: Versione minima di SQLite con `ALTER TABLE ... DROP COLUMN`.
DROP_COLUMN_MIN_VERSION = (3, 35, 0)


def _column_exists(cursor: sqlite3.Cursor, table: str, column: str) -> bool:
    cursor.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cursor.fetchall())


def _table_exists(cursor: sqlite3.Cursor, table: str) -> bool:
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    )
    return cursor.fetchone() is not None


def _supports_drop_column() -> bool:
    return sqlite3.sqlite_version_info >= DROP_COLUMN_MIN_VERSION


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db"):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # 1. Le regole di handicap sul sistema Fargo, prima delle righe di
        #    rating: sono le uniche che potrebbero riferirsi a un rating
        #    inesistente.
        if _table_exists(cursor, "rating_handicap_rule"):
            cursor.execute(
                "DELETE FROM rating_handicap_rule WHERE rating_system = 'fargo'"
            )
            print(f"  ✓ Regole di handicap Fargo rimosse: {cursor.rowcount}")

        # 2. I rating Fargo eventualmente importati.
        if _table_exists(cursor, "player_rating"):
            cursor.execute("DELETE FROM player_rating WHERE rating_system = 'fargo'")
            print(f"  ✓ Righe player_rating Fargo rimosse: {cursor.rowcount}")

        # 3. La colonna, dove il motore lo permette (vedi docstring).
        if not _column_exists(cursor, "user", "fargo_rating"):
            print("  ⏭️  user.fargo_rating già assente")
        elif _supports_drop_column():
            cursor.execute("ALTER TABLE user DROP COLUMN fargo_rating")
            print("  ✓ Colonna user.fargo_rating eliminata")
        else:
            print(
                f"  ⏭️  SQLite {sqlite3.sqlite_version} non ha ALTER TABLE DROP "
                f"COLUMN (serve la "
                f"{'.'.join(str(n) for n in DROP_COLUMN_MIN_VERSION)}): la "
                "colonna user.fargo_rating resta. È vuota, nullable e nessun "
                "codice la legge più — la pulizia dei dati Fargo (passi 1 e 2) "
                "è comunque avvenuta."
            )

        # Un `commit` solo, in fondo e su ogni strada: la prima stesura
        # chiudeva la connessione senza committare prima di sollevare, quindi
        # anche le cancellazioni dei passi 1 e 2 — che erano riuscite —
        # venivano buttate via a ogni tentativo.
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    upgrade_sqlite()
