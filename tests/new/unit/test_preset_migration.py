"""La migration dei preset produce lo schema che l'ORM si aspetta (ADR-082).

I test di comportamento costruiscono lo schema con ``db.create_all()``: una
migration sbagliata la vedrebbe solo la produzione. Qui si **esegue**, due
volte, e le colonne si confrontano una per una con quelle del modello. Il nome
unico per proprietario è un vincolo del database, e ha il suo test.
"""

from __future__ import annotations

import importlib
import sqlite3

import pytest

from models.preset.models import ConfigPreset

MIGRATION = "migrations.20261012_preset_dei_direttori"


def _preset(owner: int, nome: str) -> str:
    return (
        "INSERT INTO config_preset "
        "(owner_id, name, kind, payload, schema_version, created_at, updated_at) "
        f"VALUES ({owner}, '{nome}', 'gara', '{{}}', 1, '2026-10-12', '2026-10-12')"
    )


@pytest.fixture
def db_di_ieri(tmp_path):
    percorso = tmp_path / "ieri.db"
    conn = sqlite3.connect(percorso)
    conn.executescript("""
        CREATE TABLE user (id INTEGER PRIMARY KEY);
        INSERT INTO user VALUES (1);
        INSERT INTO user VALUES (2);
        """)
    conn.commit()
    conn.close()
    return str(percorso)


def test_lo_schema_coincide_col_modello(db_di_ieri):
    importlib.import_module(MIGRATION).upgrade_sqlite(db_di_ieri)
    conn = sqlite3.connect(db_di_ieri)
    colonne = {r[1] for r in conn.execute("PRAGMA table_info(config_preset)")}
    conn.close()
    assert colonne == {c.name for c in ConfigPreset.__table__.columns}


def test_si_puo_rieseguire(db_di_ieri):
    importlib.import_module(MIGRATION).upgrade_sqlite(db_di_ieri)
    importlib.import_module(MIGRATION).upgrade_sqlite(db_di_ieri)


def test_lo_stesso_nome_due_volte_allo_stesso_direttore_non_ci_sta(db_di_ieri):
    importlib.import_module(MIGRATION).upgrade_sqlite(db_di_ieri)
    conn = sqlite3.connect(db_di_ieri)
    conn.execute(_preset(1, "Lunedì"))
    conn.execute(_preset(2, "Lunedì"))  # un altro direttore: ci sta
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(_preset(1, "Lunedì"))
    conn.close()
