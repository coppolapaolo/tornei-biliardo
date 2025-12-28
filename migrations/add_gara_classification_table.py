"""Database migration: Add gara_classification table.

Date: 2025-12-28

This migration adds the gara_classification table to store final standings
for completed gare. This is part of the Classification Strategy Pattern refactor.

Purpose:
- Store final gara rankings after all rounds complete
- Track tiebreaker resolution status
- Store campionato points for gare in championships
- Enable historical record keeping

New Table:
- gara_classification

Backward Compatibility:
- New table, no existing data affected
- Existing round_classification table unchanged
"""

import sqlite3
from datetime import datetime
from pathlib import Path


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db") -> None:
    """Run migration for SQLite (development)."""
    db_file = Path(db_path)
    if not db_file.exists():
        print(f"❌ Database not found: {db_path}")
        print("   Run application first to create database")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print(f"🔧 Migrating SQLite database: {db_path}")

    try:
        # Check if table already exists
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='gara_classification'
        """)
        if cursor.fetchone():
            print("⚠️  Table 'gara_classification' already exists")
            print("   Skipping migration...")
            return

        # Create gara_classification table
        print("   Creating 'gara_classification' table...")

        cursor.execute("""
            CREATE TABLE gara_classification (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                gara_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                position INTEGER NOT NULL,
                matches_won INTEGER DEFAULT 0,
                matches_lost INTEGER DEFAULT 0,
                racks_won INTEGER DEFAULT 0,
                racks_lost INTEGER DEFAULT 0,
                rack_difference INTEGER DEFAULT 0,
                tied_with_player_ids TEXT,
                tiebreaker_resolved BOOLEAN DEFAULT 1,
                spot_shot_wins INTEGER DEFAULT 0,
                campionato_points INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (gara_id) REFERENCES gara(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES user(id),
                UNIQUE (gara_id, user_id)
            )
        """)

        # Create indexes for common queries
        print("   Creating indexes...")

        cursor.execute("""
            CREATE INDEX idx_gara_classification_gara_id
            ON gara_classification(gara_id)
        """)

        cursor.execute("""
            CREATE INDEX idx_gara_classification_user_id
            ON gara_classification(user_id)
        """)

        cursor.execute("""
            CREATE INDEX idx_gara_classification_position
            ON gara_classification(gara_id, position)
        """)

        conn.commit()
        print("✅ Migration completed successfully!")

        # Verify migration
        print("\n🔍 Verifying migration...")

        cursor.execute("PRAGMA table_info(gara_classification)")
        cols = {row[1] for row in cursor.fetchall()}

        required_fields = {
            "id",
            "gara_id",
            "user_id",
            "position",
            "matches_won",
            "matches_lost",
            "racks_won",
            "racks_lost",
            "rack_difference",
            "tied_with_player_ids",
            "tiebreaker_resolved",
            "spot_shot_wins",
            "campionato_points",
            "created_at",
            "updated_at",
        }

        if required_fields.issubset(cols):
            print("   ✓ gara_classification table: All fields present")
        else:
            print(f"   ✗ gara_classification table: Missing {required_fields - cols}")

        # Check indexes
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='index' AND tbl_name='gara_classification'
        """)
        indexes = {row[0] for row in cursor.fetchall()}
        print(f"   ✓ Indexes created: {len(indexes)}")

    except sqlite3.OperationalError as e:
        print(f"❌ Migration failed: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


def upgrade_postgresql(connection_string: str) -> None:
    """Run migration for PostgreSQL (production).

    Args:
        connection_string: PostgreSQL connection string
    """
    try:
        import psycopg2
    except ImportError:
        print("❌ psycopg2 not installed. Install with: pip install psycopg2-binary")
        return

    print("🔧 Migrating PostgreSQL database...")

    conn = psycopg2.connect(connection_string)
    cursor = conn.cursor()

    try:
        # Check if table already exists
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'gara_classification'
            )
        """)
        if cursor.fetchone()[0]:
            print("⚠️  Table 'gara_classification' already exists")
            print("   Skipping migration...")
            return

        # Create gara_classification table
        print("   Creating 'gara_classification' table...")

        cursor.execute("""
            CREATE TABLE gara_classification (
                id SERIAL PRIMARY KEY,
                gara_id INTEGER NOT NULL REFERENCES gara(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL REFERENCES "user"(id),
                position INTEGER NOT NULL,
                matches_won INTEGER DEFAULT 0,
                matches_lost INTEGER DEFAULT 0,
                racks_won INTEGER DEFAULT 0,
                racks_lost INTEGER DEFAULT 0,
                rack_difference INTEGER DEFAULT 0,
                tied_with_player_ids JSONB,
                tiebreaker_resolved BOOLEAN DEFAULT TRUE,
                spot_shot_wins INTEGER DEFAULT 0,
                campionato_points INTEGER DEFAULT 0,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                UNIQUE (gara_id, user_id)
            )
        """)

        # Create indexes
        print("   Creating indexes...")

        cursor.execute("""
            CREATE INDEX idx_gara_classification_gara_id
            ON gara_classification(gara_id)
        """)

        cursor.execute("""
            CREATE INDEX idx_gara_classification_user_id
            ON gara_classification(user_id)
        """)

        cursor.execute("""
            CREATE INDEX idx_gara_classification_position
            ON gara_classification(gara_id, position)
        """)

        conn.commit()
        print("✅ PostgreSQL migration completed successfully!")

    except Exception as e:
        print(f"❌ PostgreSQL migration failed: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


def downgrade_sqlite(db_path: str = "instance/billiard_campionato.db") -> None:
    """Rollback migration for SQLite."""
    db_file = Path(db_path)
    if not db_file.exists():
        print(f"❌ Database not found: {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print(f"🔧 Rolling back SQLite database: {db_path}")

    try:
        cursor.execute("DROP TABLE IF EXISTS gara_classification")
        conn.commit()
        print("✅ Rollback completed successfully!")
    except sqlite3.OperationalError as e:
        print(f"❌ Rollback failed: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


def downgrade_postgresql(connection_string: str) -> None:
    """Rollback migration for PostgreSQL."""
    try:
        import psycopg2
    except ImportError:
        print("❌ psycopg2 not installed. Install with: pip install psycopg2-binary")
        return

    print("🔧 Rolling back PostgreSQL database...")

    conn = psycopg2.connect(connection_string)
    cursor = conn.cursor()

    try:
        cursor.execute("DROP TABLE IF EXISTS gara_classification")
        conn.commit()
        print("✅ PostgreSQL rollback completed successfully!")
    except Exception as e:
        print(f"❌ PostgreSQL rollback failed: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    import os
    import sys

    print("=" * 60)
    print("Gara Classification Table Migration")
    print("=" * 60)
    print()

    if len(sys.argv) > 1:
        if sys.argv[1] == "postgresql":
            # PostgreSQL migration
            db_url = os.environ.get("DATABASE_URL")
            if not db_url:
                print("❌ DATABASE_URL environment variable not set")
                sys.exit(1)
            upgrade_postgresql(db_url)
        elif sys.argv[1] == "downgrade":
            # Rollback SQLite
            downgrade_sqlite()
        elif sys.argv[1] == "downgrade-postgresql":
            # Rollback PostgreSQL
            db_url = os.environ.get("DATABASE_URL")
            if not db_url:
                print("❌ DATABASE_URL environment variable not set")
                sys.exit(1)
            downgrade_postgresql(db_url)
        else:
            print(f"❌ Unknown command: {sys.argv[1]}")
            print("\nUsage:")
            print("  python migrations/add_gara_classification_table.py                    # SQLite (dev)")
            print("  python migrations/add_gara_classification_table.py postgresql         # PostgreSQL (prod)")
            print("  python migrations/add_gara_classification_table.py downgrade          # Rollback SQLite")
            print("  python migrations/add_gara_classification_table.py downgrade-postgresql  # Rollback PostgreSQL")
            sys.exit(1)
    else:
        # Default: SQLite migration
        upgrade_sqlite()

    print()
    print("=" * 60)
