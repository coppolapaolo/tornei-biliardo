"""Il «Link al regolamento» di gare e campionati (ADR-075).

Una colonna nuova, `rules_url`, su `gara` e su `campionato`: il documento del
regolamento, mostrato come «Regolamento completo» in fondo alla pagina
pubblica «Regolamento di gara». La gara senza il suo usa quello del
campionato, in diretta come la locandina. Il link esterno della vetrina resta
un'altra cosa, con la sua etichetta.

Idempotente: aggiunge la colonna solo se manca. Tabelle assenti sono un no-op
dichiarato. Nessun riempimento: il campo nasce vuoto.
"""

import sqlite3

migration_name = "20260929_link_al_regolamento"


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db") -> None:
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        tabelle = {r[0] for r in cursor.execute("SELECT name FROM sqlite_master")}
        for tabella in ("gara", "campionato"):
            if tabella not in tabelle:
                continue
            colonne = {r[1] for r in cursor.execute(f"PRAGMA table_info({tabella})")}
            if "rules_url" not in colonne:
                cursor.execute(
                    f"ALTER TABLE {tabella} ADD COLUMN rules_url VARCHAR(500)"
                )
            print(f"  ✓ {tabella}.rules_url")
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    upgrade_sqlite()
