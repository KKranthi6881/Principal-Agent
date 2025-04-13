"""
Base Agent module that defines the core Agent class
All specialized agents will inherit from this base class
"""

from typing import Dict, List, Optional, Any
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Agent:
    """
    Base Agent class that provides core agent functionality
    
    Attributes:
        name (str): The name of the agent
        description (str): A description of what the agent does
        tools (List): Tools the agent has access to
    """
    
    def __init__(self, name: str, description: str, tools: Optional[List] = None):
        """
        Initialize a new Agent
        
        Args:
            name: Name of the agent
            description: Description of what the agent does
            tools: List of tools the agent has access to
        """
        self.name = name
        self.description = description
        self.tools = tools or []
        self.state = {}
        
    def add_tool(self, tool):
        """Add a tool to the agent's toolset"""
        self.tools.append(tool)
        
    def add_tools(self, tools):
        """Add multiple tools to the agent's toolset"""
        self.tools.extend(tools)
        
    def set_state(self, state):
        """Set the agent's state"""
        self.state = state
        
    def update_state(self, state_update):
        """Update the agent's state with new key-value pairs"""
        self.state.update(state_update)
        
    def get_state(self):
        """Get the agent's current state"""
        return self.state
        
    def run(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run the agent on the given input data
        
        Args:
            input_data: Input data for the agent
            
        Returns:
            Output from the agent
        """
        # This method should be implemented by each specific agent
        raise NotImplementedError("Subclasses must implement run()") 