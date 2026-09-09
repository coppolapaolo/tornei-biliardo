"""Competizione di prova (ADR-058): flag, scadenza e giocatori fittizi.

Tre colonne su `gara` e `campionato` — il flag `is_prova`, la scadenza
`prova_expires_at` e la data dell'avviso di scadenza — e tre su `user`: il
flag `is_fittizio` e le due chiavi esterne che dicono a quale prova un
giocatore fittizio appartiene.

Nessun backfill: le competizioni e gli utenti esistenti non sono prove, e il
default `0` sui flag lo dice da solo. Le due colonne su `user` **non** sono
chiavi esterne: `gara.director_id` riferisce già `user`, e una FK di ritorno
chiuderebbe un ciclo che SQLAlchemy non sa ordinare. Il legame lo garantisce
il servizio, che toglie i fittizi prima della radice (`ProvaService._elimina`).

Idempotente: ogni colonna e ogni indice vengono aggiunti solo se mancano.
"""

import os
import sqlite3
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

migration_name = "20260904_competizione_di_prova"


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

    for tabella in ("gara", "campionato"):
        _aggiungi(cursor, tabella, "is_prova", "BOOLEAN NOT NULL DEFAULT 0")
        _aggiungi(cursor, tabella, "prova_expires_at", "DATETIME")
        _aggiungi(cursor, tabella, "prova_avviso_inviato_at", "DATETIME")
        cursor.execute(
            f"CREATE INDEX IF NOT EXISTS ix_{tabella}_is_prova "
            f"ON {tabella} (is_prova)"
        )

    _aggiungi(cursor, "user", "is_fittizio", "BOOLEAN NOT NULL DEFAULT 0")
    _aggiungi(cursor, "user", "prova_gara_id", "INTEGER")
    _aggiungi(cursor, "user", "prova_campionato_id", "INTEGER")
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS ix_user_is_fittizio ON user (is_fittizio)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS ix_user_prova_gara_id ON user (prova_gara_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS ix_user_prova_campionato_id "
        "ON user (prova_campionato_id)"
    )
    print("  ✓ Indici delle prove")

    conn.commit()
    conn.close()


if __name__ == "__main__":
    upgrade_sqlite()
