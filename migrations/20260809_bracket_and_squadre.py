"""Coordinate di tabellone sui match, opzioni di sorteggio sulla gara, squadre.

Tre blocchi, tutti al servizio dei formati a tabellone (eliminazione diretta e
doppio KO), che finora esistevano nel dominio ma non erano utilizzabili.

1. ``match.bracket_type`` / ``bracket_round`` / ``bracket_slot``
   Il tabellone non era persistito: dal turno 2 i vincitori venivano
   riaccoppiati nell'ordine di ritorno della query, quindi la struttura del
   tabellone non veniva rispettata. Tre colonne e non un indice heap perché il
   losers bracket non è un albero binario completo — alterna round minori e
   maggiori con lo stesso numero di match — e la tripla li rappresenta
   uniformemente entrambi. NULL su tutte e tre = match non-tabellone, oppure
   gara antecedente a questa migration (le strategie ricadono sul ramo legacy).

2. Opzioni di sorteggio su ``gara``
   ``separate_teammates`` (evita i derby nei primi turni), ``third_place_match``
   (finale 3°/4°), ``draw_seed`` (rende il sorteggio riproducibile fra anteprima
   e conferma), ``seeding_rating`` (quale rating usare quando la policy del
   primo turno è "rating").

3. Squadre
   ``user.squadra`` è **testo libero**: precompila l'iscrizione, nient'altro.
   La tabella ``squadra`` vive dentro una competizione — un campionato oppure
   una gara standalone, mai entrambi — e ``inscription.squadra_id`` è l'unica
   fonte autorevole per la separazione dei compagni nel sorteggio.

Idempotente: ogni ALTER è preceduto da PRAGMA table_info, gli indici usano
IF NOT EXISTS e la CREATE TABLE pure.
"""

import os
import sqlite3
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

migration_name = "20260809_bracket_and_squadre"


def _column_exists(cursor: sqlite3.Cursor, table: str, column: str) -> bool:
    cursor.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cursor.fetchall())


def _add_column(cursor: sqlite3.Cursor, table: str, column: str, ddl: str) -> None:
    if _column_exists(cursor, table, column):
        print(f"  ⏭️  {table}.{column} già esistente")
        return
    cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
    print(f"  ✓ Aggiunta colonna {table}.{column}")


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db"):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # ── 1. Coordinate di tabellone sui match ──────────────────────────────
    _add_column(cursor, "match", "bracket_type", "VARCHAR(8)")
    _add_column(cursor, "match", "bracket_round", "INTEGER")
    _add_column(cursor, "match", "bracket_slot", "INTEGER")
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS ix_match_bracket "
        "ON match (gara_id, bracket_type, bracket_round, bracket_slot)"
    )
    print("  ✓ Indice ix_match_bracket")

    # ── 2. Opzioni di sorteggio sulla gara ────────────────────────────────
    # NOT NULL con DEFAULT: le gare esistenti prendono il default, che è
    # "comportamento di prima" (nessuna separazione, nessuna finalina).
    _add_column(cursor, "gara", "separate_teammates", "BOOLEAN NOT NULL DEFAULT 0")
    _add_column(cursor, "gara", "third_place_match", "BOOLEAN NOT NULL DEFAULT 0")
    _add_column(cursor, "gara", "draw_seed", "INTEGER")
    _add_column(cursor, "gara", "seeding_rating", "VARCHAR(16) NOT NULL DEFAULT 'elo'")

    # ── 3. Squadre ────────────────────────────────────────────────────────
    _add_column(cursor, "user", "squadra", "VARCHAR(100)")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS squadra (
            id INTEGER NOT NULL PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            normalized_name VARCHAR(100) NOT NULL,
            campionato_id INTEGER REFERENCES campionato (id) ON DELETE CASCADE,
            gara_id INTEGER REFERENCES gara (id) ON DELETE CASCADE,
            is_active BOOLEAN NOT NULL DEFAULT 1,
            created_at DATETIME,
            updated_at DATETIME,
            CONSTRAINT ck_squadra_owner_exclusive CHECK (
                (campionato_id IS NOT NULL AND gara_id IS NULL)
                OR (campionato_id IS NULL AND gara_id IS NOT NULL)
            )
        )
        """)
    print("  ✓ Tabella squadra")

    # Unicità del nome normalizzato dentro il proprio elenco. Due indici
    # separati invece di uno solo: in SQLite un UNIQUE su (campionato_id,
    # normalized_name) non vincolerebbe le righe con campionato_id NULL, che
    # sono esattamente quelle delle gare standalone.
    cursor.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_squadra_campionato_name "
        "ON squadra (campionato_id, normalized_name) WHERE campionato_id IS NOT NULL"
    )
    cursor.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_squadra_gara_name "
        "ON squadra (gara_id, normalized_name) WHERE gara_id IS NOT NULL"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS ix_squadra_campionato ON squadra (campionato_id)"
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS ix_squadra_gara ON squadra (gara_id)")
    print("  ✓ Indici squadra")

    _add_column(
        cursor,
        "inscription",
        "squadra_id",
        "INTEGER REFERENCES squadra (id) ON DELETE SET NULL",
    )

    conn.commit()
    conn.close()
    print("  ✓ Migration completata")


if __name__ == "__main__":
    upgrade_sqlite()
