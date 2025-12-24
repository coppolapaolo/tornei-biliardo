"""Database migration: Add achievement system tables.

FASE 2: Achievement System
Date: 2025-12-24

This migration adds tables for the gamification achievement system:
- achievement: Predefined achievements with requirements and rewards
- user_achievement: User progress and unlock tracking

Tables Created:
- achievement
- user_achievement

Features:
- Progressive and non-progressive achievement types
- JSON-based flexible requirement system
- XP rewards on achievement unlock
- Achievement categorization and difficulty tiers
"""

import sqlite3
from pathlib import Path


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db") -> None:
    """Run migration for SQLite (development)."""
    db_file = Path(db_path)
    if not db_file.exists():
        print(f"❌ Database not found: {db_path}")
        print("   Run application first to create database")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print(f"🔧 Migrating SQLite database: {db_path}")

    try:
        # 1. Create achievement table
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

        # 2. Create user_achievement table
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

        # 3. Create indexes
        print("   Creating indexes...")

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_achievement_category 
            ON achievement(category)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_achievement_difficulty 
            ON achievement(difficulty)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_achievement_slug 
            ON achievement(slug)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_user_achievement_user_id 
            ON user_achievement(user_id)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_user_achievement_achievement_id 
            ON user_achievement(achievement_id)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_user_achievement_unlocked 
            ON user_achievement(is_unlocked)
        """)

        conn.commit()
        print("✅ Migration completed successfully!")

        # Verify migration
        print("\n🔍 Verifying migration...")

        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name IN ('achievement', 'user_achievement')
            ORDER BY name
        """)
        tables = [row[0] for row in cursor.fetchall()]

        if 'achievement' in tables:
            print("   ✓ achievement table created")
        else:
            print("   ✗ achievement table missing")

        if 'user_achievement' in tables:
            print("   ✓ user_achievement table created")
        else:
            print("   ✗ user_achievement table missing")

        # Verify indexes
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='index' AND tbl_name = 'achievement'
        """)
        achievement_indexes = [row[0] for row in cursor.fetchall()]
        print(f"   ✓ {len(achievement_indexes)} indexes on achievement table")

        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='index' AND tbl_name = 'user_achievement'
        """)
        user_achievement_indexes = [row[0] for row in cursor.fetchall()]
        print(f"   ✓ {len(user_achievement_indexes)} indexes on user_achievement table")

    except sqlite3.OperationalError as e:
        if "already exists" in str(e).lower():
            print(f"⚠️  Migration already applied: {e}")
            print("   Skipping...")
        else:
            print(f"❌ Migration failed: {e}")
            conn.rollback()
            raise
    finally:
        conn.close()


def upgrade_postgresql(connection_string: str) -> None:
    """Run migration for PostgreSQL (production).

    Args:
        connection_string: PostgreSQL connection string
    """
    try:
        import psycopg2
    except ImportError:
        print("❌ psycopg2 not installed. Install with: pip install psycopg2-binary")
        return

    print(f"🔧 Migrating PostgreSQL database...")

    conn = psycopg2.connect(connection_string)
    cursor = conn.cursor()

    try:
        # 1. Create achievement table
        print("   Creating 'achievement' table...")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS achievement (
                id SERIAL PRIMARY KEY,
                slug VARCHAR(100) NOT NULL UNIQUE,
                name VARCHAR(100) NOT NULL,
                description TEXT NOT NULL,
                icon_path VARCHAR(255),
                
                category VARCHAR(20) NOT NULL,
                difficulty VARCHAR(20) NOT NULL DEFAULT 'common',
                
                requirements TEXT NOT NULL,
                is_progressive BOOLEAN NOT NULL DEFAULT FALSE,
                
                xp_reward INTEGER NOT NULL DEFAULT 0,
                
                is_hidden BOOLEAN NOT NULL DEFAULT FALSE,
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 2. Create user_achievement table
        print("   Creating 'user_achievement' table...")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_achievement (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                achievement_id INTEGER NOT NULL,
                
                current_progress INTEGER NOT NULL DEFAULT 0,
                is_unlocked BOOLEAN NOT NULL DEFAULT FALSE,
                unlocked_at TIMESTAMP,
                
                is_displayed BOOLEAN NOT NULL DEFAULT TRUE,
                
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                
                FOREIGN KEY (user_id) REFERENCES "user"(id) ON DELETE CASCADE,
                FOREIGN KEY (achievement_id) REFERENCES achievement(id) ON DELETE CASCADE,
                UNIQUE(user_id, achievement_id)
            )
        """)

        # 3. Create indexes
        print("   Creating indexes...")

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_achievement_category 
            ON achievement(category)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_achievement_difficulty 
            ON achievement(difficulty)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_achievement_slug 
            ON achievement(slug)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_user_achievement_user_id 
            ON user_achievement(user_id)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_user_achievement_achievement_id 
            ON user_achievement(achievement_id)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_user_achievement_unlocked 
            ON user_achievement(is_unlocked)
        """)

        conn.commit()
        print("✅ PostgreSQL migration completed successfully!")

    except Exception as e:
        print(f"❌ PostgreSQL migration failed: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


def downgrade_sqlite(db_path: str = "instance/billiard_campionato.db") -> None:
    """Rollback migration for SQLite."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print(f"🔧 Rolling back achievement tables from: {db_path}")

    try:
        cursor.execute("DROP TABLE IF EXISTS user_achievement")
        print("   ✓ Dropped user_achievement table")

        cursor.execute("DROP TABLE IF EXISTS achievement")
        print("   ✓ Dropped achievement table")

        conn.commit()
        print("✅ Rollback completed successfully!")

    except Exception as e:
        print(f"❌ Rollback failed: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    import sys
    import os

    print("=" * 60)
    print("Achievement System Migration (FASE 2)")
    print("=" * 60)
    print()

    if len(sys.argv) > 1:
        if sys.argv[1] == "postgresql":
            # PostgreSQL migration
            db_url = os.environ.get("DATABASE_URL")
            if not db_url:
                print("❌ DATABASE_URL environment variable not set")
                sys.exit(1)
            upgrade_postgresql(db_url)
        elif sys.argv[1] == "downgrade":
            # Rollback
            downgrade_sqlite()
        else:
            print(f"❌ Unknown command: {sys.argv[1]}")
            print("\nUsage:")
            print("  python migrations/add_achievement_tables.py              # SQLite (dev)")
            print("  python migrations/add_achievement_tables.py postgresql   # PostgreSQL (prod)")
            print("  python migrations/add_achievement_tables.py downgrade    # Rollback")
            sys.exit(1)
    else:
        # Default: SQLite migration
        upgrade_sqlite()

    print()
    print("=" * 60)
