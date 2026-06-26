"""Dual ELO — rende match_rating_history polimorfa (torneo + casual).

Per il secondo pool ELO ("ELO_GLOBAL" = tornei + casual VALIDATED) la history
deve poter referenziare anche un IndividualMatch. Oggi `match_id` ha FK su
`match.id` ed è NOT NULL, quindi non regge i casual.

Questa migration:
  1. aggiunge `individual_match_id` (FK individual_match.id, nullable);
  2. rende `match_id` nullable;
  3. sostituisce la UNIQUE (match_id,user_id,rating_system) con due indici unici
     PARZIALI (uno per sorgente), così le righe con l'altra sorgente NULL non
     collidono fra loro.

SQLite non supporta DROP NOT NULL via ALTER → table-rebuild (create-copy-drop-
rename). I dati esistenti (history ELO competitiva) sono preservati; in caso di
problemi sono comunque rigenerabili con `recalculate_all_elo()`.

Idempotente: se `individual_match_id` esiste già, è un no-op.
"""

import os
import sqlite3
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

migration_name = "20260626_dual_elo_history_polymorphic"


def _column_exists(cursor: sqlite3.Cursor, table: str, column: str) -> bool:
    cursor.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cursor.fetchall())


def _create_partial_indexes(cursor: sqlite3.Cursor) -> None:
    cursor.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_match_user_rating_system "
        "ON match_rating_history (match_id, user_id, rating_system) "
        "WHERE match_id IS NOT NULL"
    )
    cursor.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_individual_match_user_rating_system "
        "ON match_rating_history (individual_match_id, user_id, rating_system) "
        "WHERE individual_match_id IS NOT NULL"
    )


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db"):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    if _column_exists(cursor, "match_rating_history", "individual_match_id"):
        print("  ⏭️  match_rating_history già polimorfa (no-op)")
        _create_partial_indexes(cursor)
        conn.commit()
        conn.close()
        return

    # FK off durante il rebuild (le FK verso questa tabella si re-validano dopo).
    cursor.execute("PRAGMA foreign_keys=OFF")

    cursor.execute("""
        CREATE TABLE match_rating_history_new (
            id INTEGER PRIMARY KEY,
            match_id INTEGER,
            individual_match_id INTEGER,
            user_id INTEGER NOT NULL,
            rating_system VARCHAR(20) NOT NULL,
            old_rating INTEGER NOT NULL,
            new_rating INTEGER NOT NULL,
            delta INTEGER NOT NULL,
            games_increment INTEGER NOT NULL DEFAULT 1,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL,
            FOREIGN KEY (match_id) REFERENCES match(id) ON DELETE CASCADE,
            FOREIGN KEY (individual_match_id)
                REFERENCES individual_match(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES user(id) ON DELETE CASCADE
        )
        """)
    cursor.execute("""
        INSERT INTO match_rating_history_new (
            id, match_id, user_id, rating_system,
            old_rating, new_rating, delta, games_increment,
            created_at, updated_at
        )
        SELECT id, match_id, user_id, rating_system,
               old_rating, new_rating, delta, games_increment,
               created_at, updated_at
        FROM match_rating_history
        """)
    cursor.execute("DROP TABLE match_rating_history")
    cursor.execute(
        "ALTER TABLE match_rating_history_new RENAME TO match_rating_history"
    )
    _create_partial_indexes(cursor)

    conn.commit()
    cursor.execute("PRAGMA foreign_keys=ON")
    conn.close()
    print(
        "  ✓ match_rating_history resa polimorfa (match_id nullable + "
        "individual_match_id + indici parziali)"
    )


if __name__ == "__main__":
    upgrade_sqlite()
