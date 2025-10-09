"""
Migration script: Add validation fields to Match and Rack

This migration adds:
- Validation confirmation fields to Match
- Operation log fields to Rack
- Soft delete support for Rack

Run with: source venv/bin/activate && PYTHONPATH=. python utils/migrations/add_match_validation_fields.py
"""

from app import create_app
from models import db

app = create_app()

with app.app_context():
    print("Starting migration: add_match_validation_fields")

    # Add columns to match table
    print("Adding validation fields to match...")
    try:
        db.session.execute(
            """
            ALTER TABLE match
            ADD COLUMN IF NOT EXISTS player1_confirmed BOOLEAN DEFAULT FALSE NOT NULL
            """
        )
        db.session.execute(
            """
            ALTER TABLE match
            ADD COLUMN IF NOT EXISTS player2_confirmed BOOLEAN DEFAULT FALSE NOT NULL
            """
        )
        db.session.execute(
            """
            ALTER TABLE match
            ADD COLUMN IF NOT EXISTS player1_confirmed_at DATETIME
            """
        )
        db.session.execute(
            """
            ALTER TABLE match
            ADD COLUMN IF NOT EXISTS player2_confirmed_at DATETIME
            """
        )
        print("✓ Validation fields added to match")
    except Exception as e:
        print(f"Note: {e} (may already exist)")

    # Add columns to rack table
    print("Adding operation log fields to rack...")
    try:
        db.session.execute(
            """
            ALTER TABLE rack
            ADD COLUMN IF NOT EXISTS added_by_id INTEGER
            """
        )
        db.session.execute(
            """
            ALTER TABLE rack
            ADD COLUMN IF NOT EXISTS added_at DATETIME
            """
        )
        db.session.execute(
            """
            ALTER TABLE rack
            ADD COLUMN IF NOT EXISTS removed_by_id INTEGER
            """
        )
        db.session.execute(
            """
            ALTER TABLE rack
            ADD COLUMN IF NOT EXISTS removed_at DATETIME
            """
        )
        db.session.execute(
            """
            ALTER TABLE rack
            ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN DEFAULT FALSE NOT NULL
            """
        )
        print("✓ Operation log fields added to rack")
    except Exception as e:
        print(f"Note: {e} (may already exist)")

    # Commit changes
    try:
        db.session.commit()
        print("✓ Migration completed successfully!")
    except Exception as e:
        db.session.rollback()
        print(f"✗ Migration failed: {e}")
        raise
