"""
Migration script to add github_path column to lineage_definitions table
"""

import sqlite3
import os
import logging
import sys

# Add the parent directory to the path so we can import from the database module
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db_setup import LINEAGE_DB

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_migration():
    """Add github_path column to lineage_definitions table"""
    
    logger.info("Running migration to add github_path column to lineage_definitions table")
    
    # Connect to the database
    conn = sqlite3.connect(LINEAGE_DB)
    cursor = conn.cursor()
    
    try:
        # Check if column already exists
        cursor.execute("PRAGMA table_info(lineage_definitions)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'github_path' not in columns:
            # Add the github_path column
            cursor.execute("ALTER TABLE lineage_definitions ADD COLUMN github_path TEXT")
            logger.info("Added github_path column to lineage_definitions table")
            
            # Update existing records - set github_path based on the root table's github_path
            cursor.execute("""
            UPDATE lineage_definitions
            SET github_path = (
                SELECT t.github_path
                FROM tables t
                WHERE t.table_id = lineage_definitions.root_table_id
            )
            """)
            
            logger.info(f"Updated {cursor.rowcount} lineage definition records with github_path")
            
            # Commit the changes
            conn.commit()
            logger.info("Successfully migrated lineage_definitions table")
        else:
            logger.info("github_path column already exists in lineage_definitions table")
        
    except Exception as e:
        logger.error(f"Error running migration: {str(e)}")
        conn.rollback()
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    run_migration()
