"""Aggiunge inscription.inscribed_by_id — chi ha iscritto il giocatore.

Il direttore può iscrivere un giocatore anche a finestra chiusa, finché la gara
non è avviata (SPECIFICHE.md, «Gara», nota del 2026-09-16). Un'iscrizione così
resta riconoscibile: la colonna dice chi l'ha registrata, e la lista degli
iscritti lo mostra con «iscritto da X», come «registrato da X» per gli inviti
ai playoff (`playoff_qualification.responded_by_id`).

Nessun backfill, ed è deliberato: NULL vuol dire «non si sa», che è la verità
per ogni iscrizione fatta prima di oggi — il direttore o il giocatore, nessuno
lo ha mai scritto.

Idempotente: ALTER preceduto da PRAGMA table_info.
"""

import os
import sqlite3
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

migration_name = "20260916_add_inscription_inscribed_by"


def _column_exists(cursor: sqlite3.Cursor, table: str, column: str) -> bool:
    cursor.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cursor.fetchall())


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db"):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    if not _column_exists(cursor, "inscription", "inscribed_by_id"):
        cursor.execute(
            "ALTER TABLE inscription "
            "ADD COLUMN inscribed_by_id INTEGER REFERENCES user(id)"
        )
        print("  ✓ Aggiunta colonna inscription.inscribed_by_id")
    else:
        print("  ⏭️  inscription.inscribed_by_id già esistente")

    conn.commit()
    conn.close()


if __name__ == "__main__":
    upgrade_sqlite()
