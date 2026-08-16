"""
Migration: Make distance nullable on individual_match for free format matches

Date: 2026-02-02
Description:
- Makes individual_match.distance nullable to support free format matches
- Free format matches have no distance limit (players end match manually)

SQLite Note: SQLite doesn't support ALTER COLUMN to change nullability.
We need to recreate the table. This migration creates a new table with
nullable distance, copies data, and swaps tables.
"""

import sqlite3


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db") -> None:
    """Apply migration to SQLite database."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check current nullability of distance column
    cursor.execute("PRAGMA table_info(individual_match)")
    columns = cursor.fetchall()
    distance_col = next((c for c in columns if c[1] == "distance"), None)

    if distance_col and distance_col[3] == 0:  # notnull = 0 means nullable
        print("Column 'distance' is already nullable, skipping...")
        conn.close()
        return

    print("Making individual_match.distance nullable...")

    try:
        # 1. Create new table with nullable distance
        # Schema matches actual DB columns (no forfeit columns)
        cursor.execute("""
            CREATE TABLE individual_match_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                proposal_id INTEGER REFERENCES match_proposal(id) ON DELETE SET NULL,
                player1_id INTEGER NOT NULL REFERENCES user(id),
                player2_id INTEGER NOT NULL REFERENCES user(id),
                billiard_hall_id INTEGER REFERENCES billiard_hall(id) ON DELETE
                    SET NULL,
                location VARCHAR(255),
                scheduled_at DATETIME NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'scheduled',
                discipline VARCHAR(50) NOT NULL DEFAULT 'palla_8',
                distance INTEGER NULL DEFAULT 5,
                is_race_to BOOLEAN NOT NULL DEFAULT 1,
                break_rule VARCHAR(20) NOT NULL DEFAULT 'alternate',
                is_multi_set BOOLEAN NOT NULL DEFAULT 0,
                match_distance INTEGER,
                is_race_to_sets BOOLEAN DEFAULT 1,
                entry_fee DECIMAL(10,2),
                notes TEXT,
                started_at DATETIME,
                completed_at DATETIME,
                player1_score INTEGER NOT NULL DEFAULT 0,
                player2_score INTEGER NOT NULL DEFAULT 0,
                winner_id INTEGER REFERENCES user(id),
                player1_confirmed BOOLEAN NOT NULL DEFAULT 0,
                player2_confirmed BOOLEAN NOT NULL DEFAULT 0,
                player1_confirmed_at DATETIME,
                player2_confirmed_at DATETIME,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                ended_at DATETIME,
                current_set_number INTEGER DEFAULT 1
            )
        """)

        # 2. Copy data from old table
        cursor.execute("""
            INSERT INTO individual_match_new (
                id, proposal_id, player1_id, player2_id, billiard_hall_id, location,
                scheduled_at, status, discipline, distance, is_race_to, break_rule,
                is_multi_set, match_distance, is_race_to_sets, entry_fee, notes,
                started_at, completed_at, player1_score, player2_score, winner_id,
                player1_confirmed, player2_confirmed, player1_confirmed_at,
                player2_confirmed_at, created_at, updated_at, ended_at,
                current_set_number
            )
            SELECT
                id, proposal_id, player1_id, player2_id, billiard_hall_id, location,
                scheduled_at, status, discipline, distance, is_race_to, break_rule,
                is_multi_set, match_distance, is_race_to_sets, entry_fee, notes,
                started_at, completed_at, player1_score, player2_score, winner_id,
                player1_confirmed, player2_confirmed, player1_confirmed_at,
                player2_confirmed_at, created_at, updated_at, ended_at,
                current_set_number
            FROM individual_match
        """)

        # 3. Drop old table
        cursor.execute("DROP TABLE individual_match")

        # 4. Rename new table
        cursor.execute("ALTER TABLE individual_match_new RENAME TO individual_match")

        # 5. Recreate indexes
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_individual_match_player1
            ON individual_match(player1_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_individual_match_player2
            ON individual_match(player2_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_individual_match_status
            ON individual_match(status)
        """)

        conn.commit()
        print("Migration completed: individual_match.distance is now nullable")

    except Exception as e:
        conn.rollback()
        print(f"Error during migration: {e}")
        raise

    finally:
        conn.close()


def downgrade_sqlite(db_path: str = "instance/billiard_campionato.db") -> None:
    """Rollback migration (limited - doesn't restore NOT NULL constraint)."""
    _ = db_path  # Unused but required by migration interface
    print("WARNING: Downgrade not implemented - distance column will remain nullable")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "downgrade":
        downgrade_sqlite()
    else:
        upgrade_sqlite()
