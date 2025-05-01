"""
Backend Server

This module starts the FastAPI server and initializes all components.
"""

import os
import uvicorn
from fastapi import FastAPI, HTTPException, Request, Body
from fastapi.middleware.cors import CORSMiddleware
import logging
import sqlite3
from typing import Dict, Any, Optional

# Import API routers
from api import llm_providers_api
from api import github_connectors_api
from api import github_vector_api
from api import models_api
from api import sql_dependencies_api
from api import settings_api
from api import sql_analysis_api
from api.sql_agent_routes import router as sql_agent_router
from api.conversation_history_api import router as conversation_history_router
from api.lineage_api import router as lineage_router

# Import database components
from database.migrations import run_migrations
from database.database import db

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Principal-Agent Backend",
    description="Backend API for SQL lineage analysis and GitHub integration",
    version="1.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(llm_providers_api.router)
#app.include_router(github_connectors_api.router)
#app.include_router(github_vector_api.router)
app.include_router(models_api.router)
app.include_router(sql_dependencies_api.router)
app.include_router(settings_api.router)
app.include_router(sql_analysis_api.router)
app.include_router(sql_agent_router, prefix="/sql-agent", tags=["SQL Agent"])
app.include_router(conversation_history_router)
app.include_router(lineage_router)
app.include_router(github_connectors_api.router)
app.include_router(github_vector_api.router)
from api import github_local_api
app.include_router(github_local_api.router)

# Architect Analyze API endpoint
@app.post("/api/architect/analyze/")
async def architect_analyze(
    query: str = Body(..., embed=True),
    conversation_id: Optional[str] = Body(None, embed=True),
    thread_id: Optional[str] = Body(None, embed=True),
    provider: Optional[str] = Body(None, embed=True),
    model: Optional[str] = Body(None, embed=True)
):
    """
    Endpoint to process user queries using the SQL Supervisor Agent
    
    Args:
        query: The user's query
        conversation_id: Existing conversation ID
        thread_id: Existing thread ID
        provider: LLM provider ID (e.g., 'openai', 'anthropic', 'ollama')
        model: LLM model ID (e.g., 'gpt-4o', 'claude-3-sonnet')
    
    Returns:
        JSON response with conversation_id, thread_id, and response text
    """
    try:
        # Log request details
        logger.info(f"Architect analyze request: query='{query}', provider={provider}, model={model}")
        
        # Special handling for ollama provider
        if provider == 'ollama':
            logger.info("Using Ollama provider - no API key required")
            
        # Import and get the SQL Supervisor Agent with the specified provider and model
        from api.sql_agent_routes import get_agent
        agent = get_agent(provider_id=provider, model_id=model)
        
        # Create a thread if needed
        if not thread_id:
            # Generate a random thread_id
            import uuid
            thread_id = str(uuid.uuid4())
            db.create_thread("user", f"Conversation {thread_id[:8]}")
        
        # Store the user message
        if not conversation_id:
            db.add_message(
                thread_id=thread_id,
                user_id="user",
                role="user",
                content=query
            )
        
        # Process the question
        result = agent.process_question(
            thread_id=thread_id,
            user_id="user",
            question=query,
        )
        
        # Get the answer
        answer = result.get("answer", "I'm sorry, I couldn't process your query.")
        
        # Store the assistant's response
        assistant_conversation_id = db.add_message(
            thread_id=thread_id,
            user_id="assistant",
            role="assistant",
            content=answer
        )
        
        return {
            "conversation_id": assistant_conversation_id,
            "thread_id": thread_id,
            "response": answer
        }
    except Exception as e:
        logger.error(f"Error in architect_analyze: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing query: {str(e)}")

# Startup event
@app.on_event("startup")
async def startup_event():
    try:
        # Run database migrations
        logger.info("Running database migrations...")
        run_migrations.run_all_migrations()
        
        # Create database directories if they don't exist
        logger.info("Ensuring database directories exist...")
        db_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "database")
        os.makedirs(db_dir, exist_ok=True)
        
        # Initialize vector stores - these should be lazy-loaded when needed
        logger.info("API initialized successfully!")
    except Exception as e:
        logger.error(f"Error during startup: {str(e)}")

# Default route
@app.get("/")
async def root():
    return {"message": "Welcome to the Data Architect API"}

# Health check endpoint
@app.get("/health")
async def health_check():
    return {"status": "healthy"}

# Run the application
if __name__ == "__main__":
    # Get port from environment or use default
    port = int(os.getenv("PORT", 8000))
    
    # Run server
    uvicorn.run(
        "run:app",
        host="0.0.0.0",
        port=port,
        reload=True  # Enable auto-reload during development
    ) 