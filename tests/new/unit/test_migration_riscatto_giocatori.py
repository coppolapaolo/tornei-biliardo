"""La migration del riscatto (ADR-086) crea le due tabelle, e si rilancia.

L'indice parziale è la sostanza: una sola richiesta in attesa per giocatore,
quante chiuse si vuole.
"""

from __future__ import annotations

import importlib
import sqlite3

import pytest

migration = importlib.import_module("migrations.20261018_riscatto_giocatori")


def _db(tmp_path) -> str:
    path = str(tmp_path / "db.sqlite")
    conn = sqlite3.connect(path)
    conn.execute('CREATE TABLE "user" (id INTEGER PRIMARY KEY, username TEXT)')
    conn.execute(
        "INSERT INTO \"user\" (id, username) VALUES (1, 'a'), (2, 'b'), (3, 'c')"
    )
    conn.commit()
    conn.close()
    return path


def _richiesta(conn, stato: str, claimant: int = 2) -> None:
    conn.execute(
        "INSERT INTO claim_request (placeholder_id, claimant_id, status, "
        "created_at, updated_at) VALUES (1, ?, ?, '2026-10-18', '2026-10-18')",
        (claimant, stato),
    )


@pytest.mark.unit
def test_crea_le_tabelle_e_si_rilancia(tmp_path):
    path = _db(tmp_path)
    migration.upgrade_sqlite(path)
    migration.upgrade_sqlite(path)

    conn = sqlite3.connect(path)
    try:
        for tabella in ("claim_request", "claim_request_recipient"):
            colonne = {r[1] for r in conn.execute(f"PRAGMA table_info({tabella})")}
            assert {"created_at", "updated_at"} <= colonne
    finally:
        conn.close()


@pytest.mark.unit
def test_una_sola_richiesta_in_attesa_per_giocatore(tmp_path):
    path = _db(tmp_path)
    migration.upgrade_sqlite(path)
    conn = sqlite3.connect(path)
    try:
        _richiesta(conn, "rejected")
        _richiesta(conn, "rejected", claimant=3)
        _richiesta(conn, "pending")
        with pytest.raises(sqlite3.IntegrityError):
            _richiesta(conn, "pending", claimant=3)
    finally:
        conn.close()


@pytest.mark.unit
def test_ha_il_suo_nome():
    assert migration.migration_name == "20261018_riscatto_giocatori"
