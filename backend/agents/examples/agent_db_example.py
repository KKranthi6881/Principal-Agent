"""
Example of using the unified database interface with agents
"""

import sys
import os
import json
from typing import Dict, Any
import uuid

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Import the unified database interface
from database.database import db
from agents.sql_supervisor import SQLSupervisorAgent

def demonstrate_basic_usage():
    """Demonstrate basic usage of the unified database interface"""
    print("\n1. Basic Database Operations")

    # Create a thread
    user_id = f"user_{str(uuid.uuid4())[:8]}"
    thread_id = db.create_thread(user_id=user_id, topic="SQL Agent Demo")
    print(f"Created thread: {thread_id}")
    
    # Add a user message
    conversation_id = db.add_message(
        thread_id=thread_id,
        user_id=user_id,
        role="user",
        content="How can I optimize my SQL joins?"
    )
    print(f"Added user message: {conversation_id}")
    
    # Add an assistant message
    assistant_id = db.add_message(
        thread_id=thread_id,
        user_id="assistant",
        role="assistant",
        content="I can help you optimize your SQL joins!"
    )
    print(f"Added assistant message: {assistant_id}")
    
    # Get thread history
    history = db.get_thread_history(thread_id)
    print(f"Thread history has {len(history)} messages")
    for msg in history:
        print(f"  - {msg['role']}: {msg['content'][:30]}...")
    
    # Log agent thinking
    thinking_id = db.log_agent_thinking(
        conversation_id=conversation_id,
        thread_id=thread_id,
        agent_name="sql_optimizer",
        thinking="I need to analyze the user's query patterns to suggest optimizations.",
        user_id=user_id
    )
    print(f"Logged agent thinking: {thinking_id}")
    
    # Log agent action
    action_id = db.log_agent_action(
        conversation_id=conversation_id,
        thread_id=thread_id,
        agent_name="sql_optimizer",
        action_name="analyze_joins",
        action_input={"query": "SELECT * FROM users JOIN orders ON users.id = orders.user_id"},
        action_output={"suggestion": "Add index on orders.user_id for faster joins"},
        user_id=user_id
    )
    print(f"Logged agent action: {action_id}")
    
    # Get agent logs
    logs = db.get_agent_logs(conversation_id)
    print(f"Found {len(logs)} agent logs")
    for log in logs:
        print(f"  - {log['agent_name']}: {log['action'] if 'action' in log else 'thinking'}")
    
    # Log tool usage
    tool_id = db.add_tool_log(
        thread_id=thread_id,
        conversation_id=conversation_id,
        user_id=user_id,
        tool_name="query_analyzer",
        tool_input={"query": "SELECT * FROM users JOIN orders ON users.id = orders.user_id"},
        tool_output={"indexes": ["orders.user_id"], "estimated_rows": 1000}
    )
    print(f"Logged tool usage: {tool_id}")

def demonstrate_agent_workflow():
    """Demonstrate how agents would use the database interface in a workflow"""
    print("\n2. Agent Workflow Example")
    
    # Create test data
    user_id = f"user_{str(uuid.uuid4())[:8]}"
    thread_id = db.create_thread(user_id=user_id, topic="SQL Query Analysis")
    print(f"Created thread: {thread_id}")
    
    # User message
    user_message = "What does this query do: SELECT * FROM orders WHERE date > '2023-01-01'"
    conversation_id = db.add_message(
        thread_id=thread_id,
        user_id=user_id,
        role="user",
        content=user_message
    )
    print(f"Added user message: {conversation_id}")
    
    # Multi-agent workflow simulation
    print("Simulating multi-agent workflow...")
    
    # Supervisor agent planning
    supervisor_thinking_id = db.log_agent_thinking(
        conversation_id=conversation_id,
        thread_id=thread_id,
        agent_name="SQL Supervisor",
        thinking="I need to break down this query and analyze its components.",
        user_id=user_id
    )
    
    planning_result = {
        "question_type": "code_summary",
        "entities": {"tables": ["orders"], "columns": ["orders.date"]},
        "plan": [
            {
                "step": 1,
                "agent": "code_summarizer",
                "action": "summarize_query",
                "params": {"query": "SELECT * FROM orders WHERE date > '2023-01-01'"}
            }
        ]
    }
    
    planning_id = db.log_agent_action(
        conversation_id=conversation_id,
        thread_id=thread_id,
        agent_name="SQL Supervisor",
        action_name="planning",
        action_input={"question": user_message},
        action_output=planning_result,
        user_id=user_id
    )
    
    # Specialized agent execution
    summarizer_thinking_id = db.log_agent_thinking(
        conversation_id=conversation_id,
        thread_id=thread_id,
        agent_name="Code Summarizer",
        thinking="Analyzing the SQL query structure and purpose...",
        user_id=user_id
    )
    
    summarizer_result = {
        "summary": "This query retrieves all columns from the orders table where the date is after January 1, 2023.",
        "tables": ["orders"],
        "filters": ["date > '2023-01-01'"]
    }
    
    summarizer_id = db.log_agent_action(
        conversation_id=conversation_id,
        thread_id=thread_id,
        agent_name="Code Summarizer",
        action_name="summarize_query",
        action_input={"query": "SELECT * FROM orders WHERE date > '2023-01-01'"},
        action_output=summarizer_result,
        user_id=user_id
    )
    
    # Supervisor agent final answer generation
    final_thinking_id = db.log_agent_thinking(
        conversation_id=conversation_id,
        thread_id=thread_id,
        agent_name="SQL Supervisor",
        thinking="Putting together the final answer based on the code summarizer's analysis...",
        user_id=user_id
    )
    
    final_answer = "This query retrieves all order records from the database that were created after January 1, 2023. It's a simple filter operation that returns all columns from the orders table for entries with a date more recent than the specified cutoff."
    
    # Save the final answer as an assistant message
    assistant_id = db.add_message(
        thread_id=thread_id,
        user_id="assistant",
        role="assistant",
        content=final_answer
    )
    
    answer_id = db.log_agent_action(
        conversation_id=conversation_id,
        thread_id=thread_id,
        agent_name="SQL Supervisor",
        action_name="generate_answer",
        action_input={"question": user_message, "summary": summarizer_result["summary"]},
        action_output={"answer": final_answer},
        user_id=user_id
    )
    
    print("Multi-agent workflow completed!")
    print(f"Answer: {final_answer}")
    
    # Get all agent logs for this conversation
    logs = db.get_agent_logs(conversation_id)
    print(f"Number of agent log entries: {len(logs)}")

if __name__ == "__main__":
    # Run the demonstrations
    demonstrate_basic_usage()
    demonstrate_agent_workflow() 