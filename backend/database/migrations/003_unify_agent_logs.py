"""
Migration to unify agent_logs table between databases
"""
import sqlite3
import os
import logging
from pathlib import Path
import json

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Database paths
DB_DIR = Path(__file__).parent.parent
CONVERSATIONS_DB = DB_DIR / "conversations.db"
LOG_INFO_DB = DB_DIR / "log_info.db"

def run_migration():
    """
    Unify agent_logs tables between databases:
    1. Update agent_logs table in conversations.db to include all fields
    2. Migrate data from log_info.db agent_logs table to conversations.db
    3. Remove old agent_logs table from log_info.db
    """
    logger.info("Running migration to unify agent_logs tables...")
    
    # Create unified agent_logs table in conversations.db
    update_conversations_db_schema()
    
    # Migrate data from log_info.db to conversations.db
    migrate_agent_logs()
    
    # Remove agent_logs table from log_info.db
    remove_agent_logs_from_log_info()
    
    logger.info("Agent logs unification completed successfully")

def update_conversations_db_schema():
    """Update the agent_logs table schema in conversations.db"""
    logger.info("Updating agent_logs table schema in conversations.db...")
    
    if not CONVERSATIONS_DB.exists():
        logger.warning(f"Conversations database does not exist at {CONVERSATIONS_DB}")
        return
    
    conn = sqlite3.connect(CONVERSATIONS_DB)
    cursor = conn.cursor()
    
    try:
        # Check if agent_logs table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='agent_logs'")
        if cursor.fetchone():
            # Rename existing table to backup
            logger.info("Backing up existing agent_logs table...")
            cursor.execute("ALTER TABLE agent_logs RENAME TO agent_logs_old")
        
        # Create new unified agent_logs table
        logger.info("Creating unified agent_logs table...")
        cursor.execute('''
        CREATE TABLE agent_logs (
            log_id TEXT PRIMARY KEY,
            thread_id TEXT NOT NULL,
            conversation_id TEXT NOT NULL,
            user_id TEXT,
            agent_name TEXT NOT NULL,
            agent_type TEXT,
            action TEXT,
            input_text TEXT,
            output_text TEXT,
            log_content TEXT,
            tool_calls JSON,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (conversation_id) REFERENCES conversations(conversation_id),
            FOREIGN KEY (thread_id) REFERENCES threads(thread_id)
        )
        ''')
        
        # Migrate data from old table if it existed
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='agent_logs_old'")
        if cursor.fetchone():
            logger.info("Migrating data from old agent_logs table...")
            cursor.execute("""
                INSERT INTO agent_logs 
                (log_id, thread_id, conversation_id, agent_name, action, log_content, created_at)
                SELECT log_id, thread_id, conversation_id, agent_name, action, log_content, created_at
                FROM agent_logs_old
            """)
            
            # Drop the old table
            cursor.execute("DROP TABLE agent_logs_old")
        
        conn.commit()
        logger.info("Successfully updated agent_logs table in conversations.db")
    except Exception as e:
        logger.error(f"Error updating schema: {str(e)}")
        conn.rollback()
    finally:
        conn.close()

def migrate_agent_logs():
    """Migrate agent_logs data from log_info.db to conversations.db"""
    logger.info("Migrating agent_logs data from log_info.db to conversations.db...")
    
    if not LOG_INFO_DB.exists():
        logger.warning(f"Log info database does not exist at {LOG_INFO_DB}")
        return
    
    if not CONVERSATIONS_DB.exists():
        logger.warning(f"Conversations database does not exist at {CONVERSATIONS_DB}")
        return
    
    # Check if agent_logs table exists in log_info.db
    log_conn = sqlite3.connect(LOG_INFO_DB)
    log_cursor = log_conn.cursor()
    
    try:
        log_cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='agent_logs'")
        if not log_cursor.fetchone():
            logger.info("No agent_logs table found in log_info.db, skipping migration")
            return
        
        # Get all records from log_info.db agent_logs
        log_cursor.execute("PRAGMA table_info(agent_logs)")
        columns = [info[1] for info in log_cursor.fetchall()]
        
        # Get column names as a string for the query
        column_names = ", ".join(columns)
        
        log_cursor.execute(f"SELECT {column_names} FROM agent_logs")
        logs = log_cursor.fetchall()
        
        if not logs:
            logger.info("No agent logs to migrate")
            return
        
        # Connect to conversations.db
        conv_conn = sqlite3.connect(CONVERSATIONS_DB)
        conv_cursor = conv_conn.cursor()
        
        for log in logs:
            # Create a dictionary with column names as keys
            log_dict = dict(zip(columns, log))
            
            # Map fields from log_info.db to conversations.db
            agent_name = log_dict.get('agent_type', 'unknown')
            agent_type = log_dict.get('agent_type')
            input_text = log_dict.get('input_text')
            output_text = log_dict.get('output_text')
            user_id = log_dict.get('user_id')
            thread_id = log_dict.get('thread_id')
            conversation_id = log_dict.get('conversation_id')
            log_id = log_dict.get('log_id')
            
            # Convert tool_calls to string if it exists
            tool_calls = log_dict.get('tool_calls')
            if tool_calls:
                # Handle if it's already a JSON string or a Python object
                if not isinstance(tool_calls, str):
                    tool_calls = json.dumps(tool_calls)
            
            try:
                # Insert into conversations.db agent_logs table
                conv_cursor.execute("""
                    INSERT OR IGNORE INTO agent_logs
                    (log_id, thread_id, conversation_id, user_id, agent_name, agent_type,
                    action, input_text, output_text, tool_calls)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    log_id, thread_id, conversation_id, user_id, agent_name, agent_type,
                    "processing", input_text, output_text, tool_calls
                ))
            except Exception as e:
                logger.error(f"Error migrating log {log_id}: {str(e)}")
        
        conv_conn.commit()
        logger.info(f"Successfully migrated {len(logs)} agent logs")
    except Exception as e:
        logger.error(f"Error during migration: {str(e)}")
        if 'conv_conn' in locals():
            conv_conn.rollback()
    finally:
        log_conn.close()
        if 'conv_conn' in locals():
            conv_conn.close()

def remove_agent_logs_from_log_info():
    """Remove agent_logs table from log_info.db as it's now in conversations.db"""
    logger.info("Removing agent_logs table from log_info.db...")
    
    if not LOG_INFO_DB.exists():
        logger.warning(f"Log info database does not exist at {LOG_INFO_DB}")
        return
    
    conn = sqlite3.connect(LOG_INFO_DB)
    cursor = conn.cursor()
    
    try:
        # Check if agent_logs table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='agent_logs'")
        if cursor.fetchone():
            # Create a backup table
            cursor.execute("ALTER TABLE agent_logs RENAME TO agent_logs_backup")
            logger.info("Renamed agent_logs to agent_logs_backup in log_info.db")
        else:
            logger.info("No agent_logs table found in log_info.db")
        
        conn.commit()
    except Exception as e:
        logger.error(f"Error removing agent_logs table: {str(e)}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    run_migration() 