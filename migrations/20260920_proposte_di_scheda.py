"""Le schede che l'istruttore propone agli allievi (ADR-071, fase 8d).

Una tabella nuova, nessuna colonna toccata. In particolare **non** si tocca
`training_sheet_reader`, che resta l'unico posto in cui è scritto chi legge che
cosa (ADR-069): una proposta non apre niente, e la scheda nasce solo quando
l'allievo accetta — con lui proprietario.

* `training_assignment` — chi propone, a chi, quale scheda (il modello), da
  quale gruppo, con che biglietto; poi `closed_at` e `outcome` dicono com'è
  finita, e `sheet_id` quale scheda è nata dall'accettazione.

Un indice unico **parziale** sulle sole righe in attesa: «una proposta per
volta, per coppia (istruttore, allievo)». È imposto dal database e non da un
`if`, perché un'unicità che vive in Python è invisibile a chi scrive in blocco
(ADR-070 §2).

Idempotente: CREATE TABLE/INDEX IF NOT EXISTS. La tabella nasce con
`created_at` e `updated_at`, che `BaseModel` pretende (incidente `categoria`,
2026-08-19).
"""

import os
import sqlite3
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

migration_name = "20260920_proposte_di_scheda"


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db"):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS training_assignment (
            id INTEGER NOT NULL PRIMARY KEY,
            instructor_id INTEGER NOT NULL REFERENCES user(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES user(id) ON DELETE CASCADE,
            source_sheet_id INTEGER NOT NULL
                REFERENCES training_sheet(id) ON DELETE CASCADE,
            sheet_id INTEGER REFERENCES training_sheet(id) ON DELETE SET NULL,
            group_id INTEGER REFERENCES training_group(id) ON DELETE SET NULL,
            message VARCHAR(500),
            proposed_at DATETIME NOT NULL,
            closed_at DATETIME,
            outcome VARCHAR(12),
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL
        )
        """)
    cursor.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_training_assignment_in_attesa "
        "ON training_assignment (instructor_id, user_id) WHERE closed_at IS NULL"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS ix_training_assignment_user_id "
        "ON training_assignment (user_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS ix_training_assignment_group_id "
        "ON training_assignment (group_id)"
    )
    print("  ✓ Tabella training_assignment")

    conn.commit()
    conn.close()


if __name__ == "__main__":
    upgrade_sqlite()
