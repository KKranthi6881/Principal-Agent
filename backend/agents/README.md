# SQL Multi-Agent System

This directory contains a multi-agent system for analyzing SQL code, tracing lineage, and understanding dependencies between tables and columns across different SQL dialects.

## Architecture

The system is built using a hierarchical agent architecture:

1. **Supervisor Agent**: Coordinates the specialized agents based on the user's question
2. **Specialized Agents**:
   - **Lineage Agent**: Analyzes SQL code to extract table and column lineage
   - **Dependency Agent**: Analyzes dependencies between tables, columns, and scripts
   - **Code Summarizer Agent**: Summarizes SQL code and provides explanations
   - **Description Summarizer Agent**: Provides business and technical descriptions for tables and columns

## Components

- **Base Agents**: Core agent classes that all other agents inherit from
  - `Agent`: Base class for all agents
  - `SupervisorAgent`: Base class for supervisor agents that coordinate other agents

- **SQL Agents**: Specialized agents for SQL analysis
  - `LineageAgent`: Traces lineage of tables and columns
  - `DependencyAgent`: Analyzes dependencies and impact of changes
  - `CodeSummarizerAgent`: Summarizes SQL code and explains what it does
  - `DescriptionSummarizerAgent`: Provides business and technical descriptions

- **SQL Supervisor**: Coordinates the specialized SQL agents to answer questions
  - `SQLSupervisorAgent`: Main entry point for the system

## Workflow

1. User submits a question about SQL code, tables, or columns
2. Supervisor agent plans how to answer the question using specialized agents
3. Each step in the plan is executed by the appropriate specialized agent
4. Supervisor agent combines the results to formulate a comprehensive answer
5. Response is returned to the user

## Agent States and Logging

All agent actions and states are logged in the database, allowing for:
- Traceability of agent thinking and decisions
- Visibility of agent workflow in the UI
- Persistent conversation history with thread and conversation IDs

## Usage

The system is exposed through FastAPI endpoints:

- `POST /sql-agent/threads/`: Create a new conversation thread
- `POST /sql-agent/messages/`: Send a message to the agent system
- `GET /sql-agent/threads/{thread_id}/messages/`: Get the conversation history
- `GET /sql-agent/logs/{conversation_id}/`: Get the agent logs for a conversation

## Example Questions

The system can answer a wide range of questions, including:

1. Where is the sales amount logic defined?
2. What's the lineage of the order_summary column?
3. What are the dependencies of the fact_orders table?
4. What script files does the fact_orders table exist in?
5. What are the sources for fact_orders?
6. If I modify the fact_orders table columns, what would be the impact?
7. What are the downstream scripts for model/data/fct_orders?
8. Give me a summary of the model/data/fct_orders script.
9. What changes were made to the order_summary column in the last 2 weeks?
10. Have any new tables or columns been changed recently?

## Technologies

- LangGraph for agent workflow and state management
- LangChain for LLM integration and tools
- FastAPI for exposing endpoints
- SQLite for conversation and state storage 