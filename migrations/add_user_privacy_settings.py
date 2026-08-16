"""Database migration: Add user privacy settings tables.

Date: 2025-12-28

This migration adds tables for user privacy management:
- user_privacy_setting: General privacy settings (show/hide categories)
- hidden_match: Individual matches hidden by users
- hidden_inscription: Individual inscriptions (gare) hidden by users
- hidden_campionato: Campionati hidden by users

Tables Created:
- user_privacy_setting
- hidden_match
- hidden_inscription
- hidden_campionato
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
        # 1. Create user_privacy_setting table
        print("   Creating 'user_privacy_setting' table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_privacy_setting (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL UNIQUE,
                show_email BOOLEAN NOT NULL DEFAULT 1,
                show_phone BOOLEAN NOT NULL DEFAULT 1,
                show_statistics BOOLEAN NOT NULL DEFAULT 1,
                show_recent_matches BOOLEAN NOT NULL DEFAULT 1,
                show_classifications BOOLEAN NOT NULL DEFAULT 1,
                show_challenge_stats BOOLEAN NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES user(id) ON DELETE CASCADE
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_privacy_user_id
            ON user_privacy_setting(user_id)
        """)

        # 2. Create hidden_match table
        print("   Creating 'hidden_match' table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS hidden_match (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                match_id INTEGER NOT NULL,
                hidden_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES user(id) ON DELETE CASCADE,
                FOREIGN KEY (match_id) REFERENCES match(id) ON DELETE CASCADE,
                UNIQUE(user_id, match_id)
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_hidden_match_user_id
            ON hidden_match(user_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_hidden_match_match_id
            ON hidden_match(match_id)
        """)

        # 3. Create hidden_inscription table
        print("   Creating 'hidden_inscription' table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS hidden_inscription (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                inscription_id INTEGER NOT NULL,
                hidden_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES user(id) ON DELETE CASCADE,
                FOREIGN KEY (inscription_id) REFERENCES inscription(id)
                    ON DELETE CASCADE,
                UNIQUE(user_id, inscription_id)
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_hidden_inscription_user_id
            ON hidden_inscription(user_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_hidden_inscription_inscription_id
            ON hidden_inscription(inscription_id)
        """)

        # 4. Create hidden_campionato table
        print("   Creating 'hidden_campionato' table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS hidden_campionato (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                campionato_id INTEGER NOT NULL,
                hidden_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES user(id) ON DELETE CASCADE,
                FOREIGN KEY (campionato_id) REFERENCES campionato(id) ON DELETE CASCADE,
                UNIQUE(user_id, campionato_id)
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_hidden_campionato_user_id
            ON hidden_campionato(user_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_hidden_campionato_campionato_id
            ON hidden_campionato(campionato_id)
        """)

        conn.commit()
        print("Migration completed successfully!")
        print(
            (
                "   Created tables: user_privacy_setting, hidden_match, "
                "hidden_inscription, hidden_campionato"
            )
        )

    except sqlite3.OperationalError as e:
        if "already exists" in str(e).lower():
            print(f"Migration already applied: {e}")
        else:
            conn.rollback()
            raise
    finally:
        conn.close()


def downgrade_sqlite(db_path: str = "instance/billiard_campionato.db") -> None:
    """Rollback migration."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print("Rolling back privacy settings migration...")

    cursor.execute("DROP TABLE IF EXISTS hidden_campionato")
    cursor.execute("DROP TABLE IF EXISTS hidden_inscription")
    cursor.execute("DROP TABLE IF EXISTS hidden_match")
    cursor.execute("DROP TABLE IF EXISTS user_privacy_setting")

    conn.commit()
    conn.close()
    print("Rollback completed!")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "downgrade":
        downgrade_sqlite()
    else:
        upgrade_sqlite()
