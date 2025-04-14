"""
SQL Agent API Routes
"""

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel
from typing import Dict, List, Optional, Any
import uuid
import logging
import os
from datetime import datetime

from agents.sql_supervisor import SQLSupervisorAgent
# Use the unified database interface instead of direct ConversationDB
from database.database import db
from tools.sql_tools.llm_interface import llm_interface as sql_tools

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create a router
router = APIRouter()

# Initialize the agent
# In a real app, you'd initialize this with proper LLM models
agent = None

class ThreadRequest(BaseModel):
    """Request to create a new thread"""
    user_id: str
    topic: str

class ThreadResponse(BaseModel):
    """Response for a thread creation"""
    thread_id: str
    topic: str
    created_at: str

class MessageRequest(BaseModel):
    """Request to send a message"""
    thread_id: str
    user_id: str
    message: str
    repo_url: Optional[str] = None
    dialect: Optional[str] = None

class MessageResponse(BaseModel):
    """Response containing a message"""
    conversation_id: str
    thread_id: str
    user_id: str
    role: str
    content: str
    created_at: str

class ConversationHistory(BaseModel):
    """Conversation history"""
    thread_id: str
    messages: List[MessageResponse]

def get_agent(provider_id: str = None, model_id: str = None) -> SQLSupervisorAgent:
    """Get the SQL supervisor agent with the specified provider and model
    
    Args:
        provider_id: Provider ID (e.g., 'openai', 'anthropic', 'ollama')
        model_id: Model ID (e.g., 'gpt-4o', 'claude-3-5-sonnet', 'llama3')
        
    Returns:
        Initialized SQL supervisor agent
    """
    global agent
    
    try:
        # Import the necessary components
        from langchain_openai import ChatOpenAI
        from langchain_anthropic import ChatAnthropic
        from langchain_google_genai import ChatGoogleGenerativeAI
        from langchain_community.chat_models import ChatOllama
        from config.llm_config import get_provider_config_from_db
        
        # Get the model based on provider
        if provider_id and model_id:
            logger.info(f"Initializing agent with provider: {provider_id}, model: {model_id}")
            
            # Get provider configuration from database
            config = get_provider_config_from_db(provider_id)
            
            # Initialize the appropriate model based on provider
            if provider_id == "openai":
                # Check if API key exists for OpenAI
                if not config.get("api_key"):
                    logger.error("No API key found for OpenAI")
                    raise HTTPException(status_code=400, detail="OpenAI API key is required but not configured")
                
                model = ChatOpenAI(
                    model_name=model_id,
                    api_key=config.get("api_key"),
                    base_url=config.get("base_url"),
                    organization=config.get("organization")
                )
            elif provider_id == "anthropic":
                # Check if API key exists for Anthropic
                if not config.get("api_key"):
                    logger.error("No API key found for Anthropic")
                    raise HTTPException(status_code=400, detail="Anthropic API key is required but not configured")
                
                model = ChatAnthropic(
                    model=model_id,
                    api_key=config.get("api_key")
                )
            elif provider_id == "google":
                # Check if API key exists for Google
                if not config.get("api_key"):
                    logger.error("No API key found for Google")
                    raise HTTPException(status_code=400, detail="Google API key is required but not configured")
                
                model = ChatGoogleGenerativeAI(
                    model=model_id,
                    google_api_key=config.get("api_key")
                )
            elif provider_id == "ollama":
                # Ollama is local, so no API key check is needed
                logger.info("Using Ollama - no API key required")
                
                model = ChatOllama(
                    model=model_id,
                    base_url=config.get("base_url") or "http://localhost:11434"
                )
            else:
                # Default to OpenAI if provider not recognized
                logger.warning(f"Provider {provider_id} not recognized, falling back to OpenAI")
                config = get_provider_config_from_db("openai")
                
                # Check if API key exists for fallback OpenAI
                if not config.get("api_key"):
                    logger.error("No API key found for fallback OpenAI provider")
                    raise HTTPException(status_code=400, detail="OpenAI API key is required but not configured")
                
                model = ChatOpenAI(
                    model_name="gpt-4o",
                    api_key=config.get("api_key"),
                    base_url=config.get("base_url"),
                    organization=config.get("organization")
                )
        else:
            # Use default OpenAI model from database if no provider/model specified
            logger.info("No provider/model specified, using default OpenAI model")
            config = get_provider_config_from_db("openai")
            
            # Check if API key exists for default OpenAI
            if not config.get("api_key"):
                logger.error("No API key found for default OpenAI provider")
                raise HTTPException(status_code=400, detail="OpenAI API key is required but not configured")
            
            model = ChatOpenAI(
                model_name="gpt-4o",
                api_key=config.get("api_key"),
                base_url=config.get("base_url"),
                organization=config.get("organization")
            )
        
        # Initialize the agent with the unified database interface
        agent = SQLSupervisorAgent(
            model=model,
            database=db,  # Pass the unified database interface
            sql_tools=sql_tools
        )
        
        logger.info("SQL Supervisor Agent initialized successfully")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error initializing agent: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error initializing agent: {str(e)}")
            
    return agent

@router.post("/threads/", response_model=ThreadResponse)
async def create_thread(request: ThreadRequest):
    """Create a new conversation thread"""
    try:
        thread_id = db.create_thread(request.user_id, request.topic)
        
        # Get the thread info
        thread_info = {
            "thread_id": thread_id,
            "topic": request.topic,
            "created_at": datetime.now().isoformat()
        }
        
        return thread_info
    except Exception as e:
        logger.error(f"Error creating thread: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error creating thread: {str(e)}")

@router.post("/messages/", response_model=MessageResponse)
async def send_message(
    request: MessageRequest, 
    background_tasks: BackgroundTasks,
    agent: SQLSupervisorAgent = Depends(get_agent)
):
    """Send a message to the agent"""
    try:
        # Store the user message
        conversation_id = db.add_message(
            thread_id=request.thread_id,
            user_id=request.user_id,
            role="user",
            content=request.message
        )
        
        # Create a placeholder for the assistant's response
        assistant_id = db.add_message(
            thread_id=request.thread_id,
            user_id="assistant",
            role="assistant",
            content="Thinking..."
        )
        
        # Process the message in the background
        background_tasks.add_task(
            process_message,
            agent=agent,
            thread_id=request.thread_id,
            user_id=request.user_id,
            conversation_id=assistant_id,
            message=request.message,
            repo_url=request.repo_url
        )
        
        # Get the user message info
        history = db.get_thread_history(request.thread_id)
        message_info = None
        
        for msg in history:
            if msg.get("conversation_id") == conversation_id:
                message_info = msg
                break
                
        if not message_info:
            raise HTTPException(status_code=404, detail="Message not found")
            
        return {
            "conversation_id": message_info.get("conversation_id"),
            "thread_id": message_info.get("thread_id"),
            "user_id": message_info.get("user_id"),
            "role": message_info.get("role"),
            "content": message_info.get("content"),
            "created_at": message_info.get("created_at", datetime.now().isoformat())
        }
    except Exception as e:
        logger.error(f"Error sending message: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error sending message: {str(e)}")

@router.get("/threads/{thread_id}/messages/", response_model=ConversationHistory)
async def get_thread_history(thread_id: str):
    """Get the conversation history for a thread"""
    try:
        history = db.get_thread_history(thread_id)
        
        messages = []
        for msg in history:
            messages.append({
                "conversation_id": msg.get("conversation_id"),
                "thread_id": msg.get("thread_id"),
                "user_id": msg.get("user_id"),
                "role": msg.get("role"),
                "content": msg.get("content"),
                "created_at": msg.get("created_at", datetime.now().isoformat())
            })
            
        return {
            "thread_id": thread_id,
            "messages": messages
        }
    except Exception as e:
        logger.error(f"Error getting thread history: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting thread history: {str(e)}")

@router.get("/logs/{conversation_id}/", response_model=Dict[str, Any])
async def get_agent_logs(conversation_id: str):
    """Get the agent logs for a conversation"""
    try:
        logs = db.get_agent_logs(conversation_id)
        
        return {
            "conversation_id": conversation_id,
            "logs": logs
        }
    except Exception as e:
        logger.error(f"Error getting agent logs: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting agent logs: {str(e)}")

async def process_message(
    agent: SQLSupervisorAgent,
    thread_id: str,
    user_id: str,
    conversation_id: str,
    message: str,
    repo_url: Optional[str] = None
):
    """Process a message in the background"""
    try:
        # Process the message with the agent
        result = agent.process_question(
            thread_id=thread_id,
            user_id=user_id,
            question=message,
            repo_url=repo_url
        )
        
        # Get the answer from the result
        answer = result.get("answer", "I'm sorry, I couldn't process your question.")
        
        # Use the unified database interface to update the placeholder message
        # Connect to the database using the conversation_db's connection
        db_conn = db.conversation_db._get_connection()
        cursor = db_conn.cursor()
        
        try:
            cursor.execute(
                "UPDATE conversations SET content = ? WHERE conversation_id = ?",
                (answer, conversation_id)
            )
            
            db_conn.commit()
        except Exception as e:
            logger.error(f"Error updating conversation: {str(e)}")
            db_conn.rollback()
        finally:
            db_conn.close()
            
        logger.info(f"Message processed successfully: {conversation_id}")
    except Exception as e:
        logger.error(f"Error processing message: {str(e)}")
        
        # Update the placeholder message with an error
        try:
            # Use the unified database interface's connection
            db_conn = db.conversation_db._get_connection()
            cursor = db_conn.cursor()
            
            try:
                cursor.execute(
                    "UPDATE conversations SET content = ? WHERE conversation_id = ?",
                    (f"Error processing message: {str(e)}", conversation_id)
                )
                
                db_conn.commit()
            except Exception as update_e:
                logger.error(f"Error updating conversation with error: {str(update_e)}")
                db_conn.rollback()
            finally:
                db_conn.close()
        except Exception as db_e:
            logger.error(f"Error connecting to database: {str(db_e)}") 