"""Il listino delle quote per categoria (ADR-079).

Una colonna nuova su `categoria`: `entry_fee`, nullable. Nessuna categoria
esistente ha una quota: restano tutte a NULL, cioè fuori dal listino, e le gare
continuano a mostrare la quota unica di sempre (`gara.entry_fee`).

Una tabella assente è un no-op dichiarato, non un errore. Rilanciata, non fa
niente.
"""

import sqlite3

migration_name = "20261006_listino_quote_categoria"


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db") -> None:
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        presenti = {
            riga[1] for riga in cursor.execute('PRAGMA table_info("categoria")')
        }
        if not presenti:
            print("  ⏭️  tabella categoria assente")
            return
        if "entry_fee" in presenti:
            print("  ⏭️  categoria.entry_fee già esistente")
            return
        cursor.execute('ALTER TABLE "categoria" ADD COLUMN entry_fee FLOAT')
        conn.commit()
        print("  ✓ Aggiunta colonna categoria.entry_fee")
    finally:
        conn.close()


if __name__ == "__main__":
    upgrade_sqlite()
