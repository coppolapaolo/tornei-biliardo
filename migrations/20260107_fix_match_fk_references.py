"""
Migration: Fix foreign key references from match_backup to match

Date: 2026-01-07
Description:
- Fix FK references in child tables that incorrectly point to match_backup
- Affected tables: rack, match_result, trio_match, set, tiebreaker, hidden_match, gara_bye_challenge
"""

import sqlite3


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db") -> None:
    """Fix all tables with broken FK references to match_backup."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = OFF")
    cursor = conn.cursor()

    tables_to_fix = [
        {
            "name": "rack",
            "create_sql": """
                CREATE TABLE rack (
                    id INTEGER NOT NULL PRIMARY KEY,
                    match_id INTEGER NOT NULL REFERENCES match(id) ON DELETE CASCADE,
                    rack_number INTEGER NOT NULL,
                    winner_id INTEGER REFERENCES user(id),
                    reported_by_id INTEGER REFERENCES user(id),
                    confirmed_by_player BOOLEAN,
                    validated_by_admin BOOLEAN,
                    admin_note TEXT,
                    created_at DATETIME,
                    added_by_id INTEGER REFERENCES user(id),
                    added_at DATETIME,
                    removed_by_id INTEGER REFERENCES user(id),
                    removed_at DATETIME,
                    is_deleted BOOLEAN NOT NULL DEFAULT 0
                )
            """,
            "columns": "id, match_id, rack_number, winner_id, reported_by_id, "
            "confirmed_by_player, validated_by_admin, admin_note, created_at, "
            "added_by_id, added_at, removed_by_id, removed_at, is_deleted",
        },
        {
            "name": "match_result",
            "create_sql": """
                CREATE TABLE match_result (
                    id INTEGER NOT NULL PRIMARY KEY,
                    match_id INTEGER NOT NULL REFERENCES match(id),
                    user_id INTEGER NOT NULL REFERENCES user(id),
                    player1_score INTEGER,
                    player2_score INTEGER,
                    winner_id INTEGER REFERENCES user(id),
                    created_at DATETIME
                )
            """,
            "columns": "id, match_id, user_id, player1_score, player2_score, winner_id, created_at",
        },
        {
            "name": "trio_match",
            "create_sql": """
                CREATE TABLE trio_match (
                    id INTEGER NOT NULL PRIMARY KEY,
                    match_id INTEGER NOT NULL REFERENCES match(id),
                    player1_id INTEGER NOT NULL REFERENCES user(id),
                    player2_id INTEGER NOT NULL REFERENCES user(id),
                    player3_id INTEGER NOT NULL REFERENCES user(id),
                    current_player1_id INTEGER REFERENCES user(id),
                    current_player2_id INTEGER REFERENCES user(id),
                    waiting_player_id INTEGER REFERENCES user(id),
                    player1_racks INTEGER,
                    player2_racks INTEGER,
                    player3_racks INTEGER,
                    is_completed BOOLEAN,
                    winner_id INTEGER REFERENCES user(id),
                    created_at DATETIME
                )
            """,
            "columns": "id, match_id, player1_id, player2_id, player3_id, "
            "current_player1_id, current_player2_id, waiting_player_id, "
            "player1_racks, player2_racks, player3_racks, is_completed, winner_id, created_at",
        },
        {
            "name": "set",
            "create_sql": """
                CREATE TABLE "set" (
                    id INTEGER NOT NULL PRIMARY KEY,
                    match_id INTEGER NOT NULL REFERENCES match(id) ON DELETE CASCADE,
                    set_number INTEGER NOT NULL,
                    distance INTEGER NOT NULL,
                    is_race_to BOOLEAN NOT NULL DEFAULT 1,
                    player1_racks INTEGER NOT NULL DEFAULT 0,
                    player2_racks INTEGER NOT NULL DEFAULT 0,
                    status VARCHAR(20) NOT NULL DEFAULT 'pending',
                    winner_id INTEGER REFERENCES user(id),
                    started_at DATETIME,
                    completed_at DATETIME,
                    discipline VARCHAR(50),
                    is_multi_discipline BOOLEAN NOT NULL DEFAULT 0,
                    discipline_rotation JSON,
                    discipline_assignment JSON,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT uq_match_set_number UNIQUE (match_id, set_number)
                )
            """,
            "columns": "id, match_id, set_number, distance, is_race_to, player1_racks, "
            "player2_racks, status, winner_id, started_at, completed_at, "
            "discipline, is_multi_discipline, discipline_rotation, "
            "discipline_assignment, created_at, updated_at",
        },
        {
            "name": "tiebreaker",
            "create_sql": """
                CREATE TABLE tiebreaker (
                    id INTEGER NOT NULL PRIMARY KEY,
                    match_id INTEGER NOT NULL REFERENCES match(id),
                    campionato_id INTEGER REFERENCES campionato(id),
                    gara_id INTEGER REFERENCES gara(id),
                    tiebreaker_type VARCHAR(20) NOT NULL,
                    status VARCHAR(20),
                    player1_id INTEGER NOT NULL REFERENCES user(id),
                    player2_id INTEGER NOT NULL REFERENCES user(id),
                    winner_id INTEGER REFERENCES user(id),
                    created_at DATETIME,
                    started_at DATETIME,
                    completed_at DATETIME,
                    configuration JSON,
                    notes TEXT
                )
            """,
            "columns": "id, match_id, campionato_id, gara_id, tiebreaker_type, status, "
            "player1_id, player2_id, winner_id, created_at, started_at, "
            "completed_at, configuration, notes",
        },
        {
            "name": "hidden_match",
            "create_sql": """
                CREATE TABLE hidden_match (
                    id INTEGER NOT NULL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES user(id) ON DELETE CASCADE,
                    match_id INTEGER NOT NULL REFERENCES match(id) ON DELETE CASCADE,
                    hidden_at DATETIME NOT NULL,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT uq_hidden_match_user_match UNIQUE (user_id, match_id)
                )
            """,
            "columns": "id, user_id, match_id, hidden_at, created_at, updated_at",
        },
        {
            "name": "gara_bye_challenge",
            "create_sql": """
                CREATE TABLE gara_bye_challenge (
                    id INTEGER NOT NULL PRIMARY KEY,
                    gara_id INTEGER NOT NULL REFERENCES gara(id) ON DELETE CASCADE,
                    challenge_attempt_id INTEGER REFERENCES challenge_attempt(id) ON DELETE SET NULL,
                    round_number INTEGER NOT NULL,
                    user_id INTEGER NOT NULL REFERENCES user(id) ON DELETE CASCADE,
                    match_id INTEGER REFERENCES match(id) ON DELETE SET NULL,
                    is_completed BOOLEAN NOT NULL DEFAULT 0,
                    completed_at DATETIME,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT uq_gara_bye_challenge UNIQUE (gara_id, user_id, round_number)
                )
            """,
            "columns": "id, gara_id, challenge_attempt_id, round_number, user_id, "
            "match_id, is_completed, completed_at, created_at, updated_at",
        },
    ]

    for table_info in tables_to_fix:
        table_name = table_info["name"]
        print(f"Fixing table: {table_name}")

        # Check if table exists and has the broken FK
        cursor.execute(
            f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{table_name}'"
        )
        result = cursor.fetchone()
        if not result:
            print(f"  Table {table_name} does not exist, skipping")
            continue

        current_sql = result[0]
        if "match_backup" not in current_sql:
            print(f"  Table {table_name} already has correct FK, skipping")
            continue

        try:
            # Rename to backup
            cursor.execute(
                f'ALTER TABLE "{table_name}" RENAME TO "{table_name}_backup"'
            )
            print(f"  Renamed {table_name} to {table_name}_backup")

            # Create new table with correct FK
            cursor.execute(table_info["create_sql"])
            print(f"  Created new {table_name} with correct FK")

            # Copy data
            columns = table_info["columns"]
            cursor.execute(f"""
                INSERT INTO "{table_name}" ({columns})
                SELECT {columns} FROM "{table_name}_backup"
            """)
            row_count = cursor.rowcount
            print(f"  Copied {row_count} rows")

            # Drop backup
            cursor.execute(f'DROP TABLE "{table_name}_backup"')
            print(f"  Dropped {table_name}_backup")

        except sqlite3.Error as e:
            print(f"  ERROR fixing {table_name}: {e}")
            # Try to recover by renaming backup back
            try:
                cursor.execute(f'DROP TABLE IF EXISTS "{table_name}"')
                cursor.execute(
                    f'ALTER TABLE "{table_name}_backup" RENAME TO "{table_name}"'
                )
                print(f"  Recovered {table_name} from backup")
            except sqlite3.Error:
                pass
            raise

    # Re-create indexes for hidden_match
    try:
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_hidden_match_user_id ON hidden_match(user_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_hidden_match_match_id ON hidden_match(match_id)"
        )
        print("Re-created indexes for hidden_match")
    except sqlite3.Error as e:
        print(f"Warning: Could not create indexes: {e}")

    # Re-create index for gara_bye_challenge
    try:
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS ix_gara_bye_challenge_gara_id ON gara_bye_challenge(gara_id)"
        )
        print("Re-created index for gara_bye_challenge")
    except sqlite3.Error as e:
        print(f"Warning: Could not create index: {e}")

    conn.execute("PRAGMA foreign_keys = ON")
    conn.commit()
    conn.close()
    print("\nMigration completed successfully!")


def downgrade_sqlite(db_path: str = "instance/billiard_campionato.db") -> None:
    """No downgrade - this is a fix migration."""
    print("This migration fixes broken FK references. No downgrade available.")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "downgrade":
        downgrade_sqlite()
    else:
        upgrade_sqlite()
