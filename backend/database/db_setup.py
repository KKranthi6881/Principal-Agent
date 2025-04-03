import sqlite3
import os
from pathlib import Path

# Database paths
DB_DIR = Path(__file__).parent
CONVERSATIONS_DB = DB_DIR / "conversations.db"
LOG_INFO_DB = DB_DIR / "log_info.db"
METADATA_DB = DB_DIR / "metadata.db"

def setup_conversations_db():
    conn = sqlite3.connect(CONVERSATIONS_DB)
    cursor = conn.cursor()
    
    # Create threads table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS threads (
        thread_id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        topic TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Create conversations table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS conversations (
        conversation_id TEXT PRIMARY KEY,
        thread_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        role TEXT NOT NULL,  -- 'user' or 'assistant'
        content TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (thread_id) REFERENCES threads(thread_id)
    )
    ''')
    
    conn.commit()
    conn.close()

def setup_log_info_db():
    conn = sqlite3.connect(LOG_INFO_DB)
    cursor = conn.cursor()
    
    # Create agent_logs table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS agent_logs (
        log_id TEXT PRIMARY KEY,
        thread_id TEXT NOT NULL,
        conversation_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        agent_type TEXT NOT NULL,  -- 'code_explainer', 'dependency_explainer', 'summarizer'
        input_text TEXT,
        output_text TEXT,
        tool_calls JSON,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Create tool_logs table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS tool_logs (
        log_id TEXT PRIMARY KEY,
        thread_id TEXT NOT NULL,
        conversation_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        tool_name TEXT NOT NULL,
        tool_input JSON,
        tool_output JSON,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    conn.commit()
    conn.close()

def setup_metadata_db():
    conn = sqlite3.connect(METADATA_DB)
    cursor = conn.cursor()
    
    # Create users table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY,
        username TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Create connections table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS connections (
        connection_id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        connection_type TEXT NOT NULL,  -- 'github', 'snowflake', etc.
        connection_details JSON NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(user_id)
    )
    ''')
    
    # Create code_metadata table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS code_metadata (
        metadata_id TEXT PRIMARY KEY,
        connection_id TEXT NOT NULL,
        file_path TEXT NOT NULL,
        file_type TEXT NOT NULL,
        content_hash TEXT NOT NULL,
        metadata JSON,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (connection_id) REFERENCES connections(connection_id)
    )
    ''')
    
    conn.commit()
    conn.close()

def setup_all_databases():
    # Create database directory if it doesn't exist
    DB_DIR.mkdir(parents=True, exist_ok=True)
    
    # Setup all databases
    setup_conversations_db()
    setup_log_info_db()
    setup_metadata_db()
    
    print("All databases and tables have been created successfully!")

if __name__ == "__main__":
    setup_all_databases() 