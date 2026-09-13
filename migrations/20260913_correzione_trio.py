"""Correzione del trio e della partita a set: quel che la traccia non teneva.

La correzione di un risultato chiuso (issue #90) scriveva da quale punteggio a
quale, per i due giocatori di `match`. Dal 2026-09-13 si correggono anche il
trio e la partita a set, e a `match` mancano due cose:

* i triangoli del terzo giocatore del trio, prima e dopo;
* il dettaglio dei set («4–1 · 2–4 · 1–4»), prima e dopo: sul match ci sono
  solo i set vinti, che restano uguali quando cambia un set.

Nessun backfill: le correzioni esistenti sono tutte di partite a due, e per
quelle le quattro colonne restano vuote.

Idempotente: ogni colonna viene aggiunta solo se manca.
"""

import os
import sqlite3
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

migration_name = "20260913_correzione_trio"


def _colonne(cursor: sqlite3.Cursor, tabella: str) -> set:
    return {row[1] for row in cursor.execute(f"PRAGMA table_info({tabella})")}


def _aggiungi(cursor: sqlite3.Cursor, tabella: str, colonna: str, ddl: str) -> None:
    if colonna in _colonne(cursor, tabella):
        print(f"  = {tabella}.{colonna} gia' presente")
        return
    cursor.execute(f"ALTER TABLE {tabella} ADD COLUMN {colonna} {ddl}")
    print(f"  ✓ {tabella}.{colonna}")


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db"):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    _aggiungi(cursor, "match_correction", "previous_player3_score", "INTEGER")
    _aggiungi(cursor, "match_correction", "new_player3_score", "INTEGER")
    _aggiungi(cursor, "match_correction", "previous_detail", "VARCHAR(120)")
    _aggiungi(cursor, "match_correction", "new_detail", "VARCHAR(120)")

    conn.commit()
    conn.close()


if __name__ == "__main__":
    upgrade_sqlite()
