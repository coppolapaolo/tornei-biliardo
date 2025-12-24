"""Database migration: Add gamification configuration tables.

Task 6.3: DB-backed gamification configuration system
Date: 2025-12-24

This migration adds tables for admin-configurable gamification rules:
- gamification_config: Key-value store for XP rates, level curve params
- level_unlock: Feature unlocks at specific levels
- streak_milestone: Streak milestone rewards configuration

Tables Created:
- gamification_config
- level_unlock
- streak_milestone

Seeds initial data from xp_config.py hardcoded values for backward compatibility.
"""

import sqlite3
from pathlib import Path
from datetime import datetime


# Default values from xp_config.py for initial seeding
DEFAULT_XP_RATES = [
    ("xp_match_win", 50, "XP awarded for winning a match", "xp_rates"),
    ("xp_match_loss", 20, "XP awarded for losing a match", "xp_rates"),
    ("xp_tournament_inscription", 25, "XP for registering to a tournament", "xp_rates"),
    ("xp_tournament_completion", 100, "XP for completing a tournament", "xp_rates"),
    ("xp_tournament_podium", 200, "Bonus XP for top 3 finish", "xp_rates"),
    ("xp_tournament_win", 500, "Bonus XP for winning a tournament", "xp_rates"),
    ("xp_streak_bonus", 30, "XP per week of streak", "xp_rates"),
    ("xp_challenge_completion", 150, "XP for completing a challenge", "xp_rates"),
]

DEFAULT_LEVEL_PARAMS = [
    ("level_base_xp", 100, "Base XP for level 1", "level_curve"),
    ("level_power", 150, "Level curve power (divided by 100, so 150 = 1.5)", "level_curve"),
]

DEFAULT_STREAK_CONFIG = [
    ("max_freeze_count", 3, "Maximum freeze tokens a user can hold", "streak"),
]

DEFAULT_LEVEL_UNLOCKS = [
    (5, "match_proposals", "Proposte Match", "Puoi proporre match individuali"),
    (10, "tournament_creation", "Creazione Tornei", "Accesso all'assistente creazione tornei"),
    (15, "priority_invites", "Inviti Prioritari", "Ricevi inviti prioritari ai tornei"),
    (20, "custom_badge_display", "Badge Personalizzati", "Puoi scegliere quali badge mostrare"),
    (25, "venue_suggestion", "Suggerimenti Venue", "Puoi suggerire nuove venue"),
    (30, "challenge_creation", "Creazione Challenge", "Puoi creare challenge per altri"),
    (40, "director_fast_track", "Direttore Fast-Track", "Richiesta direttore auto-approvata"),
    (50, "legend_status", "Status Leggenda", "Accesso alla Hall of Fame"),
]

DEFAULT_STREAK_MILESTONES = [
    # (weeks, freeze_tokens, xp_bonus_multiplier, is_recurring)
    (4, 1, 1, False),    # Prima milestone: 1 freeze token
    (12, 1, 1, True),    # Milestone trimestrale: 1 freeze (ricorrente)
    (52, 2, 1, False),   # Milestone annuale: 2 freeze tokens
]


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db") -> None:
    """Run migration for SQLite (development)."""
    db_file = Path(db_path)
    if not db_file.exists():
        print(f"Database not found: {db_path}")
        print("   Run application first to create database")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print(f"Migrating SQLite database: {db_path}")

    try:
        # 1. Create gamification_config table
        print("   Creating 'gamification_config' table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS gamification_config (
                key VARCHAR(50) PRIMARY KEY,
                value INTEGER NOT NULL,
                description VARCHAR(255),
                category VARCHAR(50) NOT NULL DEFAULT 'general',
                updated_by_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (updated_by_id) REFERENCES user(id) ON DELETE SET NULL
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_gamification_config_category
            ON gamification_config(category)
        """)

        # 2. Create level_unlock table
        print("   Creating 'level_unlock' table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS level_unlock (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                level INTEGER NOT NULL UNIQUE,
                feature_code VARCHAR(50) NOT NULL,
                feature_name VARCHAR(100) NOT NULL,
                description VARCHAR(255),
                is_active BOOLEAN NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_level_unlock_level
            ON level_unlock(level)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_level_unlock_active
            ON level_unlock(is_active)
        """)

        # 3. Create streak_milestone table
        print("   Creating 'streak_milestone' table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS streak_milestone (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                weeks INTEGER NOT NULL UNIQUE,
                freeze_tokens INTEGER NOT NULL DEFAULT 1,
                xp_bonus_multiplier INTEGER NOT NULL DEFAULT 1,
                is_recurring BOOLEAN NOT NULL DEFAULT 0,
                is_active BOOLEAN NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_streak_milestone_weeks
            ON streak_milestone(weeks)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_streak_milestone_active
            ON streak_milestone(is_active)
        """)

        conn.commit()
        print("   Tables created successfully!")

        # Seed initial data
        print("\n   Seeding initial configuration data...")
        seed_initial_data(cursor)
        conn.commit()

        print("\nMigration completed successfully!")

        # Verify migration
        print("\nVerifying migration...")

        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name IN (
                'gamification_config', 'level_unlock', 'streak_milestone'
            )
            ORDER BY name
        """)
        tables = [row[0] for row in cursor.fetchall()]

        expected_tables = ['gamification_config', 'level_unlock', 'streak_milestone']

        for table in expected_tables:
            if table in tables:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                print(f"   Table {table}: {count} rows")
            else:
                print(f"   Table {table}: MISSING!")

    except sqlite3.OperationalError as e:
        if "already exists" in str(e).lower():
            print(f"Migration already applied: {e}")
            print("   Skipping table creation, checking seed data...")
            seed_initial_data(cursor)
            conn.commit()
        else:
            print(f"Migration failed: {e}")
            conn.rollback()
            raise
    finally:
        conn.close()


def seed_initial_data(cursor: sqlite3.Cursor) -> None:
    """Seed initial configuration data from xp_config.py defaults."""
    now = datetime.utcnow().isoformat()

    # Seed XP rates
    print("      Seeding XP rates...")
    for key, value, description, category in DEFAULT_XP_RATES:
        cursor.execute("""
            INSERT OR IGNORE INTO gamification_config (key, value, description, category, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (key, value, description, category, now, now))

    # Seed level curve params
    print("      Seeding level curve parameters...")
    for key, value, description, category in DEFAULT_LEVEL_PARAMS:
        cursor.execute("""
            INSERT OR IGNORE INTO gamification_config (key, value, description, category, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (key, value, description, category, now, now))

    # Seed streak config
    print("      Seeding streak configuration...")
    for key, value, description, category in DEFAULT_STREAK_CONFIG:
        cursor.execute("""
            INSERT OR IGNORE INTO gamification_config (key, value, description, category, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (key, value, description, category, now, now))

    # Seed level unlocks
    print("      Seeding level unlocks...")
    for level, feature_code, feature_name, description in DEFAULT_LEVEL_UNLOCKS:
        cursor.execute("""
            INSERT OR IGNORE INTO level_unlock (level, feature_code, feature_name, description, is_active, created_at, updated_at)
            VALUES (?, ?, ?, ?, 1, ?, ?)
        """, (level, feature_code, feature_name, description, now, now))

    # Seed streak milestones
    print("      Seeding streak milestones...")
    for weeks, freeze_tokens, xp_multiplier, is_recurring in DEFAULT_STREAK_MILESTONES:
        cursor.execute("""
            INSERT OR IGNORE INTO streak_milestone (weeks, freeze_tokens, xp_bonus_multiplier, is_recurring, is_active, created_at, updated_at)
            VALUES (?, ?, ?, ?, 1, ?, ?)
        """, (weeks, freeze_tokens, xp_multiplier, is_recurring, now, now))

    print("      Seed data complete!")


def downgrade_sqlite(db_path: str = "instance/billiard_campionato.db") -> None:
    """Rollback migration for SQLite."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print(f"Rolling back gamification config tables from: {db_path}")

    try:
        tables = ['streak_milestone', 'level_unlock', 'gamification_config']

        for table in tables:
            cursor.execute(f"DROP TABLE IF EXISTS {table}")
            print(f"   Dropped {table} table")

        conn.commit()
        print("Rollback completed successfully!")

    except Exception as e:
        print(f"Rollback failed: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    import sys

    print("=" * 60)
    print("Gamification Configuration Tables Migration (Task 6.3)")
    print("=" * 60)
    print()

    if len(sys.argv) > 1:
        if sys.argv[1] == "downgrade":
            downgrade_sqlite()
        else:
            print(f"Unknown command: {sys.argv[1]}")
            print("\nUsage:")
            print("  python migrations/add_gamification_config_tables.py           # Apply migration")
            print("  python migrations/add_gamification_config_tables.py downgrade # Rollback")
            sys.exit(1)
    else:
        upgrade_sqlite()

    print()
    print("=" * 60)
