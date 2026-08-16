"""Chi semina una `feature_config` deve scrivere anche i timestamp.

``feature_config.created_at`` e ``updated_at`` sono NOT NULL **senza** default
a livello di tabella: il default vive sul modello SQLAlchemy. Le migration però
parlano ``sqlite3`` diretto, dove quel modello non c'è — quindi un INSERT che
li omette non fallisce «un po'», fallisce del tutto.

E il danno non si ferma alla feature mancante. La migration muore a metà, il
runner non registra nulla, e la connessione lasciata aperta blocca il database:
**tutte** le migration successive falliscono con «database is locked». È
successo con il referto TPA, e il sintomo visibile era una funzione che non si
sbloccava mai per nessuno.

Il test gira le migration di seed su un database temporaneo con lo schema
minimo: se una nuova dimentica i timestamp, si scopre qui e non in produzione.
"""

import importlib.util
import sqlite3
from pathlib import Path

import pytest

MIGRATIONS = Path(__file__).resolve().parents[3] / "migrations"

#: Le migration che seminano `feature_config`, con il codice che devono creare.
SEEDING_MIGRATIONS = [
    ("20260816_add_tpa_referto.py", "tpa_scoresheet"),
]

SCHEMA = """
CREATE TABLE feature_config (
    id INTEGER PRIMARY KEY,
    code VARCHAR(50) NOT NULL UNIQUE,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    rules TEXT,
    is_active BOOLEAN NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL
)
"""


def _load(filename: str):
    spec = importlib.util.spec_from_file_location("mig", MIGRATIONS / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("filename,code", SEEDING_MIGRATIONS)
def test_la_feature_viene_davvero_seminata(filename, code, tmp_path):
    """Non basta che la migration «giri»: la riga deve esserci."""
    db_path = str(tmp_path / "seed.db")
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()

    _load(filename).upgrade_sqlite(db_path)

    conn = sqlite3.connect(db_path)
    try:
        seminata = conn.execute(
            "SELECT COUNT(*) FROM feature_config WHERE code = ?", (code,)
        ).fetchone()[0]
        timestamp = conn.execute(
            "SELECT created_at, updated_at FROM feature_config WHERE code = ?",
            (code,),
        ).fetchone()
    finally:
        conn.close()

    assert seminata == 1, f"{filename} non ha seminato '{code}'"
    assert all(timestamp), "created_at/updated_at devono essere valorizzati"


@pytest.mark.parametrize("filename,code", SEEDING_MIGRATIONS)
def test_rieseguirla_non_rompe(filename, code, tmp_path):
    """Le migration sono idempotenti: il runner può ripassarci sopra."""
    db_path = str(tmp_path / "seed.db")
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()

    module = _load(filename)
    module.upgrade_sqlite(db_path)
    module.upgrade_sqlite(db_path)

    conn = sqlite3.connect(db_path)
    try:
        quante = conn.execute(
            "SELECT COUNT(*) FROM feature_config WHERE code = ?", (code,)
        ).fetchone()[0]
    finally:
        conn.close()

    assert quante == 1, "la seconda esecuzione ha duplicato la feature"
