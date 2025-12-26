"""Database migration: Add tiebreaker configuration fields to Gara.

Date: 2025-12-26

This migration adds tiebreaker configuration fields to support end-of-gara
spareggio (playoff) for tied positions:

- tiebreaker_enabled: Boolean flag to enable tiebreaker
- tiebreaker_until_position: Position up to which tiebreakers are performed
- tiebreaker_mode: "playoff_match" or "challenge"
- tiebreaker_challenge_id: FK to Challenge table (for challenge mode)

Tables Modified:
- gara

Backward Compatibility:
- All new fields have sensible defaults (enabled=True, position=3, mode=playoff_match)
- Existing records will use playoff match mode by default
"""

import sqlite3
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
        # Add tiebreaker fields to gara table
        print("   Adding tiebreaker fields to 'gara' table...")

        cursor.execute("""
            ALTER TABLE gara
            ADD COLUMN tiebreaker_enabled BOOLEAN DEFAULT 1 NOT NULL
        """)

        cursor.execute("""
            ALTER TABLE gara
            ADD COLUMN tiebreaker_until_position INTEGER DEFAULT 3
        """)

        cursor.execute("""
            ALTER TABLE gara
            ADD COLUMN tiebreaker_mode VARCHAR(20) DEFAULT 'playoff_match'
        """)

        cursor.execute("""
            ALTER TABLE gara
            ADD COLUMN tiebreaker_challenge_id INTEGER REFERENCES challenge(id) ON DELETE SET NULL
        """)

        conn.commit()
        print("✅ Migration completed successfully!")

        # Verify migration
        print("\n🔍 Verifying migration...")

        cursor.execute("PRAGMA table_info(gara)")
        gara_cols = {row[1] for row in cursor.fetchall()}

        required_fields = {
            "tiebreaker_enabled",
            "tiebreaker_until_position",
            "tiebreaker_mode",
            "tiebreaker_challenge_id"
        }

        if required_fields.issubset(gara_cols):
            print("   ✓ gara table: All tiebreaker fields present")
        else:
            print(f"   ✗ gara table: Missing {required_fields - gara_cols}")

    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            print(f"⚠️  Migration already applied: {e}")
            print("   Skipping...")
        else:
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

    print(f"🔧 Migrating PostgreSQL database...")

    conn = psycopg2.connect(connection_string)
    cursor = conn.cursor()

    try:
        # Add tiebreaker fields to gara table
        print("   Adding tiebreaker fields to 'gara' table...")

        cursor.execute("""
            ALTER TABLE gara
            ADD COLUMN IF NOT EXISTS tiebreaker_enabled BOOLEAN DEFAULT TRUE NOT NULL
        """)

        cursor.execute("""
            ALTER TABLE gara
            ADD COLUMN IF NOT EXISTS tiebreaker_until_position INTEGER DEFAULT 3
        """)

        cursor.execute("""
            ALTER TABLE gara
            ADD COLUMN IF NOT EXISTS tiebreaker_mode VARCHAR(20) DEFAULT 'playoff_match'
        """)

        cursor.execute("""
            ALTER TABLE gara
            ADD COLUMN IF NOT EXISTS tiebreaker_challenge_id INTEGER REFERENCES challenge(id) ON DELETE SET NULL
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
    """Rollback migration for SQLite.

    Note: SQLite doesn't support DROP COLUMN before version 3.35.0.
    For older versions, this requires recreating the table.
    """
    print("⚠️  SQLite downgrade requires manual intervention")
    print("   (SQLite < 3.35.0 doesn't support DROP COLUMN)")
    print("\n   To rollback:")
    print("   1. Backup your database")
    print("   2. Recreate tables without tiebreaker columns")
    print("   3. Copy data from backup")


if __name__ == "__main__":
    import sys
    import os

    print("=" * 60)
    print("Tiebreaker Fields Migration")
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
            # Rollback
            downgrade_sqlite()
        else:
            print(f"❌ Unknown command: {sys.argv[1]}")
            print("\nUsage:")
            print("  python migrations/add_tiebreaker_fields.py              # SQLite (dev)")
            print("  python migrations/add_tiebreaker_fields.py postgresql   # PostgreSQL (prod)")
            print("  python migrations/add_tiebreaker_fields.py downgrade    # Rollback")
            sys.exit(1)
    else:
        # Default: SQLite migration
        upgrade_sqlite()

    print()
    print("=" * 60)
