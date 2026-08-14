"""Normalizza le discipline sul vocabolario unico di `Discipline`.

Il progetto ha convissuto con due vocabolari per la stessa cosa: le gare
salvavano `8_ball` (il valore dell'enum `Discipline`), i match individuali
`palla_8` — il nome italiano usato come valore persistito. Nessuno dei due era
validato: le colonne sono `String`, quindi il disallineamento non produceva
errori. Il filtro di visualizzazione ripiegava su `raw.replace("_"," ").title()`
e mostrava "Palla 8", che sembrava corretto; nel frattempo ogni confronto fra
discipline scritte dai due lati era falso.

Questa migration porta i dati esistenti sul valore canonico. Il codice è già
stato ripulito dai letterali: da qui in avanti solo `Discipline` scrive.

Colonne toccate — tutte quelle che nominano una disciplina, non solo quelle dei
match individuali: un valore vecchio può essere finito ovunque tramite copia fra
entità (una gara di playoff eredita la disciplina della gara sorgente).

Le due colonne JSON di `set` contengono i valori annidati nel testo
(`["palla_9", "palla_10"]`, `{"1": "palla_8"}`), quindi vanno sostituite con
`REPLACE` sulle virgolette, non con un confronto di uguaglianza.

Idempotente: una seconda esecuzione non trova più righe da convertire.
"""

import os
import sqlite3
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

migration_name = "20260811_normalize_discipline_vocabulary"

# Deve restare allineato a `_DISCIPLINE_LEGACY_ALIASES` in models/status_enum.py.
ALIASES = {
    "palla_8": "8_ball",
    "palla_9": "9_ball",
    "palla_10": "10_ball",
}

# (tabella, colonna) con un singolo valore di disciplina.
SCALAR_COLUMNS = [
    ("gara", "discipline"),
    ("individual_match", "discipline"),
    ("match", "discipline"),
    ("match_proposal", "discipline"),
    ("playoff_configuration", "discipline"),
    ("playoff_match", "discipline"),
    ("round_configuration", "discipline"),
    ("set", "discipline"),
    ("set_rack", "discipline_override"),
]

# (tabella, colonna) con i valori dentro un documento JSON.
JSON_COLUMNS = [
    ("set", "discipline_rotation"),
    ("set", "discipline_assignment"),
]


def _table_exists(cursor: sqlite3.Cursor, table: str) -> bool:
    cursor.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    )
    return cursor.fetchone() is not None


def _column_exists(cursor: sqlite3.Cursor, table: str, column: str) -> bool:
    cursor.execute(f'PRAGMA table_info("{table}")')
    return any(row[1] == column for row in cursor.fetchall())


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db"):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    converted = 0

    for table, column in SCALAR_COLUMNS:
        if not _table_exists(cursor, table) or not _column_exists(
            cursor, table, column
        ):
            print(f"  ⏭️  {table}.{column} assente")
            continue

        for legacy, canonical in ALIASES.items():
            cursor.execute(
                f'UPDATE "{table}" SET "{column}" = ? WHERE "{column}" = ?',
                (canonical, legacy),
            )
            if cursor.rowcount:
                converted += cursor.rowcount
                print(
                    f"  ✓ {table}.{column}: {cursor.rowcount} righe "
                    f"{legacy} → {canonical}"
                )

    for table, column in JSON_COLUMNS:
        if not _table_exists(cursor, table) or not _column_exists(
            cursor, table, column
        ):
            print(f"  ⏭️  {table}.{column} assente")
            continue

        for legacy, canonical in ALIASES.items():
            # Le virgolette nel pattern evitano che `palla_1` (inesistente, ma
            # per non dipendere da quel dettaglio) intacchi `palla_10`.
            cursor.execute(
                f'UPDATE "{table}" SET "{column}" = REPLACE("{column}", ?, ?) '
                f'WHERE "{column}" LIKE ?',
                (f'"{legacy}"', f'"{canonical}"', f"%{legacy}%"),
            )
            if cursor.rowcount:
                converted += cursor.rowcount
                print(
                    f"  ✓ {table}.{column} (JSON): {cursor.rowcount} righe "
                    f"{legacy} → {canonical}"
                )

    conn.commit()

    # Verifica: nessun valore residuo fuori dal vocabolario. Non solleva — il
    # DB può contenere discipline scritte a mano da import o test — ma lo dice,
    # perché un residuo silenzioso è esattamente il difetto che ha originato
    # questa migration.
    residual = []
    for table, column in SCALAR_COLUMNS:
        if not _table_exists(cursor, table) or not _column_exists(
            cursor, table, column
        ):
            continue
        placeholders = ",".join("?" for _ in ALIASES)
        cursor.execute(
            f'SELECT DISTINCT "{column}" FROM "{table}" '
            f'WHERE "{column}" IN ({placeholders})',
            tuple(ALIASES),
        )
        for row in cursor.fetchall():
            residual.append(f"{table}.{column} = {row[0]!r}")

    conn.close()

    print(f"  ✓ {converted} valori normalizzati")
    if residual:
        print("  ⚠️  residui del vocabolario storico: " + ", ".join(residual))


if __name__ == "__main__":
    upgrade_sqlite()
