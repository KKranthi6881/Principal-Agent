"""
Vector store package for managing embedding databases
"""

# Import important modules for external use
from .vector_manager import VectorManager
from .github_vectorstore import get_github_vector_store, decrypt_api_key, add_code_files_batch

__all__ = ['VectorManager', 'get_github_vector_store', 'decrypt_api_key', 'add_code_files_batch'] 