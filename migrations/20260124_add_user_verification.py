"""Database migration: Add user verification (email/password reset).
2026-01-24

This migration adds:
1. is_verified column to user table
2. user_token table for secure tokens (verification, password reset)
"""

import sqlite3
from pathlib import Path


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db") -> None:
    """Run migration for SQLite."""
    db_file = Path(db_path)
    if not db_file.exists():
        # Try alternate path if default doesn't exist (e.g. tornei_biliardo.db vs
        # billiard_campionato.db)
        # The user seems to be using tornei_biliardo.db in the update_schema script
        # attempt
        alt_path = "instance/tornei_biliardo.db"
        if Path(alt_path).exists():
            db_path = alt_path
            db_file = Path(db_path)
        else:
            print(f"Database not found at {db_path} or instance/tornei_biliardo.db")
            # Proceeding anyway as it might be created later or we want to test
            # connections,
            # but standard runner checks logic often happens outside.

    if not db_file.exists():
        print(f"Database not found: {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print(f"Migrating SQLite database: {db_path}")

    try:
        # 1. Add is_verified to user table
        print("   Adding 'is_verified' column to user table...")
        try:
            cursor.execute(
                "ALTER TABLE user ADD COLUMN is_verified BOOLEAN DEFAULT 0 NOT NULL"
            )
        except sqlite3.OperationalError as e:
            if (
                "duplicate column" in str(e).lower()
                or "already exists" in str(e).lower()
            ):
                print("   Column 'is_verified' already exists, skipping.")
            else:
                raise

        # 2. Create user_token table
        print("   Creating 'user_token' table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_token (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                token VARCHAR(100) NOT NULL,
                token_type VARCHAR(20) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                -- BaseModel le aggiunge a ogni entità: senza, l'INSERT
                -- dell'ORM fallisce con «no such column». Vale solo per le
                -- installazioni nuove — dove la tabella c'è già, questa
                -- CREATE non viene eseguita (vedi 20260820_timestamps_basemodel).
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL,
                is_used BOOLEAN DEFAULT 0,
                FOREIGN KEY(user_id) REFERENCES user (id),
                UNIQUE (token)
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS ix_user_token_token
            ON user_token (token)
        """)

        conn.commit()
        print("Migration completed successfully!")

    except Exception as e:
        conn.rollback()
        print(f"Migration failed: {e}")
        raise
    finally:
        conn.close()


def downgrade_sqlite(db_path: str = "instance/billiard_campionato.db") -> None:
    """Rollback migration."""
    # Note: SQLite doesn't support DROP COLUMN easily before recent versions
    # We will primarily drop the new table.

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print("Rolling back user verification migration...")

    cursor.execute("DROP TABLE IF EXISTS user_token")
    # Dropping is_verified column is hard in SQLite, skipping for simple rollback
    print("   Dropped user_token table. (is_verified column remains)")

    conn.commit()
    conn.close()


if __name__ == "__main__":
    upgrade_sqlite()
