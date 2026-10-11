"""La migration della fase finale proposta dal campionato produce lo schema
che l'ORM si aspetta.

Stesso presidio di ``test_fase_finale_migration.py``: i test di comportamento
costruiscono lo schema con ``db.create_all()``, quindi una migration sbagliata
la vedrebbe solo la produzione. Qui si **esegue**, due volte, su un database
«di ieri».
"""

from __future__ import annotations

import importlib
import sqlite3

import pytest

MIGRATION = "migrations.20261012_fase_finale_proposta"

ATTESE = {
    "default_final_phase_mode",
    "default_qualifiers_per_group",
    "default_third_place_match",
    "default_final_phase_time_limit_minutes",
}


def _colonne(conn: sqlite3.Connection, tabella: str) -> set[str]:
    return {riga[1] for riga in conn.execute(f"PRAGMA table_info({tabella})")}


@pytest.fixture
def db_di_ieri(tmp_path):
    percorso = tmp_path / "ieri.db"
    conn = sqlite3.connect(percorso)
    conn.executescript("""
        CREATE TABLE campionato (id INTEGER PRIMARY KEY, name VARCHAR(100));
        INSERT INTO campionato VALUES (1, 'Lunedì al 74');
        """)
    conn.commit()
    conn.close()
    return str(percorso)


def _esegui(percorso: str) -> None:
    importlib.import_module(MIGRATION).upgrade_sqlite(percorso)


def test_aggiunge_le_colonne_del_modello(db_di_ieri):
    from models.campionato.models import Campionato

    _esegui(db_di_ieri)
    conn = sqlite3.connect(db_di_ieri)
    assert ATTESE <= _colonne(conn, "campionato")
    assert ATTESE <= {c.name for c in Campionato.__table__.columns}


def test_i_campionati_esistenti_non_propongono_fase_finale(db_di_ieri):
    _esegui(db_di_ieri)
    conn = sqlite3.connect(db_di_ieri)
    riga = conn.execute(
        "SELECT default_final_phase_mode, default_qualifiers_per_group, "
        "default_third_place_match, default_final_phase_time_limit_minutes "
        "FROM campionato"
    ).fetchone()
    assert riga == ("nessuna", 2, 0, None)


def test_e_idempotente(db_di_ieri):
    _esegui(db_di_ieri)
    _esegui(db_di_ieri)


def test_senza_tabella_non_solleva(tmp_path):
    _esegui(str(tmp_path / "vuoto.db"))
