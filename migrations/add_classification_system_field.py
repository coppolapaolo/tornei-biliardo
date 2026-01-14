"""Database migration: Add classification_system field to Gara and Campionato.

Date: 2026-01-14

This migration adds classification system configuration:

- gara.classification_system: RACK, WINS, or POSITION
- campionato.default_classification_system: Default for new gare

See docs/CLASSIFICATION_SYSTEM.md for details on each system:
- RACK: Orders by total racks won
- WINS: Orders by matches won, then rack differential
- POSITION: Orders by bracket position (elimination tournaments)

Tables Modified:
- gara
- campionato

Backward Compatibility:
- Default is "WINS" (most common for Amalfi/Random/Round-Robin strategies)
- Existing gare will use WINS, which matches current behavior
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
        # Check if columns already exist
        cursor.execute("PRAGMA table_info(gara)")
        gara_cols = {row[1] for row in cursor.fetchall()}

        cursor.execute("PRAGMA table_info(campionato)")
        campionato_cols = {row[1] for row in cursor.fetchall()}

        # Add classification_system to gara table
        if "classification_system" not in gara_cols:
            print("   Adding classification_system to 'gara' table...")
            cursor.execute("""
                ALTER TABLE gara
                ADD COLUMN classification_system VARCHAR(10) DEFAULT 'WINS' NOT NULL
            """)
            print("   ✓ gara.classification_system added")
        else:
            print("   ⏭️  gara.classification_system already exists")

        # Add default_classification_system to campionato table
        if "default_classification_system" not in campionato_cols:
            print("   Adding default_classification_system to 'campionato' table...")
            cursor.execute("""
                ALTER TABLE campionato
                ADD COLUMN default_classification_system VARCHAR(10) DEFAULT 'WINS' NOT NULL
            """)
            print("   ✓ campionato.default_classification_system added")
        else:
            print("   ⏭️  campionato.default_classification_system already exists")

        conn.commit()
        print("✅ Migration completed successfully!")

        # Verify migration
        print("\n🔍 Verifying migration...")

        cursor.execute("PRAGMA table_info(gara)")
        gara_cols = {row[1] for row in cursor.fetchall()}

        cursor.execute("PRAGMA table_info(campionato)")
        campionato_cols = {row[1] for row in cursor.fetchall()}

        if "classification_system" in gara_cols:
            print("   ✓ gara.classification_system present")
        else:
            print("   ✗ gara.classification_system MISSING")

        if "default_classification_system" in campionato_cols:
            print("   ✓ campionato.default_classification_system present")
        else:
            print("   ✗ campionato.default_classification_system MISSING")

        # Show sample data
        cursor.execute("SELECT id, name, classification_system FROM gara LIMIT 3")
        rows = cursor.fetchall()
        if rows:
            print("\n📊 Sample gara data:")
            for row in rows:
                print(f"   Gara {row[0]} ({row[1]}): {row[2]}")

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
        # Add classification_system to gara table
        print("   Adding classification_system to 'gara' table...")
        cursor.execute("""
            ALTER TABLE gara
            ADD COLUMN IF NOT EXISTS classification_system VARCHAR(10) DEFAULT 'WINS' NOT NULL
        """)

        # Add default_classification_system to campionato table
        print("   Adding default_classification_system to 'campionato' table...")
        cursor.execute("""
            ALTER TABLE campionato
            ADD COLUMN IF NOT EXISTS default_classification_system VARCHAR(10) DEFAULT 'WINS' NOT NULL
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
        cursor.execute("ALTER TABLE gara DROP COLUMN IF EXISTS classification_system")
        cursor.execute("ALTER TABLE campionato DROP COLUMN IF EXISTS default_classification_system")

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
