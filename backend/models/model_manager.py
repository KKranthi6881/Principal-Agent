"""
Model Manager for handling LLM operations
"""
from typing import List, Dict, Any, Optional

from config.llm_config import (
    get_provider_config, 
    DEFAULT_PROVIDER, 
    DEFAULT_TEMPERATURE, 
    DEFAULT_MAX_TOKENS
)
from .llm_providers import get_llm_provider, BaseLLMProvider

# Import providers conditionally to avoid errors if they're not installed
# These imports are just for type hints and for listing available models
try:
    from .llm_providers.openai import OpenAIProvider
except ImportError:
    OpenAIProvider = None

try:
    from .llm_providers.anthropic import AnthropicProvider
except ImportError:
    AnthropicProvider = None

try:
    from .llm_providers.google import GoogleProvider
except ImportError:
    GoogleProvider = None

try:
    from .llm_providers.huggingface import HuggingFaceProvider
except ImportError:
    HuggingFaceProvider = None

try:
    from .llm_providers.ollama import OllamaProvider
except ImportError:
    OllamaProvider = None


class ModelManager:
    """
    Model Manager for handling LLM operations
    """
    
    def __init__(self):
        """Initialize the ModelManager"""
        self.default_provider = DEFAULT_PROVIDER
        self.default_model = None  # Will be determined based on provider
        
        # Dictionary of provider classes, filtered to only include those that are available
        self.providers = {}
        if OpenAIProvider:
            self.providers["openai"] = OpenAIProvider
        if AnthropicProvider:
            self.providers["anthropic"] = AnthropicProvider
        if GoogleProvider:
            self.providers["google"] = GoogleProvider
        if HuggingFaceProvider:
            self.providers["huggingface"] = HuggingFaceProvider
        if OllamaProvider:
            self.providers["ollama"] = OllamaProvider
        
        # If no providers are available, add a default warning
        if not self.providers:
            print("WARNING: No LLM providers are available. Please install at least one provider package.")
    
    def get_provider(self, provider_name: str = None, model_name: str = None, **kwargs) -> BaseLLMProvider:
        """
        Get an LLM provider
        
        Args:
            provider_name (str, optional): Name of the provider. Defaults to None.
            model_name (str, optional): Name of the model. Defaults to None.
            **kwargs: Additional arguments to pass to the provider
            
        Returns:
            BaseLLMProvider: An instance of the requested LLM provider
        """
        provider_name = provider_name or self.default_provider
        
        # Get the provider through the factory function, which has its own error handling
        try:
            return get_llm_provider(provider_name, model_name=model_name, **kwargs)
        except ValueError as e:
            # If the default provider isn't available, try to fall back to the first available one
            if provider_name == self.default_provider and self.providers:
                fallback_provider = next(iter(self.providers.keys()))
                print(f"Warning: Default provider '{provider_name}' not available. "
                      f"Falling back to '{fallback_provider}'")
                return get_llm_provider(fallback_provider, model_name=None, **kwargs)
            else:
                raise e
    
    def get_all_providers(self) -> List[Dict[str, Any]]:
        """
        Get information about all available providers
        
        Returns:
            List[Dict[str, Any]]: List of provider information dictionaries
        """
        result = []
        
        for provider_id, provider_class in self.providers.items():
            try:
                result.append({
                    "id": provider_id,
                    "name": provider_class.get_provider_name(),
                    "models": provider_class.get_available_models()
                })
            except Exception as e:
                print(f"Error getting information for provider {provider_id}: {e}")
                # Include the provider with a warning about the error
                result.append({
                    "id": provider_id,
                    "name": f"{provider_id.title()} (Error)",
                    "models": []
                })
        
        return result
    
    def get_all_models(self) -> List[Dict[str, Any]]:
        """
        Get information about all available models across all providers
        
        Returns:
            List[Dict[str, Any]]: List of model information dictionaries
        """
        all_models = []
        
        for provider_id, provider_class in self.providers.items():
            try:
                provider_name = provider_class.get_provider_name()
                models = provider_class.get_available_models()
                
                for model in models:
                    all_models.append({
                        "id": f"{provider_id}/{model['id']}",
                        "provider_id": provider_id,
                        "provider_name": provider_name,
                        "model_id": model["id"],
                        "name": model["name"],
                        "context_length": model.get("context_length", 0),
                        "description": model.get("description", "")
                    })
            except Exception as e:
                print(f"Error getting models for provider {provider_id}: {e}")
        
        return all_models
    
    def chat_completion(self, messages: List[Dict[str, str]], provider_name: str = None, 
                        model_name: str = None, temperature: float = DEFAULT_TEMPERATURE,
                        max_tokens: int = DEFAULT_MAX_TOKENS, **kwargs) -> str:
        """
        Generate a chat completion
        
        Args:
            messages (List[Dict[str, str]]): List of messages in the conversation
            provider_name (str, optional): Name of the provider. Defaults to None.
            model_name (str, optional): Name of the model. Defaults to None.
            temperature (float, optional): Temperature for generation. Defaults to DEFAULT_TEMPERATURE.
            max_tokens (int, optional): Maximum tokens to generate. Defaults to DEFAULT_MAX_TOKENS.
            **kwargs: Additional arguments to pass to the chat completion
            
        Returns:
            str: The generated response
        """
        try:
            provider = self.get_provider(
                provider_name, 
                model_name, 
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs
            )
            return provider.chat_completion(messages, **kwargs)
        except Exception as e:
            error_message = f"Error generating chat completion: {str(e)}"
            print(error_message)
            return f"I encountered an error: {error_message}"


# Create a singleton instance
model_manager = ModelManager() 