"""Backfill current_player*/waiting_player on historic walkover trios.

Source: deferred-work.md A5 (2026-04-19). Trio walkovers created BEFORE the
walkover-side-effects-unified refactor were completed without calling
`TrioMatch.initialize_matchup()`, so their `current_player1_id`,
`current_player2_id` and `waiting_player_id` remain NULL. An admin reset of
such a trio crashes the serializer (see spec-walkover-side-effects-unified).

Target rows: completed trios with zero racks played and NULL current players.
For rack 1 the matchup is always (P1 vs P2, P3 waits) regardless of distance
— see `TrioConfig.get_matchup_for_rack(1)` = (0, 1, 2). So the backfill is
a single UPDATE per row mapping player*_id -> current/waiting columns.

Idempotent: the NULL filter means a second run touches zero rows.
"""

import sqlite3

migration_name = "20260419_backfill_walkover_trio_matchup"


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db"):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # `total_racks_played` is a SQLAlchemy computed property counting active
    # (non-soft-deleted) trio_rack rows. In SQL we replicate with NOT EXISTS
    # — a walkover trio has zero live trio_rack entries.
    target_predicate = """
        is_completed = 1
        AND current_player1_id IS NULL
        AND NOT EXISTS (
            SELECT 1 FROM trio_rack
            WHERE trio_rack.trio_match_id = trio_match.id
              AND trio_rack.is_deleted = 0
        )
    """

    cursor.execute(f"SELECT COUNT(*) FROM trio_match WHERE {target_predicate}")
    target_count = cursor.fetchone()[0]

    if target_count == 0:
        print("  ⏭️  No historic walkover trios need backfill")
        conn.close()
        return

    cursor.execute(f"""
        UPDATE trio_match
        SET current_player1_id = player1_id,
            current_player2_id = player2_id,
            waiting_player_id = player3_id
        WHERE {target_predicate}
        """)
    conn.commit()
    print(f"  ✓ Backfilled {target_count} walkover trio row(s)")
    conn.close()
