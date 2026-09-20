"""Gli obiettivi di allenamento (#316).

Una tabella sola per le tre forme — un risultato su un esercizio, un'abilità che
sale, la costanza — perché quello che cambia fra loro è **da dove si legge il
progresso**, non com'è fatta la riga.

Niente colonne per il progresso: si legge ogni volta dalle stesse fonti
dell'andamento. Le due date che si scrivono sono fatti: `reached_at`, la prima
volta che l'obiettivo risulta raggiunto, e `abandoned_at`, quando si lascia.

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

migration_name = "20260920_obiettivi_di_allenamento"


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db"):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS training_goal (
            id INTEGER NOT NULL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES user(id) ON DELETE CASCADE,
            kind VARCHAR(20) NOT NULL,
            challenge_id INTEGER REFERENCES challenge(id) ON DELETE CASCADE,
            axis VARCHAR(20),
            axis_value VARCHAR(40),
            target INTEGER NOT NULL,
            rule VARCHAR(20),
            per_week INTEGER,
            baseline INTEGER,
            deadline_kind VARCHAR(20) NOT NULL DEFAULT 'nessuna',
            deadline DATE,
            reached_at DATETIME,
            abandoned_at DATETIME,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL
        )
        """)
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS ix_training_goal_user_id "
        "ON training_goal (user_id)"
    )
    print("  ✓ Tabella training_goal")

    conn.commit()
    conn.close()


if __name__ == "__main__":
    upgrade_sqlite()
