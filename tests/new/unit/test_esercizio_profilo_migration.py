"""La migration del profilo dell'esercizio produce lo schema che l'ORM si aspetta.

I test di comportamento costruiscono lo schema con ``db.create_all()``, quindi
non vedono mai una migration sbagliata: la vede solo la produzione, con un «no
such column». Qui la migration si **esegue** su un DB che somiglia a quello di
ieri, due volte, e le colonne che lascia si confrontano una per una con quelle
dei modelli.
"""

from __future__ import annotations

import importlib
import sqlite3

import pytest

from models.challenge.models import (
    Challenge,
    ChallengeAttempt,
    ChallengeCategory,
    ChallengeRating,
    ChallengeVariant,
)

MIGRATION = "migrations.20260919_profilo_esercizio"
# Le migration venute dopo sulle stesse tabelle. I modelli descrivono lo schema
# di OGGI, quindi il confronto colonna per colonna vale sulla catena intera:
# fermarsi a questa migration farebbe fallire il test a ogni colonna nuova.
SUCCESSIVE = ("migrations.20260920_prova_fatta_di_colpi",)


def _colonne(conn: sqlite3.Connection, tabella: str) -> set[str]:
    return {riga[1] for riga in conn.execute(f"PRAGMA table_info({tabella})")}


@pytest.fixture
def db_di_ieri(tmp_path):
    """Le tre tabelle che la migration tocca o cita, com'erano prima."""
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
        INSERT INTO challenge_attempt VALUES
            (1, 1, 1, 7, NULL, 1, '2026-01-02', NULL, NULL, NULL,
             '2026-01-02', '2026-01-02');
        """)
    conn.commit()
    conn.close()
    return str(percorso)


def test_lo_schema_coincide_con_i_modelli(db_di_ieri):
    migration = importlib.import_module(MIGRATION)
    migration.upgrade_sqlite(db_di_ieri)
    for successiva in SUCCESSIVE:
        importlib.import_module(successiva).upgrade_sqlite(db_di_ieri)

    conn = sqlite3.connect(db_di_ieri)
    for modello in (
        Challenge,
        ChallengeAttempt,
        ChallengeCategory,
        ChallengeVariant,
        ChallengeRating,
    ):
        attese = {c.name for c in modello.__table__.columns}
        assert _colonne(conn, modello.__tablename__) == attese, modello.__tablename__
    conn.close()


def test_si_puo_rieseguire(db_di_ieri):
    migration = importlib.import_module(MIGRATION)
    migration.upgrade_sqlite(db_di_ieri)
    migration.upgrade_sqlite(db_di_ieri)


def test_nessun_backfill(db_di_ieri):
    """L'esercizio e la prova di ieri restano senza profilo e senza variante."""
    importlib.import_module(MIGRATION).upgrade_sqlite(db_di_ieri)
    conn = sqlite3.connect(db_di_ieri)
    assert conn.execute(
        "SELECT declared_level, family, family_step, cue_ball_reset FROM challenge"
    ).fetchone() == (None, None, None, None)
    assert conn.execute("SELECT variant_id FROM challenge_attempt").fetchone() == (
        None,
    )
    assert conn.execute("SELECT COUNT(*) FROM challenge_category").fetchone() == (0,)
    conn.close()


def test_il_voto_fuori_scala_lo_rifiuta_anche_il_db(db_di_ieri):
    importlib.import_module(MIGRATION).upgrade_sqlite(db_di_ieri)
    conn = sqlite3.connect(db_di_ieri)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO challenge_rating "
            "(challenge_id, user_id, rating, created_at, updated_at) "
            "VALUES (1, 1, 6, '2026-01-01', '2026-01-01')"
        )
    conn.close()
