"""
Migration: Remove entry_fee columns from individual match tables.

Individual matches are always free - entry_fee is not needed.
This removes the unused column from both match_proposal and individual_match tables.

Migration name: 20260203_remove_individual_match_entry_fee
"""

from flask import current_app

migration_name = "20260203_remove_individual_match_entry_fee"


def upgrade(op):
    """Drop entry_fee columns from match_proposal and individual_match tables."""
    # SQLite doesn't support DROP COLUMN directly, so we need to recreate tables
    # However, for SQLite 3.35.0+ (2021), DROP COLUMN is supported
    # PythonAnywhere uses Python 3.10+ which has SQLite 3.37+

    # Check if columns exist before dropping
    from models.base import db

    # For match_proposal table
    try:
        # Check if column exists
        result = db.session.execute(
            db.text("PRAGMA table_info(match_proposal)")
        ).fetchall()
        columns = [row[1] for row in result]

        if "entry_fee" in columns:
            op.execute("ALTER TABLE match_proposal DROP COLUMN entry_fee")
            current_app.logger.info(
                "Dropped entry_fee column from match_proposal table"
            )
        else:
            current_app.logger.info(
                "entry_fee column already removed from match_proposal"
            )
    except Exception as e:
        current_app.logger.warning(
            f"Could not drop entry_fee from match_proposal: {e}"
        )

    # For individual_match table
    try:
        result = db.session.execute(
            db.text("PRAGMA table_info(individual_match)")
        ).fetchall()
        columns = [row[1] for row in result]

        if "entry_fee" in columns:
            op.execute("ALTER TABLE individual_match DROP COLUMN entry_fee")
            current_app.logger.info(
                "Dropped entry_fee column from individual_match table"
            )
        else:
            current_app.logger.info(
                "entry_fee column already removed from individual_match"
            )
    except Exception as e:
        current_app.logger.warning(
            f"Could not drop entry_fee from individual_match: {e}"
        )


def downgrade(op):
    """Re-add entry_fee columns (for rollback)."""
    try:
        op.execute(
            "ALTER TABLE match_proposal ADD COLUMN entry_fee NUMERIC(10, 2) DEFAULT 0"
        )
    except Exception:
        pass  # Column might already exist

    try:
        op.execute(
            "ALTER TABLE individual_match ADD COLUMN entry_fee NUMERIC(10, 2)"
        )
    except Exception:
        pass  # Column might already exist
