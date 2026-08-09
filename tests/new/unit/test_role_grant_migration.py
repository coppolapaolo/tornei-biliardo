"""Test della migration 20260809_add_role_grant_tables (ADR-038).

Il rischio vero di questa migration non è che fallisca: è che **diverga** dai
modelli. In sviluppo e nei test le tabelle nascono da ``db.create_all()``, in
produzione da questo file. Se i due schemi si allontanano, il bug si manifesta
solo in produzione — e sugli indici UNIQUE parziali significherebbe perdere il
presidio contro il doppio grant senza alcun errore visibile.

Il test confronta quindi lo schema prodotto dalla migration con quello
prodotto dal metadata SQLAlchemy, colonna per colonna e indice per indice.
"""

from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

import pytest

MIGRATION_PATH = (
    Path(__file__).resolve().parents[3]
    / "migrations"
    / "20260809_add_role_grant_tables.py"
)

TABLES = ("role_grant", "role_request", "role_request_recipient")


def _load_migration_module():
    spec = importlib.util.spec_from_file_location(
        "add_role_grant_tables", MIGRATION_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _columns(conn: sqlite3.Connection, table: str) -> dict[str, tuple]:
    """Mappa colonna → (tipo, notnull, pk), normalizzata."""
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {r[1]: (r[2].upper(), bool(r[3]), bool(r[5])) for r in rows}


def _index_sql(conn: sqlite3.Connection, table: str) -> dict[str, str]:
    """Mappa nome indice → SQL normalizzato (spazi collassati)."""
    rows = conn.execute(
        "SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name=?",
        (table,),
    ).fetchall()
    return {
        name: " ".join(sql.split())
        for name, sql in rows
        if sql  # sql=None → auto-index
    }


@pytest.fixture
def migrated_db(tmp_path) -> sqlite3.Connection:
    """DB temporaneo su cui la migration è stata applicata una volta sola."""
    db_path = tmp_path / "migrated.db"
    _load_migration_module().upgrade_sqlite(str(db_path))
    conn = sqlite3.connect(db_path)
    yield conn
    conn.close()


def test_migration_declares_a_tracking_name():
    """Senza `migration_name` il runner non registra l'applicazione."""
    assert _load_migration_module().migration_name == "20260809_add_role_grant_tables"


def test_creates_the_three_tables(migrated_db):
    names = {
        r[0]
        for r in migrated_db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert set(TABLES) <= names


def test_partial_unique_indexes_carry_their_where_clause(migrated_db):
    """La parzialità è la sostanza: senza WHERE l'indice cambia semantica.

    Un UNIQUE pieno su (user_id, role) impedirebbe di ri-concedere un ruolo
    dopo una revoca; senza UNIQUE del tutto, due concedenti in corsa
    creerebbero due grant attivi.
    """
    grant_indexes = _index_sql(migrated_db, "role_grant")
    assert "uq_role_grant_active" in grant_indexes
    sql = grant_indexes["uq_role_grant_active"]
    assert "UNIQUE" in sql.upper()
    assert "WHERE revoked_at IS NULL" in sql

    request_indexes = _index_sql(migrated_db, "role_request")
    assert "uq_role_request_pending" in request_indexes
    sql = request_indexes["uq_role_request_pending"]
    assert "UNIQUE" in sql.upper()
    assert "WHERE status = 'pending'" in sql


def test_partial_index_actually_enforces_one_active_grant(migrated_db):
    """Verifica funzionale, non solo testuale, dell'indice parziale."""
    migrated_db.execute(
        "INSERT INTO role_grant (user_id, role, granted_by_id, granted_at,"
        " created_at, updated_at) VALUES (1,'examiner',9,'2026-01-01',"
        "'2026-01-01','2026-01-01')"
    )
    with pytest.raises(sqlite3.IntegrityError):
        migrated_db.execute(
            "INSERT INTO role_grant (user_id, role, granted_by_id, granted_at,"
            " created_at, updated_at) VALUES (1,'examiner',9,'2026-01-02',"
            "'2026-01-02','2026-01-02')"
        )

    # Dopo la revoca la riga esce dall'indice: il ri-grant deve passare.
    migrated_db.execute("UPDATE role_grant SET revoked_at='2026-01-03' WHERE user_id=1")
    migrated_db.execute(
        "INSERT INTO role_grant (user_id, role, granted_by_id, granted_at,"
        " created_at, updated_at) VALUES (1,'examiner',9,'2026-01-04',"
        "'2026-01-04','2026-01-04')"
    )
    count = migrated_db.execute(
        "SELECT COUNT(*) FROM role_grant WHERE user_id=1"
    ).fetchone()[0]
    assert count == 2


def test_migration_is_idempotent(tmp_path):
    """Rieseguirla non deve sollevare: il runner può ripassarci sopra."""
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
    """Anti-drift: migration e `db.create_all()` devono produrre lo stesso schema.

    È il test che conta. Se qualcuno cambia i modelli senza scrivere una nuova
    migration, la produzione resterebbe indietro in silenzio.
    """
    from sqlalchemy.dialects import sqlite as sqlite_dialect
    from sqlalchemy.schema import CreateIndex, CreateTable

    from models.base import db

    # Schema "atteso": quello del metadata, materializzato su un DB vergine.
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
                # Normalizza l'unica differenza sintattica innocua: la
                # migration usa IF NOT EXISTS, il metadata no.
                assert (
                    actual_ix[name].replace("IF NOT EXISTS ", "") == expected_ix[name]
                ), f"indice {name} divergente"
    finally:
        actual_conn.close()
        expected_conn.close()
