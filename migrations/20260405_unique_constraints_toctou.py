"""Add UNIQUE constraints to prevent TOCTOU race conditions.

Creates two unique indexes:
  1. individual_match(proposal_id) — prevents double-accept of same proposal
     (WHERE proposal_id IS NOT NULL — matches without proposal are allowed)
  2. proposal_invitation(proposal_id, invited_user_id) — prevents duplicate invites

SQLite allows multiple NULLs in UNIQUE columns by default, so the partial index
on (1) is explicit for clarity and portability.

Idempotent: uses IF NOT EXISTS. Pre-checks for existing duplicates and
halts loudly if found (no auto-fix).
"""

import sqlite3

migration_name = "20260405_unique_constraints_toctou"


def _count_duplicates(cursor: sqlite3.Cursor, query: str) -> int:
    cursor.execute(query)
    row = cursor.fetchone()
    return row[0] if row and row[0] is not None else 0


def upgrade_sqlite(db_path: str):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # --- Pre-check: duplicates on individual_match.proposal_id ---
    dup_matches = _count_duplicates(
        cursor,
        """
        SELECT COUNT(*) FROM (
            SELECT proposal_id FROM individual_match
            WHERE proposal_id IS NOT NULL
            GROUP BY proposal_id HAVING COUNT(*) > 1
        )
        """,
    )
    if dup_matches > 0:
        conn.close()
        raise RuntimeError(
            f"Cannot apply UNIQUE constraint: {dup_matches} duplicate "
            f"proposal_id values in individual_match. Dedupe manually before "
            f"running this migration."
        )

    # --- Pre-check: duplicates on proposal_invitation(proposal_id, invited_user_id) ---
    dup_invites = _count_duplicates(
        cursor,
        """
        SELECT COUNT(*) FROM (
            SELECT proposal_id, invited_user_id FROM proposal_invitation
            GROUP BY proposal_id, invited_user_id HAVING COUNT(*) > 1
        )
        """,
    )
    if dup_invites > 0:
        conn.close()
        raise RuntimeError(
            f"Cannot apply UNIQUE constraint: {dup_invites} duplicate "
            f"(proposal_id, invited_user_id) pairs in proposal_invitation. "
            f"Dedupe manually before running this migration."
        )

    # --- Create UNIQUE indexes (idempotent) ---
    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_individual_match_proposal
        ON individual_match(proposal_id)
        WHERE proposal_id IS NOT NULL
        """)
    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_proposal_invitation_user
        ON proposal_invitation(proposal_id, invited_user_id)
        """)

    conn.commit()
    conn.close()
    print(
        (
            "  Created UNIQUE indexes: uq_individual_match_proposal, "
            "uq_proposal_invitation_user"
        )
    )
