"""Referto TPA: tabelle del referto e sblocco della funzione — ADR-044.

Crea:
  1. `tpa_referto`  — un referto per match individuale, con chi lo compila e
     quante bilie ha il rack (8, 9 o 10);
  2. `tpa_comando`  — il registro di cio' che il compilatore preme, in ordine.
     E' l'unica verita': rack, turni, errori e TPA si ricavano rigiocandolo.

E semina la feature `tpa_scoresheet` su `feature_config`, con le soglie iniziali
di sblocco: aver gia' giocato una gara, un campionato, tre match individuali,
tre drill e un esame certificato.

**Le soglie qui sono solo il punto di partenza.** Da quel momento si cambiano
dalla gestione gamification (`/gamification/admin/features/tpa_scoresheet`)
senza toccare il codice: questa migration non le riscrive se la feature esiste
gia', proprio per non calpestare una regola decisa dall'admin.

Idempotente: CREATE TABLE IF NOT EXISTS, indici con IF NOT EXISTS, e seed della
feature solo se il codice non c'e' ancora.
"""

import json
import os
import sqlite3
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

migration_name = "20260816_add_tpa_referto"

FEATURE_CODE = "tpa_scoresheet"
FEATURE_NAME = "Referto TPA"
FEATURE_DESCRIPTION = (
    "Prendere il referto completo di un match singolo con il metodo Accu-Stats "
    "(TPA) invece di segnare i soli rack vinti. Si sblocca a chi ha gia' "
    "attraversato tutte le forme di gioco della piattaforma."
)

#: Un solo insieme di condizioni, quindi vanno soddisfatte tutte.
FEATURE_RULES = [
    {
        "description": (
            "Ha gia' giocato gare, campionati, match individuali, drill ed esami"
        ),
        "conditions": [
            {
                "type": "METRIC",
                "metric": "tournaments_played",
                "operator": "gte",
                "value": 1,
            },
            {
                "type": "METRIC",
                "metric": "campionati_played",
                "operator": "gte",
                "value": 1,
            },
            {
                "type": "METRIC",
                "metric": "individual_matches_played",
                "operator": "gte",
                "value": 3,
            },
            {
                "type": "METRIC",
                "metric": "challenges_completed",
                "operator": "gte",
                "value": 3,
            },
            {
                "type": "METRIC",
                "metric": "exams_certified",
                "operator": "gte",
                "value": 1,
            },
        ],
    }
]


def _table_exists(cursor: sqlite3.Cursor, table: str) -> bool:
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    )
    return cursor.fetchone() is not None


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db"):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tpa_referto (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            individual_match_id INTEGER NOT NULL UNIQUE
                REFERENCES individual_match (id) ON DELETE CASCADE,
            compiler_id INTEGER NOT NULL REFERENCES user (id),
            game_type INTEGER NOT NULL,
            closed_at DATETIME,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL
        )
        """)
    print("  ✓ Tabella tpa_referto")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tpa_comando (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referto_id INTEGER NOT NULL
                REFERENCES tpa_referto (id) ON DELETE CASCADE,
            sequence INTEGER NOT NULL,
            command VARCHAR(16) NOT NULL,
            pressed_at DATETIME NOT NULL,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL,
            CONSTRAINT uq_tpa_comando_sequence UNIQUE (referto_id, sequence)
        )
        """)
    print("  ✓ Tabella tpa_comando")

    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_tpa_comando_referto ON tpa_comando (referto_id)"
    )
    print("  ✓ Indice idx_tpa_comando_referto")

    if _table_exists(cursor, "feature_config"):
        cursor.execute(
            "SELECT code FROM feature_config WHERE code = ?", (FEATURE_CODE,)
        )
        if cursor.fetchone() is None:
            # `created_at`/`updated_at` sono NOT NULL su `feature_config` e non
            # hanno un default a livello di tabella: il default sta sul modello
            # SQLAlchemy, che qui non c'e' perche' la migration parla sqlite3
            # diretto. Ometterli faceva fallire l'INSERT, e con lui l'intera
            # migration — quindi la feature del referto non veniva mai seminata
            # e la catena delle migration successive si fermava.
            cursor.execute(
                "INSERT INTO feature_config "
                "(code, name, description, rules, is_active, "
                " created_at, updated_at) "
                "VALUES (?, ?, ?, ?, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
                (
                    FEATURE_CODE,
                    FEATURE_NAME,
                    FEATURE_DESCRIPTION,
                    json.dumps(FEATURE_RULES),
                ),
            )
            print(f"  ✓ Feature '{FEATURE_CODE}' seminata con le soglie iniziali")
        else:
            print(f"  ⏭️  Feature '{FEATURE_CODE}' già presente: regole invariate")
    else:
        print("  ⚠️  Tabella feature_config assente: seed della feature saltato")

    conn.commit()
    conn.close()


if __name__ == "__main__":
    upgrade_sqlite()
