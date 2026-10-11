"""La migration della fase finale produce lo schema che l'ORM si aspetta.

Stesso presidio di ``test_gironi_migration.py``: i test di comportamento
costruiscono lo schema con ``db.create_all()``, quindi una migration sbagliata
la vedrebbe solo la produzione. Qui si **esegue**, due volte, su un database
«di ieri».
"""

from __future__ import annotations

import importlib
import sqlite3

import pytest

MIGRATION = "migrations.20261011_fase_finale"


def _colonne(conn: sqlite3.Connection, tabella: str) -> set[str]:
    return {riga[1] for riga in conn.execute(f"PRAGMA table_info({tabella})")}


@pytest.fixture
def db_di_ieri(tmp_path):
    percorso = tmp_path / "ieri.db"
    conn = sqlite3.connect(percorso)
    conn.executescript("""
        CREATE TABLE gara (id INTEGER PRIMARY KEY, campionato_id INTEGER);
        INSERT INTO gara VALUES (1, 1);
        INSERT INTO gara VALUES (2, NULL);
        """)
    conn.commit()
    conn.close()
    return str(percorso)


def _esegui(percorso: str) -> None:
    importlib.import_module(MIGRATION).upgrade_sqlite(percorso)


def test_aggiunge_le_colonne_del_modello(db_di_ieri):
    from models.competition.models import Gara

    _esegui(db_di_ieri)
    conn = sqlite3.connect(db_di_ieri)
    attese = {
        "final_phase_mode",
        "qualifiers_per_group",
        "final_phase_time_limit_minutes",
    }
    assert attese <= _colonne(conn, "gara")
    assert attese <= {c.name for c in Gara.__table__.columns}


def test_le_gare_esistenti_restano_senza_fase_finale(db_di_ieri):
    _esegui(db_di_ieri)
    conn = sqlite3.connect(db_di_ieri)
    righe = conn.execute(
        "SELECT final_phase_mode, qualifiers_per_group, "
        "final_phase_time_limit_minutes FROM gara"
    ).fetchall()
    assert righe == [("nessuna", None, None), ("nessuna", None, None)]


def test_e_idempotente(db_di_ieri):
    _esegui(db_di_ieri)
    _esegui(db_di_ieri)


def test_senza_tabella_non_solleva(tmp_path):
    _esegui(str(tmp_path / "vuoto.db"))
