"""La migration delle regole della fase finale e della finale produce lo
schema che l'ORM si aspetta.

Stesso presidio di ``test_fase_finale_proposta_migration.py``: i test di
comportamento costruiscono lo schema con ``db.create_all()``, quindi una
migration sbagliata la vedrebbe solo la produzione. Qui si **esegue**, due
volte, su un database «di ieri».
"""

from __future__ import annotations

import importlib
import sqlite3

import pytest

MIGRATION = "migrations.20261012_regole_della_finale"

DELLA_GARA = {"final_phase_distance", "final_time_limit_minutes", "final_distance"}
DEL_CAMPIONATO = {f"default_{c}" for c in DELLA_GARA}


def _colonne(conn: sqlite3.Connection, tabella: str) -> set[str]:
    return {riga[1] for riga in conn.execute(f"PRAGMA table_info({tabella})")}


@pytest.fixture
def db_di_ieri(tmp_path):
    percorso = tmp_path / "ieri.db"
    conn = sqlite3.connect(percorso)
    conn.executescript("""
        CREATE TABLE gara (id INTEGER PRIMARY KEY, name VARCHAR(100));
        CREATE TABLE campionato (id INTEGER PRIMARY KEY, name VARCHAR(100));
        INSERT INTO gara VALUES (1, 'Lunedì al 74');
        INSERT INTO campionato VALUES (1, 'Lunedì al 74');
        """)
    conn.commit()
    conn.close()
    return str(percorso)


def _esegui(percorso: str) -> None:
    importlib.import_module(MIGRATION).upgrade_sqlite(percorso)


def test_aggiunge_le_colonne_del_modello(db_di_ieri):
    from models.campionato.models import Campionato
    from models.competition.models import Gara

    _esegui(db_di_ieri)
    conn = sqlite3.connect(db_di_ieri)
    assert DELLA_GARA <= _colonne(conn, "gara")
    assert DEL_CAMPIONATO <= _colonne(conn, "campionato")
    assert DELLA_GARA <= {c.name for c in Gara.__table__.columns}
    assert DEL_CAMPIONATO <= {c.name for c in Campionato.__table__.columns}


def test_le_gare_esistenti_restano_come_prima(db_di_ieri):
    _esegui(db_di_ieri)
    conn = sqlite3.connect(db_di_ieri)
    riga = conn.execute(
        "SELECT final_phase_distance, final_time_limit_minutes, final_distance "
        "FROM gara"
    ).fetchone()
    assert riga == (None, None, None)


def test_e_idempotente(db_di_ieri):
    _esegui(db_di_ieri)
    _esegui(db_di_ieri)


def test_senza_tabelle_non_solleva(tmp_path):
    _esegui(str(tmp_path / "vuoto.db"))
