"""Test delle migration dello schema esame (ADR-042).

Sono due file, ma un solo schema: ``20260816_exam_schema_rework`` rifà il
dominio, ``20260817_add_exam_request_tables`` aggiunge l'appuntamento e
ricostruisce ``exam_attempt`` per agganciarcelo. Il test li applica **in
sequenza**, che è come girano in produzione: verificarli isolati direbbe poco,
perché il secondo riscrive una tabella del primo.

Due rischi, diversi fra loro:

1. **Drift.** In sviluppo e nei test le tabelle nascono da ``db.create_all()``,
   in produzione da questi file. Se i due schemi si allontanano il bug si
   manifesta solo in produzione — e su un indice UNIQUE parziale significherebbe
   perdere un presidio anti-TOCTOU senza alcun errore visibile. Il confronto è
   colonna per colonna, indice per indice **e chiave esterna per chiave
   esterna**: le FK contano davvero, perché il DB gira con
   ``PRAGMA foreign_keys=ON`` (``models/base.py``) e ``PRAGMA table_info`` non
   le mostra, quindi un confronto sulle sole colonne le lascerebbe divergere in
   silenzio.
2. **Il presupposto «le tabelle sono vuote».** Entrambe ricreano tabelle: se
   l'ipotesi fosse falsa, i dati sparirebbero in silenzio. Devono fermarsi, e
   va verificato che si fermino davvero.
"""

from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

import pytest

MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "migrations"
MIGRATION_PATH = MIGRATIONS_DIR / "20260816_exam_schema_rework.py"
REQUEST_MIGRATION_PATH = MIGRATIONS_DIR / "20260817_add_exam_request_tables.py"

#: Tabelle del dominio esame, nell'ordine in cui le migration le creano.
TABLES = (
    "exam",
    "exam_examiner",
    "exam_challenge",
    "exam_attempt",
    "exam_challenge_result",
    "exam_request",
    "exam_request_recipient",
    "exam_time_proposal",
)


def _load(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_migration_module():
    return _load(MIGRATION_PATH)


def _load_request_migration_module():
    return _load(REQUEST_MIGRATION_PATH)


def _apply_chain(db_path: Path) -> None:
    """Le migration nell'ordine in cui girano in produzione."""
    _load_migration_module().upgrade_sqlite(str(db_path))
    _load_request_migration_module().upgrade_sqlite(str(db_path))


def _columns(conn: sqlite3.Connection, table: str) -> dict[str, tuple]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {r[1]: (r[2].upper(), bool(r[3]), bool(r[5])) for r in rows}


def _index_sql(conn: sqlite3.Connection, table: str) -> dict[str, str]:
    rows = conn.execute(
        "SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name=?",
        (table,),
    ).fetchall()
    return {name: " ".join(sql.split()) for name, sql in rows if sql}


def _foreign_keys(conn: sqlite3.Connection, table: str) -> set[tuple]:
    """(colonna locale, tabella riferita, colonna riferita, ON DELETE)."""
    rows = conn.execute(f"PRAGMA foreign_key_list({table})").fetchall()
    return {(r[3], r[2], r[4], (r[6] or "NO ACTION").upper()) for r in rows}


@pytest.fixture
def migrated_db(tmp_path) -> sqlite3.Connection:
    db_path = tmp_path / "migrated.db"
    _apply_chain(db_path)
    conn = sqlite3.connect(db_path)
    yield conn
    conn.close()


def test_migrations_declare_a_tracking_name():
    assert _load_migration_module().migration_name == "20260816_exam_schema_rework"
    assert (
        _load_request_migration_module().migration_name
        == "20260817_add_exam_request_tables"
    )


def test_creates_every_table_of_the_domain(migrated_db):
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


def test_the_appointment_tables_are_there_with_their_guard(migrated_db):
    """Il presidio della corsa «due esaminatori accettano insieme»."""
    insert = (
        "INSERT INTO exam_request_recipient (request_id, examiner_id, status,"
        " created_at, updated_at) VALUES (1, ?, ?, '2026-01-01', '2026-01-01')"
    )
    migrated_db.execute(insert, (10, "accepted"))

    # Un secondo accettante sulla stessa richiesta non passa…
    with pytest.raises(sqlite3.IntegrityError):
        migrated_db.execute(insert, (11, "accepted"))

    # …ma gli altri esiti convivono quanti sono.
    migrated_db.execute(insert, (11, "closed"))
    migrated_db.execute(insert, (12, "closed"))
    count = migrated_db.execute(
        "SELECT COUNT(*) FROM exam_request_recipient"
    ).fetchone()[0]
    assert count == 3


def test_one_session_per_appointment(migrated_db):
    """L'altra corsa: due sessioni per lo stesso appuntamento."""
    insert = (
        "INSERT INTO exam_attempt (exam_id, user_id, mode, status, started_at,"
        " exam_request_id, created_at, updated_at) VALUES (1, ?, 'certified',"
        " 'awaiting_player_start', '2026-01-01', ?, '2026-01-01', '2026-01-01')"
    )
    migrated_db.execute(insert, (1, 7))

    with pytest.raises(sqlite3.IntegrityError):
        migrated_db.execute(insert, (2, 7))

    # L'indice è parziale: i tentativi in autonomia hanno tutti NULL.
    migrated_db.execute(insert, (1, None))
    migrated_db.execute(insert, (2, None))
    count = migrated_db.execute("SELECT COUNT(*) FROM exam_attempt").fetchone()[0]
    assert count == 3


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


def test_the_rebuild_refuses_to_drop_recorded_attempts(tmp_path):
    """Stessa regola per la seconda migration, che ricostruisce i tentativi."""
    db_path = tmp_path / "with_attempts.db"
    _load_migration_module().upgrade_sqlite(str(db_path))

    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO exam_attempt (exam_id, user_id, mode, status, started_at,"
        " created_at, updated_at) VALUES (1, 1, 'self_practice', 'in_progress',"
        " '2026-01-01', '2026-01-01', '2026-01-01')"
    )
    conn.commit()
    conn.close()

    with pytest.raises(RuntimeError, match="non sono vuote"):
        _load_request_migration_module().upgrade_sqlite(str(db_path))

    conn = sqlite3.connect(db_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM exam_attempt").fetchone()[0] == 1
    finally:
        conn.close()


def test_migrations_are_idempotent(tmp_path):
    db_path = tmp_path / "twice.db"
    _apply_chain(db_path)
    _apply_chain(db_path)

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
    _apply_chain(actual_path)
    actual_conn = sqlite3.connect(actual_path)

    try:
        for table in TABLES:
            assert _columns(actual_conn, table) == _columns(
                expected_conn, table
            ), f"colonne divergenti su {table}"

            assert _foreign_keys(actual_conn, table) == _foreign_keys(
                expected_conn, table
            ), f"chiavi esterne divergenti su {table}"

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
