"""Riattiva i 4 achievement social/avversari resi ottenibili.

Source: GAMIFICATION_V3 §11-ter — "popolare ciò che funziona".

La migrazione 20260605 aveva disattivato 12 achievement non ottenibili. Quattro
di essi (social/avversari) sono ora **metric-driven** (models/gamification/
achievement_metrics.py) e cablati agli eventi reali, quindi sono diventati
ottenibili:

  - social_butterfly   → proposte di partita create (MatchProposal.proposer)
  - popular_player     → proposte/inviti accettati (MatchProposal.accepted_by)
  - diverse_competitor → avversari distinti affrontati
  - community_pillar   → avversari distinti affrontati (soglia alta)

Questa migrazione li riattiva sui DB esistenti (il seeding idempotente salta le
righe già presenti, quindi non basterebbe cambiare i seed). È complementare a
20260605: stato netto disattivato = 12 − 4 = 8, coerente con
UNOBTAINABLE_ACHIEVEMENT_SLUGS nei seed.

Idempotente: l'UPDATE riporta a 1 solo ciò che è ancora a 0.
"""

import sqlite3

migration_name = "20260606_reactivate_social_achievements"

REACTIVATED_ACHIEVEMENT_SLUGS = [
    "social_butterfly",
    "popular_player",
    "diverse_competitor",
    "community_pillar",
]


def _table_exists(cursor: sqlite3.Cursor, table: str) -> bool:
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    )
    return cursor.fetchone() is not None


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db"):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    if not _table_exists(cursor, "achievement"):
        print("  ⏭️  tabella achievement assente, niente da riattivare")
        conn.close()
        return

    placeholders = ",".join("?" for _ in REACTIVATED_ACHIEVEMENT_SLUGS)
    cursor.execute(
        f"UPDATE achievement SET is_active = 1 "
        f"WHERE slug IN ({placeholders}) AND is_active = 0",
        REACTIVATED_ACHIEVEMENT_SLUGS,
    )
    print(f"  ✓ Riattivati {cursor.rowcount} achievement social/avversari")

    conn.commit()
    conn.close()
