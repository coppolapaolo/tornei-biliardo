"""Aggiunge il flag handicap mode a Campionato e Gara.

Feature (2026-06): un match giocato "con handicap" non aggiorna i rating
(Elo/Fargo). Il flag è configurabile su 3 livelli con ereditarietà nullable:

    Campionato.has_handicap  (BOOLEAN NOT NULL, default 0) — radice
    Gara.has_handicap        (BOOLEAN NULL = eredita dal campionato)
    Match.has_handicap       (BOOLEAN NULL = eredita dalla gara)

`match.has_handicap` esiste GIÀ nello schema (colonna del sistema handicap di
distanza, mai popolata): qui non va toccata, solo riusata come override
per-match. La semantica effettiva è esposta da Match.effective_has_handicap /
Gara.effective_has_handicap.

Questa migration aggiunge SOLO le due colonne mancanti (schema). Il backfill
della gara reale in produzione che deve avere l'handicap è gestito a parte da
`scripts/set_gara_handicap.py` (decisione: evitare di hardcodare un id di
produzione in una migration che gira anche su dev/test).

Idempotente: ogni ALTER è preceduto da un PRAGMA table_info check.
"""

import sqlite3

migration_name = "20260609_handicap_mode"


def _column_exists(cursor: sqlite3.Cursor, table: str, column: str) -> bool:
    cursor.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cursor.fetchall())


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db"):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # ── Campionato.has_handicap (NOT NULL, default 0) ────────────────────
    if not _column_exists(cursor, "campionato", "has_handicap"):
        cursor.execute(
            "ALTER TABLE campionato ADD COLUMN has_handicap BOOLEAN NOT NULL DEFAULT 0"
        )
        print("  ✓ Aggiunta colonna campionato.has_handicap")
    else:
        print("  ⏭️  campionato.has_handicap già esistente")

    # ── Gara.has_handicap (NULL = eredita dal campionato) ────────────────
    if not _column_exists(cursor, "gara", "has_handicap"):
        cursor.execute("ALTER TABLE gara ADD COLUMN has_handicap BOOLEAN")
        print("  ✓ Aggiunta colonna gara.has_handicap")
    else:
        print("  ⏭️  gara.has_handicap già esistente")

    # match.has_handicap esiste già: NON la tocchiamo.

    conn.commit()
    conn.close()
