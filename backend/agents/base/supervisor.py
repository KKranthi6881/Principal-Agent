"""
Supervisor Agent module that defines the SupervisorAgent class
This agent coordinates other specialized agents
"""

from typing import Dict, List, Any, Optional
import logging
import json
from langchain_core.messages import BaseMessage
from langgraph.graph import StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Checkpointer
from datetime import datetime

from .agent import Agent

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SupervisorAgent(Agent):
    """
    Supervisor Agent class that coordinates other specialized agents
    
    Attributes:
        name (str): The name of the agent
        description (str): A description of what the agent does
        agents (Dict): Dictionary of specialized agents
        model: Language model to use
        checkpointer: Checkpointer for saving state
    """
    
    def __init__(
        self, 
        name: str = "Supervisor", 
        description: str = "Coordinates other specialized agents",
        agents: Optional[Dict[str, Agent]] = None,
        model = None,
        checkpointer: Checkpointer = None,
    ):
        """
        Initialize a new SupervisorAgent
        
        Args:
            name: Name of the agent
            description: Description of what the agent does
            agents: Dictionary of specialized agents
            model: Language model to use
            checkpointer: Checkpointer for saving state
        """
        super().__init__(name, description)
        self.agents = agents or {}
        self.model = model
        self.checkpointer = checkpointer
        self.graph = None
        self.compiled_graph = None
        self.response = None
        
    def add_agent(self, agent_id: str, agent: Agent):
        """Add an agent to the supervisor's agent set"""
        self.agents[agent_id] = agent
        
    def build_graph(self):
        """
        Build the agent workflow graph
        This method should be implemented by specific supervisor agents
        """
        raise NotImplementedError("Subclasses must implement build_graph()")
        
    def compile_graph(self):
        """
        Compile the agent workflow graph
        """
        if not self.graph:
            logger.info(f"Building new workflow graph for {self.name}")
            self.build_graph()
            
        logger.info(f"Compiling workflow graph for {self.name}")
        self.compiled_graph = self.graph.compile(checkpointer=self.checkpointer)
        return self.compiled_graph
        
    def reset_graph(self):
        """
        Reset the graph and compiled_graph attributes
        """
        logger.info(f"Resetting workflow graph for {self.name}")
        self.graph = None
        self.compiled_graph = None
        
    async def ainvoke(self, input_data: Dict[str, Any], **kwargs):
        """
        Asynchronously invoke the supervisor agent with input data
        
        Args:
            input_data: Input data for the agent
            **kwargs: Additional arguments
            
        Returns:
            Response from the agent workflow
        """
        conversation_id = input_data.get("conversation_id", "unknown")
        thread_id = input_data.get("thread_id", "unknown")
        
        # Ensure we have a fresh graph
        logger.info(f"Ensuring fresh graph for thread {thread_id}, conversation {conversation_id}")
        
        # Add some entropy to each invocation to avoid state collisions
        input_data["_invoke_id"] = f"{conversation_id}_{thread_id}_{int(datetime.now().timestamp()*1000)}"
        
        # Create a new compiled graph for each invocation
        try:
            if self.compiled_graph is None:
                logger.info(f"Compiling graph for {self.name} with fresh state")
                self.compile_graph()
            
            # Execute the workflow asynchronously
            logger.info(f"Asynchronously invoking {self.name} workflow")
            response = await self.compiled_graph.ainvoke(input_data, **kwargs)
            self.response = response
            logger.info(f"Async workflow execution completed successfully")
            return response
        except Exception as e:
            logger.error(f"Error in ainvoke: {str(e)}")
            logger.exception("Ainvoke exception details:")
            raise
        
    def invoke(self, input_data: Dict[str, Any], **kwargs):
        """
        Invoke the supervisor agent with input data
        
        Args:
            input_data: Input data for the agent
            **kwargs: Additional arguments
            
        Returns:
            Response from the agent workflow
        """
        conversation_id = input_data.get("conversation_id", "unknown")
        thread_id = input_data.get("thread_id", "unknown")
        
        # Ensure we have a fresh graph
        logger.info(f"Ensuring fresh graph for thread {thread_id}, conversation {conversation_id}")
        
        # Add some entropy to each invocation to avoid state collisions
        input_data["_invoke_id"] = f"{conversation_id}_{thread_id}_{int(datetime.now().timestamp()*1000)}"
        
        # Create a new compiled graph for each invocation
        try:
            if self.compiled_graph is None:
                logger.info(f"Compiling graph for {self.name} with fresh state")
                self.compile_graph()
            
            # Execute the workflow
            logger.info(f"Invoking {self.name} workflow")
            response = self.compiled_graph.invoke(input_data, **kwargs)
            self.response = response
            logger.info(f"Workflow execution completed successfully")
            return response
        except Exception as e:
            logger.error(f"Error in invoke: {str(e)}")
            logger.exception("Invoke exception details:")
            raise
        
    def run(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run the supervisor agent on the given input data
        
        Args:
            input_data: Input data for the agent
            
        Returns:
            Output from the agent
        """
        return self.invoke(input_data)
    
    def get_agent(self, agent_id: str) -> Optional[Agent]:
        """Get an agent by ID"""
        return self.agents.get(agent_id)
        
    def log_workflow(self, thread_id: str, conversation_id: str, workflow_state: Dict[str, Any]):
        """
        Log the workflow state to a file
        
        Args:
            thread_id: The thread ID
            conversation_id: The conversation ID
            workflow_state: The current workflow state
        """
        log_data = {
            "thread_id": thread_id,
            "conversation_id": conversation_id,
            "workflow_state": workflow_state
        }
        
        log_file = f"logs/workflow_{thread_id}_{conversation_id}.json"
        try:
            with open(log_file, "w") as f:
                json.dump(log_data, f, indent=2)
            logger.info(f"Workflow state logged to {log_file}")
        except Exception as e:
            logger.error(f"Error logging workflow state: {str(e)}") 