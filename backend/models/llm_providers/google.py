"""
Google provider implementation
"""
import os
from typing import List, Dict, Any, Optional

# Fix imports to use conditional imports to handle missing packages
try:
    from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAI
except ImportError:
    # Provide fallback stubs for testing or development
    ChatGoogleGenerativeAI = None
    GoogleGenerativeAI = None

from .base import BaseLLMProvider


class GoogleProvider(BaseLLMProvider):
    """
    Google provider implementation for LangChain integration
    """
    
    def __init__(self, model_name: str = "gemini-1.5-pro", temperature: float = 0, 
                 max_tokens: Optional[int] = None, timeout: Optional[int] = None, 
                 max_retries: int = 2, api_key: Optional[str] = None, **kwargs):
        """
        Initialize the Google provider
        
        Args:
            model_name (str, optional): Name of the model to use. Defaults to "gemini-1.5-pro".
            temperature (float, optional): Temperature parameter for response generation. Defaults to 0.
            max_tokens (int, optional): Maximum number of tokens to generate. Defaults to None.
            timeout (int, optional): Timeout in seconds for the API call. Defaults to None.
            max_retries (int, optional): Maximum number of retries for failed API calls. Defaults to 2.
            api_key (str, optional): Google API key. Defaults to None.
            **kwargs: Additional provider-specific parameters
        """
        super().__init__(model_name, temperature, max_tokens, timeout, max_retries, **kwargs)
        
        # Check if required packages are installed
        if ChatGoogleGenerativeAI is None:
            raise ImportError(
                "Could not import langchain_google_genai package. "
                "Please install it with `pip install langchain-google-genai`."
            )
        
        self.api_key = api_key or os.environ.get("GOOGLE_API_KEY")
        
    def get_llm(self):
        """
        Get an instance of the Google LLM
        
        Returns:
            GoogleGenerativeAI: An instance of the Google LangChain LLM
        """
        return GoogleGenerativeAI(
            model=self.model_name,
            temperature=self.temperature,
            max_output_tokens=self.max_tokens,
            timeout=self.timeout,
            maxRetries=self.max_retries,
            google_api_key=self.api_key,
            **self.additional_params
        )
    
    def get_chat_model(self):
        """
        Get an instance of the Google Chat Model
        
        Returns:
            ChatGoogleGenerativeAI: An instance of the Google LangChain Chat Model
        """
        return ChatGoogleGenerativeAI(
            model=self.model_name,
            temperature=self.temperature,
            max_output_tokens=self.max_tokens,
            timeout=self.timeout,
            max_retries=self.max_retries,
            google_api_key=self.api_key,
            **self.additional_params
        )
    
    @classmethod
    def get_available_models(cls) -> List[Dict[str, Any]]:
        """
        Get a list of available Google models
        
        Returns:
            List[Dict[str, Any]]: List of model information dictionaries
        """
        return [
            {"id": "gemini-1.5-pro", "name": "Gemini 1.5 Pro", "context_length": 1000000, "description": "Most capable model with vision capabilities"},
            {"id": "gemini-1.5-flash", "name": "Gemini 1.5 Flash", "context_length": 1000000, "description": "Balanced, cost-effective solution"},
            {"id": "gemini-1.0-pro", "name": "Gemini 1.0 Pro", "context_length": 32000, "description": "Previous generation model"},
            {"id": "gemini-1.0-ultra", "name": "Gemini 1.0 Ultra", "context_length": 32000, "description": "Previous generation high-capability model"}
        ]
    
    @staticmethod
    def get_provider_name() -> str:
        """
        Get the name of the provider
        
        Returns:
            str: The provider name
        """
        return "Google" 