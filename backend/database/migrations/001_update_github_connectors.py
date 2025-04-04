"""
Migration to update github_connectors table with repo_url column
"""
import os
import sqlite3

def run_migration():
    """
    Run the migration to update the github_connectors table
    """
    # Path to metadata database
    db_path = os.path.join('database', 'metadata.db')
    
    # Connect to the database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check if the github_connectors table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='github_connectors'")
    if cursor.fetchone():
        # Check if repo_url column exists
        cursor.execute("PRAGMA table_info(github_connectors)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'repo_url' not in columns:
            print("Adding repo_url column to github_connectors table...")
            cursor.execute("ALTER TABLE github_connectors ADD COLUMN repo_url TEXT")
            conn.commit()
            print("repo_url column added successfully")
        else:
            print("repo_url column already exists")
    else:
        print("github_connectors table does not exist, skipping migration")
    
    conn.close()
    
    print("GitHub connectors table migration completed!")

if __name__ == "__main__":
    run_migration() 