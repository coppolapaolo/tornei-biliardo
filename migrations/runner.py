"""Migration runner with tracking.

Executes only pending migrations and records them in migrations_history table.

Usage:
    python migrations/runner.py                    # Run pending migrations
    python migrations/runner.py --status           # Show migration status
    python migrations/runner.py --mark-all-applied # Mark all as applied (for existing DBs)
"""

import sqlite3
import importlib.util
import sys
from pathlib import Path
from datetime import datetime


def get_db_path() -> str:
    """Get database path from environment or default."""
    import os
    return os.environ.get("DATABASE_PATH", "instance/billiard_campionato.db")


def ensure_migrations_table(conn: sqlite3.Connection) -> None:
    """Create migrations_history table if not exists."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS migrations_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            migration_name TEXT UNIQUE NOT NULL,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()


def get_applied_migrations(conn: sqlite3.Connection) -> set:
    """Get set of already applied migration names."""
    cursor = conn.execute("SELECT migration_name FROM migrations_history")
    return {row[0] for row in cursor.fetchall()}


def get_migration_files() -> list:
    """Get all migration files sorted by name."""
    migrations_dir = Path(__file__).parent
    files = sorted(migrations_dir.glob("*.py"))
    # Exclude runner.py and __init__.py
    excluded = {"runner.py", "__init__.py"}
    return [f for f in files if f.name not in excluded]


def run_migration(migration_path: Path, db_path: str) -> bool:
    """Run a single migration file.

    Returns True if successful, False otherwise.
    """
    print(f"  Running: {migration_path.name}")

    try:
        # Load migration module
        spec = importlib.util.spec_from_file_location(
            migration_path.stem,
            migration_path
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # Run SQLite upgrade
        if hasattr(module, 'upgrade_sqlite'):
            module.upgrade_sqlite(db_path)
            return True
        else:
            print(f"    Warning: No upgrade_sqlite function found")
            return False

    except Exception as e:
        error_msg = str(e).lower()
        # Handle "already exists" errors as success
        if "duplicate column" in error_msg or "already exists" in error_msg:
            print(f"    Already applied (column exists)")
            return True
        print(f"    Error: {e}")
        return False


def record_migration(conn: sqlite3.Connection, migration_name: str) -> None:
    """Record a migration as applied."""
    conn.execute(
        "INSERT OR IGNORE INTO migrations_history (migration_name, applied_at) VALUES (?, ?)",
        (migration_name, datetime.utcnow().isoformat())
    )
    conn.commit()


def show_status(conn: sqlite3.Connection) -> None:
    """Show status of all migrations."""
    applied = get_applied_migrations(conn)
    all_migrations = get_migration_files()

    print("\nMigration Status:")
    print("-" * 50)

    for migration_file in all_migrations:
        name = migration_file.name
        status = "✓ Applied" if name in applied else "○ Pending"
        print(f"  {status}: {name}")

    print("-" * 50)
    print(f"Total: {len(all_migrations)} | Applied: {len(applied)} | Pending: {len(all_migrations) - len(applied)}")


def mark_all_applied(conn: sqlite3.Connection) -> None:
    """Mark all existing migrations as applied without running them.

    Useful for existing databases where migrations were run manually.
    """
    all_migrations = get_migration_files()
    applied = get_applied_migrations(conn)

    print("\nMarking all migrations as applied...")

    for migration_file in all_migrations:
        name = migration_file.name
        if name not in applied:
            record_migration(conn, name)
            print(f"  Marked: {name}")

    print("Done!")


def run_pending_migrations() -> int:
    """Run all pending migrations.

    Returns number of migrations run.
    """
    db_path = get_db_path()

    if not Path(db_path).exists():
        print(f"Database not found: {db_path}")
        print("Run application first to create database")
        return 0

    conn = sqlite3.connect(db_path)

    try:
        ensure_migrations_table(conn)
        applied = get_applied_migrations(conn)
        all_migrations = get_migration_files()

        pending = [m for m in all_migrations if m.name not in applied]

        if not pending:
            print("No pending migrations.")
            return 0

        print(f"\nRunning {len(pending)} pending migration(s)...")
        print("-" * 50)

        run_count = 0
        for migration_file in pending:
            success = run_migration(migration_file, db_path)
            if success:
                record_migration(conn, migration_file.name)
                run_count += 1

        print("-" * 50)
        print(f"Completed: {run_count}/{len(pending)} migrations")

        return run_count

    finally:
        conn.close()


if __name__ == "__main__":
    print("=" * 60)
    print("Migration Runner")
    print("=" * 60)

    db_path = get_db_path()
    print(f"Database: {db_path}")

    if len(sys.argv) > 1:
        if sys.argv[1] == "--status":
            conn = sqlite3.connect(db_path)
            ensure_migrations_table(conn)
            show_status(conn)
            conn.close()
        elif sys.argv[1] == "--mark-all-applied":
            conn = sqlite3.connect(db_path)
            ensure_migrations_table(conn)
            mark_all_applied(conn)
            conn.close()
        else:
            print(f"Unknown option: {sys.argv[1]}")
            print("\nUsage:")
            print("  python migrations/runner.py                    # Run pending")
            print("  python migrations/runner.py --status           # Show status")
            print("  python migrations/runner.py --mark-all-applied # Mark all applied")
            sys.exit(1)
    else:
        run_pending_migrations()
