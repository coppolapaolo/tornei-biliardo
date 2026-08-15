"""Aggiunge user.timezone — il fuso orario di chi legge (ADR-043).

La piattaforma mostrava ogni orario in ``Europe/Rome``, scritto a mano dentro
i filtri Jinja. Per un'app pensata anche in inglese è sbagliato: un giocatore a
Londra vede «21:00» per un match che per lui comincia alle 20:00, e non ha modo
di accorgersene — l'orario è plausibile, solo sbagliato.

La colonna tiene il nome IANA del fuso (``Europe/Rome``, ``America/New_York``).
Non lo si chiede all'utente: lo si deduce dal browser al login e lo si
riverifica a ogni pagina. Ma va **scritto**, non solo dedotto: promemoria e
notifiche nascono in uno scheduled task, dove nessun browser esiste, e le
caselle di posta non eseguono JavaScript.

Nessun backfill, ed è deliberato. Indovinare il fuso degli account esistenti
non si può fare da qui: l'unico che lo sa è il browser, e lo dirà al prossimo
accesso. Fino ad allora NULL, che significa «mai dedotto» e si comporta come
prima — ora italiana. Distinguere «non lo so» da «è Roma» conta: il primo si
correggerà da solo, il secondo resterebbe sbagliato per sempre per chi sta
altrove.

Idempotente: ALTER preceduto da PRAGMA table_info.
"""

import os
import sqlite3
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

migration_name = "20260815_add_user_timezone"


def _column_exists(cursor: sqlite3.Cursor, table: str, column: str) -> bool:
    cursor.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cursor.fetchall())


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db"):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    if not _column_exists(cursor, "user", "timezone"):
        cursor.execute("ALTER TABLE user ADD COLUMN timezone VARCHAR(64)")
        print("  ✓ Aggiunta colonna user.timezone")
    else:
        print("  ⏭️  user.timezone già esistente")

    cursor.execute("SELECT COUNT(*) FROM user WHERE timezone IS NULL")
    pending = cursor.fetchone()[0]
    print(
        f"  ℹ️  {pending} utenti senza fuso: lo dedurranno dal browser al "
        "prossimo accesso, fino ad allora leggono in ora italiana"
    )

    conn.commit()
    conn.close()


if __name__ == "__main__":
    upgrade_sqlite()
