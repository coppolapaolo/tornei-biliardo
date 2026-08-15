"""Test della migration 20260816_exam_schema_rework (ADR-042).

Due rischi, diversi fra loro:

1. **Drift.** In sviluppo e nei test le tabelle nascono da ``db.create_all()``,
   in produzione da questo file. Se i due schemi si allontanano il bug si
   manifesta solo in produzione — e sull'indice UNIQUE parziale significherebbe
   perdere il presidio contro il doppio tentativo aperto senza alcun errore
   visibile. Il test li confronta colonna per colonna e indice per indice.
2. **Il presupposto «le tabelle sono vuote».** La migration ricrea lo schema da
   zero: se l'ipotesi fosse falsa, i dati sparirebbero in silenzio. Deve
   fermarsi, e va verificato che si fermi davvero.
"""

from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

import pytest

MIGRATION_PATH = (
    Path(__file__).resolve().parents[3]
    / "migrations"
    / "20260816_exam_schema_rework.py"
)

TABLES = (
    "exam",
    "exam_examiner",
    "exam_challenge",
    "exam_attempt",
    "exam_challenge_result",
)


def _load_migration_module():
    spec = importlib.util.spec_from_file_location("exam_schema_rework", MIGRATION_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _columns(conn: sqlite3.Connection, table: str) -> dict[str, tuple]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {r[1]: (r[2].upper(), bool(r[3]), bool(r[5])) for r in rows}


def _index_sql(conn: sqlite3.Connection, table: str) -> dict[str, str]:
    rows = conn.execute(
        "SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name=?",
        (table,),
    ).fetchall()
    return {name: " ".join(sql.split()) for name, sql in rows if sql}


@pytest.fixture
def migrated_db(tmp_path) -> sqlite3.Connection:
    db_path = tmp_path / "migrated.db"
    _load_migration_module().upgrade_sqlite(str(db_path))
    conn = sqlite3.connect(db_path)
    yield conn
    conn.close()


def test_migration_declares_a_tracking_name():
    assert _load_migration_module().migration_name == "20260816_exam_schema_rework"


def test_creates_all_five_tables(migrated_db):
    names = {
        r[0]
        for r in migrated_db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert set(TABLES) <= names


def test_the_old_columns_are_gone(migrated_db):
    """Il rework è drop-and-recreate proprio per non trascinarsele dietro."""
    assert "director_id" not in _columns(migrated_db, "exam")
    assert "grading_criteria" not in _columns(migrated_db, "exam")
    assert "examiner_id" in _columns(migrated_db, "exam")

    attempt_columns = _columns(migrated_db, "exam_attempt")
    assert "final_grade" not in attempt_columns
    assert "completed" not in attempt_columns
    assert {"mode", "status", "passed", "certified_at"} <= set(attempt_columns)

    assert "weight" not in _columns(migrated_db, "exam_challenge")
    assert "max_score" in _columns(migrated_db, "exam_challenge")


def test_the_partial_index_allows_repeating_an_exam(migrated_db):
    """Verifica funzionale: un solo allenamento *aperto*, non un solo tentativo."""
    insert = (
        "INSERT INTO exam_attempt (exam_id, user_id, mode, status, started_at,"
        " created_at, updated_at) VALUES (1, 1, 'self_practice', ?,"
        " '2026-01-01', '2026-01-01', '2026-01-01')"
    )
    migrated_db.execute(insert, ("in_progress",))

    with pytest.raises(sqlite3.IntegrityError):
        migrated_db.execute(insert, ("in_progress",))

    # Chiuso il primo, il secondo tentativo deve passare.
    migrated_db.execute("UPDATE exam_attempt SET status='completed' WHERE id=1")
    migrated_db.execute(insert, ("in_progress",))
    count = migrated_db.execute("SELECT COUNT(*) FROM exam_attempt").fetchone()[0]
    assert count == 2


def test_a_certified_session_is_not_blocked_by_the_index(migrated_db):
    """L'indice guarda solo l'allenamento: la sessione certificata è un'altra cosa."""
    insert = (
        "INSERT INTO exam_attempt (exam_id, user_id, mode, status, started_at,"
        " created_at, updated_at) VALUES (1, 1, ?, 'in_progress',"
        " '2026-01-01', '2026-01-01', '2026-01-01')"
    )
    migrated_db.execute(insert, ("self_practice",))
    migrated_db.execute(insert, ("certified",))

    count = migrated_db.execute("SELECT COUNT(*) FROM exam_attempt").fetchone()[0]
    assert count == 2


def test_migration_refuses_to_drop_a_non_empty_table(tmp_path):
    """L'ipotesi «sono vuote» è verificata, non assunta."""
    db_path = tmp_path / "with_data.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE exam (id INTEGER PRIMARY KEY, name TEXT, director_id INTEGER)"
    )
    conn.execute("INSERT INTO exam (name, director_id) VALUES ('vecchio', 1)")
    conn.commit()
    conn.close()

    with pytest.raises(RuntimeError, match="non sono vuote"):
        _load_migration_module().upgrade_sqlite(str(db_path))

    conn = sqlite3.connect(db_path)
    try:
        # Non ha toccato nulla: la riga è ancora lì.
        assert conn.execute("SELECT COUNT(*) FROM exam").fetchone()[0] == 1
        assert "director_id" in _columns(conn, "exam")
    finally:
        conn.close()


def test_migration_is_idempotent(tmp_path):
    db_path = tmp_path / "twice.db"
    module = _load_migration_module()
    module.upgrade_sqlite(str(db_path))
    module.upgrade_sqlite(str(db_path))

    conn = sqlite3.connect(db_path)
    try:
        for table in TABLES:
            assert _columns(conn, table)
    finally:
        conn.close()


def test_schema_matches_the_sqlalchemy_models(app, tmp_path):
    """Anti-drift: migration e `db.create_all()` producono lo stesso schema."""
    from sqlalchemy.dialects import sqlite as sqlite_dialect
    from sqlalchemy.schema import CreateIndex, CreateTable

    from models.base import db

    expected_path = tmp_path / "from_models.db"
    expected_conn = sqlite3.connect(expected_path)
    dialect = sqlite_dialect.dialect()
    with app.app_context():
        for table_name in TABLES:
            table = db.metadata.tables[table_name]
            expected_conn.execute(str(CreateTable(table).compile(dialect=dialect)))
            for index in table.indexes:
                expected_conn.execute(str(CreateIndex(index).compile(dialect=dialect)))
    expected_conn.commit()

    actual_path = tmp_path / "from_migration.db"
    _load_migration_module().upgrade_sqlite(str(actual_path))
    actual_conn = sqlite3.connect(actual_path)

    try:
        for table in TABLES:
            assert _columns(actual_conn, table) == _columns(
                expected_conn, table
            ), f"colonne divergenti su {table}"

            actual_ix = _index_sql(actual_conn, table)
            expected_ix = _index_sql(expected_conn, table)
            assert set(actual_ix) == set(expected_ix), f"indici divergenti su {table}"
            for name in expected_ix:
                # Unica differenza sintattica innocua: IF NOT EXISTS.
                assert (
                    actual_ix[name].replace("IF NOT EXISTS ", "") == expected_ix[name]
                ), f"indice {name} divergente"
    finally:
        actual_conn.close()
        expected_conn.close()
