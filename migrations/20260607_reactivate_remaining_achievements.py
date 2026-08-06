"""Riattiva gli ultimi 8 achievement, ora resi ottenibili (metric-driven).

Source: GAMIFICATION_V3 §11-ter — "popolare ciò che funziona".

Completata la Fase 2, ogni achievement ha una sorgente dati reale
(models/gamification/achievement_metrics.py + rami booleani in
achievement_service). Gli ultimi 8 ancora disattivati diventano ottenibili:

  - hot_streak / unstoppable        → serie di vittorie consecutive (Match)
  - category_climber / elite_player → categoria giocatore (PlayerCategory)
  - challenge_master / drill_addict → drill completati (ChallengeAttempt)
  - perfectionist                   → drill superati "perfetti" (passed=True)
  - strategy_explorer               → strategie di matchmaking provate (Gara)

Riattiva queste righe sui DB esistenti (il seeding idempotente salta le righe già
presenti). Insieme a 20260605 (disattiva 12) e 20260606 (riattiva 4), lo stato
netto disattivato torna a 0 — coerente con UNOBTAINABLE_ACHIEVEMENT_SLUGS (vuoto)
nei seed.

Idempotente: l'UPDATE riporta a 1 solo ciò che è ancora a 0.
"""

import sqlite3

migration_name = "20260607_reactivate_remaining_achievements"

REACTIVATED_ACHIEVEMENT_SLUGS = [
    "hot_streak",
    "unstoppable",
    "category_climber",
    "elite_player",
    "challenge_master",
    "drill_addict",
    "perfectionist",
    "strategy_explorer",
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
    print(f"  ✓ Riattivati {cursor.rowcount} achievement (metric-driven)")

    conn.commit()
    conn.close()
