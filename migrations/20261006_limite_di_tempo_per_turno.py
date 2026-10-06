"""Il limite di tempo di un singolo turno (ADR-077, ADR-027).

Una colonna nuova su `round_configuration`: `time_limit_minutes`, con tre
stati — NULL = come la gara, 0 = senza limite per questo turno, N minuti.
Nessun riempimento: i turni configurati finora seguono la gara.

Una tabella assente è un no-op dichiarato, non un errore. Rilanciata, non fa
niente.
"""

import sqlite3

migration_name = "20261006_limite_di_tempo_per_turno"


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db") -> None:
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        presenti = {
            riga[1] for riga in cursor.execute("PRAGMA table_info(round_configuration)")
        }
        if not presenti:
            print("  ⏭️  tabella round_configuration assente")
            return
        if "time_limit_minutes" in presenti:
            print("  ⏭️  round_configuration.time_limit_minutes già esistente")
            return
        cursor.execute(
            "ALTER TABLE round_configuration ADD COLUMN time_limit_minutes INTEGER"
        )
        conn.commit()
        print("  ✓ Aggiunta colonna round_configuration.time_limit_minutes")
    finally:
        conn.close()


if __name__ == "__main__":
    upgrade_sqlite()
