"""Le sfide contro un non registrato scritte a mezzogiorno si chiudono da sole.

Fino alla regola del 2026-10-18 sera la sfida contro un giocatore non
registrato restava ``in_progress`` con una firma sola, «in attesa del
riscatto». Dalla regola nuova si chiude con la firma di chi l'ha giocata: le
righe scritte prima vanno chiuse allo stesso modo, altrimenti resterebbero
appese — e dopo un riscatto bloccherebbero chi l'ha riscattato.

La migration si **esegue** su un database nella forma di ieri, due volte.
"""

from __future__ import annotations

import importlib
import sqlite3

import pytest

MIGRATION = "migrations.20261018_sfide_registrate_da_uno"

#: utenti: id → is_placeholder
UTENTI = {1: 0, 2: 0, 7: 1, 8: 1}

#: id → (p1, p2, s1, s2, p1_confirmed, p2_confirmed, p1_at, p2_at, scorer, status)
RIGHE = {
    # Marco (1) contro Gino (7), firmata da Marco: si chiude, vince Marco.
    1: (1, 7, 3, 1, 1, 0, "2026-10-18 12:00:00", None, None, "in_progress"),
    # Gino (8) primo giocatore, vince lui, firma Anna (2): si chiude.
    2: (8, 2, 3, 2, 0, 1, None, "2026-10-18 13:00:00", None, "in_progress"),
    # Due registrati, una firma: è una sfida normale che aspetta. Resta.
    3: (1, 2, 3, 0, 1, 0, "2026-10-18 12:00:00", None, None, "in_progress"),
    # Contro un non registrato ma senza firme: si sta giocando. Resta.
    4: (1, 7, 1, 1, 0, 0, None, None, None, "in_progress"),
    # Partita di un terzo con un non registrato: ha le sue regole. Resta.
    5: (1, 7, 3, 0, 1, 0, "2026-10-18 12:00:00", None, 2, "in_progress"),
    # Già annullata. Resta.
    6: (1, 7, 3, 0, 1, 0, "2026-10-18 12:00:00", None, None, "cancelled"),
}

#: id → (status, recorded_by_id, winner_id)
ATTESI = {
    1: ("completed", 1, 1),
    2: ("completed", 2, 8),
    3: ("in_progress", None, None),
    4: ("in_progress", None, None),
    5: ("in_progress", None, None),
    6: ("cancelled", None, None),
}


@pytest.fixture
def db_di_ieri(tmp_path):
    percorso = tmp_path / "ieri.db"
    conn = sqlite3.connect(percorso)
    conn.execute('CREATE TABLE "user" (id INTEGER PRIMARY KEY, is_placeholder BOOLEAN)')
    conn.executemany('INSERT INTO "user" VALUES (?, ?)', list(UTENTI.items()))
    conn.execute("""
        CREATE TABLE individual_match (
            id INTEGER PRIMARY KEY,
            player1_id INTEGER, player2_id INTEGER,
            player1_score INTEGER, player2_score INTEGER,
            player1_confirmed BOOLEAN, player2_confirmed BOOLEAN,
            player1_confirmed_at DATETIME, player2_confirmed_at DATETIME,
            scorer_id INTEGER,
            status VARCHAR(20) NOT NULL,
            winner_id INTEGER,
            ended_at DATETIME
        )
        """)
    conn.executemany(
        "INSERT INTO individual_match VALUES (?,?,?,?,?,?,?,?,?,?,?,NULL,NULL)",
        [(i, *valori) for i, valori in RIGHE.items()],
    )
    conn.commit()
    conn.close()
    return str(percorso)


def _righe(percorso: str) -> dict:
    conn = sqlite3.connect(percorso)
    try:
        return {
            i: (stato, chi, vincitore)
            for i, stato, chi, vincitore in conn.execute(
                "SELECT id, status, recorded_by_id, winner_id FROM individual_match"
            )
        }
    finally:
        conn.close()


@pytest.mark.unit
def test_si_chiudono_solo_quelle_contro_un_non_registrato(db_di_ieri):
    importlib.import_module(MIGRATION).upgrade_sqlite(db_di_ieri)
    assert _righe(db_di_ieri) == ATTESI
    conn = sqlite3.connect(db_di_ieri)
    try:
        # La data di fine è quella della firma.
        assert conn.execute(
            "SELECT ended_at FROM individual_match WHERE id = 1"
        ).fetchone() == ("2026-10-18 12:00:00",)
    finally:
        conn.close()


@pytest.mark.unit
def test_rilanciata_non_cambia_niente(db_di_ieri):
    migration = importlib.import_module(MIGRATION)
    migration.upgrade_sqlite(db_di_ieri)
    migration.upgrade_sqlite(db_di_ieri)
    assert _righe(db_di_ieri) == ATTESI


@pytest.mark.unit
def test_i_valori_sono_quelli_dell_enum():
    from models.status_enum import MatchStatus

    migration = importlib.import_module(MIGRATION)
    assert migration.REGISTRATA == MatchStatus.CLOSED_UNILATERALLY.value
    assert migration.IN_CORSO == MatchStatus.IN_PROGRESS.value


@pytest.mark.unit
def test_senza_tabella_o_senza_non_registrati_e_un_no_op(tmp_path):
    vuoto = tmp_path / "vuoto.db"
    sqlite3.connect(vuoto).close()
    importlib.import_module(MIGRATION).upgrade_sqlite(str(vuoto))

    vecchio = tmp_path / "vecchio.db"
    conn = sqlite3.connect(vecchio)
    conn.execute('CREATE TABLE "user" (id INTEGER PRIMARY KEY)')
    conn.execute(
        "CREATE TABLE individual_match (id INTEGER PRIMARY KEY, status TEXT, "
        "scorer_id INTEGER, player1_confirmed_at DATETIME)"
    )
    conn.commit()
    conn.close()
    importlib.import_module(MIGRATION).upgrade_sqlite(str(vecchio))
