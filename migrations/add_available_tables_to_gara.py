"""Database migration: Add available_tables field to Gara.

Feature: Gara-specific table configuration
Date: 2025-12-27

This migration adds a column to support gara-specific table assignment:
- available_tables: JSON string storing list of specific table names

Tables Modified:
- gara

Backward Compatibility:
- Field is nullable, NULL means use venue's tables
- Existing records continue working with venue-based assignment
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
        # Add available_tables field to gara table
        print("   Adding available_tables field to 'gara' table...")

        cursor.execute("""
            ALTER TABLE gara
            ADD COLUMN available_tables TEXT
        """)

        conn.commit()
        print("Migration completed successfully!")

        # Verify migration
        print("\nVerifying migration...")

        cursor.execute("PRAGMA table_info(gara)")
        gara_cols = {row[1] for row in cursor.fetchall()}

        if "available_tables" in gara_cols:
            print("   gara table: available_tables field present")
        else:
            print("   gara table: available_tables field MISSING")

    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            print(f"Migration already applied: {e}")
            print("   Skipping...")
        else:
            print(f"Migration failed: {e}")
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
        print("psycopg2 not installed. Install with: pip install psycopg2-binary")
        return

    print("Migrating PostgreSQL database...")

    conn = psycopg2.connect(connection_string)
    cursor = conn.cursor()

    try:
        # Add available_tables field to gara table
        print("   Adding available_tables field to 'gara' table...")

        cursor.execute("""
            ALTER TABLE gara
            ADD COLUMN IF NOT EXISTS available_tables TEXT
        """)

        conn.commit()
        print("PostgreSQL migration completed successfully!")

    except Exception as e:
        print(f"PostgreSQL migration failed: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    import sys
    import os

    print("=" * 60)
    print("Gara Available Tables Migration")
    print("=" * 60)
    print()

    if len(sys.argv) > 1:
        if sys.argv[1] == "postgresql":
            # PostgreSQL migration
            db_url = os.environ.get("DATABASE_URL")
            if not db_url:
                print("DATABASE_URL environment variable not set")
                sys.exit(1)
            upgrade_postgresql(db_url)
        else:
            print(f"Unknown command: {sys.argv[1]}")
            print("\nUsage:")
            print(
                (
                    "  python migrations/add_available_tables_to_gara.py              "
                    "# SQLite (dev)"
                )
            )
            print(
                (
                    "  python migrations/add_available_tables_to_gara.py postgresql   "
                    "# PostgreSQL (prod)"
                )
            )
            sys.exit(1)
    else:
        # Default: SQLite migration
        upgrade_sqlite()

    print()
    print("=" * 60)
