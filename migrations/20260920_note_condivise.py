"""Le note di una seduta si possono aprire a chi legge la scheda (ADR-069).

Una colonna sola, ``training_sheet.readers_see_notes``, spenta per default:
leggere una scheda non è leggere quello che ci si scrive sopra a fine serata.
Chi vuole che l'istruttore legga anche le note lo dice, scheda per scheda.

Il default **falso** vale anche per le schede che esistono già, ed è la
risposta giusta: nessuno ha acconsentito a niente, e un backfill che
«aprisse» le note in silenzio sarebbe esattamente il contrario del consenso
che questa colonna serve a esprimere.

Idempotente: SQLite non ha ``ADD COLUMN IF NOT EXISTS``, quindi si guarda
prima il ``PRAGMA``.
"""

import sqlite3

migration_name = "20260920_note_condivise"


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db") -> None:
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        colonne = {
            riga[1] for riga in cursor.execute("PRAGMA table_info(training_sheet)")
        }
        if "readers_see_notes" in colonne:
            print("  training_sheet.readers_see_notes c'era già: nulla da fare")
            return
        cursor.execute(
            "ALTER TABLE training_sheet "
            "ADD COLUMN readers_see_notes BOOLEAN NOT NULL DEFAULT 0"
        )
        conn.commit()
        print("  ✓ training_sheet.readers_see_notes")
    finally:
        conn.close()


if __name__ == "__main__":  # pragma: no cover - uso manuale
    upgrade_sqlite()
