"""
Migration: Add IndividualSet model for multi-set individual matches

Date: 2026-02-02
Description:
- Create individual_set table for storing set data in multi-set individual matches
- Add individual_set_id column to individual_rack table (nullable for backward
    compatibility)
- Add current_set_number column to individual_match table

This migration supports Phase 2 of the multi-set implementation plan.
"""

import sqlite3


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db") -> None:
    """Apply migration to SQLite database."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 1. Create individual_set table
    try:
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='individual_set'
        """)
        if cursor.fetchone():
            print("Table 'individual_set' already exists, skipping...")
        else:
            cursor.execute("""
                CREATE TABLE individual_set (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    match_id INTEGER NOT NULL REFERENCES individual_match(id)
                        ON DELETE CASCADE,
                    set_number INTEGER NOT NULL,
                    distance INTEGER NOT NULL,
                    is_race_to BOOLEAN NOT NULL DEFAULT 1,
                    player1_racks INTEGER NOT NULL DEFAULT 0,
                    player2_racks INTEGER NOT NULL DEFAULT 0,
                    status VARCHAR(20) NOT NULL DEFAULT 'pending',
                    winner_id INTEGER REFERENCES user(id),
                    started_at DATETIME,
                    completed_at DATETIME,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(match_id, set_number)
                )
            """)
            print("Created 'individual_set' table")

            # Create indexes
            cursor.execute("""
                CREATE INDEX idx_individual_set_match_id
                ON individual_set(match_id)
            """)
            print("Created index idx_individual_set_match_id")

            cursor.execute("""
                CREATE INDEX idx_individual_set_status
                ON individual_set(status)
            """)
            print("Created index idx_individual_set_status")
    except Exception as e:
        print(f"Error creating individual_set table: {e}")
        raise

    # 2. Add individual_set_id column to individual_rack table
    try:
        cursor.execute("PRAGMA table_info(individual_rack)")
        columns = [col[1] for col in cursor.fetchall()]

        if "individual_set_id" not in columns:
            cursor.execute("""
                ALTER TABLE individual_rack
                ADD COLUMN individual_set_id INTEGER REFERENCES individual_set(id)
                    ON DELETE CASCADE
            """)
            print("Added 'individual_set_id' column to individual_rack table")

            # Create index for the FK
            cursor.execute("""
                CREATE INDEX idx_individual_rack_set_id
                ON individual_rack(individual_set_id)
            """)
            print("Created index idx_individual_rack_set_id")
        else:
            print("Column 'individual_set_id' already exists in individual_rack table")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            print("Column 'individual_set_id' already exists in individual_rack table")
        else:
            raise

    # 3. Add current_set_number column to individual_match table
    try:
        cursor.execute("PRAGMA table_info(individual_match)")
        columns = [col[1] for col in cursor.fetchall()]

        if "current_set_number" not in columns:
            cursor.execute("""
                ALTER TABLE individual_match
                ADD COLUMN current_set_number INTEGER DEFAULT 1
            """)
            print("Added 'current_set_number' column to individual_match table")
        else:
            print(
                "Column 'current_set_number' already exists in individual_match table"
            )
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            print(
                "Column 'current_set_number' already exists in individual_match table"
            )
        else:
            raise

    conn.commit()
    conn.close()
    print("Migration 20260202_individual_set_model completed successfully!")


def downgrade_sqlite(db_path: str = "instance/billiard_campionato.db") -> None:
    """Rollback migration (limited support in SQLite)."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print("WARNING: Downgrade is limited for SQLite")

    # Drop the individual_set table
    try:
        cursor.execute("DROP TABLE IF EXISTS individual_set")
        print("Dropped 'individual_set' table")
    except Exception as e:
        print(f"Error dropping table: {e}")

    # Note: SQLite doesn't support DROP COLUMN easily
    # The individual_set_id and current_set_number columns will remain

    print(
        "Note: individual_set_id and current_set_number columns remain in their tables"
    )

    conn.commit()
    conn.close()


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "downgrade":
        downgrade_sqlite()
    else:
        upgrade_sqlite()
