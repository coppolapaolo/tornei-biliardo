"""Allinea la descrizione dell'achievement 'perfectionist' alla metrica reale.

La metrica `perfect_challenges` (achievement_metrics.py) conta i drill
**pass/fail distinti superati** (`passed=True`): i drill a punteggio non
dichiarano un massimo assoluto nel modello, quindi non vengono conteggiati. La
vecchia descrizione "Ottieni perfect score su 5 drill diversi" suggeriva invece
i drill a punteggio, ingannando chi faceva un ottimo punteggio numerico senza
veder progredire l'achievement.

Questa migrazione riallinea la descrizione in DB ("Supera 5 drill pass/fail
diversi"), coerente con il seed aggiornato (insert-only, non tocca le righe
esistenti). Nessun cambio di metrica o di sblocchi.

Idempotente: aggiorna solo se la descrizione è ancora quella vecchia.
"""

import sqlite3

migration_name = "20260606_perfectionist_honest_description"

_SLUG = "perfectionist"
_OLD = "Ottieni perfect score su 5 drill diversi"
_NEW = "Supera 5 drill pass/fail diversi"


def _table_exists(cursor: sqlite3.Cursor, table: str) -> bool:
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    )
    return cursor.fetchone() is not None


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db"):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    if not _table_exists(cursor, "achievement"):
        print("  ⏭️  tabella achievement assente, niente da aggiornare")
        conn.close()
        return

    cursor.execute(
        "UPDATE achievement SET description = ? " "WHERE slug = ? AND description = ?",
        (_NEW, _SLUG, _OLD),
    )
    print(f"  ✓ Descrizione 'perfectionist' aggiornata su {cursor.rowcount} riga/e")

    conn.commit()
    conn.close()
