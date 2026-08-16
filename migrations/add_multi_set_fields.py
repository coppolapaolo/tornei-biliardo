"""Database migration: Add multi-set fields to Gara, MatchProposal, and IndividualMatch.

Phase 6: Frontend Integration
Date: 2025-10-07

This migration adds three new columns to support multi-set match configuration:
- is_multi_set: Boolean flag to enable multi-set mode
- match_distance: Number of sets to play
- sets_best_of: Whether sets are "best-of N" or "exactly N"

Tables Modified:
- gara
- match_proposal
- individual_match

Backward Compatibility:
- All new fields have sensible defaults (is_multi_set=False)
- Existing records will work as single-set matches
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
        # 1. Add fields to gara table
        print("   Adding multi-set fields to 'gara' table...")

        cursor.execute("""
            ALTER TABLE gara
            ADD COLUMN is_multi_set BOOLEAN DEFAULT 0 NOT NULL
        """)

        cursor.execute("""
            ALTER TABLE gara
            ADD COLUMN match_distance INTEGER
        """)

        cursor.execute("""
            ALTER TABLE gara
            ADD COLUMN sets_best_of BOOLEAN DEFAULT 1
        """)

        # 2. Add fields to match_proposal table
        print("   Adding multi-set fields to 'match_proposal' table...")

        cursor.execute("""
            ALTER TABLE match_proposal
            ADD COLUMN is_multi_set BOOLEAN DEFAULT 0
        """)

        cursor.execute("""
            ALTER TABLE match_proposal
            ADD COLUMN match_distance INTEGER
        """)

        cursor.execute("""
            ALTER TABLE match_proposal
            ADD COLUMN sets_best_of BOOLEAN DEFAULT 1
        """)

        # 3. Add fields to individual_match table
        print("   Adding multi-set fields to 'individual_match' table...")

        cursor.execute("""
            ALTER TABLE individual_match
            ADD COLUMN is_multi_set BOOLEAN DEFAULT 0 NOT NULL
        """)

        cursor.execute("""
            ALTER TABLE individual_match
            ADD COLUMN match_distance INTEGER
        """)

        cursor.execute("""
            ALTER TABLE individual_match
            ADD COLUMN sets_best_of BOOLEAN DEFAULT 1
        """)

        conn.commit()
        print("✅ Migration completed successfully!")

        # Verify migration
        print("\n🔍 Verifying migration...")

        cursor.execute("PRAGMA table_info(gara)")
        gara_cols = {row[1] for row in cursor.fetchall()}

        cursor.execute("PRAGMA table_info(match_proposal)")
        proposal_cols = {row[1] for row in cursor.fetchall()}

        cursor.execute("PRAGMA table_info(individual_match)")
        match_cols = {row[1] for row in cursor.fetchall()}

        required_fields = {"is_multi_set", "match_distance", "sets_best_of"}

        if required_fields.issubset(gara_cols):
            print("   ✓ gara table: All fields present")
        else:
            print(f"   ✗ gara table: Missing {required_fields - gara_cols}")

        if required_fields.issubset(proposal_cols):
            print("   ✓ match_proposal table: All fields present")
        else:
            print(
                f"   ✗ match_proposal table: Missing {required_fields - proposal_cols}"
            )

        if required_fields.issubset(match_cols):
            print("   ✓ individual_match table: All fields present")
        else:
            print(
                f"   ✗ individual_match table: Missing {required_fields - match_cols}"
            )

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

    print("🔧 Migrating PostgreSQL database...")

    conn = psycopg2.connect(connection_string)
    cursor = conn.cursor()

    try:
        # 1. Add fields to gara table
        print("   Adding multi-set fields to 'gara' table...")

        cursor.execute("""
            ALTER TABLE gara
            ADD COLUMN IF NOT EXISTS is_multi_set BOOLEAN DEFAULT FALSE NOT NULL
        """)

        cursor.execute("""
            ALTER TABLE gara
            ADD COLUMN IF NOT EXISTS match_distance INTEGER
        """)

        cursor.execute("""
            ALTER TABLE gara
            ADD COLUMN IF NOT EXISTS sets_best_of BOOLEAN DEFAULT TRUE
        """)

        # 2. Add fields to match_proposal table
        print("   Adding multi-set fields to 'match_proposal' table...")

        cursor.execute("""
            ALTER TABLE match_proposal
            ADD COLUMN IF NOT EXISTS is_multi_set BOOLEAN DEFAULT FALSE
        """)

        cursor.execute("""
            ALTER TABLE match_proposal
            ADD COLUMN IF NOT EXISTS match_distance INTEGER
        """)

        cursor.execute("""
            ALTER TABLE match_proposal
            ADD COLUMN IF NOT EXISTS sets_best_of BOOLEAN DEFAULT TRUE
        """)

        # 3. Add fields to individual_match table
        print("   Adding multi-set fields to 'individual_match' table...")

        cursor.execute("""
            ALTER TABLE individual_match
            ADD COLUMN IF NOT EXISTS is_multi_set BOOLEAN DEFAULT FALSE NOT NULL
        """)

        cursor.execute("""
            ALTER TABLE individual_match
            ADD COLUMN IF NOT EXISTS match_distance INTEGER
        """)

        cursor.execute("""
            ALTER TABLE individual_match
            ADD COLUMN IF NOT EXISTS sets_best_of BOOLEAN DEFAULT TRUE
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
    print("   2. Recreate tables without multi-set columns")
    print("   3. Copy data from backup")


if __name__ == "__main__":
    import sys
    import os

    print("=" * 60)
    print("Multi-Set Fields Migration (Phase 6)")
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
            print(
                (
                    "  python migrations/add_multi_set_fields.py              # SQLite "
                    "(dev)"
                )
            )
            print(
                (
                    "  python migrations/add_multi_set_fields.py postgresql   # "
                    "PostgreSQL (prod)"
                )
            )
            print("  python migrations/add_multi_set_fields.py downgrade    # Rollback")
            sys.exit(1)
    else:
        # Default: SQLite migration
        upgrade_sqlite()

    print()
    print("=" * 60)
