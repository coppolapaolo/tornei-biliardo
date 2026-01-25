"""Database migration: Add Gamification ABAC tables.
2026-01-26

This migration adds:
1. feature_config table (ABAC Rules)
2. user_feature_usage table (Nudge tracking)
3. gamification_override column to user table
"""

import sqlite3
import logging
from pathlib import Path

logger = logging.getLogger("migration")

def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db") -> None:
    """Run migration for SQLite."""
    db_file = Path(db_path)
    if not db_file.exists():
         # Fallback logic similar to other migrations
        alt_path = "instance/tornei_biliardo.db"
        if Path(alt_path).exists():
            db_path = alt_path
            db_file = Path(db_path)

    if not db_file.exists():
        print(f"Database not found: {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print(f"Migrating SQLite database: {db_path}")

    try:
        # 1. Create feature_config table
        print("   Creating 'feature_config' table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS feature_config (
                code VARCHAR(50) NOT NULL PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                description TEXT,
                rules TEXT NOT NULL DEFAULT '[]',
                is_active BOOLEAN DEFAULT 1,
                badge_slug VARCHAR(100)
            )
        """)

        # 2. Create user_feature_usage table
        print("   Creating 'user_feature_usage' table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_feature_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                feature_code VARCHAR(50) NOT NULL,
                usage_count INTEGER DEFAULT 0,
                last_used_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                
                FOREIGN KEY(user_id) REFERENCES user (id) ON DELETE CASCADE,
                FOREIGN KEY(feature_code) REFERENCES feature_config (code) ON DELETE CASCADE,
                UNIQUE (user_id, feature_code)
            )
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_feature_usage_user 
            ON user_feature_usage (user_id)
        """)

        # 3. Add gamification_override to user table
        print("   Adding 'gamification_override' column to user table...")
        try:
            cursor.execute("ALTER TABLE user ADD COLUMN gamification_override BOOLEAN DEFAULT 0 NOT NULL")
        except sqlite3.OperationalError as e:
            if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
                print("   Column 'gamification_override' already exists, skipping.")
            else:
                raise

        conn.commit()
        print("Migration completed successfully!")

    except Exception as e:
        conn.rollback()
        print(f"Migration failed: {e}")
        raise
    finally:
        conn.close()
