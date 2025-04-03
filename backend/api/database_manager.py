import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Any
import json
from datetime import datetime

class DatabaseManager:
    def __init__(self):
        self.db_dir = Path(__file__).parent.parent / "database"
        self.conversations_db = self.db_dir / "conversations.db"
        self.log_info_db = self.db_dir / "log_info.db"
        self.metadata_db = self.db_dir / "metadata.db"

    def _get_connection(self, db_path: Path) -> sqlite3.Connection:
        return sqlite3.connect(db_path)

    def create_thread(self, user_id: str, topic: str) -> str:
        """Create a new conversation thread"""
        conn = self._get_connection(self.conversations_db)
        cursor = conn.cursor()
        
        thread_id = f"thread_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{user_id}"
        cursor.execute(
            "INSERT INTO threads (thread_id, user_id, topic) VALUES (?, ?, ?)",
            (thread_id, user_id, topic)
        )
        conn.commit()
        conn.close()
        return thread_id

    def add_conversation(self, thread_id: str, user_id: str, role: str, content: str) -> str:
        """Add a new conversation message"""
        conn = self._get_connection(self.conversations_db)
        cursor = conn.cursor()
        
        conversation_id = f"conv_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{thread_id}"
        cursor.execute(
            "INSERT INTO conversations (conversation_id, thread_id, user_id, role, content) VALUES (?, ?, ?, ?, ?)",
            (conversation_id, thread_id, user_id, role, content)
        )
        conn.commit()
        conn.close()
        return conversation_id

    def get_thread_conversations(self, thread_id: str, limit: int = 6) -> List[Dict[str, Any]]:
        """Get recent conversations for a thread"""
        conn = self._get_connection(self.conversations_db)
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT * FROM conversations WHERE thread_id = ? ORDER BY created_at DESC LIMIT ?",
            (thread_id, limit)
        )
        columns = [description[0] for description in cursor.description]
        conversations = [dict(zip(columns, row)) for row in cursor.fetchall()]
        conn.close()
        return conversations

    def log_agent_activity(self, thread_id: str, conversation_id: str, user_id: str, 
                         agent_type: str, input_text: str, output_text: str, 
                         tool_calls: Optional[Dict] = None) -> str:
        """Log agent activity"""
        conn = self._get_connection(self.log_info_db)
        cursor = conn.cursor()
        
        log_id = f"log_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{thread_id}"
        cursor.execute(
            """INSERT INTO agent_logs 
               (log_id, thread_id, conversation_id, user_id, agent_type, input_text, output_text, tool_calls)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (log_id, thread_id, conversation_id, user_id, agent_type, input_text, 
             output_text, json.dumps(tool_calls) if tool_calls else None)
        )
        conn.commit()
        conn.close()
        return log_id

    def log_tool_usage(self, thread_id: str, conversation_id: str, user_id: str,
                      tool_name: str, tool_input: Dict, tool_output: Dict) -> str:
        """Log tool usage"""
        conn = self._get_connection(self.log_info_db)
        cursor = conn.cursor()
        
        log_id = f"tool_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{thread_id}"
        cursor.execute(
            """INSERT INTO tool_logs 
               (log_id, thread_id, conversation_id, user_id, tool_name, tool_input, tool_output)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (log_id, thread_id, conversation_id, user_id, tool_name,
             json.dumps(tool_input), json.dumps(tool_output))
        )
        conn.commit()
        conn.close()
        return log_id

    def create_user(self, user_id: str, username: str, email: str) -> None:
        """Create a new user"""
        conn = self._get_connection(self.metadata_db)
        cursor = conn.cursor()
        
        cursor.execute(
            "INSERT INTO users (user_id, username, email) VALUES (?, ?, ?)",
            (user_id, username, email)
        )
        conn.commit()
        conn.close()

    def add_connection(self, user_id: str, connection_type: str, connection_details: Dict) -> str:
        """Add a new connection for a user"""
        conn = self._get_connection(self.metadata_db)
        cursor = conn.cursor()
        
        connection_id = f"conn_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{user_id}"
        cursor.execute(
            """INSERT INTO connections 
               (connection_id, user_id, connection_type, connection_details)
               VALUES (?, ?, ?, ?)""",
            (connection_id, user_id, connection_type, json.dumps(connection_details))
        )
        conn.commit()
        conn.close()
        return connection_id

    def add_code_metadata(self, connection_id: str, file_path: str, file_type: str,
                         content_hash: str, metadata: Dict) -> str:
        """Add metadata for a code file"""
        conn = self._get_connection(self.metadata_db)
        cursor = conn.cursor()
        
        metadata_id = f"meta_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{connection_id}"
        cursor.execute(
            """INSERT INTO code_metadata 
               (metadata_id, connection_id, file_path, file_type, content_hash, metadata)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (metadata_id, connection_id, file_path, file_type, content_hash, json.dumps(metadata))
        )
        conn.commit()
        conn.close()
        return metadata_id 