"""
LLM Providers module for different language model providers.
This package contains implementations for various LLM providers like OpenAI, Anthropic, Google, etc.
"""

from .base import BaseLLMProvider

# Import providers with try-except blocks to handle missing packages gracefully
try:
    from .openai import OpenAIProvider
except ImportError:
    OpenAIProvider = None

try:
    from .anthropic import AnthropicProvider
except ImportError:
    AnthropicProvider = None

try:
    from .google import GoogleProvider
except ImportError:
    GoogleProvider = None

try:
    from .huggingface import HuggingFaceProvider
except ImportError:
    HuggingFaceProvider = None

try:
    from .ollama import OllamaProvider
except ImportError:
    OllamaProvider = None

# Factory method to get the appropriate LLM provider
def get_llm_provider(provider_name, **kwargs):
    """
    Factory method to get an LLM provider instance based on the provider name.
    
    Args:
        provider_name (str): Name of the provider (openai, anthropic, google, huggingface, ollama)
        **kwargs: Additional arguments to pass to the provider constructor
        
    Returns:
        BaseLLMProvider: An instance of the requested LLM provider
    """
    providers = {
        "openai": OpenAIProvider,
        "anthropic": AnthropicProvider,
        "google": GoogleProvider,
        "huggingface": HuggingFaceProvider,
        "ollama": OllamaProvider,
    }
    
    provider_class = providers.get(provider_name.lower())
    if not provider_class:
        available_providers = [k for k, v in providers.items() if v is not None]
        raise ValueError(
            f"Provider {provider_name} not supported or not installed. "
            f"Available providers: {available_providers}"
        )
    
    try:
        return provider_class(**kwargs)
    except ImportError as e:
        raise ValueError(
            f"Provider {provider_name} is available but its dependencies are not installed: {str(e)}"
        ) 