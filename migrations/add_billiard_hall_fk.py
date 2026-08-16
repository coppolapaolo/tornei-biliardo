"""Database migration: Add billiard_hall_id FK to Gara, MatchProposal, IndividualMatch.

Sprint 10: Location/Venue Refactoring (P1)
Date: 2025-12-30

This migration adds billiard_hall_id foreign key to:
- gara: References BilliardHall for competition venue
- match_proposal: References BilliardHall for venue-based proposals
- individual_match: References BilliardHall for venue-based matches

Tables Modified:
- gara (add billiard_hall_id FK)
- match_proposal (add billiard_hall_id FK)
- individual_match (add billiard_hall_id FK)

Backward Compatibility:
- New FK fields are nullable (existing records continue to work)
- Legacy 'location' string field is kept for backward compatibility
- Models have location_display property that prefers billiard_hall.name
- venue property uses FK first, then falls back to name lookup

Note: PlayerAvailability is deprecated in favor of UserLocationAvailability
(from models/location/models.py) which already uses FK correctly.
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

    tables_to_migrate = ["gara", "match_proposal", "individual_match"]
    migrated = []
    skipped = []

    for table in tables_to_migrate:
        try:
            print(f"   Adding billiard_hall_id to '{table}' table...")
            cursor.execute(f"""
                ALTER TABLE {table}
                ADD COLUMN billiard_hall_id INTEGER REFERENCES billiard_hall(id)
                    ON DELETE SET NULL
            """)
            migrated.append(table)
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                skipped.append(table)
            else:
                print(f"❌ Migration failed for {table}: {e}")
                conn.rollback()
                raise

    conn.commit()

    if migrated:
        print(f"✅ Migration completed for: {', '.join(migrated)}")
    if skipped:
        print(f"⚠️  Already migrated (skipped): {', '.join(skipped)}")

    # Verify migration
    print("\n🔍 Verifying migration...")

    for table in tables_to_migrate:
        cursor.execute(f"PRAGMA table_info({table})")
        cols = {row[1] for row in cursor.fetchall()}

        if "billiard_hall_id" in cols:
            print(f"   ✓ {table} table: billiard_hall_id present")
        else:
            print(f"   ✗ {table} table: billiard_hall_id missing")

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

    tables_to_migrate = ["gara", "match_proposal", "individual_match"]

    try:
        for table in tables_to_migrate:
            print(f"   Adding billiard_hall_id to '{table}' table...")
            cursor.execute(f"""
                ALTER TABLE {table}
                ADD COLUMN IF NOT EXISTS billiard_hall_id INTEGER
                    REFERENCES billiard_hall(id) ON DELETE SET NULL
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
    print("   2. Recreate tables without billiard_hall_id column")
    print("   3. Copy data from backup")


if __name__ == "__main__":
    import sys
    import os

    print("=" * 60)
    print("Add BilliardHall FK Migration (Sprint 10 - P1)")
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
                    "  python migrations/add_billiard_hall_fk.py              # SQLite "
                    "(dev)"
                )
            )
            print(
                (
                    "  python migrations/add_billiard_hall_fk.py postgresql   # "
                    "PostgreSQL (prod)"
                )
            )
            print("  python migrations/add_billiard_hall_fk.py downgrade    # Rollback")
            sys.exit(1)
    else:
        # Default: SQLite migration
        upgrade_sqlite()

    print()
    print("=" * 60)
