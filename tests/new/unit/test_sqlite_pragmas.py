"""Presidio sui PRAGMA applicati a ogni connessione SQLite (ADR-045).

Il test che conta è quello sul journal mode: `PRAGMA journal_mode=WAL` ha
corrotto il DB di produzione due volte (2026-06-10 e 2026-08-17) perché su NFS
la memoria condivisa che il WAL usa per coordinare i processi non è coerente.

Questi test guardano il **comportamento** di una connessione vera, non il testo
del sorgente: un WAL reintrodotto per un'altra strada (config, engine options,
un secondo listener) verrebbe preso comunque.

Nota: la suite gira su `sqlite:///:memory:`, dove `journal_mode` è sempre
`memory` e un WAL sarebbe inerte — per questo qui si usa un DB **su file**,
l'unico posto in cui il guasto si manifesta.
"""

import sqlite3

import pytest
from sqlalchemy import create_engine, text

# L'import registra il listener globale `_set_sqlite_pragma` su Engine.
from models.base import SQLITE_BUSY_TIMEOUT_MS  # noqa: F401


@pytest.fixture
def file_engine(tmp_path):
    """Engine su un DB SQLite **su file** (non in memoria)."""
    engine = create_engine(f"sqlite:///{tmp_path / 'probe.db'}")
    yield engine
    engine.dispose()


def test_journal_mode_is_not_wal(file_engine):
    """Il WAL non deve tornare: su NFS corrompe il DB (ADR-045)."""
    with file_engine.connect() as conn:
        mode = conn.execute(text("PRAGMA journal_mode")).scalar()

    assert mode is not None
    assert mode.lower() != "wal", (
        "PRAGMA journal_mode=WAL è tornato. Su PythonAnywhere lo storage è NFS "
        "e il WAL vi corrompe il database ('database disk image is malformed', "
        "incidenti 2026-06-10 e 2026-08-17). Vedi docs/adr/"
        "ADR-045-no-wal-on-network-storage.md prima di rimetterlo."
    )


def test_busy_timeout_is_set(file_engine):
    """Senza busy_timeout ogni contesa di lock è un errore immediato."""
    with file_engine.connect() as conn:
        timeout = conn.execute(text("PRAGMA busy_timeout")).scalar()

    assert timeout == SQLITE_BUSY_TIMEOUT_MS


def test_foreign_keys_are_enabled(file_engine):
    """SQLite disattiva le FK a ogni connessione: servono per ON DELETE CASCADE."""
    with file_engine.connect() as conn:
        enabled = conn.execute(text("PRAGMA foreign_keys")).scalar()

    assert enabled == 1


def test_a_file_db_defaults_to_a_rollback_journal(tmp_path):
    """Il default di SQLite è già sicuro: il WAL era una scelta esplicita.

    Documenta *perché* rimuovere la riga basta, senza doverne aggiungere una
    che forzi `DELETE`: un file nuovo nasce con un rollback journal.
    """
    db_path = tmp_path / "plain.db"
    conn = sqlite3.connect(str(db_path))
    try:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    finally:
        conn.close()

    assert mode.lower() != "wal"
