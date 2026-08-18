"""Aggiunge ``challenge.max_score``: il tetto di punteggio dell'esercizio.

Facoltativo, e resta NULL su tutti gli esercizi esistenti — che e' il valore
giusto, non un buco da riempire: «non lo so» e «non ha un tetto» si scrivono
allo stesso modo, e indovinare un massimo per prove gia' in catalogo
significherebbe inventare una regola che nessuno ha mai dichiarato.

Non tocca ``exam_challenge.max_score``, che risponde a un'altra domanda: quanto
pesa quell'esercizio **dentro quell'esame** (ADR-042). Questo dice quanto vale
al massimo la prova in se'. Il primo fa da valore proposto al secondo.

Idempotente: se la colonna c'e' gia', non fa niente.
"""

import sqlite3

migration_name = "20260818_challenge_max_score"


def _column_exists(cursor: sqlite3.Cursor, table: str, column: str) -> bool:
    cursor.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cursor.fetchall())


def _table_exists(cursor: sqlite3.Cursor, table: str) -> bool:
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    )
    return cursor.fetchone() is not None


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db"):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    if not _table_exists(cursor, "challenge"):
        print("  ⏭️  tabella challenge assente, niente da fare")
        conn.close()
        return

    if _column_exists(cursor, "challenge", "max_score"):
        print("  ⏭️  challenge.max_score già presente")
    else:
        cursor.execute("ALTER TABLE challenge ADD COLUMN max_score INTEGER")
        print("  ✓ challenge.max_score aggiunta (NULL su tutti gli esercizi)")

    conn.commit()
    conn.close()
