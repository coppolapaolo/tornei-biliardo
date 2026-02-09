"""Fix match_proposal and individual_match tables that lost all constraints.

Migration 20260203 used CREATE TABLE ... AS SELECT which strips PRIMARY KEY,
FOREIGN KEY, NOT NULL, DEFAULT, and AUTOINCREMENT. This migration recreates
both tables with proper constraints while preserving existing data.
"""

import sqlite3

migration_name = "20260209_fix_match_proposal_constraints"


def upgrade_sqlite(db_path: str):
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = OFF")
    cursor = conn.cursor()

    # --- Fix match_proposal ---
    cursor.execute("PRAGMA table_info(match_proposal)")
    cols = [row[1] for row in cursor.fetchall()]
    if "id" in cols:
        # Check if PK is already correct (idempotency)
        cursor.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='match_proposal'"
        )
        schema = cursor.fetchone()[0]
        if "PRIMARY KEY" not in schema.upper():
            print("  Rebuilding match_proposal with constraints...")
            columns_str = ", ".join(cols)
            cursor.execute(f"""
                CREATE TABLE match_proposal_fixed (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    proposer_id INTEGER NOT NULL REFERENCES user(id) ON DELETE CASCADE,
                    proposal_type TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    billiard_hall_id INTEGER REFERENCES billiard_hall(id) ON DELETE SET NULL,
                    location TEXT,
                    scheduled_at DATETIME NOT NULL,
                    expires_at DATETIME NOT NULL,
                    discipline TEXT DEFAULT 'palla_8',
                    distance INTEGER DEFAULT 5,
                    is_race_to BOOLEAN DEFAULT 1,
                    break_rule TEXT DEFAULT 'alternate',
                    description TEXT,
                    is_multi_set BOOLEAN DEFAULT 0,
                    match_distance INTEGER,
                    is_race_to_sets BOOLEAN DEFAULT 1,
                    accepted_by_id INTEGER REFERENCES user(id) ON DELETE SET NULL,
                    accepted_at DATETIME,
                    created_at DATETIME,
                    updated_at DATETIME
                )
            """)
            cursor.execute(f"""
                INSERT INTO match_proposal_fixed ({columns_str})
                SELECT {columns_str} FROM match_proposal
            """)
            cursor.execute("DROP TABLE match_proposal")
            cursor.execute("ALTER TABLE match_proposal_fixed RENAME TO match_proposal")
            print("  match_proposal rebuilt with PRIMARY KEY and constraints")
        else:
            print("  match_proposal already has constraints, skipping")

    # --- Fix individual_match ---
    cursor.execute("PRAGMA table_info(individual_match)")
    cols = [row[1] for row in cursor.fetchall()]
    if "id" in cols:
        cursor.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='individual_match'"
        )
        schema = cursor.fetchone()[0]
        if "PRIMARY KEY" not in schema.upper():
            print("  Rebuilding individual_match with constraints...")
            columns_str = ", ".join(cols)
            cursor.execute(f"""
                CREATE TABLE individual_match_fixed (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    proposal_id INTEGER REFERENCES match_proposal(id),
                    player1_id INTEGER NOT NULL REFERENCES user(id) ON DELETE CASCADE,
                    player2_id INTEGER NOT NULL REFERENCES user(id) ON DELETE CASCADE,
                    billiard_hall_id INTEGER REFERENCES billiard_hall(id) ON DELETE SET NULL,
                    location TEXT,
                    scheduled_at DATETIME NOT NULL,
                    status TEXT NOT NULL DEFAULT 'scheduled',
                    discipline TEXT NOT NULL DEFAULT 'palla_8',
                    distance INTEGER,
                    is_race_to BOOLEAN NOT NULL DEFAULT 1,
                    break_rule TEXT NOT NULL DEFAULT 'alternate',
                    is_multi_set BOOLEAN NOT NULL DEFAULT 0,
                    match_distance INTEGER,
                    is_race_to_sets BOOLEAN DEFAULT 1,
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
                    created_at DATETIME,
                    updated_at DATETIME,
                    ended_at DATETIME,
                    current_set_number INTEGER
                )
            """)
            cursor.execute(f"""
                INSERT INTO individual_match_fixed ({columns_str})
                SELECT {columns_str} FROM individual_match
            """)
            cursor.execute("DROP TABLE individual_match")
            cursor.execute(
                "ALTER TABLE individual_match_fixed RENAME TO individual_match"
            )
            print("  individual_match rebuilt with PRIMARY KEY and constraints")
        else:
            print("  individual_match already has constraints, skipping")

    conn.execute("PRAGMA foreign_keys = ON")
    conn.commit()
    conn.close()
    print("  Done!")
