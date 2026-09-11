"""Aggiunge live_event — gli aggiornamenti live passano dal database.

Fino a oggi gli eventi che le pagine aperte chiedono ogni tre secondi (rack
segnato, partita chiusa, turno nuovo) stavano in un dizionario Python dentro
`routes/sse.py`. In produzione la web app gira su **tre processi** uWSGI, con
tre dizionari che non si parlano: un evento scritto dal worker che ha servito
il giocatore lo vedeva solo un poll capitato sullo stesso worker, e siccome il
cursore del client avanza a ogni poll, quello mancato era perso. Circa un
evento su tre arrivava. Vedi ADR-057.

La tabella è l'unica cosa che i tre processi condividono. Vive di righe
effimere: la pulizia cancella tutto ciò che ha più di un minuto, quindi la sua
dimensione è quella di un minuto di gara, poche decine di righe.

``AUTOINCREMENT`` è necessario, non decorativo: il cursore del client è l'id
dell'ultimo evento visto, e col rowid semplice SQLite riassegna il numero
della riga più alta appena cancellata.

Nessun backfill: gli eventi vecchi sono, per definizione, scaduti.

Idempotente: CREATE TABLE IF NOT EXISTS + CREATE INDEX IF NOT EXISTS.
"""

import os
import sqlite3
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

migration_name = "20260902_live_event"


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db"):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS live_event (
            id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
            scope VARCHAR(32) NOT NULL,
            scope_id INTEGER NOT NULL,
            event_type VARCHAR(64) NOT NULL,
            payload TEXT NOT NULL,
            ts FLOAT NOT NULL,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL
        )
        """)
    print("  ✓ Tabella live_event")

    cursor.execute(
        "CREATE INDEX IF NOT EXISTS ix_live_event_scope "
        "ON live_event (scope, scope_id, id)"
    )
    print("  ✓ Indice su (scope, scope_id, id)")

    conn.commit()
    conn.close()


if __name__ == "__main__":
    upgrade_sqlite()
