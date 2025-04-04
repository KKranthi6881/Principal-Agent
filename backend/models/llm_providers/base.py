"""
Base class for LLM providers
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional


class BaseLLMProvider(ABC):
    """
    Abstract base class for LLM providers.
    All provider implementations should inherit from this class.
    """
    
    def __init__(self, model_name: str, temperature: float = 0, max_tokens: Optional[int] = None, 
                 timeout: Optional[int] = None, max_retries: int = 2, **kwargs):
        """
        Initialize the LLM provider
        
        Args:
            model_name (str): Name of the model to use
            temperature (float, optional): Temperature parameter for response generation. Defaults to 0.
            max_tokens (int, optional): Maximum number of tokens to generate. Defaults to None.
            timeout (int, optional): Timeout in seconds for the API call. Defaults to None.
            max_retries (int, optional): Maximum number of retries for failed API calls. Defaults to 2.
            **kwargs: Additional provider-specific parameters
        """
        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.max_retries = max_retries
        self.additional_params = kwargs
        
    @abstractmethod
    def get_llm(self):
        """
        Get the LangChain LLM instance.
        
        Returns:
            LLM: An instance of the LangChain LLM
        """
        pass
    
    @abstractmethod
    def get_chat_model(self):
        """
        Get the LangChain Chat Model instance.
        
        Returns:
            ChatModel: An instance of the LangChain Chat Model
        """
        pass
    
    def chat_completion(self, messages: List[Dict[str, str]], **kwargs) -> str:
        """
        Generate a chat completion.
        
        Args:
            messages (List[Dict[str, str]]): List of messages in the conversation
            **kwargs: Additional parameters for the chat completion
            
        Returns:
            str: The generated response
        """
        chat_model = self.get_chat_model()
        response = chat_model.invoke(messages, **kwargs)
        return response.content
    
    @classmethod
    def get_available_models(cls) -> List[Dict[str, Any]]:
        """
        Get a list of available models for this provider.
        
        Returns:
            List[Dict[str, Any]]: List of model information dictionaries
        """
        return []
    
    @staticmethod
    def get_provider_name() -> str:
        """
        Get the name of the provider.
        
        Returns:
            str: The provider name
        """
        return "base" 