"""I gruppi di allievi dell'istruttore, con il loro storico (D12, fase 8c).

Due tabelle nuove, nessuna colonna toccata: i gruppi non cambiano niente di
quello che c'era — e soprattutto non toccano `training_sheet_reader`, che
resta l'unico posto in cui è scritto chi legge che cosa (ADR-069).

* `training_group` — il corso: nome, periodo, e di chi è. Il periodo
  (`started_on`/`ended_on`) è il **calendario dichiarato**; lo stato è
  `closed_at`, perché «finisce il 15/12» si scrive a settembre e non vuol dire
  che il corso sia finito;
* `training_group_member` — chi ne fa parte, da quando a quando.

Un indice unico **parziale** su (istruttore, allievo) fra le sole righe aperte:
«un allievo sta in un gruppo solo per volta, per lo stesso istruttore». È
imposto dal database e non da un `if`, perché un'unicità che vive in Python è
invisibile a chi scrive in blocco (`UserMergeService` legge lo schema).

Idempotente: CREATE TABLE/INDEX IF NOT EXISTS. Le tabelle nascono con
`created_at` e `updated_at`, che `BaseModel` pretende (incidente `categoria`,
2026-08-19).
"""

import os
import sqlite3
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

migration_name = "20260920_gruppi_di_allievi"


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db"):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS training_group (
            id INTEGER NOT NULL PRIMARY KEY,
            instructor_id INTEGER NOT NULL REFERENCES user(id) ON DELETE CASCADE,
            name VARCHAR(120) NOT NULL,
            started_on DATE,
            ended_on DATE,
            closed_at DATETIME,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL
        )
        """)
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS ix_training_group_instructor_id "
        "ON training_group (instructor_id)"
    )
    print("  ✓ Tabella training_group")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS training_group_member (
            id INTEGER NOT NULL PRIMARY KEY,
            group_id INTEGER NOT NULL
                REFERENCES training_group(id) ON DELETE CASCADE,
            instructor_id INTEGER NOT NULL REFERENCES user(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES user(id) ON DELETE CASCADE,
            joined_at DATETIME NOT NULL,
            left_at DATETIME,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL
        )
        """)
    cursor.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_training_group_member_attivo "
        "ON training_group_member (instructor_id, user_id) WHERE left_at IS NULL"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS ix_training_group_member_group_id "
        "ON training_group_member (group_id)"
    )
    print("  ✓ Tabella training_group_member")

    conn.commit()
    conn.close()


if __name__ == "__main__":
    upgrade_sqlite()
