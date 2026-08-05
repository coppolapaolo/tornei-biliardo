"""Database migration: Add waitlist_reason field to Inscription.

Date: 2026-01-14

This migration adds the waitlist_reason field to track why an inscription
is on the waiting list:

- CAPACITY: max_participants exceeded (standard waitlist)
- PARITY: odd_number_policy="no" and player count became odd

Tables Modified:
- inscription

Backward Compatibility:
- Default is NULL (existing waitlist entries remain unchanged)
- Existing waitlist entries with reason=NULL are treated as CAPACITY
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
        # Check if column already exists
        cursor.execute("PRAGMA table_info(inscription)")
        cols = {row[1] for row in cursor.fetchall()}

        # Add waitlist_reason to inscription table
        if "waitlist_reason" not in cols:
            print("   Adding waitlist_reason to 'inscription' table...")
            cursor.execute("""
                ALTER TABLE inscription
                ADD COLUMN waitlist_reason VARCHAR(20) DEFAULT NULL
            """)
            print("   ✓ inscription.waitlist_reason added")
        else:
            print("   ⏭️  inscription.waitlist_reason already exists")

        conn.commit()
        print("✅ Migration completed successfully!")

        # Verify migration
        print("\n🔍 Verifying migration...")

        cursor.execute("PRAGMA table_info(inscription)")
        cols = {row[1] for row in cursor.fetchall()}

        if "waitlist_reason" in cols:
            print("   ✓ inscription.waitlist_reason present")
        else:
            print("   ✗ inscription.waitlist_reason MISSING")

        # Show sample data
        cursor.execute("""
            SELECT id, user_id, gara_id, is_waitlist, waitlist_reason
            FROM inscription
            WHERE is_waitlist = 1
            LIMIT 3
        """)
        rows = cursor.fetchall()
        if rows:
            print("\n📊 Sample waitlist inscriptions:")
            for row in rows:
                print(
                    f"   Inscription {row[0]} (user={row[1]}, gara={row[2]}): "
                    f"reason={row[4] or 'NULL'}"
                )
        else:
            print("\n📊 No waitlist inscriptions found")

    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            print(f"   ⏭️  Column already exists, skipping")
            conn.commit()
        else:
            conn.rollback()
            print(f"❌ Migration failed: {e}")
            raise
    finally:
        conn.close()


def upgrade_postgresql(connection_string: str) -> None:
    """Run migration for PostgreSQL (production)."""
    try:
        import psycopg2
    except ImportError:
        print("❌ psycopg2 not installed. Run: pip install psycopg2-binary")
        return

    conn = psycopg2.connect(connection_string)
    cursor = conn.cursor()

    print("🔧 Migrating PostgreSQL database")

    try:
        # Add waitlist_reason to inscription table
        print("   Adding waitlist_reason to 'inscription' table...")
        cursor.execute("""
            ALTER TABLE inscription
            ADD COLUMN IF NOT EXISTS waitlist_reason VARCHAR(20) DEFAULT NULL
        """)

        conn.commit()
        print("✅ Migration completed successfully!")

    except Exception as e:
        conn.rollback()
        print(f"❌ Migration failed: {e}")
        raise
    finally:
        conn.close()


def downgrade_sqlite(db_path: str = "instance/billiard_campionato.db") -> None:
    """Rollback migration for SQLite."""
    print("⚠️  SQLite does not support DROP COLUMN easily.")
    print("   To rollback, restore from backup or recreate tables.")


def downgrade_postgresql(connection_string: str) -> None:
    """Rollback migration for PostgreSQL."""
    try:
        import psycopg2
    except ImportError:
        print("❌ psycopg2 not installed")
        return

    conn = psycopg2.connect(connection_string)
    cursor = conn.cursor()

    print("🔧 Rolling back PostgreSQL migration")

    try:
        cursor.execute("ALTER TABLE inscription DROP COLUMN IF EXISTS waitlist_reason")

        conn.commit()
        print("✅ Rollback completed successfully!")

    except Exception as e:
        conn.rollback()
        print(f"❌ Rollback failed: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    import os

    db_url = os.environ.get("DATABASE_URL")

    if db_url and db_url.startswith("postgres"):
        upgrade_postgresql(db_url)
    else:
        upgrade_sqlite()
