"""
Configuration for LLM providers
"""
import os
from typing import Dict, Any

# Helper function to get environment variable or default
def get_env(name: str, default: str = None) -> str:
    """Get environment variable or default value"""
    return os.environ.get(name, default)

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
    "default_model": "claude-3-5-sonnet-20240620"
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
    """Get the configuration for a specific provider"""
    configs = {
        "openai": OPENAI_CONFIG,
        "anthropic": ANTHROPIC_CONFIG,
        "google": GOOGLE_CONFIG,
        "huggingface": HUGGINGFACE_CONFIG,
        "ollama": OLLAMA_CONFIG
    }
    
    return configs.get(provider_name.lower(), {}) 