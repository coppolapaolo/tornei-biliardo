"""Il sistema delle serate nei campionati a piazzamenti (ADR-080).

Una colonna nuova, `campionato.default_gara_classification_system`: nei
campionati a piazzamenti (POSITION) il sistema con cui il campionato propone
di ordinare ogni serata che non è un tabellone — vittorie, triangoli o punti.
NULL = vittorie, cioè quello che le gare non a tabellone di un campionato a
piazzamenti ricevevano già (`resolve_classification_system` ripiega su
vittorie). Nei campionati che sommano i totali non si legge.

Nessun riempimento: nessuna classifica esistente cambia. Una tabella assente è
un no-op dichiarato, non un errore. Rilanciata, non fa niente.
"""

import sqlite3

migration_name = "20261011_sistema_delle_gare_a_piazzamenti"

TABELLA = "campionato"
COLONNA = "default_gara_classification_system"
TIPO = "VARCHAR(10)"


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db") -> None:
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        presenti = {riga[1] for riga in cursor.execute(f"PRAGMA table_info({TABELLA})")}
        if not presenti:
            print(f"  ⏭️  tabella {TABELLA} assente")
            return
        if COLONNA in presenti:
            print(f"  ⏭️  {TABELLA}.{COLONNA} già esistente")
            return
        cursor.execute(f'ALTER TABLE "{TABELLA}" ADD COLUMN {COLONNA} {TIPO}')
        conn.commit()
        print(f"  ✓ Aggiunta colonna {TABELLA}.{COLONNA}")
    finally:
        conn.close()


if __name__ == "__main__":
    upgrade_sqlite()
