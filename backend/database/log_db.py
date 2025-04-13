"""
SQLite database connector for storing tool logs and agent activity
"""

import sqlite3
import logging
import json
import uuid
from typing import Dict, List, Any, Optional

# Import the database path from db_setup
from .db_setup import LOG_INFO_DB, setup_log_info_db

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class LogDB:
    """
    SQLite database connector for storing tool logs and agent activity
    """
    
    def __init__(self, db_path: str = LOG_INFO_DB):
        """
        Initialize a new LogDB
        
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
        setup_log_info_db()
            
    def add_tool_log(self, thread_id: str, conversation_id: str, user_id: str, 
                     tool_name: str, tool_input: Dict, tool_output: Dict) -> str:
        """
        Add a tool log
        
        Args:
            thread_id: ID of the thread
            conversation_id: ID of the conversation
            user_id: ID of the user
            tool_name: Name of the tool
            tool_input: Input to the tool
            tool_output: Output from the tool
            
        Returns:
            Log ID
        """
        log_id = str(uuid.uuid4())
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # Convert dicts to JSON strings
            tool_input_json = json.dumps(tool_input) if tool_input else None
            tool_output_json = json.dumps(tool_output) if tool_output else None
                
            cursor.execute(
                """INSERT INTO tool_logs 
                   (log_id, thread_id, conversation_id, user_id, tool_name, tool_input, tool_output) 
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (log_id, thread_id, conversation_id, user_id, tool_name, tool_input_json, tool_output_json)
            )
            
            conn.commit()
            logger.info(f"Added log for tool {tool_name} to conversation {conversation_id}")
            return log_id
        except Exception as e:
            logger.error(f"Error adding tool log: {str(e)}")
            conn.rollback()
            raise
        finally:
            conn.close()
            
    def get_tool_logs(self, conversation_id: str) -> List[Dict]:
        """
        Get tool logs for a conversation
        
        Args:
            conversation_id: ID of the conversation
            
        Returns:
            List of tool logs
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                """SELECT log_id, tool_name, tool_input, tool_output, created_at 
                   FROM tool_logs 
                   WHERE conversation_id = ? 
                   ORDER BY created_at ASC""",
                (conversation_id,)
            )
            
            result = []
            for row in cursor.fetchall():
                row_dict = dict(row)
                
                # Parse JSON fields
                for field in ['tool_input', 'tool_output']:
                    if row_dict.get(field):
                        try:
                            row_dict[field] = json.loads(row_dict[field])
                        except (json.JSONDecodeError, TypeError):
                            pass  # Keep as string if not valid JSON
                    
                result.append(row_dict)
                
            return result
        except Exception as e:
            logger.error(f"Error getting tool logs: {str(e)}")
            raise
        finally:
            conn.close()
    
    def get_thread_tool_logs(self, thread_id: str) -> List[Dict]:
        """
        Get all tool logs for a thread
        
        Args:
            thread_id: ID of the thread
            
        Returns:
            List of tool logs
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                """SELECT log_id, conversation_id, tool_name, tool_input, tool_output, created_at 
                   FROM tool_logs 
                   WHERE thread_id = ? 
                   ORDER BY created_at ASC""",
                (thread_id,)
            )
            
            result = []
            for row in cursor.fetchall():
                row_dict = dict(row)
                
                # Parse JSON fields
                for field in ['tool_input', 'tool_output']:
                    if row_dict.get(field):
                        try:
                            row_dict[field] = json.loads(row_dict[field])
                        except (json.JSONDecodeError, TypeError):
                            pass  # Keep as string if not valid JSON
                    
                result.append(row_dict)
                
            return result
        except Exception as e:
            logger.error(f"Error getting thread tool logs: {str(e)}")
            raise
        finally:
            conn.close() 