"""Test del backfill conservativo delle coordinate di tabellone (Step 11).

La cosa da proteggere non e' quel che il backfill scrive, ma quel che
**rifiuta di scrivere**: ricostruire un tabellone su una gara gia' avanti di
un turno produrrebbe un albero falso, che dice di accoppiamenti mai avvenuti.
Meglio nessun dato che un dato inventato — quelle gare restano sul ramo
legacy.

Test puro su uno SQLite temporaneo con lo schema minimo: la migration parla
SQL diretto e non deve dipendere dai modelli.
"""

from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

MIGRATION_PATH = (
    Path(__file__).resolve().parents[3]
    / "migrations"
    / "20260815_backfill_bracket_coordinates.py"
)


def _migration():
    spec = importlib.util.spec_from_file_location("backfill_bracket", MIGRATION_PATH)
    assert spec and spec.loader
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def _schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE gara (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            matchmaking_strategy VARCHAR(50),
            current_round INTEGER DEFAULT 0
        );
        CREATE TABLE match (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            gara_id INTEGER,
            round_number INTEGER NOT NULL,
            is_trio INTEGER DEFAULT 0,
            bracket_type VARCHAR(8),
            bracket_round INTEGER,
            bracket_slot INTEGER
        );
        """)
    conn.commit()


def _gara(conn, strategy="direct_elimination", current_round=1, **match_kwargs):
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO gara (matchmaking_strategy, current_round) VALUES (?, ?)",
        (strategy, current_round),
    )
    return cur.lastrowid


def _match(conn, gara_id, round_number=1, is_trio=0, bracket_type=None):
    conn.execute(
        "INSERT INTO match (gara_id, round_number, is_trio, bracket_type) "
        "VALUES (?, ?, ?, ?)",
        (gara_id, round_number, is_trio, bracket_type),
    )


def _coordinate(conn, gara_id):
    return conn.execute(
        "SELECT bracket_type, bracket_round, bracket_slot FROM match "
        "WHERE gara_id = ? ORDER BY id",
        (gara_id,),
    ).fetchall()


@pytest.fixture
def db(tmp_path):
    percorso = tmp_path / "test.db"
    conn = sqlite3.connect(percorso)
    _schema(conn)
    yield conn, str(percorso)
    conn.close()


class TestGareToccate:
    def test_primo_turno_pieno(self, db):
        conn, percorso = db
        gara_id = _gara(conn)
        for _ in range(4):
            _match(conn, gara_id)
        conn.commit()

        _migration().upgrade_sqlite(percorso)

        assert _coordinate(conn, gara_id) == [
            ("W", 1, 0),
            ("W", 1, 1),
            ("W", 1, 2),
            ("W", 1, 3),
        ]

    def test_idempotente(self, db):
        """Rieseguirla non deve rimescolare gli slot gia' assegnati."""
        conn, percorso = db
        gara_id = _gara(conn)
        for _ in range(4):
            _match(conn, gara_id)
        conn.commit()

        modulo = _migration()
        modulo.upgrade_sqlite(percorso)
        prima = _coordinate(conn, gara_id)
        modulo.upgrade_sqlite(percorso)

        assert _coordinate(conn, gara_id) == prima


class TestGareLasciateStare:
    def test_gara_gia_al_secondo_turno(self, db):
        """Il caso che il backfill esiste per non rovinare."""
        conn, percorso = db
        gara_id = _gara(conn, current_round=2)
        for _ in range(4):
            _match(conn, gara_id, round_number=1)
        for _ in range(2):
            _match(conn, gara_id, round_number=2)
        conn.commit()

        _migration().upgrade_sqlite(percorso)

        assert all(riga[0] is None for riga in _coordinate(conn, gara_id))

    def test_turno_uno_non_potenza_di_due(self, db):
        """Tre nodi non sono un albero: assegnare slot sarebbe inventare."""
        conn, percorso = db
        gara_id = _gara(conn)
        for _ in range(3):
            _match(conn, gara_id)
        conn.commit()

        _migration().upgrade_sqlite(percorso)

        assert all(riga[0] is None for riga in _coordinate(conn, gara_id))

    def test_trio_nel_primo_turno(self, db):
        conn, percorso = db
        gara_id = _gara(conn)
        _match(conn, gara_id)
        _match(conn, gara_id, is_trio=1)
        conn.commit()

        _migration().upgrade_sqlite(percorso)

        assert all(riga[0] is None for riga in _coordinate(conn, gara_id))

    def test_strategia_non_a_tabellone(self, db):
        conn, percorso = db
        gara_id = _gara(conn, strategy="amalfi")
        for _ in range(4):
            _match(conn, gara_id)
        conn.commit()

        _migration().upgrade_sqlite(percorso)

        assert all(riga[0] is None for riga in _coordinate(conn, gara_id))

    def test_coordinate_gia_presenti_non_si_riscrivono(self, db):
        conn, percorso = db
        gara_id = _gara(conn)
        _match(conn, gara_id, bracket_type="W")
        _match(conn, gara_id)
        conn.commit()

        _migration().upgrade_sqlite(percorso)

        assert [riga[0] for riga in _coordinate(conn, gara_id)] == ["W", None]


class TestSchemaAssente:
    def test_senza_le_colonne_non_fa_nulla(self, tmp_path):
        """Eseguita prima della migration dello schema, esce senza scrivere."""
        percorso = tmp_path / "vuoto.db"
        conn = sqlite3.connect(percorso)
        conn.executescript("""
            CREATE TABLE gara (id INTEGER PRIMARY KEY, matchmaking_strategy TEXT,
                               current_round INTEGER);
            CREATE TABLE match (id INTEGER PRIMARY KEY, gara_id INTEGER,
                                round_number INTEGER);
            """)
        conn.commit()

        _migration().upgrade_sqlite(str(percorso))  # non deve sollevare
        conn.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
