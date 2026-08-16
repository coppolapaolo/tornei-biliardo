"""Aggiunge challenge.diagram_scene: il disegno del drill, quando c'e'.

Un drill si crea in due modi: caricando una foto del tavolo preparato, oppure
disegnandolo col builder. Nel secondo caso servono **due** cose, e non sono la
stessa: l'immagine per mostrarlo (`image_path`, gia' esistente e NOT NULL) e la
scena per modificarlo (questa colonna).

Nessuna delle due sa fare il mestiere dell'altra. Da un PNG non si torna
indietro alle bilie, quindi senza scena correggere una posizione vorrebbe dire
ridisegnare tutto da capo. Una scena, all'opposto, non entra in un `<img>`:
tenerla da sola vorrebbe dire ridisegnare il drill a ogni miniatura del
catalogo, e per chi legge la guida o riceve una notifica non ci sarebbe niente
da guardare.

La colonna e' **nullable** perche' la maggioranza dei drill nasce da una foto e
un disegno non ce l'ha. NULL qui non e' un dato mancante: significa «questo
drill non e' stato costruito», ed e' esattamente cio' che distingue chi puo'
riaprire il builder da chi no.

Idempotente: l'ALTER e' preceduto da PRAGMA table_info.
"""

import os
import sqlite3
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

migration_name = "20260816_add_challenge_diagram_scene"


def _column_exists(cursor: sqlite3.Cursor, table: str, column: str) -> bool:
    cursor.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cursor.fetchall())


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db"):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    if not _column_exists(cursor, "challenge", "diagram_scene"):
        cursor.execute("ALTER TABLE challenge ADD COLUMN diagram_scene TEXT")
        print("  ✓ Aggiunta colonna challenge.diagram_scene")
    else:
        print("  ⏭️  challenge.diagram_scene già esistente")

    conn.commit()
    conn.close()


if __name__ == "__main__":
    upgrade_sqlite()
