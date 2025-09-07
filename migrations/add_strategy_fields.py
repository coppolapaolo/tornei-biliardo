#!/usr/bin/env python3
"""
Migration script to add strategy configuration fields to the Gara table.
"""

import sqlite3
import sys
from pathlib import Path

# Database path
DB_PATH = Path(__file__).parent.parent / "instance" / "billiard_campionato.db"

def migrate():
    """Add new strategy configuration columns to the gara table."""
    
    if not DB_PATH.exists():
        print(f"Database not found at {DB_PATH}")
        return False
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Check if columns already exist
        cursor.execute("PRAGMA table_info(gara)")
        columns = [col[1] for col in cursor.fetchall()]
        
        new_columns = [
            ("matchmaking_strategy", "VARCHAR(50)", "'amalfi'"),
            ("first_round_policy", "VARCHAR(50)", "'random'"),
            ("odd_number_policy", "VARCHAR(50)", "'bye'"),
            ("anti_rematch_enabled", "BOOLEAN", "1"),
            ("rating_type", "VARCHAR(20)", "'fargo'")
        ]
        
        columns_added = 0
        for col_name, col_type, default_value in new_columns:
            if col_name not in columns:
                print(f"Adding column {col_name}...")
                sql = f"ALTER TABLE gara ADD COLUMN {col_name} {col_type} DEFAULT {default_value}"
                cursor.execute(sql)
                columns_added += 1
            else:
                print(f"Column {col_name} already exists, skipping...")
        
        if columns_added > 0:
            # Update existing rows with default values
            cursor.execute("""
                UPDATE gara 
                SET matchmaking_strategy = 'amalfi',
                    first_round_policy = 'random',
                    odd_number_policy = 'bye',
                    anti_rematch_enabled = 1,
                    rating_type = 'fargo'
                WHERE matchmaking_strategy IS NULL
            """)
            
            conn.commit()
            print(f"Successfully added {columns_added} columns to gara table")
        else:
            print("All columns already exist, no migration needed")
        
        return True
        
    except Exception as e:
        print(f"Error during migration: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

if __name__ == "__main__":
    success = migrate()
    sys.exit(0 if success else 1)