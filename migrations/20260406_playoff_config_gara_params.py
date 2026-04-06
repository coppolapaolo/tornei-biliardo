"""Add gara parameter columns to playoff_configuration table.

Allows admin to override discipline, distance, rounds_count, strategy_type
and odd_number_policy per playoff config. NULL = inherit from campionato.
Idempotent: checks column existence before ALTER.
"""

import sqlite3

migration_name = "20260406_playoff_config_gara_params"


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db"):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("PRAGMA table_info(playoff_configuration)")
    cols = {row[1] for row in cursor.fetchall()}

    new_columns = [
        ("discipline", "VARCHAR(50) DEFAULT NULL"),
        ("distance", "INTEGER DEFAULT NULL"),
        ("rounds_count", "INTEGER DEFAULT NULL"),
        ("strategy_type", "VARCHAR(50) DEFAULT NULL"),
        ("odd_number_policy", "VARCHAR(20) DEFAULT NULL"),
    ]

    for col_name, col_def in new_columns:
        if col_name not in cols:
            cursor.execute(
                f"ALTER TABLE playoff_configuration ADD COLUMN {col_name} {col_def}"
            )
            print(f"  ✓ playoff_configuration.{col_name} added")
        else:
            print(f"  ⏭️  playoff_configuration.{col_name} already exists")

    conn.commit()
    conn.close()
