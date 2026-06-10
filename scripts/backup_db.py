#!/usr/bin/env python3
"""SQLite database backup script with rotation.

Creates a consistent backup using sqlite3's backup API (no lock required),
saves timestamped copies, and rotates old backups.

Setup on PythonAnywhere:
    Tasks → Add scheduled task (daily)
    Command: /home/paolocoppola/mysite/venv/bin/python /home/paolocoppola/mysite/scripts/backup_db.py

Or run manually:
    python scripts/backup_db.py
"""

import sqlite3
import sys
from datetime import datetime
from pathlib import Path

# Configuration
PROJECT_DIR = Path(__file__).parent.parent
DB_PATH = PROJECT_DIR / "instance" / "billiard_campionato.db"
BACKUP_DIR = PROJECT_DIR / "backups"
MAX_BACKUPS = 7


def create_backup(db_path: Path = DB_PATH, backup_dir: Path = BACKUP_DIR) -> Path:
    """Create a consistent SQLite backup using the backup API.

    Returns the path to the created backup file.
    Raises FileNotFoundError if the source DB doesn't exist.
    """
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"backup_{timestamp}.db"

    source = sqlite3.connect(str(db_path))
    try:
        dest = sqlite3.connect(str(backup_path))
        try:
            source.backup(dest)
        finally:
            dest.close()
    finally:
        source.close()

    return backup_path


def rotate_backups(
    backup_dir: Path = BACKUP_DIR, max_backups: int = MAX_BACKUPS
) -> int:
    """Remove oldest backups keeping only max_backups most recent.

    Returns the number of deleted backup files.
    """
    if not backup_dir.exists():
        return 0

    backups = sorted(backup_dir.glob("backup_*.db"), key=lambda p: p.name)
    to_delete = backups[:-max_backups] if len(backups) > max_backups else []

    for old_backup in to_delete:
        old_backup.unlink()

    return len(to_delete)


def main() -> int:
    """Run backup and rotation. Returns 0 on success, 1 on failure."""
    print(f"Database backup script")
    print(f"Source: {DB_PATH}")
    print(f"Backup dir: {BACKUP_DIR}")
    print()

    try:
        backup_path = create_backup()
        size_mb = backup_path.stat().st_size / (1024 * 1024)
        print(f"Backup created: {backup_path.name} ({size_mb:.1f} MB)")

        deleted = rotate_backups()
        if deleted:
            print(f"Rotation: removed {deleted} old backup(s)")

        remaining = len(list(BACKUP_DIR.glob("backup_*.db")))
        print(f"Total backups: {remaining}/{MAX_BACKUPS}")
        print("\nBackup completed successfully.")
        return 0

    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
