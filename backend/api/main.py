from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from typing import Dict, List, Optional, Any
from api.database_manager import DatabaseManager
from api.vector_store_manager import VectorStoreManager
from api.github_connectors_api import router as github_connectors_router
from api.llm_providers_api import router as llm_providers_router
from api.models_api import router as models_router
from api.github_vector_api import router as github_vector_router
from api.github_local_api import router as github_local_router
from fastapi.middleware.cors import CORSMiddleware
import os
import sqlite3
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Path to metadata database
METADATA_DB = os.path.join('database', 'metadata.db')

app = FastAPI(
    title="Data Architect API",
    description="API for Data Architect operations",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify the allowed origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

db_manager = DatabaseManager()
vector_manager = VectorStoreManager()

# Include routers
app.include_router(models_router, prefix="/models")
app.include_router(llm_providers_router)
app.include_router(github_connectors_router)
app.include_router(github_vector_router)
app.include_router(github_local_router)

# Pydantic models for request/response
class ThreadCreate(BaseModel):
    user_id: str
    topic: str

class ConversationCreate(BaseModel):
    thread_id: str
    user_id: str
    role: str
    content: str

class AgentLogCreate(BaseModel):
    thread_id: str
    conversation_id: str
    user_id: str
    agent_type: str
    input_text: str
    output_text: str
    tool_calls: Optional[Dict] = None

class ToolLogCreate(BaseModel):
    thread_id: str
    conversation_id: str
    user_id: str
    tool_name: str
    tool_input: Dict
    tool_output: Dict

class UserCreate(BaseModel):
    user_id: str
    username: str
    email: str

class ConnectionCreate(BaseModel):
    user_id: str
    connection_type: str
    connection_details: Dict

class CodeMetadataCreate(BaseModel):
    connection_id: str
    file_path: str
    file_type: str
    content_hash: str
    metadata: Dict

class VectorStoreDocument(BaseModel):
    content: str
    metadata: Dict[str, Any]

class VectorStoreSearch(BaseModel):
    query: str
    n_results: int = 5

# Initialize database
def init_db():
    """Initialize the database with necessary tables"""
    conn = sqlite3.connect(METADATA_DB)
    cursor = conn.cursor()
    
    # Create necessary tables
    # Users table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY,
        username TEXT NOT NULL,
        email TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # LLM Providers table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS llm_providers (
        provider_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        description TEXT,
        api_url TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # LLM Provider Configuration table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS llm_provider_configs (
        config_id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        provider_id TEXT NOT NULL,
        api_key TEXT,
        api_key_encrypted BOOLEAN DEFAULT FALSE,
        base_url TEXT,
        organization TEXT,
        default_model TEXT,
        active BOOLEAN DEFAULT TRUE,
        additional_settings TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (user_id),
        FOREIGN KEY (provider_id) REFERENCES llm_providers (provider_id)
    )
    ''')
    
    # LLM Models table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS llm_models (
        model_id TEXT PRIMARY KEY,
        provider_id TEXT NOT NULL,
        name TEXT NOT NULL,
        description TEXT,
        context_length INTEGER,
        is_default BOOLEAN DEFAULT FALSE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (provider_id) REFERENCES llm_providers (provider_id)
    )
    ''')
    
    # GitHub connectors table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS github_connectors (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        name TEXT NOT NULL,
        description TEXT,
        github_type TEXT NOT NULL,
        api_url TEXT,
        token TEXT,
        token_encrypted BOOLEAN DEFAULT FALSE,
        owner TEXT,
        organization TEXT,
        repositories TEXT,
        default_branch TEXT DEFAULT 'main',
        active BOOLEAN DEFAULT TRUE,
        repo_url TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (user_id)
    )
    ''')
    
    # Insert default LLM providers
    providers = [
        ('openai', 'OpenAI', 'OpenAI API for GPT models', 'https://api.openai.com'),
        ('anthropic', 'Anthropic', 'Anthropic API for Claude models', 'https://api.anthropic.com'),
        ('google', 'Google AI', 'Google AI API for Gemini models', 'https://generativelanguage.googleapis.com'),
        ('huggingface', 'HuggingFace', 'HuggingFace Inference API', 'https://api-inference.huggingface.co'),
        ('ollama', 'Ollama', 'Local LLM server using Ollama', 'http://localhost:11434')
    ]
    
    for provider in providers:
        cursor.execute(
            '''
            INSERT OR IGNORE INTO llm_providers (provider_id, name, description, api_url)
            VALUES (?, ?, ?, ?)
            ''',
            provider
        )
    
    # Insert default models for providers
    models = [
        # OpenAI models
        ('gpt-4o', 'openai', 'GPT-4o', 'Latest GPT-4 Omni model with vision capabilities', 128000, True),
        ('gpt-4-turbo', 'openai', 'GPT-4 Turbo', 'Improved GPT-4 model with longer context', 128000, False),
        ('gpt-4', 'openai', 'GPT-4', 'High-capability GPT-4 model', 8192, False),
        ('gpt-3.5-turbo', 'openai', 'GPT-3.5 Turbo', 'Fast and cost-effective GPT-3.5 model', 16385, False),
        
        # Anthropic models
        ('claude-3-opus', 'anthropic', 'Claude 3 Opus', 'Highest capability Claude model', 200000, True),
        ('claude-3-sonnet', 'anthropic', 'Claude 3 Sonnet', 'Balanced Claude model with good capabilities', 200000, False),
        ('claude-3-haiku', 'anthropic', 'Claude 3 Haiku', 'Fast and efficient Claude model', 200000, False),
        
        # Google models
        ('gemini-pro', 'google', 'Gemini Pro', 'Balanced model for most tasks', 32768, True),
        ('gemini-ultra', 'google', 'Gemini Ultra', 'Highest capability Gemini model', 32768, False),
        
        # Ollama models
        ('llama3', 'ollama', 'Llama 3', 'Meta\'s Llama 3 model via Ollama', 8192, True),
        ('llama3:8b', 'ollama', 'Llama 3 8B', 'Smaller Llama 3 model', 8192, False),
        ('mistral', 'ollama', 'Mistral', 'Mistral AI 7B model', 8192, False),
        ('mixtral', 'ollama', 'Mixtral', 'Mixtral 8x7B MoE model', 32768, False)
    ]
    
    for model in models:
        cursor.execute(
            '''
            INSERT OR IGNORE INTO llm_models 
            (model_id, provider_id, name, description, context_length, is_default)
            VALUES (?, ?, ?, ?, ?, ?)
            ''',
            model
        )
    
    conn.commit()
    conn.close()

# Initialize database on startup
@app.on_event("startup")
async def startup_event():
    """Run on application startup"""
    init_db()

# Root endpoint
@app.get("/")
async def root():
    """Root endpoint"""
    return {"message": "Welcome to the Data Architect API"}

# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}

# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all requests"""
    response = await call_next(request)
    logger.info(f"{request.method} {request.url.path} - {response.status_code}")
    return response

# Database endpoints
@app.post("/threads/", response_model=Dict[str, str])
async def create_thread(thread: ThreadCreate):
    thread_id = db_manager.create_thread(thread.user_id, thread.topic)
    return {"thread_id": thread_id}

@app.post("/conversations/", response_model=Dict[str, str])
async def add_conversation(conversation: ConversationCreate):
    conversation_id = db_manager.add_conversation(
        conversation.thread_id,
        conversation.user_id,
        conversation.role,
        conversation.content
    )
    return {"conversation_id": conversation_id}

@app.get("/threads/{thread_id}/conversations/", response_model=List[Dict[str, Any]])
async def get_thread_conversations(thread_id: str, limit: int = 6):
    return db_manager.get_thread_conversations(thread_id, limit)

@app.post("/logs/agent/", response_model=Dict[str, str])
async def log_agent_activity(log: AgentLogCreate):
    log_id = db_manager.log_agent_activity(
        log.thread_id,
        log.conversation_id,
        log.user_id,
        log.agent_type,
        log.input_text,
        log.output_text,
        log.tool_calls
    )
    return {"log_id": log_id}

@app.post("/logs/tool/", response_model=Dict[str, str])
async def log_tool_usage(log: ToolLogCreate):
    log_id = db_manager.log_tool_usage(
        log.thread_id,
        log.conversation_id,
        log.user_id,
        log.tool_name,
        log.tool_input,
        log.tool_output
    )
    return {"log_id": log_id}

@app.post("/users/", response_model=Dict[str, str])
async def create_user(user: UserCreate):
    db_manager.create_user(user.user_id, user.username, user.email)
    return {"message": "User created successfully"}

@app.post("/connections/", response_model=Dict[str, str])
async def add_connection(connection: ConnectionCreate):
    connection_id = db_manager.add_connection(
        connection.user_id,
        connection.connection_type,
        connection.connection_details
    )
    return {"connection_id": connection_id}

@app.post("/code-metadata/", response_model=Dict[str, str])
async def add_code_metadata(metadata: CodeMetadataCreate):
    metadata_id = db_manager.add_code_metadata(
        metadata.connection_id,
        metadata.file_path,
        metadata.file_type,
        metadata.content_hash,
        metadata.metadata
    )
    return {"metadata_id": metadata_id}

# Vector store endpoints
@app.post("/vector/github/", response_model=Dict[str, str])
async def add_github_file(file_path: str, document: VectorStoreDocument):
    doc_id = vector_manager.add_github_file(
        file_path,
        document.content,
        document.metadata
    )
    return {"doc_id": doc_id}

@app.post("/vector/github/search/", response_model=List[Dict[str, Any]])
async def search_github_files(search: VectorStoreSearch):
    return vector_manager.search_github_files(search.query, search.n_results)

@app.post("/vector/document/", response_model=Dict[str, str])
async def add_document(document: VectorStoreDocument):
    doc_id = vector_manager.add_document(
        document.content,
        document.metadata
    )
    return {"doc_id": doc_id}

@app.post("/vector/document/search/", response_model=List[Dict[str, Any]])
async def search_documents(search: VectorStoreSearch):
    return vector_manager.search_documents(search.query, search.n_results)

@app.post("/vector/summary/", response_model=Dict[str, str])
async def add_conversation_summary(thread_id: str, document: VectorStoreDocument):
    summary_id = vector_manager.add_conversation_summary(
        thread_id,
        document.content,
        document.metadata
    )
    return {"summary_id": summary_id}

@app.post("/vector/summary/search/", response_model=List[Dict[str, Any]])
async def search_conversation_summaries(search: VectorStoreSearch):
    return vector_manager.search_conversation_summaries(search.query, search.n_results)

@app.delete("/vector/{collection_name}/{doc_id}")
async def delete_document(collection_name: str, doc_id: str):
    try:
        vector_manager.delete_document(collection_name, doc_id)
        return {"message": "Document deleted successfully"}
    except AttributeError:
        raise HTTPException(status_code=400, detail="Invalid collection name")

@app.get("/api/thread-conversations")
async def get_all_thread_conversations():
    """
    Get all conversation threads with their latest messages
    Returns a list of thread IDs, latest questions, and conversation counts
    """
    try:
        conn = sqlite3.connect(os.path.join('database', 'conversations.db'))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Query to get threads with latest message and conversation count
        cursor.execute("""
            SELECT 
                t.thread_id,
                t.topic,
                t.created_at as thread_created_at,
                (
                    SELECT c.content 
                    FROM conversations c 
                    WHERE c.thread_id = t.thread_id AND c.role = 'user'
                    ORDER BY c.created_at DESC 
                    LIMIT 1
                ) as latest_question,
                (
                    SELECT c.created_at 
                    FROM conversations c 
                    WHERE c.thread_id = t.thread_id
                    ORDER BY c.created_at DESC 
                    LIMIT 1
                ) as latest_timestamp,
                (
                    SELECT COUNT(*) 
                    FROM conversations c 
                    WHERE c.thread_id = t.thread_id
                ) as conversation_count,
                (
                    SELECT c.conversation_id
                    FROM conversations c
                    WHERE c.thread_id = t.thread_id
                    ORDER BY c.created_at ASC
                    LIMIT 1
                ) as first_conversation_id
            FROM threads t
            ORDER BY latest_timestamp DESC
        """)
        
        threads = []
        for row in cursor.fetchall():
            threads.append({
                "thread_id": row["thread_id"],
                "topic": row["topic"],
                "latest_question": row["latest_question"],
                "latest_timestamp": row["latest_timestamp"],
                "conversation_count": row["conversation_count"],
                "first_conversation_id": row["first_conversation_id"],
                "thread_created_at": row["thread_created_at"]
            })
        
        return {"status": "success", "threads": threads}
    except Exception as e:
        logger.error(f"Error getting thread conversations: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        conn.close()

# Add a test endpoint to check if models are available
@app.get("/test-models")
async def test_models():
    """Test endpoint to check if models are available"""
    try:
        if not model_manager:
            from models.model_manager import model_manager
            
        models = model_manager.get_all_models()
        return {"success": True, "models": models}
    except Exception as e:
        logger.error(f"Error in test-models endpoint: {str(e)}")
        return {"success": False, "error": str(e)} 