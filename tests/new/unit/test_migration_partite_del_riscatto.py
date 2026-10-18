"""La migration delle partite del riscatto crea la tabella, e si rilancia.

Il vincolo è la sostanza: una sfida si annota una volta sola per richiesta,
e la stessa sfida può stare sotto due richieste — una partita di altri due
fra due giocatori non registrati, riscattati da due persone diverse.
"""

from __future__ import annotations

import importlib
import sqlite3

import pytest

migration = importlib.import_module("migrations.20261018_partite_del_riscatto")


def _riga(conn, richiesta: int, partita: int) -> None:
    conn.execute(
        "INSERT INTO claim_request_match (request_id, individual_match_id, "
        "created_at, updated_at) VALUES (?, ?, '2026-10-18', '2026-10-18')",
        (richiesta, partita),
    )


@pytest.mark.unit
def test_crea_la_tabella_e_si_rilancia(tmp_path):
    path = str(tmp_path / "db.sqlite")
    migration.upgrade_sqlite(path)
    migration.upgrade_sqlite(path)

    conn = sqlite3.connect(path)
    try:
        colonne = {r[1] for r in conn.execute("PRAGMA table_info(claim_request_match)")}
        assert {
            "request_id",
            "individual_match_id",
            "created_at",
            "updated_at",
        } <= colonne
    finally:
        conn.close()


@pytest.mark.unit
def test_una_sfida_una_volta_per_richiesta(tmp_path):
    path = str(tmp_path / "db.sqlite")
    migration.upgrade_sqlite(path)
    conn = sqlite3.connect(path)
    try:
        _riga(conn, 1, 7)
        _riga(conn, 2, 7)
        with pytest.raises(sqlite3.IntegrityError):
            _riga(conn, 1, 7)
    finally:
        conn.close()


@pytest.mark.unit
def test_ha_il_suo_nome():
    assert migration.migration_name == "20261018_partite_del_riscatto"
