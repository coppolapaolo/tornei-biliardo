"""La partita interrotta a tempo dal direttore (ADR-077).

Una colonna nuova su `match`: `closed_on_time`, NOT NULL con default 0. Nessuna
partita esistente è stata interrotta: restano tutte a 0.

Una tabella assente è un no-op dichiarato, non un errore. Rilanciata, non fa
niente.
"""

import sqlite3

migration_name = "20261006_partita_interrotta_a_tempo"


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db") -> None:
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        presenti = {riga[1] for riga in cursor.execute('PRAGMA table_info("match")')}
        if not presenti:
            print("  ⏭️  tabella match assente")
            return
        if "closed_on_time" in presenti:
            print("  ⏭️  match.closed_on_time già esistente")
            return
        cursor.execute(
            'ALTER TABLE "match" ADD COLUMN closed_on_time BOOLEAN NOT NULL DEFAULT 0'
        )
        conn.commit()
        print("  ✓ Aggiunta colonna match.closed_on_time")
    finally:
        conn.close()


if __name__ == "__main__":
    upgrade_sqlite()
