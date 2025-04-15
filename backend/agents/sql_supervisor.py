"""
SQL Supervisor Agent module that defines the SQLSupervisorAgent class
This agent coordinates specialized SQL agents to answer questions about SQL code
"""

from typing import Dict, List, Optional, Any, Annotated, TypedDict, Sequence
import logging
import json
import os
import sys
import operator
from pathlib import Path
from typing_extensions import TypedDict
from datetime import datetime
import time

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser

from langgraph.graph import StateGraph, START, END
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Checkpointer

# Ensure the backend directory is in the path
backend_dir = str(Path(__file__).parent.parent)
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from .base.supervisor import SupervisorAgent
from .sql_agents.lineage_agent import LineageAgent
from .sql_agents.dependency_agent import DependencyAgent
from .sql_agents.code_summarizer import CodeSummarizerAgent
from .sql_agents.description_summarizer import DescriptionSummarizerAgent

# Try to import from database
try:
    from database.database import db
except ImportError:
    # Fallback to a mock DB if not available
    db = None
    logger.warning("Database module not found, using mock database")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SQLSupervisorAgent(SupervisorAgent):
    """
    SQL Supervisor Agent that coordinates other specialized SQL agents
    
    Attributes:
        name (str): The name of the agent
        description (str): A description of what the agent does
        agents (Dict): Dictionary of specialized agents
        model: Language model to use
        checkpointer: Checkpointer for saving state
        database: Database interface for storing conversations and logs
        sql_tools: SQL analysis tools
        github_tools: GitHub tools
    """
    
    def __init__(
        self, 
        name: str = "SQL Supervisor", 
        description: str = "Coordinates specialized SQL agents to answer questions about SQL code",
        agents: Optional[Dict[str, Any]] = None,
        model = None,
        checkpointer: Checkpointer = None,
        database = None,
        sql_tools = None,
        github_tools = None
    ):
        """
        Initialize a new SQLSupervisorAgent
        
        Args:
            name: Name of the agent
            description: Description of what the agent does
            agents: Dictionary of specialized agents
            model: Language model to use
            checkpointer: Checkpointer for saving state
            database: Unified database interface for storing conversations and logs
            sql_tools: SQL analysis tools
            github_tools: GitHub tools
        """
        super().__init__(name, description, agents, model, checkpointer)
        self.database = database
        self.sql_tools = sql_tools
        self.github_tools = github_tools
        
        # Create specialized agents if not provided
        if not agents:
            self._create_specialized_agents()
            
        # Set up the parser
        self.parser = JsonOutputParser()
        
        # Set up prompt templates
        self.planning_prompt = ChatPromptTemplate.from_template(
"""You are a SQL Analysis Planning expert. Your job is to plan how to answer user questions about SQL code, tables, columns, and their dependencies.

User Question: {question}

Previous Conversation Context:
{context}

Based on the user's question, I need you to create a plan for answering it using specialized SQL agents.

Please provide a detailed plan in JSON format with the following structure shown in the example below:

{{"question_type": "One of: lineage_analysis, dependency_analysis, impact_analysis, code_summary, table_description, column_description, or general_query",
  "entities": {{
    "tables": ["table1", "table2"],
    "columns": ["table.column1", "table.column2"],
    "files": ["file1.sql", "file2.sql"]
  }},
  "plan": [
    {{
      "step": 1,
      "agent": "agent_name",
      "action": "action_name",
      "params": {{
        "param1": "value1",
        "param2": "value2"
      }},
      "reason": "Reason for this step"
    }}
  ],
  "dialect": "The SQL dialect to use (postgres, snowflake, tsql, etc.)",
  "summary": "A summary of the plan"
}}

Available agents and their actions with required parameters:
- lineage_agent:
  - analyze_lineage(table_name: str, direction: str = "upstream", max_depth: int = 5)
  - trace_table_lineage(table_name: str)
  - trace_column_lineage(table_name: str, column_name: str)
- dependency_agent:
  - analyze_dependencies(table_name: str, include_columns: bool = True)
  - analyze_impact(table_name: str)
- code_summarizer:
  - summarize_file(file_path: str)
  - describe_column(table_name: str, column_name: str)
- description_summarizer:
  - describe_table(table_name: str)
  - describe_column(table_name: str, column_name: str)

IMPORTANT: Make sure to use the correct parameter names as specified above. For example:
- Use 'table_name' instead of 'table' or 'file'
- Use 'file_path' instead of 'file' for summarize_file
- Include all required parameters for each action

Be thorough in your planning and ensure that all steps are necessary to answer the user's question completely.
""")
        
        self.thinking_prompt = ChatPromptTemplate.from_template(
"""You are a SQL Analysis expert. Your job is to think through how to answer a complex SQL question using the results from various specialized agents.

User Question: {question}

Planning: {planning}

Agent Results:
{agent_results}

Previous Conversation Context:
{context}

Now, think through how you would answer the user's question using the results from the specialized agents.
Consider:
1. What are the key insights from the agent results?
2. How do these insights relate to the user's question?
3. Is there any missing information that we need to address?
4. What is the most clear and helpful way to present this information to the user?

Provide your detailed thinking process below:
""")
        
        self.final_response_prompt = ChatPromptTemplate.from_template(
"""You are a SQL Analysis expert. Your job is to provide a clear and helpful response to the user's question based on the analysis performed.

User Question: {question}

Planning: {planning}

Agent Results:
{agent_results}

Thinking Process:
{thinking}

Previous Conversation Context:
{context}

Based on the above analysis, provide a clear and concise response to the user's question. Make sure to:
1. Directly address the user's question
2. Present insights in a logical order
3. Use clear language and formatting
4. Include relevant data points and examples
5. Note any limitations or caveats

Your response:
""")
        
    def _create_specialized_agents(self):
        """Create the specialized agents if not provided"""
        # Initialize GitHub wrapper if we have GitHub tools
        github_wrapper = None
        if self.github_tools:
            github_wrapper = self.github_tools.get_github_wrapper()
            
        # Initialize SQL tools with GitHub wrapper
        if self.sql_tools:
            self.sql_tools.initialize_with_github(github_wrapper)
            
        self.agents = {
            "lineage_agent": LineageAgent(model=self.model, sql_tools=self.sql_tools),
            "dependency_agent": DependencyAgent(model=self.model, sql_tools=self.sql_tools, github_tools=self.github_tools),
            "code_summarizer": CodeSummarizerAgent(model=self.model, sql_tools=self.sql_tools),
            "description_summarizer": DescriptionSummarizerAgent(model=self.model, sql_tools=self.sql_tools)
        }
        
    def build_graph(self):
        """Build the agent workflow graph with unique node names to avoid state collisions"""
        
        # Add a timestamp to make node names unique for this graph instance
        timestamp = int(time.time() * 1000)
        
        # Define the state type
        class AgentState(TypedDict):
            thread_id: str
            conversation_id: str
            user_id: str
            question: str
            context: str
            messages: Annotated[Sequence[BaseMessage], operator.add]
            planning: Dict[str, Any]
            agent_results: Dict[str, Any]
            thinking: str
            answer: str
            current_step: int
            max_steps: int
            dialect: str
            repo_url: Optional[str]
            
        # Create a new graph
        self.graph = StateGraph(AgentState)
        
        # Use unique node names by adding timestamp
        planning_node = f"planning_{timestamp}"
        execute_node = f"execute_step_{timestamp}"
        thinking_node = f"thinking_{timestamp}"
        answer_node = f"generate_answer_{timestamp}"
        
        logger.info(f"Building new graph with unique nodes: {planning_node}, {execute_node}, {thinking_node}, {answer_node}")
        
        # Add nodes to the graph
        self.graph.add_node(planning_node, self._planning_node)
        self.graph.add_node(execute_node, self._execute_step_node)
        self.graph.add_node(thinking_node, self._thinking_node)
        self.graph.add_node(answer_node, self._generate_answer_node)
        
        # Define the edges - note the order is important!
        # First, set the entry point
        self.graph.set_entry_point(planning_node)
        
        # Then add edges between nodes (NOT using START as the end node)
        self.graph.add_edge(planning_node, execute_node)
        
        # Add conditional edges
        self.graph.add_conditional_edges(
            execute_node,
            self._should_continue_execution,
            {
                "continue": execute_node,
                "done": thinking_node
            }
        )
        
        self.graph.add_edge(thinking_node, answer_node)
        self.graph.add_edge(answer_node, END)
        
        return self.graph
        
    def _planning_node(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Plan how to answer the user's question using specialized agents
        
        Args:
            state: Current state of the workflow
            
        Returns:
            Updated state with planning information
        """
        thread_id = state.get("thread_id")
        conversation_id = state.get("conversation_id")
        user_id = state.get("user_id")
        question = state.get("question")
        context = state.get("context", "")
        
        # Check if planning is already in the state and not None
        # This helps avoid state collisions when the key exists but actual planning hasn't happened
        if state.get("planning") is not None:
            # Planning already exists, just return the state
            logger.info(f"Planning already exists in state for thread {thread_id}, conversation {conversation_id}")
            return state
        
        # Create a planning prompt
        planning_input = {
            "question": question,
            "context": context
        }
        
        # Log the planning action using enhanced method
        if self.database:
            self.database.log_agent_thinking(
                conversation_id=conversation_id,
                thread_id=thread_id,
                agent_name=self.name,
                thinking=f"Planning how to answer the question: {question}",
                user_id=user_id
            )
        
        # Run the planning prompt
        planning_response = self.model.invoke(
            self.planning_prompt.format_messages(**planning_input)
        )
        
        # Parse the response
        planning_content = planning_response.content
        
        # Try to parse the JSON from the response
        try:
            # Extract JSON from the response if it's wrapped in backticks
            import re
            json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', planning_content)
            if json_match:
                planning_json = json.loads(json_match.group(1).strip())
            else:
                planning_json = json.loads(planning_content)
                
            # Use the enhanced logging method for the planning result
            if self.database:
                self.database.log_agent_action(
                    conversation_id=conversation_id,
                    thread_id=thread_id,
                    agent_name=self.name,
                    action_name="planning",
                    action_input=planning_input,
                    action_output=planning_json,
                    user_id=user_id
                )
            
            # Update the state - ONLY add planning and dialect
            return {
                **state,
                "planning": planning_json,
                "dialect": planning_json.get("dialect", "")
                # Remove reset of current_step and overwrite of max_steps
                # "current_step": 0, 
                # "max_steps": len(planning_json.get("plan", [])), 
                # "agent_results": {} # Keep agent_results reset if needed, or handle differently
            }
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing planning response: {str(e)}")
            logger.debug(f"Response content: {planning_content}")
            
            # Log the error using enhanced method
            if self.database:
                self.database.log_agent_thinking(
                    conversation_id=conversation_id,
                    thread_id=thread_id,
                    agent_name=self.name,
                    thinking=f"Error parsing planning response: {str(e)}\\nResponse: {planning_content}",
                    user_id=user_id
                )
                
            # Return a simple error plan
            error_plan = {
                "question_type": "error",
                "entities": {},
                "plan": [],
                "dialect": "",
                "summary": f"Error parsing planning response: {str(e)}"
            }
            
            # Update state with error plan, keep original steps
            return {
                **state,
                "planning": error_plan,
                "dialect": ""
            }
        
    def _execute_step_node(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a single step in the plan"""
        thread_id = state.get("thread_id")
        conversation_id = state.get("conversation_id")
        user_id = state.get("user_id")
        dialect = state.get("dialect", "")
        repo_url = state.get("repo_url")
        
        try:
            # Get the current step from the plan
            current_step = state.get("current_step", 0)
            plan = state.get("planning", {}).get("plan", [])
            
            if current_step >= len(plan):
                return state
            
            step = plan[current_step]
            agent_name = step.get("agent")
            action_name = step.get("action")
            params = step.get("params", {})
            
            # Add dialect and repo_url to params if available
            if dialect and "dialect" not in params:
                params["dialect"] = dialect
            if repo_url and "repo_url" not in params:
                params["repo_url"] = repo_url
                
            # For lineage actions, make sure to include visualization data
            if agent_name == "lineage_agent" and action_name in ["trace_table_lineage", "trace_column_lineage"]:
                params["include_visualization"] = True
            
            # Get the agent
            agent = self.agents.get(agent_name)
            if not agent:
                logger.error(f"Agent {agent_name} not found")
                # Add error to agent_results
                agent_results = state.get("agent_results", {})
                step_key = f"step_{current_step}"
                agent_results[step_key] = {
                    "agent": agent_name,
                    "action": action_name,
                    "error": f"Agent {agent_name} not found",
                    "params": params
                }
                
                # Log the error
                if self.database:
                    self.database.log_agent_thinking(
                        conversation_id=conversation_id,
                        thread_id=thread_id,
                        agent_name=self.name,
                        thinking=f"Error in step {current_step}: Agent {agent_name} not found",
                        user_id=user_id
                    )
                
                # Continue to the next step
                return {
                    **state,
                    "current_step": current_step + 1,
                    "agent_results": agent_results
                }
            
            # Prepare the input data for the agent
            input_data = {
                "action": action_name,
                "params": params
            }
            
            # Log the agent action
            if self.database:
                self.database.log_agent_thinking(
                    conversation_id=conversation_id,
                    thread_id=thread_id,
                    agent_name=self.name,
                    thinking=f"Executing step {current_step}: {agent_name}.{action_name}({params})",
                    user_id=user_id
                )
            
            try:
                # Run the agent
                result = agent.run(input_data)
                
                # Check for errors in the result
                if "error" in result:
                    logger.error(f"Error in agent {agent_name} action {action_name}: {result['error']}")
                    
                    # Try a recovery strategy
                    if "No SQL files found" in result["error"] and agent_name == "lineage_agent":
                        # Try with a lower max_depth or different search strategy
                        fallback_params = params.copy()
                        if "max_depth" in fallback_params:
                            fallback_params["max_depth"] = min(3, fallback_params["max_depth"])
                        
                        logger.info(f"Trying fallback with params: {fallback_params}")
                        fallback_input = {
                            "action": action_name,
                            "params": fallback_params
                        }
                        
                        # Try the fallback
                        result = agent.run(fallback_input)
                    
                # Process visualization data for lineage results
                if agent_name == "lineage_agent" and "visualization" in result:
                    # Ensure the visualization data is properly formatted
                    visualization = result["visualization"]
                    visualization_data = self._ensure_visualization_format(visualization)
                    
                    # Store visualization separately to avoid duplicate data
                    result["visualization_data"] = visualization_data
                
                # Log the result using enhanced method
                if self.database:
                    self.database.log_agent_action(
                        conversation_id=conversation_id,
                        thread_id=thread_id,
                        agent_name=agent_name,
                        action_name=action_name,
                        action_input=input_data,
                        action_output=result,
                        user_id=user_id
                    )
                
                # Update the agent_results
                agent_results = state.get("agent_results", {})
                step_key = f"step_{current_step}"
                agent_results[step_key] = {
                    "agent": agent_name,
                    "action": action_name,
                    "result": result,
                    "params": params
                }
                
                # Update the state
                return {
                    **state,
                    "current_step": current_step + 1,
                    "agent_results": agent_results
                }
                
            except Exception as e:
                logger.error(f"Error executing agent {agent_name} action {action_name}: {str(e)}")
                
                # Log the error using enhanced method
                if self.database:
                    self.database.log_agent_thinking(
                        conversation_id=conversation_id,
                        thread_id=thread_id,
                        agent_name=self.name,
                        thinking=f"Error in step {current_step}: {agent_name}.{action_name} - {str(e)}",
                        user_id=user_id
                    )
                
                # Update the agent_results with the error
                agent_results = state.get("agent_results", {})
                step_key = f"step_{current_step}"
                agent_results[step_key] = {
                    "agent": agent_name,
                    "action": action_name,
                    "error": str(e),
                    "params": params
                }
                
                # Continue to the next step
                return {
                    **state,
                    "current_step": current_step + 1,
                    "agent_results": agent_results
                }
                
        except Exception as e:
            logger.error(f"Error in execute_step_node: {str(e)}")
            
            # Log the error
            if self.database:
                self.database.log_agent_thinking(
                    conversation_id=conversation_id,
                    thread_id=thread_id,
                    agent_name=self.name,
                    thinking=f"Error executing step: {str(e)}",
                    user_id=user_id
                )
            
            # Simply move to the next step on error
            current_step = state.get("current_step", 0)
            agent_results = state.get("agent_results", {})
            step_key = f"step_{current_step}"
            agent_results[step_key] = {
                "error": f"Error executing step: {str(e)}"
            }
            
            return {
                **state,
                "current_step": current_step + 1,
                "agent_results": agent_results
            }
        
    def _should_continue_execution(self, state: Dict[str, Any]) -> str:
        """Check if we should continue executing steps or move to the next phase"""
        current_step = state.get("current_step", 0)  # Default to 0
        max_steps_limit = state.get("max_steps", 20) # Get the overall limit (default 20 from initial state)
        plan = state.get("planning", {}).get("plan", [])
        plan_length = len(plan)

        if current_step < plan_length and current_step < max_steps_limit:
            logger.info(f"Continuing execution to step {current_step + 1} (Step {current_step + 1}/{plan_length}, Limit: {max_steps_limit})")
            return "continue"
        elif current_step >= plan_length:
            logger.info(f"Finished plan execution at step {current_step}. Plan Length: {plan_length}.")
            return "done"
        else: # current_step >= max_steps_limit
            logger.warning(f"Max steps ({max_steps_limit}) reached at step {current_step}. Stopping execution. Plan had {plan_length} steps.")
            return "done"
            
    def _thinking_node(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Think about the results from the specialized agents to formulate an answer
        
        Args:
            state: Current state of the workflow
            
        Returns:
            Updated state with thinking information
        """
        thread_id = state.get("thread_id")
        conversation_id = state.get("conversation_id")
        user_id = state.get("user_id")
        question = state.get("question")
        planning = state.get("planning", {})
        agent_results = state.get("agent_results", {})
        context = state.get("context", "")
        
        # Format the agent results for the thinking prompt
        agent_results_str = json.dumps(agent_results, indent=2)
        
        # Create the thinking prompt input
        thinking_input = {
            "question": question,
            "planning": json.dumps(planning, indent=2),
            "agent_results": agent_results_str,
            "context": context
        }
        
        # Log the thinking process using enhanced method
        if self.database:
            self.database.log_agent_thinking(
                conversation_id=conversation_id,
                thread_id=thread_id,
                agent_name=self.name,
                thinking=f"Analyzing results from specialized agents to formulate an answer to: {question}",
                user_id=user_id
            )
        
        # Run the thinking prompt
        thinking_response = self.model.invoke(
            self.thinking_prompt.format_messages(**thinking_input)
        )
        
        # Get the thinking content
        thinking = thinking_response.content
        
        # Log the thinking result using enhanced method
        if self.database:
            self.database.log_agent_action(
                conversation_id=conversation_id,
                thread_id=thread_id,
                agent_name=self.name,
                action_name="thinking",
                action_input=thinking_input,
                action_output={"thinking": thinking},
                user_id=user_id
            )
        
        # Update the state
        return {
            **state,
            "thinking": thinking
        }
        
    def _generate_answer_node(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate the final answer to the user's question
        
        Args:
            state: Current state of the workflow
            
        Returns:
            Updated state with the answer
        """
        thread_id = state.get("thread_id")
        conversation_id = state.get("conversation_id")
        user_id = state.get("user_id")
        question = state.get("question")
        thinking = state.get("thinking", "")
        
        # Create the answer prompt input
        answer_input = {
            "question": question,
            "planning": json.dumps(state.get("planning", {})),
            "agent_results": json.dumps(state.get("agent_results", {})),
            "thinking": thinking,
            "context": state.get("context", "")
        }
        
        # Log the answer generation using enhanced method
        if self.database:
            self.database.log_agent_thinking(
                conversation_id=conversation_id,
                thread_id=thread_id,
                agent_name=self.name,
                thinking=f"Generating final answer to question: {question}",
                user_id=user_id
            )
        
        # Run the answer prompt
        answer_response = self.model.invoke(
            self.final_response_prompt.format_messages(**answer_input)
        )
        
        # Get the answer content
        answer = answer_response.content
        
        # Store the answer in the database
        if self.database:
            self.database.add_message(
                thread_id=thread_id,
                user_id=user_id,
                role="assistant",
                content=answer
            )
            
            # Log the answer generation result using enhanced method
            self.database.log_agent_action(
                conversation_id=conversation_id,
                thread_id=thread_id,
                agent_name=self.name,
                action_name="answer_generation",
                action_input=answer_input,
                action_output={"answer": answer},
                user_id=user_id
            )
        
        # Return the updated state with the answer
        return {
            **state,
            "answer": answer,
            "messages": state.get("messages", []) + [AIMessage(content=answer)]
        }
        
    def process_question(self, thread_id: str, user_id: str, question: str, repo_url: Optional[str] = None) -> Dict[str, Any]:
        """
        Process a user question using the full agent workflow
        
        Args:
            thread_id: ID of the thread
            user_id: ID of the user
            question: User's question
            repo_url: Optional repository URL for GitHub access
            
        Returns:
            Processing result with answer
        """
        # Initialize GitHub tools if repo_url is provided and we have GitHub tools
        if repo_url and self.github_tools:
            try:
                # Extract owner and repo from URL if needed
                owner, repo = None, None
                
                # Parse GitHub URL format
                import re
                github_url_match = re.match(r'https://github.com/([^/]+)/([^/]+)', repo_url)
                if github_url_match:
                    owner = github_url_match.group(1)
                    repo = github_url_match.group(2)
                    
                    # Initialize GitHub tools with specific repo
                    if owner and repo:
                        self.github_tools.initialize(owner=owner, repo=repo)
                        
                        # Create GitHub wrapper
                        github_wrapper = self.github_tools.get_github_wrapper()
                        
                        # Initialize SQL tools with GitHub wrapper
                        if self.sql_tools:
                            self.sql_tools.initialize_with_github(github_wrapper)
                        
                        logger.info(f"Initialized GitHub tools for repo: {owner}/{repo}")
                    else:
                        logger.warning(f"Failed to parse owner/repo from URL: {repo_url}")
                        
            except Exception as e:
                logger.error(f"Error initializing GitHub tools: {str(e)}")
        
        # Find or create a conversation ID
        conversation_id = self._find_or_create_conversation(thread_id, user_id)
        
        # Get conversation context
        context = self._get_conversation_context(conversation_id, thread_id, user_id)
        
        # Create initial workflow state
        initial_state = {
            "thread_id": thread_id,
            "conversation_id": conversation_id,
            "user_id": user_id,
            "question": question,
            "context": context,
            "messages": [HumanMessage(content=question)],
            "planning": None,  # Will be populated by planning node
            "agent_results": {},  # Will be populated during execution
            "thinking": "",  # Will be populated by thinking node
            "answer": "",  # Will be populated by answer node
            "repo_url": repo_url,  # Store the repo URL in the state
            "current_step": 0,  # Initialize current step
            "max_steps": 20      # Set a default maximum number of steps
        }
        
        # Create and compile the workflow graph
        graph = self.build_graph()
        compiled_graph = graph.compile()
        
        # Make sure we have initialized all tools with GitHub if needed
        if self.github_tools and self.sql_tools:
            github_wrapper = self.github_tools.get_github_wrapper()
            if github_wrapper and hasattr(self.sql_tools, 'initialize_with_github'):
                self.sql_tools.initialize_with_github(github_wrapper)
                
                # Ensure the agents have the proper tools
                self._update_agent_tools()
        
        # Invoke the graph with the initial state and checkpointer
        try:
            logger.info(f"Starting workflow for thread {thread_id}, question: {question}")
            
            if self.checkpointer:
                result = compiled_graph.invoke(
                    initial_state,
                    {"configurable": {"checkpointer": self.checkpointer}}
                )
            else:
                result = compiled_graph.invoke(initial_state)
            
            # Store the result and save the conversation
            if self.database:
                # Save the user's question
                self.database.add_message(
                    thread_id=thread_id,
                    user_id=user_id,
                    role="user",
                    content=question
                )
                
                # Save the assistant's answer
                self.database.add_message(
                    thread_id=thread_id,
                    user_id=user_id,
                    role="assistant",
                    content=result.get("answer", "No answer generated")
                )
            
            return result
            
        except Exception as e:
            logger.error(f"Error processing question: {str(e)}")
            
            # Try to return a meaningful error response
            error_message = f"I encountered an error while processing your question: {str(e)}"
            
            # Save the error message
            if self.database:
                self.database.add_message(
                    thread_id=thread_id,
                    user_id=user_id,
                    role="assistant",
                    content=error_message
                )
            
            return {
                "thread_id": thread_id,
                "conversation_id": conversation_id,
                "user_id": user_id,
                "question": question,
                "answer": error_message,
                "error": str(e)
            }
            
    def _update_agent_tools(self):
        """Update all agents with the current SQL and GitHub tools"""
        for agent_name, agent in self.agents.items():
            if hasattr(agent, 'sql_tools'):
                agent.sql_tools = self.sql_tools
            if hasattr(agent, 'github_tools'):
                agent.github_tools = self.github_tools
        
    def _find_or_create_conversation(self, thread_id: str, user_id: str) -> str:
        """Find or create a conversation ID for the given thread and user"""
        if self.database:
            try:
                conversation_id = self.database.add_message(
                    thread_id=thread_id,
                    user_id=user_id,
                    role="user",
                    content=f"Starting new conversation: {thread_id}"
                )
                logger.info(f"Added conversation start message to thread {thread_id}, conversation {conversation_id}")
                return conversation_id
            except Exception as e:
                logger.error(f"Error finding or creating conversation: {str(e)}")
                # Continue with a default conversation ID
        
        return "default_conversation_id"
        
    def _get_conversation_context(self, conversation_id: str, thread_id: str, user_id: str) -> str:
        """Get the conversation context for the given conversation ID"""
        if self.database:
            try:
                history = self.database.get_thread_history(thread_id)
                
                # Format the history as context
                context_messages = []
                for msg in history[-10:]:  # Get the last 10 messages for context
                    if msg.get("role") == "user":
                        context_messages.append(f"User: {msg.get('content', '')}")
                    else:
                        context_messages.append(f"Assistant: {msg.get('content', '')}")
                        
                context = "\n\n".join(context_messages)
                return context
            except Exception as e:
                logger.error(f"Error getting conversation history: {str(e)}")
                # Continue with empty context
        
        return ""
        
    def run(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run the SQL supervisor agent on the given input data
        
        Args:
            input_data: Input data for the agent
            
        Returns:
            Output from the agent
        """
        # Extract the required parameters
        thread_id = input_data.get("thread_id")
        user_id = input_data.get("user_id")
        question = input_data.get("question")
        repo_url = input_data.get("repo_url")
        
        if not thread_id or not user_id or not question:
            return {"error": "Thread ID, user ID, and question are required"}
            
        return self.process_question(thread_id, user_id, question, repo_url)

    def _ensure_visualization_format(self, visualization_data):
        """
        Ensure consistent format for visualization data
        
        Args:
            visualization_data: Raw visualization data
            
        Returns:
            Properly formatted visualization data
        """
        if not visualization_data or not isinstance(visualization_data, dict):
            # Return empty visualization structure
            return {
                "models": [],
                "edges": [],
                "metadata": {}
            }
            
        # Ensure the required fields exist
        if "models" not in visualization_data:
            visualization_data["models"] = []
        if "edges" not in visualization_data:
            visualization_data["edges"] = []
        if "metadata" not in visualization_data:
            visualization_data["metadata"] = {}
            
        return visualization_data 