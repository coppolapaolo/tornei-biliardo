"""La migration degli obiettivi produce lo schema che l'ORM si aspetta (#316).

Stesso presidio delle due migration prima: i test di comportamento costruiscono
lo schema con ``db.create_all()``, quindi una migration sbagliata la vedrebbe
solo la produzione. Qui si **esegue**, due volte, e le colonne si confrontano
una per una con quelle del modello.
"""

from __future__ import annotations

import importlib
import sqlite3

import pytest

from models.obiettivo.models import TrainingGoal

MIGRATION = "migrations.20260920_obiettivi_di_allenamento"


def _colonne(conn: sqlite3.Connection, tabella: str) -> set[str]:
    return {riga[1] for riga in conn.execute(f"PRAGMA table_info({tabella})")}


@pytest.fixture
def db_di_ieri(tmp_path):
    """Un database senza obiettivi: utenti ed esercizi, e basta."""
    percorso = tmp_path / "ieri.db"
    conn = sqlite3.connect(percorso)
    conn.executescript("""
        CREATE TABLE user (id INTEGER PRIMARY KEY);
        CREATE TABLE challenge (id INTEGER PRIMARY KEY);
        INSERT INTO user VALUES (1);
        INSERT INTO challenge VALUES (1);
        """)
    conn.commit()
    conn.close()
    return str(percorso)


def test_lo_schema_coincide_col_modello(db_di_ieri):
    importlib.import_module(MIGRATION).upgrade_sqlite(db_di_ieri)

    conn = sqlite3.connect(db_di_ieri)
    attese = {c.name for c in TrainingGoal.__table__.columns}
    assert _colonne(conn, TrainingGoal.__tablename__) == attese
    conn.close()


def test_si_puo_rieseguire(db_di_ieri):
    migration = importlib.import_module(MIGRATION)
    migration.upgrade_sqlite(db_di_ieri)
    migration.upgrade_sqlite(db_di_ieri)


def test_un_obiettivo_senza_esercizio_e_valido(db_di_ieri):
    """Le tre forme stanno nella stessa tabella: due colonne su tre sono NULL."""
    importlib.import_module(MIGRATION).upgrade_sqlite(db_di_ieri)

    conn = sqlite3.connect(db_di_ieri)
    conn.execute(
        "INSERT INTO training_goal "
        "(user_id, kind, target, per_week, deadline_kind, created_at, updated_at) "
        "VALUES (1, 'costanza', 8, 2, 'nessuna', '2026-01-01', '2026-01-01')"
    )
    conn.commit()
    conn.close()
