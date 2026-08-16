"""Aggiunge challenge.title: il nome del drill, quando chi lo crea gliene da' uno.

Fino a ieri un drill si chiamava con i primi 50 caratteri delle sue istruzioni,
troncati (`get_display_name()`). Funziona finche' i drill sono pochi: appena il
catalogo cresce, meta' delle card comincia con «Disponi le bilie lungo la...» e
non si distinguono piu' l'una dall'altra — proprio nel posto in cui servirebbe
di piu', cioe' scegliendo quale provare.

La colonna e' **nullable**, e resta tale anche per i drill nuovi: il titolo e'
facoltativo. NULL non e' un dato mancante da riempire, significa «chi l'ha
creato non ha voluto dargli un nome», e in quel caso il nome se lo prende dal
progressivo — `Drill 12`, dove 12 e' l'id. Non c'e' backfill per la stessa
ragione: un titolo inventato adesso sarebbe indistinguibile da uno scelto.

Idempotente: l'ALTER e' preceduto da PRAGMA table_info.
"""

import os
import sqlite3
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

migration_name = "20260816_add_challenge_title"


def _column_exists(cursor: sqlite3.Cursor, table: str, column: str) -> bool:
    cursor.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cursor.fetchall())


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db"):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    if not _column_exists(cursor, "challenge", "title"):
        cursor.execute("ALTER TABLE challenge ADD COLUMN title VARCHAR(120)")
        print("  ✓ Aggiunta colonna challenge.title")
    else:
        print("  ⏭️  challenge.title già esistente")

    conn.commit()
    conn.close()


if __name__ == "__main__":
    upgrade_sqlite()
