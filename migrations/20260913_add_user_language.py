"""Aggiunge user.language — la lingua in cui scrivere a un utente (ADR-062).

Le notifiche venivano tradotte nella lingua di **chi preme il pulsante**: un
giocatore inglese ritirato da un direttore italiano leggeva in italiano, e un
promemoria composto da uno scheduled task usciva nella lingua di ripiego per
chiunque. Il testo è per qualcun altro, quindi va composto nella sua lingua; e
fuori da una pagina — scheduled task, thread in background — la lingua del
destinatario c'è solo se è scritta in colonna. Stesso ragionamento del fuso
(ADR-043, ``user.timezone``).

La colonna tiene un codice che l'app parla (``it``, ``en``). La scrive il
selettore della lingua, che è una scelta, oppure la deduzione dal browser, che
riempie solo un vuoto e non scavalca mai una scelta.

Nessun backfill, ed è deliberato: indovinare la lingua degli account esistenti
non si può fare da qui. NULL vuol dire «mai dedotta» e si comporta come prima,
in italiano; la prima pagina aperta da quell'utente la riempie.

Idempotente: ALTER preceduto da PRAGMA table_info.
"""

import os
import sqlite3
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

migration_name = "20260913_add_user_language"


def _column_exists(cursor: sqlite3.Cursor, table: str, column: str) -> bool:
    cursor.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cursor.fetchall())


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db"):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    if not _column_exists(cursor, "user", "language"):
        cursor.execute("ALTER TABLE user ADD COLUMN language VARCHAR(8)")
        print("  ✓ Aggiunta colonna user.language")
    else:
        print("  ⏭️  user.language già esistente")

    cursor.execute("SELECT COUNT(*) FROM user WHERE language IS NULL")
    pending = cursor.fetchone()[0]
    print(
        f"  ℹ️  {pending} utenti senza lingua: la dedurranno dal browser alla "
        "prossima pagina, fino ad allora ricevono le notifiche in italiano"
    )

    conn.commit()
    conn.close()


if __name__ == "__main__":
    upgrade_sqlite()
