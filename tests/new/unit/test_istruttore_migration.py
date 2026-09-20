"""La migration del ruolo di istruttore (ADR-069).

Fa due cose e nessuna delle due si vedrebbe fallire da sola:

* semina ``request_instructor`` in ``feature_config``. Una metrica scritta male
  non solleva — ``UserMetricService`` risponde 0 a una metrica sconosciuta —
  quindi chiuderebbe il gate per sempre, in silenzio;
* aggiunge ``user.organization``. SQLite non ha ``ADD COLUMN IF NOT EXISTS``, e
  una migration che solleva su una condizione permanente dell'ambiente viene
  ritentata ogni notte da ``auto_deploy`` senza mai essere marcata applicata.
  Qui si verifica che rieseguirla sia un no-op.
"""

from __future__ import annotations

import importlib.util
import json
import sqlite3
from pathlib import Path

import pytest

from models.kpi.user_metrics import UserMetricService

MIGRATION_PATH = (
    Path(__file__).resolve().parents[3] / "migrations" / "20260920_istruttore.py"
)

CODICE = "request_instructor"


def _load_migration_module():
    spec = importlib.util.spec_from_file_location(
        "istruttore_migration", MIGRATION_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fresh_db(tmp_path) -> str:
    """Un DB con `feature_config` e uno `user` minimo, come lo trova."""
    db_path = str(tmp_path / "istruttore.db")
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE feature_config (
            code VARCHAR(50) NOT NULL PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            description TEXT,
            rules TEXT,
            is_active BOOLEAN NOT NULL,
            badge_slug VARCHAR(50),
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL
        )
        """)
    conn.execute("""
        CREATE TABLE user (
            id INTEGER NOT NULL PRIMARY KEY,
            username VARCHAR(80) NOT NULL,
            role VARCHAR(20) NOT NULL
        )
        """)
    conn.execute("INSERT INTO user (id, username, role) VALUES (1, 'luca', 'player')")
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def seminato(tmp_path):
    db_path = _fresh_db(tmp_path)
    _load_migration_module().upgrade_sqlite(db_path)
    conn = sqlite3.connect(db_path)
    yield conn, db_path
    conn.close()


def _regole(conn: sqlite3.Connection) -> list:
    riga = conn.execute(
        "SELECT rules FROM feature_config WHERE code = ?", (CODICE,)
    ).fetchone()
    assert riga is not None, "feature non seminata"
    return json.loads(riga[0])


def test_dichiara_il_nome_con_cui_viene_tracciata():
    assert _load_migration_module().migration_name == "20260920_istruttore"


def test_la_feature_e_attiva(seminato):
    conn, _ = seminato
    riga = conn.execute(
        "SELECT is_active FROM feature_config WHERE code = ?", (CODICE,)
    ).fetchone()
    assert riga is not None
    assert riga[0] == 1


def test_la_soglia_e_quella_decisa(seminato):
    """Cinque, non venti: il filtro vero è l'approvazione (ADR-069 §6)."""
    conn, _ = seminato
    assert _regole(conn)[0]["conditions"][0]["value"] == 5


def test_la_metrica_citata_esiste_davvero(seminato):
    """Un nome sbagliato non solleva: risponde 0, e chiude il gate per sempre."""
    conn, _ = seminato
    for ruleset in _regole(conn):
        for condizione in ruleset["conditions"]:
            metrica = condizione.get("metric")
            assert metrica, "una condizione METRIC senza metrica"
            assert hasattr(UserMetricService, f"_get_{metrica}"), metrica


def test_nessuna_condizione_sul_livello(seminato):
    """ADR-031: i livelli sono feedback, non barriera."""
    conn, _ = seminato
    for ruleset in _regole(conn):
        assert "LEVEL" not in {c.get("type") for c in ruleset["conditions"]}


def test_la_colonna_della_scuola_c_e(seminato):
    conn, _ = seminato
    colonne = {riga[1] for riga in conn.execute("PRAGMA table_info(user)")}
    assert "organization" in colonne


def test_rieseguirla_non_fa_niente(seminato):
    """Idempotente: nessun `duplicate column`, nessuna soglia sovrascritta."""
    conn, db_path = seminato
    conn.execute(
        "UPDATE feature_config SET rules = ? WHERE code = ?",
        (json.dumps([{"conditions": [{"type": "METRIC", "value": 99}]}]), CODICE),
    )
    conn.commit()

    _load_migration_module().upgrade_sqlite(db_path)

    # La soglia ritoccata dall'admin resta quella: l'INSERT è condizionato.
    assert _regole(conn)[0]["conditions"][0]["value"] == 99
