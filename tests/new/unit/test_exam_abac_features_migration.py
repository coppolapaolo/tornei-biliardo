"""Test della migration che semina le regole ABAC dell'esame (ADR-042).

Due rischi, entrambi silenziosi se non presidiati qui:

1. **Una metrica citata ma inesistente.** Il dispatch di ``UserMetricService``
   restituisce 0 per una metrica sconosciuta invece di sollevare: una regola
   ``METRIC`` con un nome sbagliato non fallisce, chiude il gate per sempre.
2. **Una condizione ``LEVEL``.** ADR-031 vieta di gattare le responsabilità sul
   livello; una svista qui non romperebbe nulla, semplicemente violerebbe
   l'architettura decisa.
"""

from __future__ import annotations

import importlib.util
import json
import sqlite3
from pathlib import Path

import pytest

MIGRATION_PATH = (
    Path(__file__).resolve().parents[3]
    / "migrations"
    / "20260818_add_exam_abac_features.py"
)

FEATURE_CODES = ("take_exam", "request_examiner")


def _load_migration_module():
    spec = importlib.util.spec_from_file_location(
        "add_exam_abac_features", MIGRATION_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fresh_db(tmp_path) -> str:
    """Un DB con la sola ``feature_config``, come la trova la migration."""
    db_path = str(tmp_path / "abac.db")
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
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def seeded(tmp_path) -> sqlite3.Connection:
    db_path = _fresh_db(tmp_path)
    _load_migration_module().upgrade_sqlite(db_path)
    conn = sqlite3.connect(db_path)
    yield conn
    conn.close()


def _rules(conn: sqlite3.Connection, code: str) -> list:
    row = conn.execute(
        "SELECT rules FROM feature_config WHERE code = ?", (code,)
    ).fetchone()
    assert row is not None, f"feature {code} non seminata"
    return json.loads(row[0])


def test_migration_declares_a_tracking_name():
    module = _load_migration_module()
    assert module.migration_name == "20260818_add_exam_abac_features"


def test_both_features_are_seeded_and_active(seeded):
    for code in FEATURE_CODES:
        row = seeded.execute(
            "SELECT is_active FROM feature_config WHERE code = ?", (code,)
        ).fetchone()
        assert row is not None, code
        assert row[0] == 1, code


def test_the_thresholds_are_the_ones_decided(seeded):
    assert _rules(seeded, "take_exam")[0]["conditions"][0]["value"] == 3
    assert _rules(seeded, "request_examiner")[0]["conditions"][0]["value"] == 20


def test_no_condition_is_based_on_level(seeded):
    """ADR-031: i livelli sono feedback, non barriera."""
    for code in FEATURE_CODES:
        for ruleset in _rules(seeded, code):
            types = {c.get("type") for c in ruleset["conditions"]}
            assert "LEVEL" not in types, code


def test_request_examiner_does_not_require_a_prior_exam(seeded):
    """Il deadlock di bootstrap che la soglia evita di proposito.

    Pretendere ``exams_certified >= 1`` per chiedere il ruolo significherebbe:
    per superare un esame serve un esaminatore, per diventare esaminatore serve
    un esame superato. Finché admin non nomina il primo titolare a mano,
    nessuno potrebbe chiedere il ruolo.
    """
    metrics = {
        c.get("metric")
        for ruleset in _rules(seeded, "request_examiner")
        for c in ruleset["conditions"]
    }
    assert "exams_certified" not in metrics
    assert metrics == {"challenges_completed"}


def test_every_metric_cited_actually_exists(seeded):
    """Il footgun: una metrica sconosciuta vale 0 in silenzio, per sempre."""
    from models.kpi.user_metrics import UserMetricService

    for code in FEATURE_CODES:
        for ruleset in _rules(seeded, code):
            for condition in ruleset["conditions"]:
                if condition.get("type") != "METRIC":
                    continue
                metric = condition["metric"]
                assert (
                    getattr(UserMetricService, f"_get_{metric}", None) is not None
                ), f"{code} cita la metrica inesistente {metric}"


def test_the_migration_is_idempotent(tmp_path):
    db_path = _fresh_db(tmp_path)
    module = _load_migration_module()
    module.upgrade_sqlite(db_path)
    module.upgrade_sqlite(db_path)

    conn = sqlite3.connect(db_path)
    try:
        count = conn.execute(
            "SELECT COUNT(*) FROM feature_config WHERE code IN (?, ?)", FEATURE_CODES
        ).fetchone()[0]
    finally:
        conn.close()
    assert count == 2


def test_a_threshold_tuned_from_the_console_is_not_overwritten(tmp_path):
    """Le soglie si tarano da ``/gamification/admin/features``, senza deploy.

    Se la migration rigirasse sovrascrivendo, quella taratura sparirebbe al
    primo ``auto_deploy`` — ed è il motivo per cui non usa INSERT OR REPLACE.
    """
    db_path = _fresh_db(tmp_path)
    module = _load_migration_module()
    module.upgrade_sqlite(db_path)

    conn = sqlite3.connect(db_path)
    conn.execute(
        "UPDATE feature_config SET rules = ? WHERE code = 'take_exam'",
        (json.dumps([{"description": "tarata a mano", "conditions": []}]),),
    )
    conn.commit()
    conn.close()

    module.upgrade_sqlite(db_path)

    conn = sqlite3.connect(db_path)
    try:
        rules = json.loads(
            conn.execute(
                "SELECT rules FROM feature_config WHERE code = 'take_exam'"
            ).fetchone()[0]
        )
    finally:
        conn.close()
    assert rules[0]["description"] == "tarata a mano"
