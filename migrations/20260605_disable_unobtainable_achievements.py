"""Disattiva gli achievement non ottenibili sui DB esistenti.

Source: GAMIFICATION_V3_HANDOFF.md (Fase 1 / Task B) e GAMIFICATION_V3 §11-ter.

`seed_achievements` è idempotente e SALTA le righe già presenti: cambiare
`is_active` nei seed NON aggiorna i DB già popolati in produzione. Serve quindi
questo UPDATE esplicito.

Achievement disattivati (12), in due categorie:
  - 2 stub di requisito sempre False (`_check_requirements`):
      win_streak       → hot_streak, unstoppable
      category_reached → category_climber, elite_player
  - 8 progress-based mai incrementati (nessun handler li cabla agli eventi):
      social_butterfly, popular_player, diverse_competitor, community_pillar,
      strategy_explorer, challenge_master, perfectionist, drill_addict

`is_hidden` non li nasconde (il template mostra "???"); il service filtra già
`is_active=True`, quindi `is_active=0` li rimuove davvero dalla UI.

Idempotente: l'UPDATE è naturalmente ripetibile (riporta a 0 ciò che è già 0).
Lista volutamente hardcoded per non importare lo stack applicativo nel runner
sqlite3; un test di consistenza
(tests/new/integration/gamification/test_achievement_active_filter.py) verifica
che coincida con UNOBTAINABLE_ACHIEVEMENT_SLUGS dei seed.
"""

import sqlite3

migration_name = "20260605_disable_unobtainable_achievements"

UNOBTAINABLE_ACHIEVEMENT_SLUGS = [
    # stub win_streak (manca tracking win-streak consecutivi)
    "hot_streak",
    "unstoppable",
    # stub category_reached (manca tracking categoria giocatore)
    "category_climber",
    "elite_player",
    # progress-based non cablati agli eventi
    "social_butterfly",
    "popular_player",
    "diverse_competitor",
    "community_pillar",
    "strategy_explorer",
    "challenge_master",
    "perfectionist",
    "drill_addict",
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
        print("  ⏭️  tabella achievement assente, niente da disattivare")
        conn.close()
        return

    placeholders = ",".join("?" for _ in UNOBTAINABLE_ACHIEVEMENT_SLUGS)
    cursor.execute(
        f"UPDATE achievement SET is_active = 0 "
        f"WHERE slug IN ({placeholders}) AND is_active = 1",
        UNOBTAINABLE_ACHIEVEMENT_SLUGS,
    )
    print(f"  ✓ Disattivati {cursor.rowcount} achievement non ottenibili")

    conn.commit()
    conn.close()
