"""Regression test for migration 20260419_backfill_walkover_trio_matchup.

Verifies the backfill targets only walkover trios with NULL matchup,
correctly maps player1/2/3 → current/waiting, and is idempotent.
"""

from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

import pytest

MIGRATION_PATH = (
    Path(__file__).resolve().parents[3]
    / "migrations"
    / "20260419_backfill_walkover_trio_matchup.py"
)


def _load_migration_module():
    spec = importlib.util.spec_from_file_location(
        "backfill_walkover_trio_matchup", MIGRATION_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _setup_schema(conn: sqlite3.Connection) -> None:
    """Minimal trio_match + trio_rack schema sufficient for the migration."""
    conn.executescript("""
        CREATE TABLE trio_match (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player1_id INTEGER NOT NULL,
            player2_id INTEGER NOT NULL,
            player3_id INTEGER NOT NULL,
            current_player1_id INTEGER,
            current_player2_id INTEGER,
            waiting_player_id INTEGER,
            is_completed INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE trio_rack (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trio_match_id INTEGER NOT NULL,
            is_deleted INTEGER NOT NULL DEFAULT 0
        );
        """)
    conn.commit()


def _insert_trio(
    conn: sqlite3.Connection,
    *,
    p1: int,
    p2: int,
    p3: int,
    is_completed: int = 1,
    active_racks: int = 0,
    deleted_racks: int = 0,
    current_p1: int | None = None,
    current_p2: int | None = None,
    waiting: int | None = None,
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO trio_match (
            player1_id, player2_id, player3_id,
            current_player1_id, current_player2_id, waiting_player_id,
            is_completed
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            p1,
            p2,
            p3,
            current_p1,
            current_p2,
            waiting,
            is_completed,
        ),
    )
    conn.commit()
    trio_id = cursor.lastrowid
    assert trio_id is not None
    for _ in range(active_racks):
        conn.execute(
            "INSERT INTO trio_rack (trio_match_id, is_deleted) VALUES (?, 0)",
            (trio_id,),
        )
    for _ in range(deleted_racks):
        conn.execute(
            "INSERT INTO trio_rack (trio_match_id, is_deleted) VALUES (?, 1)",
            (trio_id,),
        )
    conn.commit()
    return trio_id


@pytest.fixture
def tmp_db(tmp_path):
    db_file = tmp_path / "test.db"
    conn = sqlite3.connect(db_file)
    _setup_schema(conn)
    conn.close()
    return str(db_file)


@pytest.mark.unit
class TestBackfillWalkoverTrioMatchup:
    def test_backfills_historic_walkover_with_null_matchup(self, tmp_db):
        conn = sqlite3.connect(tmp_db)
        trio_id = _insert_trio(conn, p1=10, p2=20, p3=30)
        conn.close()

        _load_migration_module().upgrade_sqlite(tmp_db)

        conn = sqlite3.connect(tmp_db)
        row = conn.execute(
            (
                "SELECT current_player1_id, current_player2_id, waiting_player_id FROM "
                "trio_match WHERE id = ?"
            ),
            (trio_id,),
        ).fetchone()
        conn.close()
        assert row == (10, 20, 30)

    def test_skips_contested_trio(self, tmp_db):
        """Trio with racks played must NOT be rewritten (admin could have progressed the
        matchup).
        """
        conn = sqlite3.connect(tmp_db)
        trio_id = _insert_trio(
            conn,
            p1=1,
            p2=2,
            p3=3,
            active_racks=2,
            current_p1=2,
            current_p2=3,
            waiting=1,
        )
        conn.close()

        _load_migration_module().upgrade_sqlite(tmp_db)

        conn = sqlite3.connect(tmp_db)
        row = conn.execute(
            (
                "SELECT current_player1_id, current_player2_id, waiting_player_id FROM "
                "trio_match WHERE id = ?"
            ),
            (trio_id,),
        ).fetchone()
        conn.close()
        assert row == (2, 3, 1), "contested trio was rewritten"

    def test_skips_incomplete_trio(self, tmp_db):
        """is_completed=0 must not be touched (active match being played)."""
        conn = sqlite3.connect(tmp_db)
        trio_id = _insert_trio(conn, p1=1, p2=2, p3=3, is_completed=0)
        conn.close()

        _load_migration_module().upgrade_sqlite(tmp_db)

        conn = sqlite3.connect(tmp_db)
        row = conn.execute(
            (
                "SELECT current_player1_id, current_player2_id, waiting_player_id FROM "
                "trio_match WHERE id = ?"
            ),
            (trio_id,),
        ).fetchone()
        conn.close()
        assert row == (None, None, None)

    def test_skips_already_backfilled_trio(self, tmp_db):
        """Idempotent: a second pass must not overwrite populated rows."""
        conn = sqlite3.connect(tmp_db)
        trio_id = _insert_trio(
            conn,
            p1=1,
            p2=2,
            p3=3,
            current_p1=99,
            current_p2=99,
            waiting=99,  # sentinel values
        )
        conn.close()

        _load_migration_module().upgrade_sqlite(tmp_db)

        conn = sqlite3.connect(tmp_db)
        row = conn.execute(
            (
                "SELECT current_player1_id, current_player2_id, waiting_player_id FROM "
                "trio_match WHERE id = ?"
            ),
            (trio_id,),
        ).fetchone()
        conn.close()
        assert row == (99, 99, 99), "already-populated row was overwritten"

    def test_backfills_trio_with_only_soft_deleted_racks(self, tmp_db):
        """Racks that are all soft-deleted still count as zero live racks."""
        conn = sqlite3.connect(tmp_db)
        trio_id = _insert_trio(conn, p1=7, p2=8, p3=9, active_racks=0, deleted_racks=3)
        conn.close()

        _load_migration_module().upgrade_sqlite(tmp_db)

        conn = sqlite3.connect(tmp_db)
        row = conn.execute(
            (
                "SELECT current_player1_id, current_player2_id, waiting_player_id FROM "
                "trio_match WHERE id = ?"
            ),
            (trio_id,),
        ).fetchone()
        conn.close()
        assert row == (7, 8, 9)

    def test_idempotent_second_run_is_noop(self, tmp_db):
        conn = sqlite3.connect(tmp_db)
        _insert_trio(conn, p1=10, p2=20, p3=30)
        conn.close()

        module = _load_migration_module()
        module.upgrade_sqlite(tmp_db)
        module.upgrade_sqlite(tmp_db)

        conn = sqlite3.connect(tmp_db)
        rows = conn.execute(
            (
                "SELECT current_player1_id, current_player2_id, waiting_player_id FROM "
                "trio_match"
            )
        ).fetchall()
        conn.close()
        assert rows == [(10, 20, 30)]
