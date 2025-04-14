"""
API for LLM models
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import sqlite3
import os

# Handle potential import errors
try:
    from models.model_manager import model_manager
except ImportError:
    print("WARNING: Could not import model_manager. Models API functionality may be limited.")
    model_manager = None

from config.llm_config import get_active_models

# Path to metadata database
METADATA_DB = os.path.join('database', 'metadata.db')

router = APIRouter(prefix="/models", tags=["models"])


class ChatMessage(BaseModel):
    """Chat message model"""
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    """Chat completion request model"""
    messages: List[ChatMessage]
    provider: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = 0
    max_tokens: Optional[int] = None
    stream: Optional[bool] = False


class ChatCompletionResponse(BaseModel):
    """Chat completion response model"""
    content: str
    provider: str
    model: str


class ModelInfo(BaseModel):
    """Model information"""
    model_id: str
    provider_id: str
    provider_name: str
    name: str
    description: str
    context_length: int
    is_default: bool


@router.get("/providers")
async def get_providers():
    """
    Get all available LLM providers
    """
    if model_manager is None:
        return []
        
    try:
        return model_manager.get_all_providers()
    except Exception as e:
        print(f"Error getting providers: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting providers: {str(e)}")


@router.get("/")
async def get_models():
    """
    Get all available LLM models
    """
    if model_manager is None:
        return []
        
    try:
        return model_manager.get_all_models()
    except Exception as e:
        print(f"Error getting models: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting models: {str(e)}")


@router.post("/chat/completions", response_model=ChatCompletionResponse)
async def chat_completion(request: ChatCompletionRequest):
    """
    Generate a chat completion
    """
    if model_manager is None:
        raise HTTPException(
            status_code=503, 
            detail="Model manager is not available. Please check backend configuration."
        )
        
    try:
        # Convert Pydantic models to dictionaries
        messages = [{"role": msg.role, "content": msg.content} for msg in request.messages]
        
        # Get the response
        content = model_manager.chat_completion(
            messages=messages,
            provider_name=request.provider,
            model_name=request.model,
            temperature=request.temperature,
            max_tokens=request.max_tokens
        )
        
        # Determine which provider and model were used (in case defaults were applied)
        provider = request.provider or model_manager.default_provider
        model = request.model or model_manager.default_model
        
        return ChatCompletionResponse(
            content=content,
            provider=provider,
            model=model
        )
    except ValueError as e:
        # This is typically a configuration error (invalid provider, etc.)
        raise HTTPException(status_code=400, detail=f"Configuration error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating chat completion: {str(e)}")


def get_db_connection():
    """Get a connection to the metadata database"""
    conn = sqlite3.connect(METADATA_DB)
    conn.row_factory = sqlite3.Row
    return conn


@router.get("/models", response_model=List[ModelInfo])
async def get_all_models():
    """
    Get all available models regardless of active state.
    This is primarily used for admin and setup purposes.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get all models with provider info
        cursor.execute("""
            SELECT m.*, p.name as provider_name
            FROM llm_models m
            JOIN llm_providers p ON m.provider_id = p.provider_id
            ORDER BY m.provider_id, m.name
        """)
        
        models = []
        for row in cursor.fetchall():
            models.append({
                "model_id": row["model_id"],
                "provider_id": row["provider_id"],
                "provider_name": row["provider_name"],
                "name": row["name"],
                "description": row["description"],
                "context_length": row["context_length"],
                "is_default": bool(row["is_default"])
            })
        
        conn.close()
        return models
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting models: {str(e)}")


@router.get("/active", response_model=Dict[str, Any])
async def get_active_models_api():
    """
    Get all models that have active provider configurations.
    This endpoint is used by the frontend for model selection.
    """
    try:
        # Use the get_active_models function from llm_config
        active_models = get_active_models()
        
        # Transform the data structure to be more frontend-friendly
        models_list = []
        for model_id, model_data in active_models.items():
            models_list.append({
                "model_id": model_id,
                "provider_id": model_data["provider"]["id"],
                "provider_name": model_data["provider"]["name"],
                "name": model_data["model"]["name"],
                "description": model_data["model"].get("description", ""),
                "context_length": model_data["model"].get("context_length", 0),
                "is_default": model_data["model"].get("is_default", False),
                "has_api_key": bool(model_data["config"].get("api_key"))
            })
        
        # Group models by provider
        providers = {}
        for model in models_list:
            provider_id = model["provider_id"]
            if provider_id not in providers:
                providers[provider_id] = {
                    "id": provider_id,
                    "name": model["provider_name"],
                    "models": []
                }
            
            # Remove redundant provider info before adding to the group
            model_copy = model.copy()
            model_copy.pop("provider_id")
            model_copy.pop("provider_name")
            providers[provider_id]["models"].append(model_copy)
        
        return {
            "models": models_list,
            "providers": list(providers.values())
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting active models: {str(e)}")


@router.get("/models/{model_id}", response_model=ModelInfo)
async def get_model(model_id: str):
    """
    Get information about a specific model
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get the model with provider info
        cursor.execute("""
            SELECT m.*, p.name as provider_name
            FROM llm_models m
            JOIN llm_providers p ON m.provider_id = p.provider_id
            WHERE m.model_id = ?
        """, (model_id,))
        
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Model {model_id} not found")
        
        conn.close()
        
        return {
            "model_id": row["model_id"],
            "provider_id": row["provider_id"],
            "provider_name": row["provider_name"],
            "name": row["name"],
            "description": row["description"],
            "context_length": row["context_length"],
            "is_default": bool(row["is_default"])
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting model: {str(e)}")


@router.get("/models/provider/{provider_id}", response_model=List[ModelInfo])
async def get_provider_models(provider_id: str):
    """
    Get all models for a specific provider
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get all models for the provider
        cursor.execute("""
            SELECT m.*, p.name as provider_name
            FROM llm_models m
            JOIN llm_providers p ON m.provider_id = p.provider_id
            WHERE m.provider_id = ?
            ORDER BY m.name
        """, (provider_id,))
        
        models = []
        for row in cursor.fetchall():
            models.append({
                "model_id": row["model_id"],
                "provider_id": row["provider_id"],
                "provider_name": row["provider_name"],
                "name": row["name"],
                "description": row["description"],
                "context_length": row["context_length"],
                "is_default": bool(row["is_default"])
            })
        
        conn.close()
        
        if not models:
            raise HTTPException(status_code=404, detail=f"No models found for provider {provider_id}")
        
        return models
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting provider models: {str(e)}") 