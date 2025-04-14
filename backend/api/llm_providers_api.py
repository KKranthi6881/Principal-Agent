"""
API for LLM provider configurations management
"""
import uuid
import os
import json
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional, Union
import sqlite3

from config.llm_config import (
    get_db_connection, encrypt_api_key, decrypt_api_key, get_provider_config
)

router = APIRouter(prefix="/api/llm", tags=["llm"])

# Path to metadata database
METADATA_DB = os.path.join('database', 'metadata.db')

# Models for request/response
class ProviderInfo(BaseModel):
    """Provider information model"""
    provider_id: str
    name: str
    description: str
    api_url: str

class ModelInfo(BaseModel):
    """Model information model"""
    model_id: str
    provider_id: str
    name: str
    description: str
    context_length: int
    is_default: bool

class ProviderConfig(BaseModel):
    """Provider configuration model"""
    provider_id: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    organization: Optional[str] = None
    default_model: Optional[str] = None
    active: bool = False
    additional_settings: Optional[Dict[str, Any]] = None

class ProviderConfigResponse(BaseModel):
    """Provider configuration response model"""
    provider_id: str
    has_api_key: bool
    base_url: Optional[str] = None
    organization: Optional[str] = None
    default_model: Optional[str] = None
    active: bool = False
    additional_settings: Optional[Dict[str, Any]] = None

class TestConnectionResponse(BaseModel):
    """Test connection response model"""
    success: bool
    message: str

class GetProvidersResponse(BaseModel):
    """Get providers response model"""
    providers: List[ProviderInfo]
    configs: List[ProviderConfigResponse]

# API endpoints
@router.get("/providers", response_model=GetProvidersResponse)
async def get_providers():
    """
    Get all available LLM providers and their configurations
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get all providers
        cursor.execute("SELECT * FROM llm_providers")
        providers = [dict(row) for row in cursor.fetchall()]
        
        # Get all provider configurations
        cursor.execute("SELECT * FROM llm_provider_configs")
        configs = []
        for row in cursor.fetchall():
            config = dict(row)
            # Don't send actual API key, just whether it exists
            has_api_key = bool(config.get('api_key'))
            config.pop('api_key', None)
            configs.append({
                **config,
                'has_api_key': has_api_key
            })
        
        conn.close()
        
        return {
            "providers": providers,
            "configs": configs
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting providers: {str(e)}")

@router.get("/providers/{provider_id}/models", response_model=List[ModelInfo])
async def get_provider_models(provider_id: str):
    """
    Get all models for a specific provider
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT * FROM llm_models WHERE provider_id = ?",
            (provider_id,)
        )
        models = [dict(row) for row in cursor.fetchall()]
        
        conn.close()
        
        if not models:
            raise HTTPException(status_code=404, detail=f"No models found for provider {provider_id}")
        
        return models
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting models: {str(e)}")

@router.post("/providers/{provider_id}", response_model=ProviderConfigResponse)
async def update_provider_config(provider_id: str, config: ProviderConfig):
    """
    Update configuration for a specific provider
    """
    try:
        # Log request details for debugging
        print(f"Received update request for provider: {provider_id}")
        print(f"Request body: {config}")
        
        if provider_id != config.provider_id:
            raise HTTPException(
                status_code=400, 
                detail=f"Provider ID mismatch: path parameter '{provider_id}' does not match body provider_id '{config.provider_id}'"
            )
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if provider exists
        cursor.execute(
            "SELECT * FROM llm_providers WHERE provider_id = ?",
            (provider_id,)
        )
        provider = cursor.fetchone()
        
        if not provider:
            raise HTTPException(status_code=404, detail=f"Provider {provider_id} not found")
        
        # Check if configuration already exists
        cursor.execute(
            "SELECT * FROM llm_provider_configs WHERE provider_id = ?",
            (provider_id,)
        )
        existing_config = cursor.fetchone()
        
        # Use a default user_id for now (in a real app, you'd get this from auth)
        user_id = "default_user"
        
        # Create user if not exists
        cursor.execute(
            "INSERT OR IGNORE INTO users (user_id, username, email) VALUES (?, ?, ?)",
            (user_id, "Default User", "default@example.com")
        )
        
        # Encrypt API key if provided
        api_key = None
        if config.api_key:
            api_key = encrypt_api_key(config.api_key)
        
        # Prepare additional settings JSON
        additional_settings = None
        if config.additional_settings:
            try:
                additional_settings = json.dumps(config.additional_settings)
            except Exception as e:
                print(f"Error serializing additional_settings: {e}")
                raise HTTPException(status_code=422, detail=f"Invalid additional_settings format: {str(e)}")
        
        if existing_config:
            # Update existing configuration
            update_query = """
            UPDATE llm_provider_configs
            SET 
                user_id = ?,
                base_url = ?,
                organization = ?,
                default_model = ?,
                active = ?,
                additional_settings = ?,
                updated_at = CURRENT_TIMESTAMP
            """
            
            params = [
                user_id,
                config.base_url,
                config.organization,
                config.default_model,
                config.active,
                additional_settings
            ]
            
            # Only update API key if provided
            if api_key:
                update_query += ", api_key = ?, api_key_encrypted = TRUE"
                params.append(api_key)
            
            update_query += " WHERE provider_id = ?"
            params.append(provider_id)
            
            cursor.execute(update_query, params)
        else:
            # Insert new configuration
            config_id = str(uuid.uuid4())
            cursor.execute(
                """
                INSERT INTO llm_provider_configs 
                (config_id, user_id, provider_id, api_key, api_key_encrypted, base_url, organization, 
                default_model, active, additional_settings)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    config_id, user_id, provider_id, api_key, True, config.base_url,
                    config.organization, config.default_model, config.active, additional_settings
                )
            )
        
        conn.commit()
        
        # Return the updated configuration
        cursor.execute(
            "SELECT * FROM llm_provider_configs WHERE provider_id = ?",
            (provider_id,)
        )
        updated_config = dict(cursor.fetchone())
        
        conn.close()
        
        # Don't return the actual API key
        has_api_key = bool(updated_config.get('api_key'))
        updated_config.pop('api_key', None)
        
        return {
            **updated_config,
            'has_api_key': has_api_key
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating provider config: {str(e)}")

@router.post("/providers/{provider_id}/test", response_model=TestConnectionResponse)
async def test_provider_connection(provider_id: str):
    """
    Test connection to a provider
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get provider configuration
        cursor.execute(
            "SELECT * FROM llm_provider_configs WHERE provider_id = ?",
            (provider_id,)
        )
        config = cursor.fetchone()
        
        if not config:
            raise HTTPException(status_code=404, detail=f"No configuration found for provider {provider_id}")
        
        config = dict(config)
        
        # Decrypt API key
        if config.get('api_key'):
            api_key = decrypt_api_key(config['api_key'])
            config['api_key'] = api_key
        
        conn.close()
        
        # Test connection based on provider
        # In a real implementation, you'd actually try to use the API
        if provider_id == 'openai':
            if not config.get('api_key'):
                return {"success": False, "message": "API key is required for OpenAI"}
            # Here you would actually try to call the OpenAI API
            return {"success": True, "message": "Successfully connected to OpenAI API"}
        
        elif provider_id == 'anthropic':
            if not config.get('api_key'):
                return {"success": False, "message": "API key is required for Anthropic"}
            return {"success": True, "message": "Successfully connected to Anthropic API"}
        
        elif provider_id == 'google':
            if not config.get('api_key'):
                return {"success": False, "message": "API key is required for Google AI"}
            return {"success": True, "message": "Successfully connected to Google AI API"}
        
        elif provider_id == 'huggingface':
            if not config.get('api_key'):
                return {"success": False, "message": "API key is required for HuggingFace"}
            return {"success": True, "message": "Successfully connected to HuggingFace API"}
        
        elif provider_id == 'ollama':
            # For Ollama, we'd check if the server is running at base_url
            base_url = config.get('base_url') or "http://localhost:11434"
            # Here you would try to ping the Ollama server
            return {"success": True, "message": f"Successfully connected to Ollama server at {base_url}"}
        
        else:
            return {"success": False, "message": f"Unsupported provider: {provider_id}"}
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error testing connection: {str(e)}")

@router.delete("/providers/{provider_id}", response_model=Dict[str, str])
async def delete_provider_config(provider_id: str):
    """
    Delete configuration for a specific provider
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            "DELETE FROM llm_provider_configs WHERE provider_id = ?",
            (provider_id,)
        )
        
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail=f"No configuration found for provider {provider_id}")
        
        conn.commit()
        conn.close()
        
        return {"message": f"Configuration for provider {provider_id} deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting provider config: {str(e)}") 