import sqlite3
import os
from pathlib import Path
import json
import logging

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Database paths
DB_DIR = Path(__file__).parent
CONVERSATIONS_DB = DB_DIR / "conversations.db"
LOG_INFO_DB = DB_DIR / "log_info.db"
METADATA_DB = DB_DIR / "metadata.db"
LINEAGE_DB = DB_DIR / "lineage.db"

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
    
    # Create unified agent_logs table that combines both implementations
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS agent_logs (
        log_id TEXT PRIMARY KEY,
        thread_id TEXT NOT NULL,
        conversation_id TEXT NOT NULL,
        user_id TEXT,
        agent_name TEXT NOT NULL,
        agent_type TEXT,  -- 'code_explainer', 'dependency_explainer', 'summarizer', etc.
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
    
    conn.commit()
    conn.close()

def setup_log_info_db():
    conn = sqlite3.connect(LOG_INFO_DB)
    cursor = conn.cursor()
    
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
    
    # Create llm_providers table for storing provider information
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS llm_providers (
        provider_id TEXT PRIMARY KEY,
        name TEXT,
        description TEXT,
        api_url TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Create llm_provider_configs table for storing user's provider configurations
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS llm_provider_configs (
        config_id TEXT PRIMARY KEY,
        user_id TEXT,
        provider_id TEXT,
        api_key TEXT,
        api_key_encrypted BOOLEAN DEFAULT TRUE,
        base_url TEXT,
        organization TEXT,
        default_model TEXT,
        active BOOLEAN DEFAULT FALSE,
        additional_settings JSON,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (provider_id) REFERENCES llm_providers (provider_id),
        FOREIGN KEY (user_id) REFERENCES users (user_id)
    )
    ''')
    
    # Create llm_models table to store available models for each provider
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS llm_models (
        model_id TEXT PRIMARY KEY,
        provider_id TEXT,
        name TEXT,
        description TEXT,
        context_length INTEGER,
        is_default BOOLEAN DEFAULT FALSE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (provider_id) REFERENCES llm_providers (provider_id)
    )
    ''')
    
    conn.commit()
    conn.close()

def setup_lineage_db():
    """Create the lineage database and tables if they don't exist"""
    
    # Ensure database directory exists
    os.makedirs(os.path.dirname(LINEAGE_DB), exist_ok=True)
    
    # Connect to database
    conn = sqlite3.connect(LINEAGE_DB)
    cursor = conn.cursor()
    
    try:
        # Create tables table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS tables (
            table_id TEXT PRIMARY KEY,
            table_name TEXT NOT NULL,
            schema_name TEXT,
            database_name TEXT,
            github_path TEXT,
            github_repo TEXT,
            connector_id TEXT,
            tech_stack TEXT NOT NULL,
            business_description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        
        # Create columns table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS columns (
            column_id TEXT PRIMARY KEY,
            table_id TEXT NOT NULL,
            column_name TEXT NOT NULL,
            data_type TEXT,
            is_primary_key BOOLEAN DEFAULT FALSE,
            is_foreign_key BOOLEAN DEFAULT FALSE,
            business_description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (table_id) REFERENCES tables(table_id)
        )
        """)
        
        # Create relationships table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS relationships (
            relationship_id TEXT PRIMARY KEY,
            source_table_id TEXT NOT NULL,
            target_table_id TEXT NOT NULL,
            relationship_type TEXT NOT NULL,
            source_column_id TEXT,
            target_column_id TEXT,
            github_path TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (source_table_id) REFERENCES tables(table_id),
            FOREIGN KEY (target_table_id) REFERENCES tables(table_id),
            FOREIGN KEY (source_column_id) REFERENCES columns(column_id),
            FOREIGN KEY (target_column_id) REFERENCES columns(column_id)
        )
        """)
        
        # Create lineage_definitions table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS lineage_definitions (
            lineage_id TEXT PRIMARY KEY,
            root_table_id TEXT NOT NULL,
            lineage_json JSON NOT NULL,
            tech_stack TEXT NOT NULL,
            github_path TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (root_table_id) REFERENCES tables(table_id)
        )
        """)
        
        # Create indices
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tables_name ON tables(table_name)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tables_tech ON tables(tech_stack)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_columns_table ON columns(table_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_relationships_source ON relationships(source_table_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_relationships_target ON relationships(target_table_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_lineage_root ON lineage_definitions(root_table_id)")
        
        conn.commit()
        logger.info("Successfully created lineage database tables")
        
    except Exception as e:
        logger.error(f"Error setting up database: {str(e)}")
        conn.rollback()
        raise
    finally:
        conn.close()

def setup_all_databases():
    # Create database directory if it doesn't exist
    DB_DIR.mkdir(parents=True, exist_ok=True)
    
    # Setup all databases
    setup_conversations_db()
    setup_log_info_db()
    setup_metadata_db()
    setup_lineage_db()
    
    # Insert default LLM providers if they don't exist
    providers = [
        ('openai', 'OpenAI', 'OpenAI API for GPT models', 'https://api.openai.com'),
        ('anthropic', 'Anthropic', 'Anthropic API for Claude models', 'https://api.anthropic.com'),
        ('google', 'Google AI', 'Google Gemini API', 'https://generativelanguage.googleapis.com'),
        ('huggingface', 'HuggingFace', 'HuggingFace Inference API', 'https://api-inference.huggingface.co'),
        ('ollama', 'Ollama', 'Local Ollama server for open-source models', 'http://localhost:11434')
    ]
    
    conn_metadata = sqlite3.connect(METADATA_DB)
    cursor_metadata = conn_metadata.cursor()
    
    for provider in providers:
        cursor_metadata.execute(
            'INSERT OR IGNORE INTO llm_providers (provider_id, name, description, api_url) VALUES (?, ?, ?, ?)',
            provider
        )
    
    # Insert default models for each provider
    models = [
        # OpenAI models
        ('gpt-4o-mini', 'openai', 'GPT-4o Mini', 'Smaller and more cost-effective', 128000, False),
        ('gpt-4.1-mini', 'openai', 'GPT-4.1 Mini', 'Fast and powerful model', 1000000, True),
        ('gpt-4.1', 'openai', 'GPT-4.1', 'Balanced performance and cost', 1000000, False),
        ('gpt-4.1-nano', 'openai', 'GPT-4.1 Nano', 'Balanced performance and cost', 1000000, False),
        
        # Anthropic models
        ('claude-3.7-sonnet', 'anthropic', 'Claude 3.7 Sonnet', 'Latest Claude model with improved capabilities', 200000, True),
        ('claude-3.5-sonnet', 'anthropic', 'claude-3.5-sonnet', 'Most powerful Claude model', 200000, False),

        
        # Google models
        ('gemini-2.5-flash-preview-04-17', 'google', 'Gemini 2.5 Flash Preview', 'Google\'s most capable model', 1000000, True),
        ('gemini-2.0-flash', 'google', 'Gemini 2.0 Flash', 'Fast and efficient model', 1000000, False),
    
        
        # Ollama models
        ('gemma3:12b', 'ollama', 'gemma3:12b', 'Google\'s lightweight open model', 120000, True)
    ]
    
    for model in models:
        cursor_metadata.execute(
            'INSERT OR IGNORE INTO llm_models (model_id, provider_id, name, description, context_length, is_default) VALUES (?, ?, ?, ?, ?, ?)',
            model
        )
    
    conn_metadata.commit()
    conn_metadata.close()
    
    print("All databases and tables have been created successfully!")

if __name__ == "__main__":
    setup_all_databases() 