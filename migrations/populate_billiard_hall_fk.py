"""Database migration: Populate billiard_hall_id FK from location strings.

Sprint 10: Location/Venue Refactoring (P1)
Date: 2025-12-30

This migration populates the billiard_hall_id FK field for existing records
based on their location string field. It matches location strings to
BilliardHall.name and sets the FK where a match is found.

Tables Updated:
- gara: Match location → billiard_hall_id
- match_proposal: Match location → billiard_hall_id
- individual_match: Match location → billiard_hall_id

Notes:
- Only updates records where billiard_hall_id is NULL
- Case-sensitive match on BilliardHall.name
- Creates missing BilliardHall entries for unmatched locations (optional)
"""

import sqlite3
from pathlib import Path
from typing import Dict, List, Tuple


def get_venue_mapping(cursor) -> Dict[str, int]:
    """Get mapping of venue names to IDs."""
    cursor.execute("SELECT id, name FROM billiard_hall")
    return {row[1]: row[0] for row in cursor.fetchall()}


def populate_fk_sqlite(
    db_path: str = "instance/billiard_campionato.db",
    create_missing_venues: bool = False,
) -> None:
    """Populate billiard_hall_id FK for SQLite (development).

    Args:
        db_path: Path to SQLite database
        create_missing_venues: If True, create BilliardHall entries for
                              unmatched locations (not recommended)
    """
    db_file = Path(db_path)
    if not db_file.exists():
        print(f"❌ Database not found: {db_path}")
        print("   Run application first to create database")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print(f"🔧 Populating billiard_hall_id FK: {db_path}")
    print()

    # Get existing venue mapping
    venue_map = get_venue_mapping(cursor)
    print(f"📍 Found {len(venue_map)} existing venues in BilliardHall table")

    tables_to_update = ["gara", "match_proposal", "individual_match"]
    total_updated = 0
    unmatched_locations: List[Tuple[str, str, int]] = []  # (table, location, count)

    for table in tables_to_update:
        print(f"\n📊 Processing '{table}' table...")

        # Check if table has both columns
        cursor.execute(f"PRAGMA table_info({table})")
        columns = {row[1] for row in cursor.fetchall()}

        if "location" not in columns:
            print(f"   ⚠️  Skipping: 'location' column not found")
            continue

        if "billiard_hall_id" not in columns:
            print(f"   ⚠️  Skipping: 'billiard_hall_id' column not found")
            print("   Run add_billiard_hall_fk.py first!")
            continue

        # Get unique locations that need FK population
        cursor.execute(f"""
            SELECT location, COUNT(*) as cnt
            FROM {table}
            WHERE location IS NOT NULL
              AND location != ''
              AND billiard_hall_id IS NULL
            GROUP BY location
        """)
        locations_to_process = cursor.fetchall()

        if not locations_to_process:
            print(f"   ✓ No records to update (all already have FK set)")
            continue

        matched = 0
        unmatched = 0

        for location, count in locations_to_process:
            if location in venue_map:
                # Match found - update FK
                venue_id = venue_map[location]
                cursor.execute(
                    f"""
                    UPDATE {table}
                    SET billiard_hall_id = ?
                    WHERE location = ?
                      AND billiard_hall_id IS NULL
                    """,
                    (venue_id, location),
                )
                matched += cursor.rowcount
                print(
                    f"   ✓ Matched '{location}' → ID {venue_id} ({cursor.rowcount} records)"
                )
            else:
                unmatched += count
                unmatched_locations.append((table, location, count))
                print(f"   ✗ No match for '{location}' ({count} records)")

        print(f"   → Updated: {matched}, Unmatched: {unmatched}")
        total_updated += matched

    conn.commit()

    # Summary
    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total records updated: {total_updated}")

    if unmatched_locations:
        print(f"\n⚠️  Unmatched locations ({len(unmatched_locations)} unique):")
        for table, location, count in unmatched_locations:
            print(f"   - {table}: '{location}' ({count} records)")
        print()
        print("To fix unmatched locations:")
        print("1. Create BilliardHall entry with matching name, OR")
        print("2. Update location string to match existing venue, OR")
        print("3. Leave as-is (FK will be NULL, fallback to string lookup)")

    conn.close()
    print()
    print("✅ Migration completed!")


def populate_fk_postgresql(connection_string: str) -> None:
    """Populate billiard_hall_id FK for PostgreSQL (production).

    Args:
        connection_string: PostgreSQL connection string
    """
    try:
        import psycopg2
    except ImportError:
        print("❌ psycopg2 not installed. Install with: pip install psycopg2-binary")
        return

    print("🔧 Populating billiard_hall_id FK (PostgreSQL)...")

    conn = psycopg2.connect(connection_string)
    cursor = conn.cursor()

    # Get existing venue mapping
    cursor.execute("SELECT id, name FROM billiard_hall")
    venue_map = {row[1]: row[0] for row in cursor.fetchall()}
    print(f"📍 Found {len(venue_map)} existing venues")

    tables = ["gara", "match_proposal", "individual_match"]
    total_updated = 0

    try:
        for table in tables:
            # Update records using subquery
            cursor.execute(f"""
                UPDATE {table}
                SET billiard_hall_id = bh.id
                FROM billiard_hall bh
                WHERE {table}.location = bh.name
                  AND {table}.billiard_hall_id IS NULL
            """)
            updated = cursor.rowcount
            total_updated += updated
            print(f"   {table}: {updated} records updated")

        conn.commit()
        print(f"\n✅ Total records updated: {total_updated}")

    except Exception as e:
        print(f"❌ Migration failed: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


def verify_migration(db_path: str = "instance/billiard_campionato.db") -> None:
    """Verify FK population status."""
    db_file = Path(db_path)
    if not db_file.exists():
        print(f"❌ Database not found: {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print("🔍 Verifying FK population status...")
    print()

    tables = ["gara", "match_proposal", "individual_match"]

    for table in tables:
        # Check if table has both columns
        cursor.execute(f"PRAGMA table_info({table})")
        columns = {row[1] for row in cursor.fetchall()}

        if "billiard_hall_id" not in columns:
            print(f"{table}: billiard_hall_id column not found")
            continue

        cursor.execute(f"""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN billiard_hall_id IS NOT NULL THEN 1 ELSE 0 END) as with_fk,
                SUM(CASE WHEN location IS NOT NULL AND location != '' THEN 1 ELSE 0 END) as with_location
            FROM {table}
        """)
        total, with_fk, with_location = cursor.fetchone()

        fk_pct = (with_fk / total * 100) if total > 0 else 0
        print(f"{table}:")
        print(f"   Total records: {total}")
        print(f"   With FK: {with_fk} ({fk_pct:.1f}%)")
        print(f"   With location string: {with_location}")
        print()

    conn.close()


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db") -> None:
    """Standard interface for migration runner."""
    populate_fk_sqlite(db_path)


if __name__ == "__main__":
    import sys
    import os

    print("=" * 60)
    print("Populate BilliardHall FK Migration (Sprint 10 - P1)")
    print("=" * 60)
    print()

    if len(sys.argv) > 1:
        if sys.argv[1] == "postgresql":
            # PostgreSQL migration
            db_url = os.environ.get("DATABASE_URL")
            if not db_url:
                print("❌ DATABASE_URL environment variable not set")
                sys.exit(1)
            populate_fk_postgresql(db_url)
        elif sys.argv[1] == "verify":
            # Verify status
            verify_migration()
        else:
            print(f"❌ Unknown command: {sys.argv[1]}")
            print("\nUsage:")
            print(
                "  python migrations/populate_billiard_hall_fk.py           # SQLite (dev)"
            )
            print(
                "  python migrations/populate_billiard_hall_fk.py postgresql # PostgreSQL (prod)"
            )
            print(
                "  python migrations/populate_billiard_hall_fk.py verify     # Check status"
            )
            sys.exit(1)
    else:
        # Default: SQLite migration
        populate_fk_sqlite()

    print()
    print("=" * 60)
