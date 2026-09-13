"""Il seed dimostrativo della guida produce due volte gli stessi dati.

Le schermate di `/aiuto` si rigenerano rilanciando `seed_demo.py` e poi la
cattura: se due esecuzioni danno tabelloni diversi, ogni ricattura riscrive
immagini che non sono cambiate e nessuno sa piu' quali lo sono davvero.

Fino al 2026-09-13 il seed fissava il `random` globale ma non il seme del
sorteggio: `RoundService.start_first_round` lo sceglie con `secrets`, e la gara
a tabellone ne ricava gli accoppiamenti. La prova, trovata dalla PR #398:
due esecuzioni davano otto semi diversi e quattro partite del tabellone
diverse.
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

RADICE = Path(__file__).resolve().parents[3]

QUERY = {
    "gare": "select id, name, matchmaking_strategy, draw_seed from gara order by id",
    "partite": (
        "select gara_id, round_number, player1_id, player2_id, is_bye, is_trio "
        "from match order by id"
    ),
    "iscrizioni": (
        "select gara_id, user_id, initial_order from inscription "
        "order by gara_id, user_id"
    ),
}


def _seed(db: Path) -> dict:
    env = dict(os.environ, DATABASE_URL=f"sqlite:///{db}")
    env.pop("FLASK_ENV", None)
    esito = subprocess.run(
        [sys.executable, "scripts/help_docs/seed_demo.py"],
        cwd=RADICE,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert esito.returncode == 0, esito.stdout[-2000:] + esito.stderr[-2000:]
    conn = sqlite3.connect(db)
    try:
        return {k: conn.execute(q).fetchall() for k, q in QUERY.items()}
    finally:
        conn.close()


def test_due_esecuzioni_del_seed_danno_gli_stessi_dati(tmp_path):
    primo = _seed(tmp_path / "primo.db")
    secondo = _seed(tmp_path / "secondo.db")

    assert primo["gare"], "il seed non ha creato gare"
    # Il seme del sorteggio c'e' su ogni gara avviata, ed e' lo stesso.
    assert any(riga[3] is not None for riga in primo["gare"])
    assert primo["gare"] == secondo["gare"]
    assert primo["partite"] == secondo["partite"]
    assert primo["iscrizioni"] == secondo["iscrizioni"]
