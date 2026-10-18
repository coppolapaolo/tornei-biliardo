"""Le partite di un terzo già rifiutate rientrano nella regola del 2026-10-18.

Fino al 2026-10-18 il rifiuto valeva solo per chi lo faceva, e la partita
restava ``in_progress`` per sempre (ADR-084, «Conseguenze negative»). Dalla
regola nuova un rifiuto basta, e la partita è ``rejected`` per tutti e due: le
righe scritte prima vanno portate lì, altrimenti resterebbero appese e il
giocatore che l'aveva confermata continuerebbe a vederla.

La migration si **esegue** su un database nella forma di ieri, due volte.
"""

from __future__ import annotations

import importlib
import sqlite3

import pytest

MIGRATION = "migrations.20261018_partita_di_un_terzo_rifiutata"

#: id → (scorer_id, status, player1_rejected_at, player2_rejected_at)
RIGHE = {
    # Confermata da A, rifiutata da B: il caso appeso.
    1: (9, "in_progress", None, "2026-10-17 20:00:00"),
    # Rifiutata da A, B non ha deciso.
    2: (9, "in_progress", "2026-10-17 20:00:00", None),
    # Dichiarata, nessun rifiuto: resta in corso.
    3: (9, "in_progress", None, None),
    # Già annullata da chi segna: resta annullata.
    4: (9, "cancelled", None, "2026-10-17 20:00:00"),
    # Sfida normale: le colonne di rifiuto non le riguardano.
    5: (None, "in_progress", None, None),
}

ATTESI = {
    1: "rejected",
    2: "rejected",
    3: "in_progress",
    4: "cancelled",
    5: "in_progress",
}


@pytest.fixture
def db_di_ieri(tmp_path):
    percorso = tmp_path / "ieri.db"
    conn = sqlite3.connect(percorso)
    conn.execute("""
        CREATE TABLE individual_match (
            id INTEGER PRIMARY KEY,
            scorer_id INTEGER,
            status VARCHAR(20) NOT NULL,
            player1_rejected_at DATETIME,
            player2_rejected_at DATETIME
        )
        """)
    conn.executemany(
        "INSERT INTO individual_match VALUES (?, ?, ?, ?, ?)",
        [(i, *valori) for i, valori in RIGHE.items()],
    )
    conn.commit()
    conn.close()
    return str(percorso)


def _stati(percorso: str) -> dict[int, str]:
    conn = sqlite3.connect(percorso)
    try:
        return dict(conn.execute("SELECT id, status FROM individual_match"))
    finally:
        conn.close()


@pytest.mark.unit
def test_le_rifiutate_diventano_rejected_e_le_altre_no(db_di_ieri):
    importlib.import_module(MIGRATION).upgrade_sqlite(db_di_ieri)
    assert _stati(db_di_ieri) == ATTESI


@pytest.mark.unit
def test_rilanciata_non_cambia_niente(db_di_ieri):
    migration = importlib.import_module(MIGRATION)
    migration.upgrade_sqlite(db_di_ieri)
    migration.upgrade_sqlite(db_di_ieri)
    assert _stati(db_di_ieri) == ATTESI


@pytest.mark.unit
def test_il_valore_e_quello_dell_enum():
    """La colonna salva i valori (``values_callable``): la migration deve
    scrivere esattamente quello che l'ORM rilegge."""
    from models.status_enum import MatchStatus

    assert importlib.import_module(MIGRATION).RIFIUTATA == MatchStatus.REJECTED.value


@pytest.mark.unit
def test_senza_tabella_o_senza_colonne_e_un_no_op(tmp_path):
    vuoto = tmp_path / "vuoto.db"
    sqlite3.connect(vuoto).close()
    importlib.import_module(MIGRATION).upgrade_sqlite(str(vuoto))

    vecchio = tmp_path / "vecchio.db"
    conn = sqlite3.connect(vecchio)
    conn.execute("CREATE TABLE individual_match (id INTEGER PRIMARY KEY, status TEXT)")
    conn.commit()
    conn.close()
    importlib.import_module(MIGRATION).upgrade_sqlite(str(vecchio))
