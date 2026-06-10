"""Database migration: Add complete gamification system tables.

FASE 9: Complete Gamification Database Setup
Date: 2025-12-24

This migration adds all tables for the gamification system:
- user_level: Player XP and level progression
- xp_transaction: Audit log for all XP awards
- achievement: Predefined achievements with requirements
- user_achievement: User progress and unlock tracking
- streak_tracker: Weekly streak tracking with freeze mechanics
- leaderboard_entry: Cached leaderboard rankings
- quest: Weekly/monthly community goals
- quest_participation: Player progress on quests

Tables Created:
- user_level
- xp_transaction
- achievement
- user_achievement
- streak_tracker
- leaderboard_entry
- quest
- quest_participation
"""

import sqlite3
from pathlib import Path


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
        # 1. Create user_level table
        print("   Creating 'user_level' table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_level (
                user_id INTEGER PRIMARY KEY,
                current_level INTEGER NOT NULL DEFAULT 1,
                current_xp INTEGER NOT NULL DEFAULT 0,
                total_xp INTEGER NOT NULL DEFAULT 0,
                highest_level_reached INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES user(id) ON DELETE CASCADE
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_user_level_total_xp
            ON user_level(total_xp)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_user_level_current_level
            ON user_level(current_level)
        """)

        # 2. Create xp_transaction table
        print("   Creating 'xp_transaction' table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS xp_transaction (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                transaction_type VARCHAR(50) NOT NULL,
                xp_amount INTEGER NOT NULL,
                reason VARCHAR(255),
                level_before INTEGER NOT NULL,
                level_after INTEGER NOT NULL,
                related_entities TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES user(id) ON DELETE CASCADE
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_xp_transaction_user_created
            ON xp_transaction(user_id, created_at)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_xp_transaction_type
            ON xp_transaction(transaction_type)
        """)

        # 3. Create achievement table (if not exists from previous migration)
        print("   Creating 'achievement' table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS achievement (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slug VARCHAR(100) NOT NULL UNIQUE,
                name VARCHAR(100) NOT NULL,
                description TEXT NOT NULL,
                icon_path VARCHAR(255),
                category VARCHAR(20) NOT NULL,
                difficulty VARCHAR(20) NOT NULL DEFAULT 'common',
                requirements TEXT NOT NULL,
                is_progressive BOOLEAN NOT NULL DEFAULT 0,
                xp_reward INTEGER NOT NULL DEFAULT 0,
                is_hidden BOOLEAN NOT NULL DEFAULT 0,
                is_active BOOLEAN NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_achievement_category
            ON achievement(category)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_achievement_slug
            ON achievement(slug)
        """)

        # 4. Create user_achievement table (if not exists)
        print("   Creating 'user_achievement' table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_achievement (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                achievement_id INTEGER NOT NULL,
                current_progress INTEGER NOT NULL DEFAULT 0,
                is_unlocked BOOLEAN NOT NULL DEFAULT 0,
                unlocked_at TIMESTAMP,
                is_displayed BOOLEAN NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES user(id) ON DELETE CASCADE,
                FOREIGN KEY (achievement_id) REFERENCES achievement(id) ON DELETE CASCADE,
                UNIQUE(user_id, achievement_id)
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_user_achievement_user_id
            ON user_achievement(user_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_user_achievement_unlocked
            ON user_achievement(is_unlocked)
        """)

        # 5. Create streak_tracker table
        print("   Creating 'streak_tracker' table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS streak_tracker (
                user_id INTEGER NOT NULL,
                streak_type VARCHAR(30) NOT NULL,
                current_streak INTEGER NOT NULL DEFAULT 0,
                longest_streak INTEGER NOT NULL DEFAULT 0,
                last_activity_week INTEGER,
                last_activity_year INTEGER,
                freeze_count INTEGER NOT NULL DEFAULT 0,
                total_freeze_earned INTEGER NOT NULL DEFAULT 0,
                last_freeze_earned_at DATE,
                last_freeze_used_at DATE,
                milestone_4_reached BOOLEAN DEFAULT 0,
                milestone_12_reached BOOLEAN DEFAULT 0,
                milestone_52_reached BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, streak_type),
                FOREIGN KEY (user_id) REFERENCES user(id) ON DELETE CASCADE
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_streak_current
            ON streak_tracker(current_streak)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_streak_longest
            ON streak_tracker(longest_streak)
        """)

        # 6. Create leaderboard_entry table
        print("   Creating 'leaderboard_entry' table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS leaderboard_entry (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                leaderboard_type VARCHAR(30) NOT NULL,
                user_id INTEGER NOT NULL,
                rank INTEGER NOT NULL,
                score REAL NOT NULL,
                period_start DATE,
                period_end DATE,
                calculated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                is_stale BOOLEAN NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES user(id) ON DELETE CASCADE
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_leaderboard_type_rank
            ON leaderboard_entry(leaderboard_type, rank)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_leaderboard_type_score
            ON leaderboard_entry(leaderboard_type, score)
        """)

        # 7. Create quest table
        print("   Creating 'quest' table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS quest (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(100) NOT NULL,
                description TEXT NOT NULL,
                quest_type VARCHAR(20) NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'upcoming',
                start_date TIMESTAMP NOT NULL,
                end_date TIMESTAMP NOT NULL,
                requirements TEXT NOT NULL,
                xp_reward INTEGER NOT NULL DEFAULT 150,
                badge_icon VARCHAR(255),
                participant_count INTEGER NOT NULL DEFAULT 0,
                completion_count INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_quest_status
            ON quest(status)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_quest_dates
            ON quest(start_date, end_date)
        """)

        # 8. Create quest_participation table
        print("   Creating 'quest_participation' table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS quest_participation (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                quest_id INTEGER NOT NULL,
                current_progress INTEGER NOT NULL DEFAULT 0,
                target_progress INTEGER NOT NULL,
                is_completed BOOLEAN NOT NULL DEFAULT 0,
                completed_at TIMESTAMP,
                xp_awarded INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES user(id) ON DELETE CASCADE,
                FOREIGN KEY (quest_id) REFERENCES quest(id) ON DELETE CASCADE,
                UNIQUE(user_id, quest_id)
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_quest_participation_user
            ON quest_participation(user_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_quest_participation_quest
            ON quest_participation(quest_id)
        """)

        conn.commit()
        print("Migration completed successfully!")

        # Verify migration
        print("\nVerifying migration...")

        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name IN (
                'user_level', 'xp_transaction', 'achievement',
                'user_achievement', 'streak_tracker',
                'leaderboard_entry', 'quest', 'quest_participation'
            )
            ORDER BY name
        """)
        tables = [row[0] for row in cursor.fetchall()]

        expected_tables = [
            "achievement",
            "leaderboard_entry",
            "quest",
            "quest_participation",
            "streak_tracker",
            "user_achievement",
            "user_level",
            "xp_transaction",
        ]

        for table in expected_tables:
            if table in tables:
                print(f"   Table {table} created")
            else:
                print(f"   Table {table} missing!")

    except sqlite3.OperationalError as e:
        if "already exists" in str(e).lower():
            print(f"Migration already applied: {e}")
            print("   Skipping...")
        else:
            print(f"Migration failed: {e}")
            conn.rollback()
            raise
    finally:
        conn.close()


def downgrade_sqlite(db_path: str = "instance/billiard_campionato.db") -> None:
    """Rollback migration for SQLite."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print(f"Rolling back gamification tables from: {db_path}")

    try:
        tables = [
            "quest_participation",
            "quest",
            "leaderboard_entry",
            "streak_tracker",
            "user_achievement",
            "achievement",
            "xp_transaction",
            "user_level",
        ]

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
    print("Gamification System Migration (FASE 9)")
    print("=" * 60)
    print()

    if len(sys.argv) > 1:
        if sys.argv[1] == "downgrade":
            downgrade_sqlite()
        else:
            print(f"Unknown command: {sys.argv[1]}")
            print("\nUsage:")
            print(
                "  python migrations/add_gamification_tables.py           # Apply migration"
            )
            print("  python migrations/add_gamification_tables.py downgrade # Rollback")
            sys.exit(1)
    else:
        upgrade_sqlite()

    print()
    print("=" * 60)
