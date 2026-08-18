"""Aggiunge user_session — la traccia degli accessi (chi, quando, per quanto).

Non c'era niente del genere. La scheda «retention» dei KPI mostra DAU/WAU/MAU
da mesi, ma li calcola sui **match giocati** (``Match.updated_at``): chi entra
ogni giorno e non gioca risulta dormiente, e una domanda semplice come «questo
utente si è mai collegato dopo essersi registrato?» non aveva risposta da
nessuna parte.

Una riga = una permanenza sul sito. ``started_at`` è l'accesso, ``last_seen_at``
l'ultima pagina servita, ``ended_at`` il logout esplicito — che quasi nessuno
fa, ed è il motivo per cui la durata si misura su ``last_seen_at``: è l'ultimo
istante in cui sappiamo che c'era, e dire di più sarebbe inventare.

Cosa **non** c'è dentro, di proposito: l'indirizzo IP (dato personale da
difendere, cancellare su richiesta e giustificare — per rispondere a «chi si
collega e quando» non serve) e lo user agent grezzo, che è un'impronta. Ne
resta la sola famiglia di dispositivo: ``mobile`` / ``tablet`` / ``desktop``.

Nessun backfill: prima di questa tabella l'informazione non esisteva da
nessuna parte, e inventarla dalle date di registrazione darebbe numeri
plausibili e falsi. La storia comincia dal primo accesso dopo il deploy.

Idempotente: CREATE TABLE IF NOT EXISTS + CREATE INDEX IF NOT EXISTS.
"""

import os
import sqlite3
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

migration_name = "20260818_add_user_session"


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db"):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_session (
            id INTEGER NOT NULL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES user(id) ON DELETE CASCADE,
            started_at DATETIME NOT NULL,
            last_seen_at DATETIME NOT NULL,
            ended_at DATETIME,
            device VARCHAR(16),
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL
        )
        """)
    print("  ✓ Tabella user_session")

    # Gli indici seguono le tre domande della schermata: «chi», «quando»,
    # «e' ancora collegato».
    for nome, colonne in (
        ("ix_user_session_user_id", "user_id"),
        ("ix_user_session_started_at", "started_at"),
        ("ix_user_session_last_seen_at", "last_seen_at"),
    ):
        cursor.execute(f"CREATE INDEX IF NOT EXISTS {nome} ON user_session ({colonne})")
    print("  ✓ Indici su user_id, started_at, last_seen_at")

    conn.commit()
    conn.close()


if __name__ == "__main__":
    upgrade_sqlite()
