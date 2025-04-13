# Database Architecture

## Overview

This directory contains the database infrastructure for the Principal-Agent system, supporting the multi-agent framework. The system uses SQLite databases for storing:

1. **Conversations & Threads**: User-agent interactions and conversation history
2. **Agent Logs**: Agent thinking, actions, and processing logs 
3. **Tool Logs**: Records of tool usage by agents
4. **Metadata**: User info, connections, code metadata, etc.

## Key Components

- **`database.py`**: Main interface for all database operations (singleton `db` instance)
- **`conversation_db.py`**: Handles conversation and thread storage
- **`log_db.py`**: Manages tool logs
- **`db_setup.py`**: Initial database schema setup
- **`migrations/`**: Database migration scripts

## Database Schema

### Conversations DB (conversations.db)

- **threads**: Conversation threads with user context
- **conversations**: Individual messages in threads
- **agent_logs**: Agent actions, thinking, and processing logs *(unified table)*

### Log Info DB (log_info.db)

- **tool_logs**: Records of tool usage by agents

### Metadata DB (metadata.db)

- **users**: User information
- **connections**: Connection details (GitHub, databases, etc.)
- **code_metadata**: Information about code files
- **llm_providers/models**: LLM configuration

## Using the Database Interface

```python
from database.database import db

# Create a thread
thread_id = db.create_thread(user_id="user123", topic="SQL Analysis")

# Add message
conversation_id = db.add_message(thread_id, user_id="user123", role="user", content="Analyze my database")

# Log agent thinking
db.log_agent_thinking(
    conversation_id=conversation_id,
    thread_id=thread_id,
    agent_name="sql_analyzer",
    thinking="I need to understand the database structure first..."
)

# Log agent action
db.log_agent_action(
    conversation_id=conversation_id,
    thread_id=thread_id,
    agent_name="sql_analyzer",
    action_name="execute_query",
    action_input={"query": "SELECT * FROM users"},
    action_output={"rows": 10, "data": []}
)

# Log tool usage
db.add_tool_log(
    thread_id=thread_id,
    conversation_id=conversation_id,
    user_id="user123",
    tool_name="snowflake_connector",
    tool_input={"query": "SELECT * FROM users"},
    tool_output={"status": "success", "result": []}
)
```

## Multi-Agent Support

The unified `agent_logs` table supports multiple agent types working together:

- Different agent names and types can be tracked
- Actions and thinking processes are recorded
- Tool calls are stored for analysis
- Thread and conversation linking enables tracing agent collaborations

## Migration

The system includes a migration (003_unify_agent_logs.py) to unify previously separate agent logging approaches into a consolidated schema. 