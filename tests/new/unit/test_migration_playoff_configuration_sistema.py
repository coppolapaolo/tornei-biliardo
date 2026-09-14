"""La migration che dà alla configurazione dei playoff il sistema della finale.

Si esegue su un database temporaneo con la tabella com'è in produzione prima
del 2026-09-14: la colonna deve comparire, vuota — cioè «eredita» — su ogni
configurazione esistente, e una seconda esecuzione non deve fare niente.
"""

import importlib.util
import sqlite3
from pathlib import Path

MIGRATION = (
    Path(__file__).resolve().parents[3]
    / "migrations"
    / "20260914_add_playoff_configuration_classification_system.py"
)

SCHEMA = """
CREATE TABLE playoff_configuration (
    id INTEGER PRIMARY KEY,
    campionato_id INTEGER NOT NULL,
    name VARCHAR(100) NOT NULL,
    strategy_type VARCHAR(50)
);
INSERT INTO playoff_configuration (id, campionato_id, name) VALUES (1, 1, 'Elite');
"""


def _migration():
    spec = importlib.util.spec_from_file_location("migration_sistema", MIGRATION)
    assert spec and spec.loader
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def _colonne(db_path) -> dict:
    conn = sqlite3.connect(db_path)
    try:
        return {
            riga[1]: riga
            for riga in conn.execute("PRAGMA table_info(playoff_configuration)")
        }
    finally:
        conn.close()


def test_aggiunge_la_colonna_vuota_e_si_puo_rilanciare(tmp_path):
    db_path = tmp_path / "prova.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    conn.close()

    migration = _migration()
    migration.upgrade_sqlite(str(db_path))
    migration.upgrade_sqlite(str(db_path))

    assert "classification_system" in _colonne(db_path)
    conn = sqlite3.connect(db_path)
    try:
        valore = conn.execute(
            "SELECT classification_system FROM playoff_configuration WHERE id = 1"
        ).fetchone()[0]
    finally:
        conn.close()
    assert valore is None


def test_la_migration_si_dichiara():
    assert _migration().migration_name == MIGRATION.stem
