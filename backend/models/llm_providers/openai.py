"""
OpenAI provider implementation
"""
import os
import sqlite3
from typing import List, Dict, Any, Optional
import logging
import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from langchain_openai import ChatOpenAI, OpenAI
from .base import BaseLLMProvider, ProviderError, ModelNotFoundError

# Logger for this module
logger = logging.getLogger(__name__)
# Set the logger level to DEBUG for detailed output
logger.setLevel(logging.DEBUG)
# Add console handler if not already added
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(levelname)s:%(name)s: %(message)s'))
    logger.addHandler(handler)

# Log module import success
logger.info("OpenAI provider module loaded successfully")

# Path to metadata database
METADATA_DB = os.path.join('database', 'metadata.db')

# Encryption/decryption utilities
def get_encryption_key():
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
    key = get_encryption_key()
    return Fernet(key)

def decrypt_api_key(encrypted_api_key: str) -> str:
    """Decrypt an API key"""
    if not encrypted_api_key:
        return None
    try:
        cipher = get_cipher()
        return cipher.decrypt(encrypted_api_key.encode()).decode()
    except Exception as e:
        logger.error(f"Error decrypting API key: {str(e)}")
        return None

def get_openai_api_key() -> str:
    """Get OpenAI API key from database or environment"""
    conn = None
    api_key = None
    
    try:
        logger.info("Attempting to retrieve OpenAI API key from database")
        conn = sqlite3.connect(METADATA_DB)
        
        # First try the llm_provider_configs table
        try:
            # Set row_factory to make results easier to access
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("SELECT api_key, api_key_encrypted FROM llm_provider_configs WHERE provider_id = ? AND active = ?", ("openai", 1))
            result = cursor.fetchone()
            
            if result and result['api_key']:
                # Check if key is encrypted and decrypt if needed
                try:
                    # SQLite stores booleans as integers (0 or 1) or strings
                    is_encrypted_val = result['api_key_encrypted']
                    is_encrypted = False
                    
                    # Handle different boolean representations
                    if isinstance(is_encrypted_val, bool):
                        is_encrypted = is_encrypted_val
                    elif isinstance(is_encrypted_val, int):
                        is_encrypted = bool(is_encrypted_val)
                    elif isinstance(is_encrypted_val, str):
                        is_encrypted = is_encrypted_val.lower() in ('true', 't', 'yes', 'y', '1')
                    else:
                        # Default to True for safety
                        is_encrypted = True
                        
                    logger.debug(f"API key encryption status: {is_encrypted} (original value: {is_encrypted_val}, type: {type(is_encrypted_val).__name__})")
                except (IndexError, KeyError):
                    # If api_key_encrypted column doesn't exist in the result
                    is_encrypted = True  # Default to encrypted for safety
                    logger.debug("Could not determine encryption status, assuming encrypted for safety")
                
                raw_key = result['api_key']
                
                if is_encrypted:
                    decrypted_key = decrypt_api_key(raw_key)
                    if decrypted_key:
                        api_key = decrypted_key
                        logger.info("Found and decrypted OpenAI API key in llm_provider_configs table")
                    else:
                        logger.warning("Failed to decrypt OpenAI API key from llm_provider_configs table")
                else:
                    api_key = raw_key
                    logger.info("Found unencrypted OpenAI API key in llm_provider_configs table")
        except Exception as e:
            logger.warning(f"Error querying llm_provider_configs table: {str(e)}")
        
        # Try environment variable as fallback
        if not api_key:
            api_key = os.environ.get("OPENAI_API_KEY")
            if api_key:
                logger.info("Using OpenAI API key from environment variable")
        
        return api_key
    except Exception as e:
        logger.error(f"Error retrieving OpenAI API key: {str(e)}")
        return os.environ.get("OPENAI_API_KEY")
    finally:
        if conn:
            conn.close()

class OpenAIProvider(BaseLLMProvider):
    """
    OpenAI LLM Provider
    """
    
    def __init__(self, model_name: str = None, temperature: float = 0, max_tokens: int = None,
                 timeout: int = 60, max_retries: int = 2, api_key: str = None, base_url: str = None,
                 organization: str = None, **kwargs):
        """
        Initialize the OpenAI LLM Provider
        
        Args:
            model_name (str, optional): Name of the model. Defaults to None.
            temperature (float, optional): Temperature for generation. Defaults to 0.
            max_tokens (int, optional): Maximum tokens to generate. Defaults to None.
            timeout (int, optional): Request timeout in seconds. Defaults to 60.
            max_retries (int, optional): Maximum number of retries. Defaults to 2.
            api_key (str, optional): OpenAI API key. Defaults to None.
            base_url (str, optional): OpenAI API base URL. Defaults to None.
            organization (str, optional): OpenAI organization ID. Defaults to None.
            **kwargs: Additional arguments to pass to the OpenAI client
        """
        super().__init__(model_name, temperature, max_tokens, timeout, max_retries, **kwargs)
        self.api_key = api_key or get_openai_api_key()
        self.base_url = base_url
        self.organization = organization
        
        # Default model if none specified
        if not self.model_name:
            self.model_name = "gpt-3.5-turbo"
        
        # Client configuration
        client_args = {
            "api_key": self.api_key
        }
        
        if self.base_url:
            client_args["base_url"] = self.base_url
        if self.organization:
            client_args["organization"] = self.organization
        if self.timeout:
            client_args["timeout"] = self.timeout
        if self.max_retries:
            client_args["max_retries"] = self.max_retries
            
        # Initialize the OpenAI client
        try:
            self.client = OpenAI(**client_args)
        except Exception as e:
            raise ProviderError(f"Error initializing OpenAI client: {str(e)}")
    
    @classmethod
    def get_provider_name(cls) -> str:
        """
        Get the provider name
        
        Returns:
            str: The provider name
        """
        return "OpenAI"
    
    @classmethod
    def get_available_models(cls) -> List[Dict[str, Any]]:
        """
        Get available OpenAI models
        
        Returns:
            List[Dict[str, Any]]: List of available models
        """
        return [
            {
                "id": "gpt-4o",
                "name": "GPT-4o",
                "description": "Latest gpt-4o model with vision capabilities",
                "context_length": 128000,
                "is_default": True
            },
            {
                "id": "gpt-4o-mini",
                "name": "GPT-4o Mini",
                "description": "Improved gpt-4o-mini model with longer context",
                "context_length": 128000,
                "is_default": False
            },
            {
                "id": "gpt-4.1-mini",
                "name": "GPT-4.1 Mini",
                "description": "High-capability gpt-4.1-mini model",
                "context_length": 8192,
                "is_default": False
            },
            {
                "id": "gpt-4.1",
                "name": "GPT-4.1",
                "description": "Fast and cost-effective gpt-4.1 model",
                "context_length": 16385,
                "is_default": False
            },
            {
                "id": "gpt-4o-nano",
                "name": "GPT-4o Nano",
                "description": "Fast and cost-effective gpt-4o-nano model",
                "context_length": 16385,
                "is_default": False
            }
        ] 

    def chat_completion(self, messages: List[Dict[str, str]], **kwargs) -> str:
        """
        Generate a chat completion
        
        Args:
            messages: List of message dictionaries with 'role' and 'content'
            **kwargs: Additional arguments for the chat completion
        
        Returns:
            str: The generated completion
        """
        if not self.api_key:
            raise ProviderError("OpenAI API key is required")
            
        try:
            # Handle case where input messages don't have proper format
            formatted_messages = []
            for msg in messages:
                if not isinstance(msg, dict) or 'role' not in msg or 'content' not in msg:
                    # Skip messages with invalid format
                    continue
                
                # Ensure roles are valid for OpenAI
                role = msg['role'].lower()
                if role not in ['system', 'user', 'assistant', 'function']:
                    # Convert unknown roles to user as fallback
                    role = 'user'
                
                formatted_messages.append({
                    "role": role,
                    "content": msg['content']
                })
            
            # If no valid messages after filtering, return an error
            if not formatted_messages:
                return "Error: No valid messages provided."
            
            # Make the API call
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=formatted_messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens if self.max_tokens else None,
                **kwargs
            )
            
            # Return just the text content
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            error_msg = f"Error generating completion: {str(e)}"
            logger.error(error_msg)
            # Return a user-friendly error message
            return f"I encountered an error while processing your request: {str(e)}" 