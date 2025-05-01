"""
Database migration to create the github_connectors table in the metadata database
"""
import os
import sqlite3

def run_migration():
    """
    Run the migration to create the github_connectors table
    """
    # Path to metadata database
    db_path = os.path.join('database', 'metadata.db')
    
    # Connect to the database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Create the github_connectors table if it doesn't exist
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS github_connectors (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        description TEXT,
        github_type TEXT NOT NULL,  -- 'public' or 'enterprise'
        api_url TEXT,               -- Only needed for enterprise GitHub
        token TEXT NOT NULL,        -- Encrypted token
        owner TEXT,                 -- GitHub user/owner
        repositories TEXT,          -- JSON array of repository names
        organization TEXT,          -- GitHub organization
        default_branch TEXT,        -- Default branch like 'main' or 'master'
        active BOOLEAN DEFAULT 1,   -- Whether this connector is active
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        repo_url TEXT               -- Direct GitHub repository URL,
        tech_stack TEXT DEFAULT 'postgresql'
    )
    ''')
    
    # Make sure the repo_url column exists (handle case where table was created before this column was added)
    try:
        # Check if repo_url column exists
        cursor.execute("PRAGMA table_info(github_connectors)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'repo_url' not in columns:
            print("Adding repo_url column to github_connectors table...")
            cursor.execute("ALTER TABLE github_connectors ADD COLUMN repo_url TEXT")
        if 'tech_stack' not in columns:
            print("Adding tech_stack column to github_connectors table...")
            cursor.execute("ALTER TABLE github_connectors ADD COLUMN tech_stack TEXT DEFAULT 'postgresql'")
    except Exception as e:
        print(f"Error checking/adding repo_url column or tech_stack column: {str(e)}")
    
    # Create indexes for better query performance
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_github_connectors_name ON github_connectors(name)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_github_connectors_active ON github_connectors(active)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_github_connectors_github_type ON github_connectors(github_type)')
    
    # Commit the changes and close the connection
    conn.commit()
    conn.close()
    
    print("GitHub connectors table created successfully!")

if __name__ == "__main__":
    run_migration() 