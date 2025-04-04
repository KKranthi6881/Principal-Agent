"""
HuggingFace provider implementation
"""
import os
from typing import List, Dict, Any, Optional

# Fix imports to use conditional imports to handle missing packages
try:
    from langchain_huggingface import HuggingFaceEndpoint, ChatHuggingFace
except ImportError:
    # Provide fallback stubs for testing or development
    HuggingFaceEndpoint = None
    ChatHuggingFace = None

from .base import BaseLLMProvider


class HuggingFaceProvider(BaseLLMProvider):
    """
    Provider implementation for HuggingFace models
    """
    
    def __init__(self, model_name: str = "mistralai/Mixtral-8x7B-Instruct-v0.1", **kwargs):
        """
        Initialize the HuggingFace provider with model and API key
        
        Args:
            model_name (str, optional): Name of the model to use. Defaults to "mistralai/Mixtral-8x7B-Instruct-v0.1".
            **kwargs: Additional arguments to pass to the provider
        """
        super().__init__(model_name, **kwargs)
        
        # Check if required packages are installed
        if HuggingFaceEndpoint is None or ChatHuggingFace is None:
            raise ImportError(
                "Could not import langchain_huggingface package. "
                "Please install it with `pip install langchain-huggingface`."
            )
        
        self.api_key = kwargs.get("api_key")
        if not self.api_key:
            raise ValueError("API key is required for HuggingFace")
        
        # Initialize the HuggingFace client
        self.client = ChatHuggingFace(
            model_name=model_name,
            huggingfacehub_api_token=self.api_key,
            temperature=kwargs.get("temperature", 0.0),
            max_new_tokens=kwargs.get("max_tokens", 1024)
        )
        
    @staticmethod
    def get_provider_name() -> str:
        """
        Get the name of the provider
        
        Returns:
            str: Provider name
        """
        return "HuggingFace"
        
    @staticmethod
    def get_available_models() -> List[Dict[str, Any]]:
        """
        Get a list of available models for this provider
        
        Returns:
            List[Dict[str, Any]]: List of model information dictionaries
        """
        return [
            {
                "id": "mistralai/Mixtral-8x7B-Instruct-v0.1",
                "name": "Mixtral 8x7B",
                "context_length": 32000,
                "description": "Powerful mixture of experts model"
            },
            {
                "id": "meta-llama/Meta-Llama-3-8B-Instruct",
                "name": "Llama 3 8B",
                "context_length": 8000,
                "description": "Compact, efficient open-source model"
            },
            {
                "id": "meta-llama/Meta-Llama-3-70B-Instruct",
                "name": "Llama 3 70B",
                "context_length": 8000,
                "description": "Powerful open-source model"
            },
            {
                "id": "mistralai/Mistral-7B-Instruct-v0.2",
                "name": "Mistral 7B",
                "context_length": 8000,
                "description": "Efficient instruction-tuned model"
            }
        ]
        
    def chat_completion(self, messages: List[Dict[str, str]], **kwargs) -> str:
        """
        Generate a chat completion using HuggingFace
        
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
            error_msg = f"Error generating chat completion with HuggingFace: {str(e)}"
            print(error_msg)
            return f"I encountered an error: {error_msg}" 