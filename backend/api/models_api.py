"""
API for LLM models
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Dict, Any, Optional

# Handle potential import errors
try:
    from models.model_manager import model_manager
except ImportError:
    print("WARNING: Could not import model_manager. Models API functionality may be limited.")
    model_manager = None

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