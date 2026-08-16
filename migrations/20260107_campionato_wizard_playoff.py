"""Database migration: Campionato wizard and playoff system improvements.

ADR-0001: Wizard Creazione Campionato Multi-Step e Sistema Playoff
Date: 2026-01-07

This migration adds:
1. Campionato: New fields for wizard and gare defaults
2. Gara: playoff_config_id FK for playoff garas
3. PlayoffConfiguration: positions_from/to for simplified criteria
4. PlayoffQualification: invited_at/expires_at for batch invitations

Tables Modified:
- campionato (add default fields, migrate without_x)
- gara (add playoff_config_id FK)
- playoff_configuration (add positions_from, positions_to)
- playoff_qualification (add invited_at, expires_at)

Backward Compatibility:
- Deprecated fields kept for compatibility (without_x, final_playoffs, scoring_policy)
- Data migration from without_x to default_odd_policy
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
    print()

    # =========================================================================
    # 1. CAMPIONATO TABLE - New columns
    # =========================================================================
    print("📋 Migrating 'campionato' table...")

    campionato_columns = [
        ("planned_gare_count", "INTEGER DEFAULT 10"),
        ("default_venue_id", "INTEGER REFERENCES billiard_hall(id) ON DELETE SET NULL"),
        ("default_entry_fee", "REAL"),
        ("default_rounds_count", "INTEGER DEFAULT 3"),
        ("default_odd_policy", "VARCHAR(30) DEFAULT 'bye'"),
        ("default_anti_rematch", "BOOLEAN DEFAULT 1"),
    ]

    for col_name, col_def in campionato_columns:
        try:
            cursor.execute(f"ALTER TABLE campionato ADD COLUMN {col_name} {col_def}")
            print(f"   ✓ Added column: {col_name}")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                print(f"   ⚠ Column already exists: {col_name}")
            else:
                raise

    # Migrate without_x → default_odd_policy
    print("   Migrating without_x → default_odd_policy...")
    try:
        cursor.execute("""
            UPDATE campionato
            SET default_odd_policy = CASE
                WHEN without_x = 1 THEN 'trio'
                ELSE 'bye'
            END
            WHERE default_odd_policy IS NULL OR default_odd_policy = ''
        """)
        print(f"   ✓ Migrated {cursor.rowcount} records")
    except sqlite3.OperationalError as e:
        print(f"   ⚠ Migration skipped: {e}")

    print()

    # =========================================================================
    # 2. GARA TABLE - Add playoff_config_id
    # =========================================================================
    print("📋 Migrating 'gara' table...")

    try:
        cursor.execute("""
            ALTER TABLE gara
            ADD COLUMN playoff_config_id INTEGER REFERENCES playoff_configuration(id)
                ON DELETE SET NULL
        """)
        print("   ✓ Added column: playoff_config_id")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            print("   ⚠ Column already exists: playoff_config_id")
        else:
            raise

    print()

    # =========================================================================
    # 3. PLAYOFF_CONFIGURATION TABLE - Add position columns
    # =========================================================================
    print("📋 Migrating 'playoff_configuration' table...")

    # Check if table exists
    cursor.execute(
        (
            "SELECT name FROM sqlite_master WHERE type='table' AND "
            "name='playoff_configuration'"
        )
    )
    if cursor.fetchone():
        playoff_config_columns = [
            ("positions_from", "INTEGER"),
            ("positions_to", "INTEGER"),
        ]

        for col_name, col_def in playoff_config_columns:
            try:
                cursor.execute(
                    f"ALTER TABLE playoff_configuration ADD COLUMN {col_name} {col_def}"
                )
                print(f"   ✓ Added column: {col_name}")
            except sqlite3.OperationalError as e:
                if "duplicate column name" in str(e).lower():
                    print(f"   ⚠ Column already exists: {col_name}")
                else:
                    raise
    else:
        print("   ⚠ Table doesn't exist yet (will be created by SQLAlchemy)")

    print()

    # =========================================================================
    # 4. PLAYOFF_QUALIFICATION TABLE - Add invitation timing columns
    # =========================================================================
    print("📋 Migrating 'playoff_qualification' table...")

    cursor.execute(
        (
            "SELECT name FROM sqlite_master WHERE type='table' AND "
            "name='playoff_qualification'"
        )
    )
    if cursor.fetchone():
        playoff_qual_columns = [
            ("invited_at", "DATETIME"),
            ("expires_at", "DATETIME"),
        ]

        for col_name, col_def in playoff_qual_columns:
            try:
                cursor.execute(
                    f"ALTER TABLE playoff_qualification ADD COLUMN {col_name} {col_def}"
                )
                print(f"   ✓ Added column: {col_name}")
            except sqlite3.OperationalError as e:
                if "duplicate column name" in str(e).lower():
                    print(f"   ⚠ Column already exists: {col_name}")
                else:
                    raise

        # Migrate notified_at → invited_at
        print("   Migrating notified_at → invited_at...")
        try:
            cursor.execute("""
                UPDATE playoff_qualification
                SET invited_at = notified_at
                WHERE invited_at IS NULL AND notified_at IS NOT NULL
            """)
            print(f"   ✓ Migrated {cursor.rowcount} records")
        except sqlite3.OperationalError as e:
            print(f"   ⚠ Migration skipped: {e}")
    else:
        print("   ⚠ Table doesn't exist yet (will be created by SQLAlchemy)")

    print()

    # =========================================================================
    # COMMIT AND VERIFY
    # =========================================================================
    conn.commit()
    print("✅ Migration committed successfully!")
    print()

    # Verification
    print("🔍 Verifying migration...")

    # Verify campionato columns
    cursor.execute("PRAGMA table_info(campionato)")
    campionato_cols = {row[1] for row in cursor.fetchall()}
    expected_campionato = [
        "planned_gare_count",
        "default_venue_id",
        "default_entry_fee",
        "default_rounds_count",
        "default_odd_policy",
        "default_anti_rematch",
    ]
    for col in expected_campionato:
        status = "✓" if col in campionato_cols else "✗"
        print(f"   {status} campionato.{col}")

    # Verify gara columns
    cursor.execute("PRAGMA table_info(gara)")
    gara_cols = {row[1] for row in cursor.fetchall()}
    status = "✓" if "playoff_config_id" in gara_cols else "✗"
    print(f"   {status} gara.playoff_config_id")

    conn.close()


def upgrade_postgresql(connection_string: str) -> None:
    """Run migration for PostgreSQL (production)."""
    try:
        import psycopg2
    except ImportError:
        print("❌ psycopg2 not installed. Install with: pip install psycopg2-binary")
        return

    print("🔧 Migrating PostgreSQL database...")

    conn = psycopg2.connect(connection_string)
    cursor = conn.cursor()

    try:
        # Campionato columns
        print("📋 Migrating 'campionato' table...")
        cursor.execute("""
            ALTER TABLE campionato
            ADD COLUMN IF NOT EXISTS planned_gare_count INTEGER DEFAULT 10,
            ADD COLUMN IF NOT EXISTS default_venue_id INTEGER
                REFERENCES billiard_hall(id) ON DELETE SET NULL,
            ADD COLUMN IF NOT EXISTS default_entry_fee REAL,
            ADD COLUMN IF NOT EXISTS default_rounds_count INTEGER DEFAULT 3,
            ADD COLUMN IF NOT EXISTS default_odd_policy VARCHAR(30) DEFAULT 'bye',
            ADD COLUMN IF NOT EXISTS default_anti_rematch BOOLEAN DEFAULT TRUE
        """)

        # Migrate without_x
        cursor.execute("""
            UPDATE campionato
            SET default_odd_policy = CASE
                WHEN without_x = TRUE THEN 'trio'
                ELSE 'bye'
            END
            WHERE default_odd_policy IS NULL OR default_odd_policy = ''
        """)
        print("   ✓ Campionato columns added and data migrated")

        # Gara column
        print("📋 Migrating 'gara' table...")
        cursor.execute("""
            ALTER TABLE gara
            ADD COLUMN IF NOT EXISTS playoff_config_id INTEGER
                REFERENCES playoff_configuration(id) ON DELETE SET NULL
        """)
        print("   ✓ Gara column added")

        # PlayoffConfiguration columns
        print("📋 Migrating 'playoff_configuration' table...")
        cursor.execute("""
            ALTER TABLE playoff_configuration
            ADD COLUMN IF NOT EXISTS positions_from INTEGER,
            ADD COLUMN IF NOT EXISTS positions_to INTEGER
        """)
        print("   ✓ PlayoffConfiguration columns added")

        # PlayoffQualification columns
        print("📋 Migrating 'playoff_qualification' table...")
        cursor.execute("""
            ALTER TABLE playoff_qualification
            ADD COLUMN IF NOT EXISTS invited_at TIMESTAMP,
            ADD COLUMN IF NOT EXISTS expires_at TIMESTAMP
        """)

        # Migrate notified_at → invited_at
        cursor.execute("""
            UPDATE playoff_qualification
            SET invited_at = notified_at
            WHERE invited_at IS NULL AND notified_at IS NOT NULL
        """)
        print("   ✓ PlayoffQualification columns added and data migrated")

        conn.commit()
        print()
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
    """
    print("⚠️  SQLite downgrade requires manual intervention")
    print("   (SQLite < 3.35.0 doesn't support DROP COLUMN)")
    print()
    print("   New columns added by this migration:")
    print("   - campionato: planned_gare_count, default_venue_id, default_entry_fee,")
    print(
        (
            "                 default_rounds_count, default_odd_policy, "
            "default_anti_rematch"
        )
    )
    print("   - gara: playoff_config_id")
    print("   - playoff_configuration: positions_from, positions_to")
    print("   - playoff_qualification: invited_at, expires_at")


if __name__ == "__main__":
    import sys
    import os

    print("=" * 70)
    print("ADR-0001: Campionato Wizard and Playoff System Migration")
    print("=" * 70)
    print()

    if len(sys.argv) > 1:
        if sys.argv[1] == "postgresql":
            db_url = os.environ.get("DATABASE_URL")
            if not db_url:
                print("❌ DATABASE_URL environment variable not set")
                sys.exit(1)
            upgrade_postgresql(db_url)
        elif sys.argv[1] == "downgrade":
            downgrade_sqlite()
        else:
            print(f"❌ Unknown command: {sys.argv[1]}")
            print()
            print("Usage:")
            print(
                (
                    "  python migrations/20260107_campionato_wizard_playoff.py         "
                    "     # SQLite (dev)"
                )
            )
            print(
                (
                    "  python migrations/20260107_campionato_wizard_playoff.py "
                    "postgresql   # PostgreSQL (prod)"
                )
            )
            print(
                (
                    "  python migrations/20260107_campionato_wizard_playoff.py "
                    "downgrade    # Rollback info"
                )
            )
            sys.exit(1)
    else:
        upgrade_sqlite()

    print()
    print("=" * 70)
