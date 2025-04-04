"""
Ollama provider implementation
"""
import os
from typing import List, Dict, Any, Optional

# Fix imports to use the correct class names
try:
    from langchain_ollama import OllamaLLM, ChatOllama
except ImportError:
    # Provide fallback stubs for testing or development
    OllamaLLM = None
    ChatOllama = None

from .base import BaseLLMProvider


class OllamaProvider(BaseLLMProvider):
    """
    Ollama provider implementation for LangChain integration
    """
    
    def __init__(self, model_name: str = "llama3", **kwargs):
        """
        Initialize the Ollama provider
        
        Args:
            model_name (str, optional): Name of the model to use. Defaults to "llama3".
            **kwargs: Additional provider-specific parameters
        """
        super().__init__(model_name, **kwargs)
        
        # Check if required packages are installed
        if OllamaLLM is None:
            raise ImportError(
                "Could not import langchain_ollama package. "
                "Please install it with `pip install langchain-ollama`."
            )
        
        self.base_url = kwargs.get("base_url") or os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
        self.temperature = kwargs.get("temperature", 0.0)
        self.max_tokens = kwargs.get("max_tokens")
        
        # Initialize the Ollama client
        self.client = ChatOllama(
            model=model_name,
            temperature=self.temperature,
            num_predict=self.max_tokens,
            base_url=self.base_url,
            num_ctx=kwargs.get("num_ctx", 4096)  # Default context size, adjust if needed
        )
    
    @staticmethod
    def get_provider_name() -> str:
        """
        Get the name of the provider
        
        Returns:
            str: The provider name
        """
        return "Ollama"
    
    @staticmethod
    def get_available_models() -> List[Dict[str, Any]]:
        """
        Get a list of available Ollama models
        
        Returns:
            List[Dict[str, Any]]: List of model information dictionaries
        """
        try:
            # This would be better with an actual API call to Ollama to get available models
            # For now, we'll return a static list of common models
            return [
                {"id": "llama3", "name": "Meta Llama 3", "context_length": 8000, "description": "Llama 3 8B model from Meta"},
                {"id": "llama3.1", "name": "Meta Llama 3.1", "context_length": 8000, "description": "Updated version of Llama 3 8B model"},
                {"id": "mistral", "name": "Mistral 7B", "context_length": 8000, "description": "Mistral AI's foundation model"},
                {"id": "mixtral", "name": "Mixtral 8x7B", "context_length": 32000, "description": "Mistral's mixture of experts model"},
                {"id": "gemma", "name": "Gemma 7B", "context_length": 8000, "description": "Google's lightweight open model"},
                {"id": "phi3:mini", "name": "Phi-3 Mini", "context_length": 4000, "description": "Microsoft's compact model"}
            ]
        except Exception as e:
            print(f"Error getting Ollama models: {e}")
            return []
    
    def chat_completion(self, messages: List[Dict[str, str]], **kwargs) -> str:
        """
        Generate a chat completion using Ollama
        
        Args:
            messages (List[Dict[str, str]]): List of messages in the conversation
            **kwargs: Additional arguments to pass to the chat completion
            
        Returns:
            str: The generated response
        """
        try:
            response = self.client.invoke(messages)
            return response.content
        except Exception as e:
            error_msg = f"Error generating chat completion with Ollama: {str(e)}"
            print(error_msg)
            return f"I encountered an error: {error_msg}" 