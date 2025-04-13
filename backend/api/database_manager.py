from typing import Dict, List, Optional, Any
import json
from datetime import datetime
import uuid

# Import the unified database interface
from database.database import db

class DatabaseManager:
    def __init__(self):
        """
        Initialize the database manager
        The unified database interface handles connections and schema initialization
        """
        pass

    def create_thread(self, user_id: str, topic: str) -> str:
        """Create a new conversation thread"""
        # Use the unified create_thread method
        return db.create_thread(user_id, topic)

    def add_conversation(self, thread_id: str, user_id: str, role: str, content: str) -> str:
        """Add a new conversation message"""
        # Use the unified add_message method (renamed from add_conversation for clarity)
        return db.add_message(thread_id, user_id, role, content)

    def get_thread_conversations(self, thread_id: str, limit: int = 6) -> List[Dict[str, Any]]:
        """Get recent conversations for a thread"""
        # Get full history from unified interface
        conversations = db.get_thread_history(thread_id)
        
        # Sort by created_at descending and limit results
        sorted_conversations = sorted(
            conversations, 
            key=lambda x: x['created_at'] if 'created_at' in x else '', 
            reverse=True
        )
        
        return sorted_conversations[:limit]

    def log_agent_activity(self, thread_id: str, conversation_id: str, user_id: str, 
                         agent_type: str, input_text: str, output_text: str, 
                         tool_calls: Optional[Dict] = None) -> str:
        """Log agent activity"""
        # Map to our unified agent_logs schema
        return db.add_agent_log(
            conversation_id=conversation_id,
            thread_id=thread_id,
            agent_name=agent_type,  # Use agent_type as agent_name
            action="processing",    # Default action for legacy compatibility
            log_content="",         # Legacy compatibility
            user_id=user_id,
            agent_type=agent_type,
            input_text=input_text,
            output_text=output_text,
            tool_calls=tool_calls
        )

    def log_tool_usage(self, thread_id: str, conversation_id: str, user_id: str,
                      tool_name: str, tool_input: Dict, tool_output: Dict) -> str:
        """Log tool usage"""
        # Use the unified add_tool_log method
        return db.add_tool_log(
            thread_id=thread_id,
            conversation_id=conversation_id,
            user_id=user_id,
            tool_name=tool_name,
            tool_input=tool_input,
            tool_output=tool_output
        )

    # Enhanced methods for multi-agent logging
    def log_agent_thinking(self, conversation_id: str, thread_id: str, agent_name: str,
                          thinking: str, user_id: str = None) -> str:
        """Log agent thinking process"""
        return db.log_agent_thinking(
            conversation_id=conversation_id,
            thread_id=thread_id,
            agent_name=agent_name,
            thinking=thinking,
            user_id=user_id
        )
    
    def log_agent_action(self, conversation_id: str, thread_id: str, agent_name: str,
                        action_name: str, action_input: Dict, action_output: Dict,
                        user_id: str = None) -> str:
        """Log an action taken by an agent"""
        return db.log_agent_action(
            conversation_id=conversation_id,
            thread_id=thread_id,
            agent_name=agent_name,
            action_name=action_name,
            action_input=action_input,
            action_output=action_output,
            user_id=user_id
        )

    # User and connection methods remain unchanged but use unified interface in the future
    def create_user(self, user_id: str, username: str, email: str) -> None:
        """Create a new user"""
        # For now, keep the direct implementation until we add user methods to unified interface
        db_conn = db.conversation_db._get_connection()
        cursor = db_conn.cursor()
        
        try:
            cursor.execute(
                "INSERT INTO users (user_id, username, email) VALUES (?, ?, ?)",
                (user_id, username, email)
            )
            db_conn.commit()
        finally:
            db_conn.close()

    def add_connection(self, user_id: str, connection_type: str, connection_details: Dict) -> str:
        """Add a new connection for a user"""
        # Generate UUID instead of timestamp-based ID
        connection_id = str(uuid.uuid4())
        
        db_conn = db.conversation_db._get_connection() 
        cursor = db_conn.cursor()
        
        try:
            cursor.execute(
                """INSERT INTO connections 
                (connection_id, user_id, connection_type, connection_details)
                VALUES (?, ?, ?, ?)""",
                (connection_id, user_id, connection_type, json.dumps(connection_details))
            )
            db_conn.commit()
            return connection_id
        finally:
            db_conn.close()

    def add_code_metadata(self, connection_id: str, file_path: str, file_type: str,
                         content_hash: str, metadata: Dict) -> str:
        """Add metadata for a code file"""
        # Generate UUID instead of timestamp-based ID
        metadata_id = str(uuid.uuid4())
        
        db_conn = db.conversation_db._get_connection()
        cursor = db_conn.cursor()
        
        try:
            cursor.execute(
                """INSERT INTO code_metadata 
                (metadata_id, connection_id, file_path, file_type, content_hash, metadata)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (metadata_id, connection_id, file_path, file_type, content_hash, json.dumps(metadata))
            )
            db_conn.commit()
            return metadata_id
        finally:
            db_conn.close() 