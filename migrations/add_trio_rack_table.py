"""Database migration: Add trio_rack table for undo functionality.

Date: 2025-01-09

This migration adds the trio_rack table to track individual racks
in trio matches, enabling undo functionality.

Following ADR-005 and the OO pattern from regular Rack model.

Tables Created:
- trio_rack

Note: Old counter columns in trio_match (player1_racks, player2_racks,
player3_racks, total_racks_played, current_round, current_rack_in_round)
are now computed properties in Python. These columns remain in the DB
but are unused. SQLite doesn't easily support DROP COLUMN.
"""

import sqlite3
from pathlib import Path


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db") -> None:
    """Run migration for SQLite (development)."""
    db_file = Path(db_path)
    if not db_file.exists():
        print(f"Database not found: {db_path}")
        print("   Run application first to create database")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print(f"Migrating SQLite database: {db_path}")

    try:
        # Check if table already exists
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='trio_rack'
        """)
        if cursor.fetchone():
            print("   Table 'trio_rack' already exists, skipping...")
            return

        # Create trio_rack table
        print("   Creating 'trio_rack' table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trio_rack (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trio_match_id INTEGER NOT NULL,
                rack_number INTEGER NOT NULL,
                winner_id INTEGER NOT NULL,
                player1_id INTEGER NOT NULL,
                player2_id INTEGER NOT NULL,
                waiting_player_id INTEGER NOT NULL,
                added_by_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_deleted BOOLEAN NOT NULL DEFAULT 0,
                removed_by_id INTEGER,
                removed_at TIMESTAMP,
                FOREIGN KEY (trio_match_id) REFERENCES trio_match(id) ON DELETE CASCADE,
                FOREIGN KEY (winner_id) REFERENCES user(id),
                FOREIGN KEY (player1_id) REFERENCES user(id),
                FOREIGN KEY (player2_id) REFERENCES user(id),
                FOREIGN KEY (waiting_player_id) REFERENCES user(id),
                FOREIGN KEY (added_by_id) REFERENCES user(id),
                FOREIGN KEY (removed_by_id) REFERENCES user(id)
            )
        """)

        # Create indexes for common queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_trio_rack_match_id
            ON trio_rack(trio_match_id)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_trio_rack_winner_id
            ON trio_rack(winner_id)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_trio_rack_active
            ON trio_rack(trio_match_id, is_deleted)
        """)

        conn.commit()
        print("   Migration completed successfully!")

    except Exception as e:
        conn.rollback()
        print(f"   Error during migration: {e}")
        raise

    finally:
        conn.close()


def upgrade_postgres(connection_string: str) -> None:
    """Run migration for PostgreSQL (production).

    Uses psycopg2 directly for DDL operations.
    """
    import psycopg2

    conn = psycopg2.connect(connection_string)
    cursor = conn.cursor()

    print("Migrating PostgreSQL database...")

    try:
        # Check if table already exists
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'trio_rack'
            )
        """)
        if cursor.fetchone()[0]:
            print("   Table 'trio_rack' already exists, skipping...")
            return

        # Create trio_rack table
        print("   Creating 'trio_rack' table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trio_rack (
                id SERIAL PRIMARY KEY,
                trio_match_id INTEGER NOT NULL REFERENCES trio_match(id) ON DELETE CASCADE,
                rack_number INTEGER NOT NULL,
                winner_id INTEGER NOT NULL REFERENCES "user"(id),
                player1_id INTEGER NOT NULL REFERENCES "user"(id),
                player2_id INTEGER NOT NULL REFERENCES "user"(id),
                waiting_player_id INTEGER NOT NULL REFERENCES "user"(id),
                added_by_id INTEGER REFERENCES "user"(id),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
                removed_by_id INTEGER REFERENCES "user"(id),
                removed_at TIMESTAMP
            )
        """)

        # Create indexes
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_trio_rack_match_id
            ON trio_rack(trio_match_id)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_trio_rack_winner_id
            ON trio_rack(winner_id)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_trio_rack_active
            ON trio_rack(trio_match_id, is_deleted)
        """)

        conn.commit()
        print("   Migration completed successfully!")

    except Exception as e:
        conn.rollback()
        print(f"   Error during migration: {e}")
        raise

    finally:
        conn.close()


def downgrade_sqlite(db_path: str = "instance/billiard_campionato.db") -> None:
    """Rollback migration for SQLite."""
    db_file = Path(db_path)
    if not db_file.exists():
        print(f"Database not found: {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print(f"Rolling back SQLite migration: {db_path}")

    try:
        cursor.execute("DROP TABLE IF EXISTS trio_rack")
        conn.commit()
        print("   Rollback completed!")

    except Exception as e:
        conn.rollback()
        print(f"   Error during rollback: {e}")
        raise

    finally:
        conn.close()


def downgrade_postgres(connection_string: str) -> None:
    """Rollback migration for PostgreSQL."""
    import psycopg2

    conn = psycopg2.connect(connection_string)
    cursor = conn.cursor()

    print("Rolling back PostgreSQL migration...")

    try:
        cursor.execute("DROP TABLE IF EXISTS trio_rack")
        conn.commit()
        print("   Rollback completed!")

    except Exception as e:
        conn.rollback()
        print(f"   Error during rollback: {e}")
        raise

    finally:
        conn.close()


# For manual testing
if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--rollback":
        downgrade_sqlite()
    else:
        upgrade_sqlite()
