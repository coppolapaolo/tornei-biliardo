"""
Migration: Add soft delete support for Gara and make Match.gara_id nullable

Date: 2026-01-06
Description:
- Add deleted_at and deleted_reason columns to gara table
- Make match.gara_id nullable to support standalone matches (detached from deleted gara)
- Change match.gara_id ondelete from CASCADE to SET NULL
"""

import sqlite3
from datetime import datetime


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db") -> None:
    """Apply migration to SQLite database."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # 1. Add deleted_at column to gara table
        cursor.execute("""
            ALTER TABLE gara ADD COLUMN deleted_at DATETIME NULL
        """)
        print("Added deleted_at column to gara table")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            print("Column deleted_at already exists in gara table")
        else:
            raise

    try:
        # 2. Add deleted_reason column to gara table
        cursor.execute("""
            ALTER TABLE gara ADD COLUMN deleted_reason VARCHAR(255) NULL
        """)
        print("Added deleted_reason column to gara table")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            print("Column deleted_reason already exists in gara table")
        else:
            raise

    # 3. For Match.gara_id nullable change, we need to recreate the table
    # First check if gara_id is already nullable
    cursor.execute("PRAGMA table_info(match)")
    columns = cursor.fetchall()
    gara_id_col = next((c for c in columns if c[1] == "gara_id"), None)

    if gara_id_col and gara_id_col[3] == 1:  # notnull = 1 means NOT NULL
        print("Making match.gara_id nullable (requires table recreation)...")

        # Get current table schema
        cursor.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='match'"
        )
        original_sql = cursor.fetchone()[0]

        # Create backup table
        cursor.execute("ALTER TABLE match RENAME TO match_backup")

        # Create new table with nullable gara_id and SET NULL on delete
        # Note: We need to construct the new table from scratch
        cursor.execute("""
            CREATE TABLE match (
                id INTEGER PRIMARY KEY,
                gara_id INTEGER NULL REFERENCES gara(id) ON DELETE SET NULL,
                round_number INTEGER NOT NULL,
                player1_id INTEGER REFERENCES user(id),
                player2_id INTEGER REFERENCES user(id),
                is_bye BOOLEAN DEFAULT 0,
                player1_score INTEGER DEFAULT 0,
                player2_score INTEGER DEFAULT 0,
                winner_id INTEGER REFERENCES user(id),
                match_distance INTEGER DEFAULT 1,
                is_multi_set BOOLEAN DEFAULT 0,
                current_set_number INTEGER DEFAULT 1,
                discipline VARCHAR(50),
                status VARCHAR(20) DEFAULT 'pending',
                is_locked BOOLEAN DEFAULT 0,
                round_locked BOOLEAN DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                is_trio BOOLEAN DEFAULT 0,
                table_assignment VARCHAR(10),
                has_handicap BOOLEAN DEFAULT 0,
                player1_handicap INTEGER DEFAULT 0,
                player2_handicap INTEGER DEFAULT 0,
                handicap_rule_id INTEGER REFERENCES handicap_rule(id),
                handicap_explanation VARCHAR(255),
                player1_confirmed BOOLEAN DEFAULT 0,
                player2_confirmed BOOLEAN DEFAULT 0,
                player1_confirmed_at DATETIME,
                player2_confirmed_at DATETIME
            )
        """)

        # Copy data from backup
        cursor.execute("""
            INSERT INTO match (
                id, gara_id, round_number, player1_id, player2_id, is_bye,
                player1_score, player2_score, winner_id, match_distance,
                is_multi_set, current_set_number, discipline, status,
                is_locked, round_locked, created_at, updated_at, is_trio,
                table_assignment, has_handicap, player1_handicap, player2_handicap,
                handicap_rule_id, handicap_explanation, player1_confirmed,
                player2_confirmed, player1_confirmed_at, player2_confirmed_at
            )
            SELECT
                id, gara_id, round_number, player1_id, player2_id, is_bye,
                player1_score, player2_score, winner_id, match_distance,
                is_multi_set, current_set_number, discipline, status,
                is_locked, round_locked, created_at, updated_at, is_trio,
                table_assignment, has_handicap, player1_handicap, player2_handicap,
                handicap_rule_id, handicap_explanation, player1_confirmed,
                player2_confirmed, player1_confirmed_at, player2_confirmed_at
            FROM match_backup
        """)

        # Drop backup table
        cursor.execute("DROP TABLE match_backup")

        print("Match table recreated with nullable gara_id")
    else:
        print("match.gara_id is already nullable")

    # Create index on gara.deleted_at for query performance
    try:
        cursor.execute("CREATE INDEX idx_gara_deleted_at ON gara(deleted_at)")
        print("Created index idx_gara_deleted_at")
    except sqlite3.OperationalError as e:
        if "already exists" in str(e).lower():
            print("Index idx_gara_deleted_at already exists")
        else:
            raise

    conn.commit()
    conn.close()
    print("Migration completed successfully!")


def downgrade_sqlite(db_path: str = "instance/billiard_campionato.db") -> None:
    """Rollback migration (not fully reversible for Match table)."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Note: SQLite doesn't support DROP COLUMN easily
    # We would need to recreate tables to fully rollback

    print("WARNING: Downgrade is not fully implemented for SQLite")
    print("The deleted_at and deleted_reason columns will remain in gara table")
    print("Match.gara_id nullable change is not reversible without data loss")

    conn.close()


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "downgrade":
        downgrade_sqlite()
    else:
        upgrade_sqlite()
