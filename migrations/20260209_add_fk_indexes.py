"""Add indexes on frequently queried foreign key columns.

These FK columns are used in joins and lookups on every page load
but lack indexes, causing full table scans. Uses IF NOT EXISTS for idempotency.
"""

migration_name = "20260209_add_fk_indexes"


def upgrade_sqlite(db_path: str):
    import sqlite3

    indexes = [
        ("idx_gara_campionato_id", "gara", "campionato_id"),
        ("idx_inscription_gara_id", "inscription", "gara_id"),
        ("idx_inscription_user_id", "inscription", "user_id"),
        ("idx_match_gara_id", "match", "gara_id"),
        ("idx_rack_match_id", "rack", "match_id"),
        ("idx_notification_user_id", "notification", "user_id"),
    ]
    conn = sqlite3.connect(db_path)
    for idx_name, table, column in indexes:
        conn.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table} ({column})")
    conn.commit()
    conn.close()
    print(f"  Created {len(indexes)} FK indexes")
