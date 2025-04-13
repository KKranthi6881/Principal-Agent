"""
Unified database interface for the Principal-Agent system
"""

from typing import Dict, List, Any, Optional
import logging

from .conversation_db import ConversationDB
from .log_db import LogDB
from .db_setup import setup_all_databases

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DatabaseInterface:
    """
    Unified database interface for the Principal-Agent system
    Provides access to all database functionality in one place
    """
    
    def __init__(self):
        """Initialize the database interface"""
        # Initialize all databases
        setup_all_databases()
        
        # Create database connectors
        self.conversation_db = ConversationDB()
        self.log_db = LogDB()
        
    # Thread operations
    def create_thread(self, user_id: str, topic: str) -> str:
        """Create a new thread"""
        return self.conversation_db.create_thread(user_id, topic)
    
    # Conversation operations
    def add_message(self, thread_id: str, user_id: str, role: str, content: str) -> str:
        """Add a message to a thread"""
        return self.conversation_db.add_message(thread_id, user_id, role, content)
    
    def get_thread_history(self, thread_id: str) -> List[Dict]:
        """Get the conversation history for a thread"""
        return self.conversation_db.get_thread_history(thread_id)
    
    # Agent logging operations
    def add_agent_log(self, conversation_id: str, thread_id: str, agent_name: str, 
                      action: str, log_content: str, user_id: str = None,
                      agent_type: str = None, input_text: str = None, 
                      output_text: str = None, tool_calls: Dict = None) -> str:
        """Add an agent log"""
        return self.conversation_db.add_agent_log(
            conversation_id, thread_id, agent_name, action, log_content,
            user_id, agent_type, input_text, output_text, tool_calls
        )
    
    def get_agent_logs(self, conversation_id: str) -> List[Dict]:
        """Get agent logs for a conversation"""
        return self.conversation_db.get_agent_logs(conversation_id)
    
    # Tool logging operations
    def add_tool_log(self, thread_id: str, conversation_id: str, user_id: str, 
                     tool_name: str, tool_input: Dict, tool_output: Dict) -> str:
        """Add a tool log"""
        return self.log_db.add_tool_log(
            thread_id, conversation_id, user_id, tool_name, tool_input, tool_output
        )
    
    def get_tool_logs(self, conversation_id: str) -> List[Dict]:
        """Get tool logs for a conversation"""
        return self.log_db.get_tool_logs(conversation_id)
    
    def get_thread_tool_logs(self, thread_id: str) -> List[Dict]:
        """Get all tool logs for a thread"""
        return self.log_db.get_thread_tool_logs(thread_id)
    
    # Helper methods for multi-agent operations
    def log_agent_thinking(self, conversation_id: str, thread_id: str, agent_name: str, 
                           thinking: str, user_id: str = None) -> str:
        """Log agent thinking process"""
        return self.add_agent_log(
            conversation_id=conversation_id,
            thread_id=thread_id,
            agent_name=agent_name,
            action="thinking",
            log_content=thinking,
            user_id=user_id
        )
    
    def log_agent_action(self, conversation_id: str, thread_id: str, agent_name: str,
                         action_name: str, action_input: Dict, action_output: Dict,
                         user_id: str = None) -> str:
        """Log an action taken by an agent"""
        log_content = {
            "action_name": action_name,
            "action_input": action_input,
            "action_output": action_output
        }
        
        return self.add_agent_log(
            conversation_id=conversation_id,
            thread_id=thread_id,
            agent_name=agent_name,
            action="action",
            log_content=log_content,
            user_id=user_id,
            tool_calls={"action_name": action_name, "input": action_input}
        )

# Create singleton instance
db = DatabaseInterface() 