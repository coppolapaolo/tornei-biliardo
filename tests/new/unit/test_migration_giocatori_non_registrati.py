"""La migration dei giocatori non registrati (ADR-085) è idempotente.

Rilanciata non fa niente, e su un DB senza la tabella `user` non solleva: una
migration che solleva non viene marcata applicata e `auto_deploy` la ritenta
ogni notte.
"""

from __future__ import annotations

import importlib
import sqlite3

import pytest

migration = importlib.import_module("migrations.20261017_giocatori_non_registrati")


def _colonne(path):
    conn = sqlite3.connect(path)
    try:
        return {r[1]: r for r in conn.execute('PRAGMA table_info("user")')}
    finally:
        conn.close()


@pytest.mark.unit
def test_aggiunge_le_tre_colonne_e_si_rilancia(tmp_path):
    path = str(tmp_path / "db.sqlite")
    conn = sqlite3.connect(path)
    conn.execute('CREATE TABLE "user" (id INTEGER PRIMARY KEY, username TEXT)')
    conn.execute("INSERT INTO \"user\" (id, username) VALUES (1, 'vecchio')")
    conn.commit()
    conn.close()

    migration.upgrade_sqlite(path)
    migration.upgrade_sqlite(path)

    colonne = _colonne(path)
    assert {"is_placeholder", "created_by_id", "claimed_at"} <= set(colonne)
    conn = sqlite3.connect(path)
    try:
        # Gli utenti che c'erano restano utenti veri.
        assert conn.execute('SELECT is_placeholder FROM "user"').fetchone() == (0,)
    finally:
        conn.close()


@pytest.mark.unit
def test_senza_la_tabella_non_solleva(tmp_path):
    migration.upgrade_sqlite(str(tmp_path / "vuoto.sqlite"))


@pytest.mark.unit
def test_ha_il_suo_nome():
    assert migration.migration_name == "20261017_giocatori_non_registrati"
