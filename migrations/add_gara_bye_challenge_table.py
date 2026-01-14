"""
Migration: add_gara_bye_challenge_table
Purpose: Create gara_bye_challenge table and migrate existing X replacement data

Sprint 11 - Challenge/Gara Decoupling
See docs/decisions/ADR-004-challenge-gara-decoupling.md

This migration:
1. Creates the gara_bye_challenge table (Competition → Challenge bridge)
2. Migrates existing ChallengeAttempt.gara_id data to new table
3. Does NOT remove deprecated fields (kept for backward compatibility)
"""

import sqlite3
from datetime import datetime


def get_migration_id() -> str:
    """Return unique migration identifier."""
    return "add_gara_bye_challenge_table"


def get_dependencies() -> list:
    """Return list of migration IDs this depends on."""
    return []  # No dependencies


def check_if_applied(cursor) -> bool:
    """Check if migration has already been applied."""
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='gara_bye_challenge'
    """)
    return cursor.fetchone() is not None


def upgrade(cursor) -> None:
    """Apply the migration."""
    print("Creating gara_bye_challenge table...")

    # Create the new table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS gara_bye_challenge (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            gara_id INTEGER NOT NULL,
            challenge_attempt_id INTEGER,
            round_number INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            match_id INTEGER,
            is_completed BOOLEAN NOT NULL DEFAULT 0,
            completed_at DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (gara_id) REFERENCES gara(id) ON DELETE CASCADE,
            FOREIGN KEY (challenge_attempt_id) REFERENCES challenge_attempt(id) ON DELETE SET NULL,
            FOREIGN KEY (user_id) REFERENCES user(id) ON DELETE CASCADE,
            FOREIGN KEY (match_id) REFERENCES match(id) ON DELETE SET NULL,
            UNIQUE (gara_id, user_id, round_number)
        )
    """)

    # Create indexes for common queries
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS ix_gara_bye_challenge_gara_id
        ON gara_bye_challenge(gara_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS ix_gara_bye_challenge_attempt_id
        ON gara_bye_challenge(challenge_attempt_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS ix_gara_bye_challenge_user_id
        ON gara_bye_challenge(user_id)
    """)

    print("Table created successfully.")

    # Migrate existing data from ChallengeAttempt.gara_id
    print("Migrating existing X replacement data...")

    cursor.execute("""
        SELECT id, gara_id, round_number, user_id, completed
        FROM challenge_attempt
        WHERE gara_id IS NOT NULL
    """)

    existing_attempts = cursor.fetchall()
    migrated_count = 0

    for attempt in existing_attempts:
        attempt_id, gara_id, round_number, user_id, completed = attempt

        # Check if already migrated (shouldn't happen, but be safe)
        cursor.execute("""
            SELECT id FROM gara_bye_challenge
            WHERE challenge_attempt_id = ?
        """, (attempt_id,))

        if cursor.fetchone():
            continue

        # Find corresponding bye match if exists
        match_id = None
        if round_number:
            cursor.execute("""
                SELECT id FROM match
                WHERE gara_id = ? AND round_number = ? AND player1_id = ? AND is_bye = 1
                LIMIT 1
            """, (gara_id, round_number, user_id))
            match_row = cursor.fetchone()
            if match_row:
                match_id = match_row[0]

        # Create GaraByeChallenge record
        now = datetime.utcnow().isoformat()
        cursor.execute("""
            INSERT INTO gara_bye_challenge
            (gara_id, challenge_attempt_id, round_number, user_id, match_id,
             is_completed, completed_at, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            gara_id,
            attempt_id,
            round_number or 1,  # Default to round 1 if not specified
            user_id,
            match_id,
            1 if completed else 0,
            now if completed else None,
            now,
            now
        ))

        migrated_count += 1

    print(f"Migrated {migrated_count} existing X replacement records.")


def downgrade(cursor) -> None:
    """Revert the migration."""
    print("Dropping gara_bye_challenge table...")

    cursor.execute("DROP TABLE IF EXISTS gara_bye_challenge")

    print("Table dropped successfully.")


def run_migration(db_path: str) -> bool:
    """Run the migration on the specified database."""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        if check_if_applied(cursor):
            print(f"Migration {get_migration_id()} already applied, skipping.")
            return True

        upgrade(cursor)
        conn.commit()
        conn.close()

        print(f"Migration {get_migration_id()} completed successfully.")
        return True

    except Exception as e:
        print(f"Migration {get_migration_id()} failed: {e}")
        return False


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db") -> None:
    """Standard interface for migration runner."""
    run_migration(db_path)


if __name__ == "__main__":
    import os
    import sys

    # Default to instance database
    db_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "instance",
        "billiard_campionato.db"
    )

    if len(sys.argv) > 1:
        db_path = sys.argv[1]

    print(f"Running migration on: {db_path}")
    success = run_migration(db_path)
    sys.exit(0 if success else 1)
