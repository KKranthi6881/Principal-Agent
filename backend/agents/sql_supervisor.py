"""
SQL Supervisor Agent module that defines the SQLSupervisorAgent class
This agent coordinates specialized SQL agents to answer questions about SQL code
"""

from typing import Dict, List, Optional, Any, Annotated, TypedDict, Sequence
import logging
import json
import os
import operator
from typing_extensions import TypedDict
from datetime import datetime

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser

from langgraph.graph import StateGraph, START, END
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Checkpointer

from .base.supervisor import SupervisorAgent
from .sql_agents.lineage_agent import LineageAgent
from .sql_agents.dependency_agent import DependencyAgent
from .sql_agents.code_summarizer import CodeSummarizerAgent
from .sql_agents.description_summarizer import DescriptionSummarizerAgent
from database.database import db

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
        self.planning_prompt = ChatPromptTemplate.from_template("""
            You are a SQL Analysis Planning expert. Your job is to plan how to answer user questions about SQL code,
            tables, columns, and their dependencies.
            
            User Question: {question}
            
            Previous Conversation Context:
            {context}
            
            Based on the user's question, I need you to create a plan for answering it using specialized SQL agents.
            
            Please provide a detailed plan in JSON format with the following structure:
            
            ```
            {
                "question_type": "One of: lineage_analysis, dependency_analysis, impact_analysis, code_summary, table_description, column_description, or general_query",
                "entities": {
                    "tables": ["table1", "table2"],
                    "columns": ["table.column1", "table.column2"],
                    "files": ["file1.sql", "file2.sql"]
                },
                "plan": [
                    {
                        "step": 1,
                        "agent": "agent_name",
                        "action": "action_name",
                        "params": {
                            "param1": "value1",
                            "param2": "value2"
                        },
                        "reason": "Reason for this step"
                    }
                ],
                "dialect": "The SQL dialect to use (postgres, snowflake, tsql, etc.)",
                "summary": "A summary of the plan"
            }
            ```
            
            Available agents and their actions:
            - lineage_agent: trace_table_lineage, trace_column_lineage, analyze_lineage
            - dependency_agent: analyze_dependencies, analyze_impact
            - code_summarizer: summarize_code, describe_column, summarize_file
            - description_summarizer: describe_table, describe_column
            
            Be thorough in your planning and ensure that all steps are necessary to answer the user's question completely.
        """)
        
        self.thinking_prompt = ChatPromptTemplate.from_template("""
            You are a SQL Analysis expert. Your job is to think through how to answer a complex SQL question 
            using the results from various specialized agents.
            
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
            
            Provide your detailed thinking process.
        """)
        
        self.answer_prompt = ChatPromptTemplate.from_template("""
            You are a SQL Analysis expert working with data engineers. Your job is to provide clear, concise, and helpful answers
            to questions about SQL code, tables, columns, and their dependencies.
            
            User Question: {question}
            
            My Thinking Process:
            {thinking}
            
            Now, provide a clear and helpful answer to the user's question. Format your response appropriately 
            using markdown formatting. Include relevant details like table names, column names, file paths, and GitHub URLs 
            when available. Make your answer professional, direct, and concise.
            
            If showing lineage or dependencies, use bullet lists or tables for clarity.
            If showing code snippets, use proper markdown code blocks with language syntax highlighting.
            If references to GitHub files are available, include them as links.
        """)
        
    def _create_specialized_agents(self):
        """Create the specialized agents if not provided"""
        self.agents = {
            "lineage_agent": LineageAgent(model=self.model, sql_tools=self.sql_tools),
            "dependency_agent": DependencyAgent(model=self.model, sql_tools=self.sql_tools, github_tools=self.github_tools),
            "code_summarizer": CodeSummarizerAgent(model=self.model, sql_tools=self.sql_tools),
            "description_summarizer": DescriptionSummarizerAgent(model=self.model, sql_tools=self.sql_tools)
        }
        
    def build_graph(self):
        """Build the agent workflow graph"""
        
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
        
        # Add nodes to the graph
        self.graph.add_node("planning", self._planning_node)
        self.graph.add_node("execute_step", self._execute_step_node)
        self.graph.add_node("thinking", self._thinking_node)
        self.graph.add_node("generate_answer", self._generate_answer_node)
        
        # Define the edges
        self.graph.add_edge(START, "planning")
        self.graph.add_edge("planning", "execute_step")
        self.graph.add_conditional_edges(
            "execute_step",
            self._should_continue_execution,
            {
                "continue": "execute_step",
                "done": "thinking"
            }
        )
        self.graph.add_edge("thinking", "generate_answer")
        self.graph.add_edge("generate_answer", END)
        
        # Set the default starting edges
        self.graph.set_entry_point(START)
        
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
            
            # Update the state
            return {
                **state,
                "planning": planning_json,
                "dialect": planning_json.get("dialect", ""),
                "current_step": 0,
                "max_steps": len(planning_json.get("plan", [])),
                "agent_results": {}
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
                    thinking=f"Error parsing planning response: {str(e)}\nResponse: {planning_content}",
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
            
            return {
                **state,
                "planning": error_plan,
                "dialect": "",
                "current_step": 0,
                "max_steps": 0,
                "agent_results": {}
            }
        
    def _execute_step_node(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a step in the plan using a specialized agent
        
        Args:
            state: Current state of the workflow
            
        Returns:
            Updated state with step execution results
        """
        thread_id = state.get("thread_id")
        conversation_id = state.get("conversation_id")
        user_id = state.get("user_id")
        planning = state.get("planning", {})
        current_step = state.get("current_step", 0)
        agent_results = state.get("agent_results", {})
        repo_url = state.get("repo_url")
        dialect = state.get("dialect", "")
        
        # Get the plan
        plan = planning.get("plan", [])
        
        # Check if we have a step to execute
        if current_step >= len(plan):
            return state
            
        # Get the current step
        step = plan[current_step]
        step_num = step.get("step", current_step + 1)
        agent_name = step.get("agent", "")
        action_name = step.get("action", "")
        params = step.get("params", {})
        reason = step.get("reason", "")
        
        # Add dialect to params if it's not there
        if dialect and "dialect" not in params:
            params["dialect"] = dialect
            
        # Add repo_url to params if it's not there and available
        if repo_url and "repo_url" not in params:
            params["repo_url"] = repo_url
            
        # Create a log describing the step execution using enhanced method
        if self.database:
            self.database.log_agent_thinking(
                conversation_id=conversation_id,
                thread_id=thread_id,
                agent_name=self.name,
                thinking=f"Executing step {step_num}: {agent_name}.{action_name}({params})\nReason: {reason}",
                user_id=user_id
            )
        
        # Get the agent
        agent = self.agents.get(agent_name)
        
        if not agent:
            logger.error(f"Agent {agent_name} not found")
            
            # Log the error using enhanced method
            if self.database:
                self.database.log_agent_thinking(
                    conversation_id=conversation_id,
                    thread_id=thread_id,
                    agent_name=self.name,
                    thinking=f"Error: Agent {agent_name} not found",
                    user_id=user_id
                )
                
            # Update the state
            step_result = {
                "status": "error",
                "error": f"Agent {agent_name} not found",
                "step": step_num,
                "agent": agent_name,
                "action": action_name
            }
            
            agent_results[f"step_{step_num}"] = step_result
            
            return {
                **state,
                "current_step": current_step + 1,
                "agent_results": agent_results
            }
            
        # Get the action
        action = getattr(agent, action_name, None)
        
        if not action or not callable(action):
            logger.error(f"Action {action_name} not found in agent {agent_name}")
            
            # Log the error using enhanced method
            if self.database:
                self.database.log_agent_thinking(
                    conversation_id=conversation_id,
                    thread_id=thread_id,
                    agent_name=self.name,
                    thinking=f"Error: Action {action_name} not found in agent {agent_name}",
                    user_id=user_id
                )
                
            # Update the state
            step_result = {
                "status": "error",
                "error": f"Action {action_name} not found in agent {agent_name}",
                "step": step_num,
                "agent": agent_name,
                "action": action_name
            }
            
            agent_results[f"step_{step_num}"] = step_result
            
            return {
                **state,
                "current_step": current_step + 1,
                "agent_results": agent_results
            }
            
        # Execute the action
        try:
            logger.info(f"Executing step {step_num}: {agent_name}.{action_name}({params})")
            result = action(**params)
            
            # Log the step result using enhanced method
            if self.database:
                self.database.log_agent_action(
                    conversation_id=conversation_id,
                    thread_id=thread_id,
                    agent_name=agent_name,
                    action_name=action_name,
                    action_input=params,
                    action_output=result,
                    user_id=user_id
                )
                
            # Update the state
            step_result = {
                "status": "success",
                "result": result,
                "step": step_num,
                "agent": agent_name,
                "action": action_name
            }
            
            agent_results[f"step_{step_num}"] = step_result
            
            return {
                **state,
                "current_step": current_step + 1,
                "agent_results": agent_results
            }
        except Exception as e:
            logger.error(f"Error executing step {step_num}: {str(e)}")
            
            # Log the error using enhanced method
            if self.database:
                self.database.log_agent_thinking(
                    conversation_id=conversation_id,
                    thread_id=thread_id,
                    agent_name=agent_name,
                    thinking=f"Error executing action {action_name}: {str(e)}",
                    user_id=user_id
                )
                
            # Update the state
            step_result = {
                "status": "error",
                "error": str(e),
                "step": step_num,
                "agent": agent_name,
                "action": action_name
            }
            
            agent_results[f"step_{step_num}"] = step_result
            
            return {
                **state,
                "current_step": current_step + 1,
                "agent_results": agent_results
            }
        
    def _should_continue_execution(self, state: Dict[str, Any]) -> str:
        """Check if we should continue executing steps or move to the next phase"""
        current_step = state.get("current_step", 1)
        max_steps = state.get("max_steps", 0)
        
        if current_step <= max_steps:
            return "continue"
        else:
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
            "thinking": thinking
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
            self.answer_prompt.format_messages(**answer_input)
        )
        
        # Get the answer content
        answer = answer_response.content
        
        # Store the answer in the database
        if self.database:
            self.database.add_message(
                thread_id=thread_id,
                user_id="assistant",
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
        Process a user question using the agent workflow
        
        Args:
            thread_id: ID of the conversation thread
            user_id: ID of the user
            question: User's question
            repo_url: GitHub repository URL (optional)
            
        Returns:
            Response from the agent workflow
        """
        # Store the user question in the database
        conversation_id = None
        if self.database:
            conversation_id = self.database.add_message(
                thread_id=thread_id,
                user_id=user_id,
                role="user",
                content=question
            )
            
        # Get the conversation history for context
        context = ""
        if self.database:
            history = self.database.get_thread_history(thread_id)
            
            # Format the history as context
            context_messages = []
            for msg in history[-10:]:  # Get the last 10 messages for context
                if msg.get("role") == "user":
                    context_messages.append(f"User: {msg.get('content', '')}")
                else:
                    context_messages.append(f"Assistant: {msg.get('content', '')}")
                    
            context = "\n\n".join(context_messages)
            
        # Create the initial state
        initial_state = {
            "thread_id": thread_id,
            "conversation_id": conversation_id,
            "user_id": user_id,
            "question": question,
            "context": context,
            "messages": [HumanMessage(content=question)],
            "repo_url": repo_url
        }
        
        # Run the workflow
        result = self.invoke(initial_state)
        
        return result
        
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