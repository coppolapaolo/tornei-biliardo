"""
Add province field to billiard_hall table for geographic matching.

Migration: 20260201_add_province_to_billiard_hall
"""

migration_name = "20260201_add_province_to_billiard_hall"


def upgrade_sqlite(op):
    """Add province column to billiard_hall table (SQLite)."""
    # Check if column already exists (idempotent)
    from sqlalchemy import inspect
    from models.base import db

    inspector = inspect(db.engine)
    columns = [col["name"] for col in inspector.get_columns("billiard_hall")]

    if "province" not in columns:
        op.execute(
            "ALTER TABLE billiard_hall ADD COLUMN province VARCHAR(2) NULL"
        )
        print("  Added 'province' column to billiard_hall table")
    else:
        print("  Column 'province' already exists, skipping")


def downgrade_sqlite(op):
    """Remove province column from billiard_hall table (SQLite)."""
    # SQLite doesn't support DROP COLUMN easily, but we can ignore for now
    print("  Downgrade: province column will remain (SQLite limitation)")
