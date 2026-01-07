"""
Migration: Add KPI tracking tables for admin dashboard

Date: 2026-01-07
Description:
- Add kpi_feature_usage table for anonymous/aggregated feature tracking
- Add kpi_daily_snapshot table for daily metrics snapshots
- Add kpi_milestone table to track reached milestones (avoid duplicate notifications)
"""

import sqlite3


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db") -> None:
    """Apply migration to SQLite database."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 1. Create kpi_feature_usage table (anonymous aggregated tracking)
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS kpi_feature_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                feature_name VARCHAR(100) NOT NULL,
                date DATE NOT NULL,
                usage_count INTEGER DEFAULT 0,
                unique_users INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(feature_name, date)
            )
        """)
        print("Created kpi_feature_usage table")
    except sqlite3.OperationalError as e:
        if "already exists" in str(e).lower():
            print("Table kpi_feature_usage already exists")
        else:
            raise

    # 2. Create index on kpi_feature_usage for fast lookups
    try:
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_kpi_feature_usage_date
            ON kpi_feature_usage(date)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_kpi_feature_usage_feature
            ON kpi_feature_usage(feature_name)
        """)
        print("Created indexes on kpi_feature_usage")
    except sqlite3.OperationalError as e:
        if "already exists" in str(e).lower():
            print("Indexes already exist")
        else:
            raise

    # 3. Create kpi_daily_snapshot table for aggregate daily metrics
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS kpi_daily_snapshot (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date DATE NOT NULL UNIQUE,
                total_users INTEGER DEFAULT 0,
                new_users INTEGER DEFAULT 0,
                active_users INTEGER DEFAULT 0,
                total_matches INTEGER DEFAULT 0,
                new_matches INTEGER DEFAULT 0,
                total_gare INTEGER DEFAULT 0,
                active_gare INTEGER DEFAULT 0,
                completed_gare INTEGER DEFAULT 0,
                total_xp_awarded INTEGER DEFAULT 0,
                avg_user_level REAL DEFAULT 0,
                retention_7d REAL DEFAULT 0,
                retention_30d REAL DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        print("Created kpi_daily_snapshot table")
    except sqlite3.OperationalError as e:
        if "already exists" in str(e).lower():
            print("Table kpi_daily_snapshot already exists")
        else:
            raise

    # 4. Create index on kpi_daily_snapshot
    try:
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_kpi_daily_snapshot_date
            ON kpi_daily_snapshot(date)
        """)
        print("Created index on kpi_daily_snapshot")
    except sqlite3.OperationalError as e:
        if "already exists" in str(e).lower():
            print("Index already exists")
        else:
            raise

    # 5. Create kpi_milestone table to track reached milestones
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS kpi_milestone (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                milestone_type VARCHAR(50) NOT NULL,
                milestone_value INTEGER NOT NULL,
                reached_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                notification_sent BOOLEAN DEFAULT 0,
                UNIQUE(milestone_type, milestone_value)
            )
        """)
        print("Created kpi_milestone table")
    except sqlite3.OperationalError as e:
        if "already exists" in str(e).lower():
            print("Table kpi_milestone already exists")
        else:
            raise

    conn.commit()
    conn.close()
    print("Migration completed successfully!")


def downgrade_sqlite(db_path: str = "instance/billiard_campionato.db") -> None:
    """Rollback migration."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("DROP TABLE IF EXISTS kpi_feature_usage")
    cursor.execute("DROP TABLE IF EXISTS kpi_daily_snapshot")
    cursor.execute("DROP TABLE IF EXISTS kpi_milestone")

    conn.commit()
    conn.close()
    print("Migration rolled back successfully!")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "downgrade":
        downgrade_sqlite()
    else:
        upgrade_sqlite()
