"""La migration della scheda produce lo schema che l'ORM si aspetta (ADR-067).

Stesso presidio di ``test_prova_fatta_di_colpi_migration.py``: i test di
comportamento costruiscono lo schema con ``db.create_all()``, quindi una
migration sbagliata la vedrebbe solo la produzione. Qui si **esegue**, due
volte, e le colonne si confrontano una per una con quelle dei modelli.

I due indici unici **parziali** hanno un test loro: sono la ragione per cui la
tabella non ha un UNIQUE normale, e in SQL una riga con NULL non è uguale a
nessun'altra — quindi senza il secondo indice due caselle «senza variante»
passerebbero entrambe.
"""

from __future__ import annotations

import importlib
import sqlite3

import pytest

from models.training_sheet.models import (
    TrainingEntry,
    TrainingSession,
    TrainingSheet,
    TrainingSheetItem,
    TrainingSheetReader,
)

MIGRATION = "migrations.20260920_scheda_di_allenamento"


def _colonne(conn: sqlite3.Connection, tabella: str) -> set[str]:
    return {riga[1] for riga in conn.execute(f"PRAGMA table_info({tabella})")}


@pytest.fixture
def db_di_ieri(tmp_path):
    """Un database senza schede: utenti, esercizi e varianti, e basta."""
    percorso = tmp_path / "ieri.db"
    conn = sqlite3.connect(percorso)
    conn.executescript("""
        CREATE TABLE user (id INTEGER PRIMARY KEY);
        CREATE TABLE challenge (id INTEGER PRIMARY KEY);
        CREATE TABLE challenge_variant (
            id INTEGER PRIMARY KEY, challenge_id INTEGER NOT NULL,
            label VARCHAR(40) NOT NULL, position INTEGER NOT NULL,
            created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL
        );
        INSERT INTO user VALUES (1);
        INSERT INTO challenge VALUES (1);
        INSERT INTO challenge_variant VALUES
            (1, 1, 'destra', 1, '2026-01-01', '2026-01-01');
        """)
    conn.commit()
    conn.close()
    return str(percorso)


def test_lo_schema_coincide_con_i_modelli(db_di_ieri):
    importlib.import_module(MIGRATION).upgrade_sqlite(db_di_ieri)

    conn = sqlite3.connect(db_di_ieri)
    for modello in (
        TrainingSheet,
        TrainingSheetItem,
        TrainingSheetReader,
        TrainingSession,
        TrainingEntry,
    ):
        attese = {c.name for c in modello.__table__.columns}
        assert _colonne(conn, modello.__tablename__) == attese, modello.__tablename__
    conn.close()


def test_si_puo_rieseguire(db_di_ieri):
    migration = importlib.import_module(MIGRATION)
    migration.upgrade_sqlite(db_di_ieri)
    migration.upgrade_sqlite(db_di_ieri)


def _scheda_con_voce(conn: sqlite3.Connection) -> None:
    conn.execute(
        "INSERT INTO training_sheet "
        "(id, name, owner_id, threshold_streak, uses_days, version, is_active, "
        " created_at, updated_at) "
        "VALUES (1, 'X', 1, 1, 0, 1, 1, '2026-01-01', '2026-01-01')"
    )
    conn.execute(
        "INSERT INTO training_sheet_item "
        "(id, sheet_id, challenge_id, position, measure, per_variant, is_active, "
        " created_at, updated_at) "
        "VALUES (1, 1, 1, 1, 'made', 1, 1, '2026-01-01', '2026-01-01')"
    )
    conn.execute(
        "INSERT INTO training_session "
        "(id, sheet_id, user_id, sheet_version, started_at, created_at, updated_at) "
        "VALUES (1, 1, 1, 1, '2026-01-01', '2026-01-01', '2026-01-01')"
    )


def test_due_caselle_senza_variante_le_rifiuta_il_db(db_di_ieri):
    """È il caso che un UNIQUE normale lascerebbe passare: NULL ≠ NULL."""
    importlib.import_module(MIGRATION).upgrade_sqlite(db_di_ieri)

    conn = sqlite3.connect(db_di_ieri)
    _scheda_con_voce(conn)
    inserisci = (
        "INSERT INTO training_entry "
        "(session_id, item_id, variant_id, value, measure, created_at, updated_at) "
        "VALUES (1, 1, NULL, 3, 'made', '2026-01-01', '2026-01-01')"
    )
    conn.execute(inserisci)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(inserisci)
    conn.close()


def test_due_caselle_sulla_stessa_variante_le_rifiuta_il_db(db_di_ieri):
    importlib.import_module(MIGRATION).upgrade_sqlite(db_di_ieri)

    conn = sqlite3.connect(db_di_ieri)
    _scheda_con_voce(conn)
    inserisci = (
        "INSERT INTO training_entry "
        "(session_id, item_id, variant_id, value, measure, created_at, updated_at) "
        "VALUES (1, 1, 1, 3, 'made', '2026-01-01', '2026-01-01')"
    )
    conn.execute(inserisci)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(inserisci)
    conn.close()


def test_due_voci_ritirate_possono_avere_avuto_lo_stesso_posto(db_di_ieri):
    """L'unicità della posizione vale fra le **attive**: il resto è storia."""
    importlib.import_module(MIGRATION).upgrade_sqlite(db_di_ieri)

    conn = sqlite3.connect(db_di_ieri)
    conn.execute(
        "INSERT INTO training_sheet "
        "(id, name, owner_id, threshold_streak, uses_days, version, is_active, "
        " created_at, updated_at) "
        "VALUES (1, 'X', 1, 1, 0, 1, 1, '2026-01-01', '2026-01-01')"
    )
    ritirata = (
        "INSERT INTO training_sheet_item "
        "(sheet_id, challenge_id, position, measure, per_variant, is_active, "
        " created_at, updated_at) "
        "VALUES (1, 1, 1, 'made', 0, 0, '2026-01-01', '2026-01-01')"
    )
    conn.execute(ritirata)
    conn.execute(ritirata)

    attiva = ritirata.replace(", 0, '2026-01-01'", ", 1, '2026-01-01'")
    conn.execute(attiva)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(attiva)
    conn.close()
