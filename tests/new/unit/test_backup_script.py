"""Tests for the SQLite backup script rotation logic."""

import sqlite3

import pytest

from scripts.backup_db import create_backup, rotate_backups


@pytest.fixture
def backup_env(tmp_path):
    """Create a temporary DB and backup directory."""
    db_path = tmp_path / "test.db"
    # Create a real SQLite database with a table
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("INSERT INTO test VALUES (1, 'hello')")
    conn.commit()
    conn.close()

    backup_dir = tmp_path / "backups"
    return db_path, backup_dir


def test_create_backup_creates_file(backup_env):
    db_path, backup_dir = backup_env
    result = create_backup(db_path, backup_dir)

    assert result.exists()
    assert result.suffix == ".db"
    assert result.parent == backup_dir


def test_create_backup_is_valid_sqlite(backup_env):
    db_path, backup_dir = backup_env
    result = create_backup(db_path, backup_dir)

    conn = sqlite3.connect(str(result))
    rows = conn.execute("SELECT * FROM test").fetchall()
    conn.close()

    assert rows == [(1, "hello")]


def test_create_backup_missing_db(tmp_path):
    with pytest.raises(FileNotFoundError):
        create_backup(tmp_path / "nonexistent.db", tmp_path / "backups")


def test_rotate_keeps_max_backups(tmp_path):
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()

    # Create 10 backup files with different timestamps
    for i in range(10):
        (backup_dir / f"backup_2026020{i}_120000.db").touch()

    deleted = rotate_backups(backup_dir, max_backups=7)

    assert deleted == 3
    remaining = list(backup_dir.glob("backup_*.db"))
    assert len(remaining) == 7


def test_rotate_no_op_when_under_limit(tmp_path):
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()

    for i in range(3):
        (backup_dir / f"backup_2026020{i}_120000.db").touch()

    deleted = rotate_backups(backup_dir, max_backups=7)

    assert deleted == 0
    assert len(list(backup_dir.glob("backup_*.db"))) == 3


def test_rotate_nonexistent_dir(tmp_path):
    deleted = rotate_backups(tmp_path / "nonexistent", max_backups=7)
    assert deleted == 0


def test_rotate_removes_oldest(tmp_path):
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()

    files = [f"backup_2026020{i}_120000.db" for i in range(5)]
    for f in files:
        (backup_dir / f).touch()

    rotate_backups(backup_dir, max_backups=3)

    remaining = sorted(p.name for p in backup_dir.glob("backup_*.db"))
    # Should keep the 3 newest (sorted alphabetically = chronologically)
    assert remaining == [
        "backup_20260202_120000.db",
        "backup_20260203_120000.db",
        "backup_20260204_120000.db",
    ]
