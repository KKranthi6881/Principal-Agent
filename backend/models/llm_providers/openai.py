"""
OpenAI provider implementation
"""
import os
from typing import List, Dict, Any, Optional

from langchain_openai import ChatOpenAI, OpenAI
from .base import BaseLLMProvider


class OpenAIProvider(BaseLLMProvider):
    """
    OpenAI provider implementation for LangChain integration
    """
    
    def __init__(self, model_name: str = "gpt-4o", temperature: float = 0, 
                 max_tokens: Optional[int] = None, timeout: Optional[int] = None, 
                 max_retries: int = 2, api_key: Optional[str] = None, 
                 base_url: Optional[str] = None, organization: Optional[str] = None, **kwargs):
        """
        Initialize the OpenAI provider
        
        Args:
            model_name (str, optional): Name of the model to use. Defaults to "gpt-4o".
            temperature (float, optional): Temperature parameter for response generation. Defaults to 0.
            max_tokens (int, optional): Maximum number of tokens to generate. Defaults to None.
            timeout (int, optional): Timeout in seconds for the API call. Defaults to None.
            max_retries (int, optional): Maximum number of retries for failed API calls. Defaults to 2.
            api_key (str, optional): OpenAI API key. Defaults to None.
            base_url (str, optional): Base URL for the OpenAI API. Defaults to None.
            organization (str, optional): OpenAI organization ID. Defaults to None.
            **kwargs: Additional provider-specific parameters
        """
        super().__init__(model_name, temperature, max_tokens, timeout, max_retries, **kwargs)
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.base_url = base_url
        self.organization = organization
        
    def get_llm(self):
        """
        Get an instance of the OpenAI LLM
        
        Returns:
            OpenAI: An instance of the OpenAI LangChain LLM
        """
        return OpenAI(
            model=self.model_name,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            timeout=self.timeout,
            max_retries=self.max_retries,
            api_key=self.api_key,
            base_url=self.base_url,
            organization=self.organization,
            **self.additional_params
        )
    
    def get_chat_model(self):
        """
        Get an instance of the OpenAI Chat Model
        
        Returns:
            ChatOpenAI: An instance of the OpenAI LangChain Chat Model
        """
        return ChatOpenAI(
            model=self.model_name,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            timeout=self.timeout,
            max_retries=self.max_retries,
            api_key=self.api_key,
            base_url=self.base_url,
            organization=self.organization,
            **self.additional_params
        )
    
    @classmethod
    def get_available_models(cls) -> List[Dict[str, Any]]:
        """
        Get a list of available OpenAI models
        
        Returns:
            List[Dict[str, Any]]: List of model information dictionaries
        """
        return [
            {"id": "gpt-4o", "name": "GPT-4o", "context_length": 128000, "description": "Most capable model, optimized for chat"},
            {"id": "gpt-4o-mini", "name": "GPT-4o Mini", "context_length": 128000, "description": "Smaller and more cost-effective model"},
            {"id": "gpt-4-turbo", "name": "GPT-4 Turbo", "context_length": 128000, "description": "High-performance model with quick response time"},
            {"id": "gpt-3.5-turbo", "name": "GPT-3.5 Turbo", "context_length": 16000, "description": "Fast and cost-effective model"}
        ]
    
    @staticmethod
    def get_provider_name() -> str:
        """
        Get the name of the provider
        
        Returns:
            str: The provider name
        """
        return "OpenAI" 