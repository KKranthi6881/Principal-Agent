"""
Anthropic LLM provider implementation
"""
from typing import List, Dict, Any, Optional

# Fix imports to use conditional imports to handle missing packages
try:
    from langchain_anthropic import ChatAnthropic, Anthropic
except ImportError:
    # Provide fallback stubs for testing or development
    ChatAnthropic = None
    Anthropic = None

from .base import BaseLLMProvider

class AnthropicProvider(BaseLLMProvider):
    """
    Provider implementation for Anthropic Claude models
    """
    
    def __init__(self, model_name: str = "claude-3.7-sonnet", **kwargs):
        """
        Initialize the Anthropic provider with model and API key
        
        Args:
            model_name (str, optional): Name of the model to use. Defaults to "claude-3.7-sonnet".
            **kwargs: Additional arguments to pass to the provider
        """
        super().__init__(model_name, **kwargs)
        
        # Check if required packages are installed
        if ChatAnthropic is None:
            raise ImportError(
                "Could not import langchain_anthropic package. "
                "Please install it with `pip install langchain-anthropic`."
            )
        
        self.api_key = kwargs.get("api_key")
        if not self.api_key:
            raise ValueError("API key is required for Anthropic")
        
        # Initialize the Anthropic client
        self.client = ChatAnthropic(
            model=model_name,
            anthropic_api_key=self.api_key,
            temperature=kwargs.get("temperature", 0.0),
            max_tokens=kwargs.get("max_tokens", 4096)
        )
        
    @staticmethod
    def get_provider_name() -> str:
        """
        Get the name of the provider
        
        Returns:
            str: Provider name
        """
        return "Anthropic"
        
    @staticmethod
    def get_available_models() -> List[Dict[str, Any]]:
        """
        Get a list of available models for this provider
        
        Returns:
            List[Dict[str, Any]]: List of model information dictionaries
        """
        return [
            {
                "id": "claude-3.7-sonnet",
                "name": "Claude 3.7 Sonnet",
                "context_length": 200000,
                "description": "Most advanced and powerful Claude model, designed for complex instructions and reasoning"
            },
            {
                "id": "claude-3.5-sonnet",
                "name": "Claude 3.5 Sonnet",
                "context_length": 200000,
                "description": "Most powerful Claude model with the most advanced reasoning capabilities"
            }
        ]
        
    def chat_completion(self, messages: List[Dict[str, str]], **kwargs) -> str:
        """
        Generate a chat completion using Anthropic
        
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
            error_msg = f"Error generating chat completion with Anthropic: {str(e)}"
            print(error_msg)
            return f"I encountered an error: {error_msg}" 