"""La migration della prova fatta di colpi produce lo schema che l'ORM si aspetta.

Stesso presidio di ``test_esercizio_profilo_migration.py``: i test di
comportamento costruiscono lo schema con ``db.create_all()`` e una migration
sbagliata la vede solo la produzione. Qui si **esegue**, due volte, su un DB
portato fino a ieri dalla migration precedente, e le colonne si confrontano una
per una con quelle dei modelli.
"""

from __future__ import annotations

import importlib
import sqlite3

import pytest

from models.challenge.models import Challenge, ChallengeAttempt, ChallengeShot

PRIMA = "migrations.20260919_profilo_esercizio"
MIGRATION = "migrations.20260920_prova_fatta_di_colpi"


def _colonne(conn: sqlite3.Connection, tabella: str) -> set[str]:
    return {riga[1] for riga in conn.execute(f"PRAGMA table_info({tabella})")}


@pytest.fixture
def db_di_ieri(tmp_path):
    percorso = tmp_path / "ieri.db"
    conn = sqlite3.connect(percorso)
    conn.executescript("""
        CREATE TABLE user (id INTEGER PRIMARY KEY);
        CREATE TABLE challenge (
            id INTEGER PRIMARY KEY, title VARCHAR(120), description TEXT NOT NULL,
            image_path VARCHAR(255) NOT NULL, diagram_scene TEXT,
            pass_fail_only BOOLEAN NOT NULL, max_score INTEGER,
            created_by_id INTEGER, is_active BOOLEAN NOT NULL,
            created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL
        );
        CREATE TABLE challenge_attempt (
            id INTEGER PRIMARY KEY, challenge_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL, score INTEGER, passed BOOLEAN,
            completed BOOLEAN NOT NULL, attempted_at DATETIME NOT NULL, notes TEXT,
            gara_id INTEGER, round_number INTEGER,
            created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL
        );
        INSERT INTO challenge VALUES
            (1, 'Spot', 'x', 'a.jpg', NULL, 0, 10, NULL, 1, '2026-01-01', '2026-01-01');
        """)
    conn.commit()
    conn.close()
    importlib.import_module(PRIMA).upgrade_sqlite(str(percorso))
    return str(percorso)


def test_lo_schema_coincide_con_i_modelli(db_di_ieri):
    importlib.import_module(MIGRATION).upgrade_sqlite(db_di_ieri)

    conn = sqlite3.connect(db_di_ieri)
    for modello in (Challenge, ChallengeAttempt, ChallengeShot):
        attese = {c.name for c in modello.__table__.columns}
        assert _colonne(conn, modello.__tablename__) == attese, modello.__tablename__
    conn.close()


def test_si_puo_rieseguire(db_di_ieri):
    migration = importlib.import_module(MIGRATION)
    migration.upgrade_sqlite(db_di_ieri)
    migration.upgrade_sqlite(db_di_ieri)


def test_gli_esercizi_di_ieri_restano_col_totale(db_di_ieri):
    """Finora esisteva un modo solo: dirlo non è inventare un dato."""
    importlib.import_module(MIGRATION).upgrade_sqlite(db_di_ieri)

    conn = sqlite3.connect(db_di_ieri)
    assert conn.execute(
        "SELECT recording_mode, shots_count FROM challenge"
    ).fetchone() == ("total", None)
    conn.close()


def test_due_colpi_nello_stesso_posto_li_rifiuta_anche_il_db(db_di_ieri):
    importlib.import_module(MIGRATION).upgrade_sqlite(db_di_ieri)

    conn = sqlite3.connect(db_di_ieri)
    inserisci = (
        "INSERT INTO challenge_shot "
        "(attempt_id, position, points, created_at, updated_at) "
        "VALUES (1, 1, 0, '2026-01-01', '2026-01-01')"
    )
    conn.execute(inserisci)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(inserisci)
    conn.close()
