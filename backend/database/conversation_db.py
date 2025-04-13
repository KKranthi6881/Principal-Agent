"""
SQLite database connector for storing conversation history
"""

import sqlite3
import logging
import json
import os
import time
import uuid
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple

# Import the database path from db_setup
from .db_setup import CONVERSATIONS_DB, setup_conversations_db

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ConversationDB:
    """
    SQLite database connector for storing conversation history
    """
    
    def __init__(self, db_path: str = CONVERSATIONS_DB):
        """
        Initialize a new ConversationDB
        
        Args:
            db_path: Path to the SQLite database
        """
        self.db_path = db_path
        self._ensure_tables_exist()
        
    def _get_connection(self) -> sqlite3.Connection:
        """Get a connection to the SQLite database"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Return rows as dictionaries
        return conn
        
    def _ensure_tables_exist(self):
        """Ensure the necessary tables exist in the database"""
        # Use the existing setup function from db_setup.py
        setup_conversations_db()
        
        # Add agent_logs table if it doesn't exist
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # Create a new table for agent thinking logs
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS agent_logs (
                    log_id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL,
                    thread_id TEXT NOT NULL,
                    agent_name TEXT NOT NULL,
                    action TEXT NOT NULL,
                    log_content TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (conversation_id) REFERENCES conversations(conversation_id),
                    FOREIGN KEY (thread_id) REFERENCES threads(thread_id)
                )
            """)
            
            conn.commit()
        except Exception as e:
            logger.error(f"Error creating agent_logs table: {str(e)}")
            conn.rollback()
        finally:
            conn.close()
            
    def create_thread(self, user_id: str, topic: str) -> str:
        """
        Create a new thread
        
        Args:
            user_id: ID of the user
            topic: Topic of the thread
            
        Returns:
            Thread ID
        """
        thread_id = str(uuid.uuid4())
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                "INSERT INTO threads (thread_id, user_id, topic) VALUES (?, ?, ?)",
                (thread_id, user_id, topic)
            )
            conn.commit()
            logger.info(f"Created thread {thread_id} for user {user_id}")
            return thread_id
        except Exception as e:
            logger.error(f"Error creating thread: {str(e)}")
            conn.rollback()
            raise
        finally:
            conn.close()
            
    def add_message(self, thread_id: str, user_id: str, role: str, content: str) -> str:
        """
        Add a message to a thread
        
        Args:
            thread_id: ID of the thread
            user_id: ID of the user
            role: Role of the message sender ('user' or 'assistant')
            content: Content of the message
            
        Returns:
            Conversation ID
        """
        conversation_id = str(uuid.uuid4())
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                "INSERT INTO conversations (conversation_id, thread_id, user_id, role, content) VALUES (?, ?, ?, ?, ?)",
                (conversation_id, thread_id, user_id, role, content)
            )
            
            # Update thread updated_at timestamp
            cursor.execute(
                "UPDATE threads SET updated_at = CURRENT_TIMESTAMP WHERE thread_id = ?",
                (thread_id,)
            )
            
            conn.commit()
            logger.info(f"Added {role} message to thread {thread_id}")
            return conversation_id
        except Exception as e:
            logger.error(f"Error adding message: {str(e)}")
            conn.rollback()
            raise
        finally:
            conn.close()
            
    def add_agent_log(self, conversation_id: str, thread_id: str, agent_name: str, 
                      action: str, log_content: str, user_id: str = None,
                      agent_type: str = None, input_text: str = None, 
                      output_text: str = None, tool_calls: Dict = None) -> str:
        """
        Add an agent log using unified schema
        
        Args:
            conversation_id: ID of the conversation
            thread_id: ID of the thread
            agent_name: Name of the agent
            action: Action being performed
            log_content: Content of the log
            user_id: Optional user ID
            agent_type: Optional agent type classification
            input_text: Optional input text for the agent
            output_text: Optional output text from the agent
            tool_calls: Optional tool calls made by the agent
            
        Returns:
            Log ID
        """
        log_id = str(uuid.uuid4())
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # Convert dict to JSON string if necessary
            if isinstance(log_content, dict):
                log_content = json.dumps(log_content)
                
            # Convert tool_calls to JSON if it exists
            tool_calls_json = None
            if tool_calls:
                tool_calls_json = json.dumps(tool_calls)
                
            cursor.execute(
                """INSERT INTO agent_logs 
                   (log_id, conversation_id, thread_id, agent_name, action, log_content,
                    user_id, agent_type, input_text, output_text, tool_calls) 
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (log_id, conversation_id, thread_id, agent_name, action, log_content,
                 user_id, agent_type, input_text, output_text, tool_calls_json)
            )
            
            conn.commit()
            logger.info(f"Added log for agent {agent_name} to conversation {conversation_id}")
            return log_id
        except Exception as e:
            logger.error(f"Error adding agent log: {str(e)}")
            conn.rollback()
            raise
        finally:
            conn.close()
            
    def get_thread_history(self, thread_id: str) -> List[Dict]:
        """
        Get the conversation history for a thread
        
        Args:
            thread_id: ID of the thread
            
        Returns:
            List of conversation messages
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                """SELECT conversation_id, thread_id, user_id, role, content, created_at 
                   FROM conversations 
                   WHERE thread_id = ? 
                   ORDER BY created_at ASC""",
                (thread_id,)
            )
            
            result = []
            for row in cursor.fetchall():
                result.append(dict(row))
                
            return result
        except Exception as e:
            logger.error(f"Error getting thread history: {str(e)}")
            raise
        finally:
            conn.close()
            
    def get_agent_logs(self, conversation_id: str) -> List[Dict]:
        """
        Get agent logs for a conversation
        
        Args:
            conversation_id: ID of the conversation
            
        Returns:
            List of agent logs
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                """SELECT log_id, agent_name, action, log_content, agent_type, 
                   input_text, output_text, tool_calls, created_at 
                   FROM agent_logs 
                   WHERE conversation_id = ? 
                   ORDER BY created_at ASC""",
                (conversation_id,)
            )
            
            result = []
            for row in cursor.fetchall():
                row_dict = dict(row)
                
                # Parse JSON content if it's a JSON string
                for field in ['log_content', 'tool_calls']:
                    if row_dict.get(field):
                        try:
                            row_dict[field] = json.loads(row_dict[field])
                        except (json.JSONDecodeError, TypeError):
                            pass  # Keep as string if not valid JSON
                    
                result.append(row_dict)
                
            return result
        except Exception as e:
            logger.error(f"Error getting agent logs: {str(e)}")
            raise
        finally:
            conn.close() 