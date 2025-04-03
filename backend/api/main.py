from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, List, Optional, Any
from .database_manager import DatabaseManager
from .vector_store_manager import VectorStoreManager

app = FastAPI(title="Data Architect API")
db_manager = DatabaseManager()
vector_manager = VectorStoreManager()

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