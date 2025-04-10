"""
Migration to add tech_stack column to github_connectors table
"""
import os
import sqlite3

def run_migration():
    """
    Run the migration to add tech_stack column to github_connectors table
    """
    # Path to metadata database
    db_path = os.path.join('database', 'metadata.db')
    
    # Connect to the database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check if the github_connectors table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='github_connectors'")
    if cursor.fetchone():
        # Check if tech_stack column exists
        cursor.execute("PRAGMA table_info(github_connectors)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'tech_stack' not in columns:
            print("Adding tech_stack column to github_connectors table...")
            cursor.execute("ALTER TABLE github_connectors ADD COLUMN tech_stack TEXT DEFAULT 'postgresql'")
            conn.commit()
            print("tech_stack column added successfully")
        else:
            print("tech_stack column already exists")
    else:
        print("github_connectors table does not exist, skipping migration")
    
    conn.close()
    
    print("GitHub connectors table migration completed!")

if __name__ == "__main__":
    run_migration() 