"""
Configuration for LLM providers
"""
import os
import sqlite3
import json
import base64
from typing import Dict, Any, Optional
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

# Helper function to get environment variable or default
def get_env(name: str, default: str = None) -> str:
    """Get environment variable or default value"""
    return os.environ.get(name, default)

# Database path
METADATA_DB = os.path.join('database', 'metadata.db')

# Encryption key generation functions
def get_encryption_key():
    """Generate encryption key from environment variables or defaults"""
    # Use environment variable or a fixed salt (not ideal for production)
    salt = os.environ.get("API_KEY_SALT", "data_architect_salt").encode()
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(os.environ.get("API_KEY_SECRET", "data_architect_secret").encode()))
    return key

def get_cipher():
    """Get Fernet cipher for encryption/decryption"""
    key = get_encryption_key()
    return Fernet(key)

def encrypt_api_key(api_key: str) -> str:
    """Encrypt an API key"""
    if not api_key:
        return None
    cipher = get_cipher()
    return cipher.encrypt(api_key.encode()).decode()

def decrypt_api_key(encrypted_api_key: str) -> str:
    """Decrypt an API key"""
    if not encrypted_api_key:
        return None
    cipher = get_cipher()
    return cipher.decrypt(encrypted_api_key.encode()).decode()

def get_db_connection():
    """Get a connection to the metadata database"""
    conn = sqlite3.connect(METADATA_DB)
    conn.row_factory = sqlite3.Row
    return conn

# OpenAI configuration
OPENAI_CONFIG = {
    "api_key": get_env("OPENAI_API_KEY"),
    "base_url": get_env("OPENAI_BASE_URL"),
    "organization": get_env("OPENAI_ORGANIZATION"),
    "default_model": "gpt-4o"
}

# Anthropic configuration
ANTHROPIC_CONFIG = {
    "api_key": get_env("ANTHROPIC_API_KEY"),
    "default_model": "claude-3.7-sonnet"
}

# Google configuration
GOOGLE_CONFIG = {
    "api_key": get_env("GOOGLE_API_KEY"),
    "default_model": "gemini-1.5-pro"
}

# HuggingFace configuration
HUGGINGFACE_CONFIG = {
    "api_key": get_env("HUGGINGFACE_API_KEY"),
    "default_model": "mistralai/Mixtral-8x7B-Instruct-v0.1"
}

# Ollama configuration
OLLAMA_CONFIG = {
    "base_url": get_env("OLLAMA_BASE_URL", "http://localhost:11434"),
    "default_model": "llama3"
}

# Default provider configurations
DEFAULT_PROVIDER = "openai"
DEFAULT_TEMPERATURE = 0
DEFAULT_MAX_TOKENS = None

def get_provider_config(provider_name: str) -> Dict[str, Any]:
    """Get the configuration for a specific provider from default settings"""
    configs = {
        "openai": OPENAI_CONFIG,
        "anthropic": ANTHROPIC_CONFIG,
        "google": GOOGLE_CONFIG,
        "huggingface": HUGGINGFACE_CONFIG,
        "ollama": OLLAMA_CONFIG
    }
    
    return configs.get(provider_name.lower(), {})

def get_provider_config_from_db(provider_name: str) -> Dict[str, Any]:
    """
    Get the configuration for a specific provider from the database
    
    Args:
        provider_name: The name of the provider (e.g., 'openai', 'anthropic')
        
    Returns:
        Dictionary containing provider configuration
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get the active provider configuration from the database
        cursor.execute(
            "SELECT * FROM llm_provider_configs WHERE provider_id = ? AND active = 1",
            (provider_name,)
        )
        config_row = cursor.fetchone()
        
        if not config_row:
            # If no active config, try any config for this provider
            cursor.execute(
                "SELECT * FROM llm_provider_configs WHERE provider_id = ?",
                (provider_name,)
            )
            config_row = cursor.fetchone()
            
        if config_row:
            # Convert SQLite Row to dict
            db_config = dict(config_row)
            
            # Decrypt API key if present and needed
            if db_config.get('api_key') and db_config.get('api_key_encrypted'):
                db_config['api_key'] = decrypt_api_key(db_config['api_key'])
            
            # Parse additional settings if present
            if db_config.get('additional_settings'):
                try:
                    db_config['additional_settings'] = json.loads(db_config['additional_settings'])
                except:
                    db_config['additional_settings'] = {}
            
            # Remove database-specific fields
            db_config.pop('config_id', None)
            db_config.pop('user_id', None)
            db_config.pop('api_key_encrypted', None)
            db_config.pop('created_at', None)
            db_config.pop('updated_at', None)
            
            conn.close()
            return db_config
        
        conn.close()
    except Exception as e:
        print(f"Error getting provider config from database: {str(e)}")
    
    # Fall back to default configuration if database lookup fails
    return get_provider_config(provider_name)

def get_active_models():
    """
    Get all active models with their provider configurations
    
    Returns:
        Dictionary of model_id -> {provider_info, model_info, config}
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get all active provider configurations
        cursor.execute(
            "SELECT c.*, p.name as provider_name FROM llm_provider_configs c "
            "JOIN llm_providers p ON c.provider_id = p.provider_id "
            "WHERE c.active = 1"
        )
        active_configs = cursor.fetchall()
        
        active_models = {}
        
        for config_row in active_configs:
            # Convert SQLite Row to dict
            config = dict(config_row)
            provider_id = config['provider_id']
            
            # Get models for this provider
            cursor.execute(
                "SELECT * FROM llm_models WHERE provider_id = ?",
                (provider_id,)
            )
            models = cursor.fetchall()
            
            for model_row in models:
                # Convert SQLite Row to dict
                model = dict(model_row)
                model_id = model['model_id']
                
                # Create model entry with provider info, model info, and config
                active_models[model_id] = {
                    'provider': {
                        'id': provider_id,
                        'name': config['provider_name']
                    },
                    'model': model,
                    'config': {
                        'base_url': config.get('base_url'),
                        'api_key': decrypt_api_key(config.get('api_key')) if config.get('api_key') else None,
                        'organization': config.get('organization')
                    }
                }
        
        conn.close()
        return active_models
        
    except Exception as e:
        print(f"Error getting active models: {str(e)}")
        return {} 