"""`scripts/tempi_di_gara.py`: i tempi di un campionato, turno per turno.

Lo script non importa l'app e apre il DB con `sqlite3` in sola lettura, così
gira in una console di produzione senza env e senza disabilitare la web app.
Il prezzo è che i modelli non lo proteggono: una colonna rinominata lo
romperebbe solo lì. Da qui il presidio sulle colonne che legge.
"""

from __future__ import annotations

import io
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import tempi_di_gara  # noqa: E402


def _db(tmp_path: Path) -> Path:
    """Un DB con le sole colonne che lo script legge, e una gara giocata."""
    percorso = tmp_path / "prova.db"
    con = sqlite3.connect(percorso)
    for tabella, colonne in tempi_di_gara.COLONNE_LETTE.items():
        con.execute(f'CREATE TABLE "{tabella}" ({", ".join(colonne)})')
    con.execute("INSERT INTO campionato VALUES (1, 'Prima Rōnin CUP', 'amalfi', NULL)")
    con.execute("INSERT INTO campionato VALUES (2, 'Vecchio', 'amalfi', '2026-01-01')")
    con.execute(
        "INSERT INTO gara VALUES "
        "(10, 1, 1, 'Gara 1', '2026-09-01', '9_ball', 5, 1, NULL, NULL),"
        "(11, 1, 2, 'Finale', '2026-09-08', '9_ball', 5, 1, 3, NULL)"
    )
    # Orari UTC, come li salva l'app: 18:00 UTC = 20:00 a Roma d'estate.
    con.execute(
        "INSERT INTO match VALUES "
        # turno 1: due partite di 30 e 50 minuti, una X, un tavolino
        "(1, 10, 1, NULL, 5, NULL, '2026-09-01 18:00:00', '2026-09-01 18:30:00', 0, 0),"
        "(2, 10, 1, NULL, 5, NULL, '2026-09-01 18:00:00', '2026-09-01 18:50:00', 0, 0),"
        "(3, 10, 1, NULL, 5, NULL, NULL, '2026-09-01 18:00:00', 1, 0),"
        "(4, 10, 1, NULL, 5, NULL, NULL, '2026-09-01 18:00:00', 0, 0),"
        # turno 2: override a 8-ball al 3, una partita senza orari
        "(5, 10, 2, '8_ball', 3, NULL,"
        " '2026-09-01 19:00:00', '2026-09-01 19:20:00', 0, 0),"
        "(6, 10, 2, '8_ball', 3, NULL, NULL, NULL, 0, 0),"
        # la finale: match_distance 1 è il default dello schema → la gara
        "(7, 11, 1, NULL, 1, 0, '2026-09-08 18:00:00', '2026-09-08 19:10:00', 0, 0)"
    )
    rack = [
        (1, "2026-09-01 18:29:00"),
        (2, "2026-09-01 18:40:00"),
        (5, "2026-09-01 19:19:00"),
        (6, "2026-09-01 19:30:00"),
        (7, "2026-09-08 19:05:00"),
    ]
    con.executemany("INSERT INTO rack VALUES (?, ?, 0)", rack)
    con.execute("INSERT INTO rack VALUES (2, '2026-09-01 18:49:00', 1)")  # tolto
    con.commit()
    con.close()
    return percorso


def _esegui(*argv: str) -> tuple[int, str]:
    out = io.StringIO()
    codice = tempi_di_gara.main(list(argv), out=out)
    return codice, out.getvalue()


@pytest.mark.unit
class TestIlRapporto:
    def test_un_turno_misurato(self, tmp_path):
        codice, testo = _esegui("Rōnin", "--db", str(_db(tmp_path)))
        assert codice == 0
        turno1 = next(r for r in testo.splitlines() if "Turno 1" in r)
        assert "9_ball, al 5 — 2 partite (+1 senza rack: tavolini)" in turno1
        assert "durata min 30′, media 40′, max 50′" in turno1
        # L'ultima chiusa alle 18:50 UTC, l'ultimo rack valido alle 18:40.
        assert "ultima chiusa alle 20:50 (ultimo rack alle 20:40)" in turno1

    def test_override_del_turno_e_partite_senza_orari(self, tmp_path):
        _, testo = _esegui("1", "--db", str(_db(tmp_path)))
        turno2 = next(r for r in testo.splitlines() if "Turno 2" in r)
        assert "8_ball, al 3 — 2 partite" in turno2
        assert "durata min 20′, media 20′, max 20′" in turno2
        assert "1 senza inizio o fine" in turno2

    def test_il_playoff_e_la_distanza_della_gara(self, tmp_path):
        _, testo = _esegui("1", "--db", str(_db(tmp_path)))
        assert "Gara 2 — Finale (2026-09-08) [PLAYOFF]" in testo
        finale = testo.split("[PLAYOFF]")[1]
        assert "9_ball, esattamente 5 — 1 partite" in finale
        assert "durata min 70′" in finale

    def test_senza_argomenti_elenca_solo_i_vivi(self, tmp_path):
        codice, testo = _esegui("--db", str(_db(tmp_path)))
        assert codice == 0
        assert "Prima Rōnin CUP" in testo and "Vecchio" not in testo

    def test_nome_ambiguo_o_assente(self, tmp_path):
        db = str(_db(tmp_path))
        codice, testo = _esegui("Inesistente", "--db", db)
        assert codice == 1 and "0 campionati" in testo

    def test_non_scrive(self, tmp_path):
        con = tempi_di_gara.apri(_db(tmp_path))
        with pytest.raises(sqlite3.OperationalError):
            con.execute("DELETE FROM rack")


@pytest.mark.unit
def test_le_colonne_lette_esistono_nei_modelli(app):
    """Lo script non importa l'app: se un modello rinomina una colonna, se ne
    accorge questo test e non la console di produzione."""
    from models.base import db

    for tabella, colonne in tempi_di_gara.COLONNE_LETTE.items():
        presenti = set(db.metadata.tables[tabella].columns.keys())
        assert set(colonne) <= presenti, (tabella, set(colonne) - presenti)
