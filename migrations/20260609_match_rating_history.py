"""Crea la tabella match_rating_history (idempotenza + revert dei rating).

Feature (2026-06): `RatingCalculationService.process_match_result` non era
idempotente — ogni MatchCompletedEvent ri-emesso (reset→ricompletamento) o un
recalc_elo su match già processati ri-applicava il delta Elo e ri-incrementava
games_played in modo cumulativo, corrompendo silenziosamente i rating.

`match_rating_history` registra il delta applicato per ogni (match, giocatore,
sistema):
- se esiste già un record per (match_id, rating_system) il ricalcolo è no-op
  (idempotenza);
- su reset/riapertura del match si sottrae il delta e si decrementa
  games_played (revert), poi si eliminano i record.

Idempotente: CREATE TABLE IF NOT EXISTS.
"""

import sqlite3

migration_name = "20260609_match_rating_history"


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db"):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS match_rating_history (
            id INTEGER PRIMARY KEY,
            match_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            rating_system VARCHAR(20) NOT NULL,
            old_rating INTEGER NOT NULL,
            new_rating INTEGER NOT NULL,
            delta INTEGER NOT NULL,
            games_increment INTEGER NOT NULL DEFAULT 1,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL,
            FOREIGN KEY (match_id) REFERENCES match(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES user(id) ON DELETE CASCADE,
            CONSTRAINT uq_match_user_rating_system
                UNIQUE (match_id, user_id, rating_system)
        )
        """)
    print("  ✓ Tabella match_rating_history pronta")

    conn.commit()
    conn.close()
