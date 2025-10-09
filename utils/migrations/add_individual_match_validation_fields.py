"""
Migration script: Add validation fields to IndividualMatch and IndividualRack

This migration adds:
- Validation confirmation fields to IndividualMatch
- Operation log fields to IndividualRack
- Soft delete support for IndividualRack

Run with: python utils/migrations/add_individual_match_validation_fields.py
"""

from app import create_app
from models import db

app = create_app()

with app.app_context():
    print("Starting migration: add_individual_match_validation_fields")

    # Add columns to individual_match table
    print("Adding validation fields to individual_match...")
    try:
        db.session.execute(
            """
            ALTER TABLE individual_match
            ADD COLUMN IF NOT EXISTS player1_confirmed BOOLEAN DEFAULT FALSE NOT NULL
            """
        )
        db.session.execute(
            """
            ALTER TABLE individual_match
            ADD COLUMN IF NOT EXISTS player2_confirmed BOOLEAN DEFAULT FALSE NOT NULL
            """
        )
        db.session.execute(
            """
            ALTER TABLE individual_match
            ADD COLUMN IF NOT EXISTS player1_confirmed_at DATETIME
            """
        )
        db.session.execute(
            """
            ALTER TABLE individual_match
            ADD COLUMN IF NOT EXISTS player2_confirmed_at DATETIME
            """
        )
        print("✓ Validation fields added to individual_match")
    except Exception as e:
        print(f"Note: {e} (may already exist)")

    # Add columns to individual_rack table
    print("Adding operation log fields to individual_rack...")
    try:
        db.session.execute(
            """
            ALTER TABLE individual_rack
            ADD COLUMN IF NOT EXISTS added_by_id INTEGER
            """
        )
        db.session.execute(
            """
            ALTER TABLE individual_rack
            ADD COLUMN IF NOT EXISTS added_at DATETIME
            """
        )
        db.session.execute(
            """
            ALTER TABLE individual_rack
            ADD COLUMN IF NOT EXISTS removed_by_id INTEGER
            """
        )
        db.session.execute(
            """
            ALTER TABLE individual_rack
            ADD COLUMN IF NOT EXISTS removed_at DATETIME
            """
        )
        db.session.execute(
            """
            ALTER TABLE individual_rack
            ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN DEFAULT FALSE NOT NULL
            """
        )
        print("✓ Operation log fields added to individual_rack")
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
