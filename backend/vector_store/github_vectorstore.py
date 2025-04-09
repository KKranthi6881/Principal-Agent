"""
GitHub Vector Store for handling GitHub repository embeddings

This module provides functions for creating and managing vector stores
containing GitHub repository data.
"""

import os
import logging
import chromadb
from chromadb.utils import embedding_functions
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64
import traceback

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Path to vector store
GITHUB_VECTOR_STORE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chromadb_github")

def get_encryption_key():
    # Use environment variable or a fixed salt (not ideal for production)
    salt = os.environ.get("API_KEY_SALT", "data_architect_salt").encode()
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(os.environ.get("API_KEY_SECRET", "data_architect_secret").encode()))
    return key

def get_cipher():
    key = get_encryption_key()
    return Fernet(key)

def encrypt_api_key(api_key: str) -> str:
    """Encrypt an API key"""
    cipher = get_cipher()
    return cipher.encrypt(api_key.encode()).decode()

def decrypt_api_key(encrypted_api_key: str) -> str:
    """Decrypt an API key"""
    if not encrypted_api_key:
        return None
    try:
        cipher = get_cipher()
        return cipher.decrypt(encrypted_api_key.encode()).decode()
    except Exception as e:
        logger.error(f"Error decrypting API key: {str(e)}")
        return None

def get_github_vector_store():
    """
    Get or create a ChromaDB collection for GitHub repository data
    
    Returns:
        ChromaDB collection for GitHub data
    """
    try:
        # Check if directory exists, recreate if missing
        if not os.path.exists(GITHUB_VECTOR_STORE_PATH):
            logger.warning(f"Vector store directory {GITHUB_VECTOR_STORE_PATH} doesn't exist, creating it")
            os.makedirs(GITHUB_VECTOR_STORE_PATH, exist_ok=True)
        
        # Initialize client
        try:
            logger.info(f"Creating ChromaDB client with path: {GITHUB_VECTOR_STORE_PATH}")
            chroma_client = chromadb.PersistentClient(path=GITHUB_VECTOR_STORE_PATH)
            logger.info("ChromaDB client created successfully")
        except Exception as e:
            logger.error(f"Error creating ChromaDB client: {e}")
            logger.error(traceback.format_exc())
            return None
        
        # Try to get existing collection, create if not found
        try:
            logger.info("Attempting to get existing collection 'github_code'")
            collection = chroma_client.get_collection("github_code")
            logger.info(f"Found existing GitHub vector store with {collection.count()} documents")
        except Exception as e:
            logger.info(f"Collection 'github_code' not found, creating it now: {e}")
            # Create new collection with default embedding function
            embedding_func = embedding_functions.DefaultEmbeddingFunction()
            collection = chroma_client.create_collection(
                name="github_code",
                embedding_function=embedding_func
            )
            logger.info("Created new GitHub vector store collection")
        
        # Wrap the collection with our enhanced functionality
        return EnhancedGitHubVectorStore(collection)
    except Exception as e:
        logger.error(f"Error getting GitHub vector store: {e}")
        logger.error(traceback.format_exc())
        return None


class EnhancedGitHubVectorStore:
    """
    Enhanced wrapper for ChromaDB collection that provides additional functionality
    for GitHub code embeddings
    """
    
    def __init__(self, collection):
        """
        Initialize with a ChromaDB collection
        
        Args:
            collection: ChromaDB collection
        """
        self.collection = collection
    
    def add(self, ids, documents, metadatas):
        """
        Add documents to the vector store
        
        Args:
            ids: List of document IDs
            documents: List of document contents
            metadatas: List of metadata dictionaries
            
        Returns:
            True if successful, False otherwise
        """
        try:
            self.collection.add(
                ids=ids,
                documents=documents,
                metadatas=metadatas
            )
            return True
        except Exception as e:
            logger.error(f"Error adding documents to vector store: {e}")
            logger.error(traceback.format_exc())
            return False
    
    def delete_by_repo_url(self, repo_url, embedding_provider=None):
        """
        Delete all documents for a specific repository from the vector store
        
        Args:
            repo_url: The repository URL
            embedding_provider: The embedding provider used (optional filter)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            where_clause = {"repo_url": repo_url}
            
            if embedding_provider:
                # No direct way to filter by embedding provider in metadata
                # We'll need to get the IDs first, then delete them
                results = self.collection.get(
                    where=where_clause
                )
                
                # Filter IDs by embedding provider if we can determine it
                # This is a limitation - we may not be able to directly filter by embedding provider
                # unless it's stored in the metadata
                
                # Delete by IDs
                if results and len(results['ids']) > 0:
                    self.collection.delete(
                        ids=results['ids']
                    )
            else:
                # Delete all documents for this repo
                self.collection.delete(
                    where=where_clause
                )
            
            logger.info(f"Deleted vectors for repository: {repo_url}")
            return True
        except Exception as e:
            logger.error(f"Error deleting vectors for repository {repo_url}: {e}")
            logger.error(traceback.format_exc())
            return False
    
    def delete_by_file_path(self, repo_url, file_path):
        """
        Delete a specific file from the vector store
        
        Args:
            repo_url: The repository URL
            file_path: The file path within the repository
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Delete document based on repo_url and file_path
            self.collection.delete(
                where={
                    "repo_url": repo_url,
                    "file_path": file_path
                }
            )
            
            logger.info(f"Deleted vectors for file: {repo_url}/{file_path}")
            return True
        except Exception as e:
            logger.error(f"Error deleting vectors for file {repo_url}/{file_path}: {e}")
            logger.error(traceback.format_exc())
            return False
    
    def query(self, query_text, repo_url=None, file_path=None, n_results=10):
        """
        Query the vector store for similar documents
        
        Args:
            query_text: The query text
            repo_url: Optional repository URL to filter by
            file_path: Optional file path to filter by
            n_results: Number of results to return
            
        Returns:
            Query results
        """
        try:
            where_clause = {}
            
            if repo_url:
                where_clause["repo_url"] = repo_url
            
            if file_path:
                where_clause["file_path"] = file_path
            
            # Execute query
            results = self.collection.query(
                query_texts=[query_text],
                n_results=n_results,
                where=where_clause if where_clause else None
            )
            
            # Format results to ensure consistent structure
            formatted_results = {
                'ids': [],
                'documents': [],
                'metadatas': [],
                'distances': []
            }
            
            # Handle results from different ChromaDB versions
            if results:
                # For newer ChromaDB versions, the results might already be flattened
                if 'ids' in results and isinstance(results['ids'][0], str):
                    formatted_results['ids'] = results['ids']
                    formatted_results['documents'] = results.get('documents', [])
                    formatted_results['metadatas'] = results.get('metadatas', [])
                    formatted_results['distances'] = results.get('distances', [])
                # For older ChromaDB versions with nested lists
                elif 'ids' in results and isinstance(results['ids'], list) and results['ids'] and isinstance(results['ids'][0], list):
                    formatted_results['ids'] = results['ids'][0]
                    if 'documents' in results and results['documents'] and isinstance(results['documents'][0], list):
                        formatted_results['documents'] = results['documents'][0]
                    if 'metadatas' in results and results['metadatas'] and isinstance(results['metadatas'][0], list):
                        formatted_results['metadatas'] = results['metadatas'][0] 
                    if 'distances' in results and results['distances'] and isinstance(results['distances'][0], list):
                        formatted_results['distances'] = results['distances'][0]
            
            logger.info(f"Query for '{query_text}' returned {len(formatted_results['ids'])} results")
            return formatted_results
            
        except Exception as e:
            logger.error(f"Error querying vector store: {e}")
            logger.error(traceback.format_exc())
            return {
                'ids': [],
                'documents': [],
                'metadatas': [],
                'distances': []
            }
    
    def get_stats(self, embedding_provider=None):
        """
        Get statistics about the vector store
        
        Args:
            embedding_provider: Optional embedding provider to filter by
            
        Returns:
            Dictionary of statistics
        """
        try:
            # Get all documents if count is not too large
            count = self.collection.count()
            
            if count > 10000:
                # For large collections, return basic info
                return {
                    "github_code": {
                        "count": count,
                        "embedding_providers": ["unknown"],
                        "repos": ["unknown - too many documents to analyze"]
                    }
                }
            
            # Get all documents
            results = self.collection.get()
            
            # Analyze metadata
            stats = {
                "github_code": {
                    "count": count,
                    "repos": set(),
                    "file_extensions": {},
                    "embedding_providers": set()
                }
            }
            
            if results and results.get('metadatas'):
                for metadata in results['metadatas']:
                    # Extract repo info
                    if 'repo_url' in metadata:
                        stats["github_code"]["repos"].add(metadata['repo_url'])
                    
                    # Extract file extension info
                    if 'file_extension' in metadata:
                        ext = metadata['file_extension']
                        if ext not in stats["github_code"]["file_extensions"]:
                            stats["github_code"]["file_extensions"][ext] = 0
                        stats["github_code"]["file_extensions"][ext] += 1
            
            # Convert sets to lists for JSON serialization
            stats["github_code"]["repos"] = list(stats["github_code"]["repos"])
            stats["github_code"]["embedding_providers"] = list(["unknown"]) # Can't determine from ChromaDB directly
            
            return stats
        except Exception as e:
            logger.error(f"Error getting vector store stats: {e}")
            logger.error(traceback.format_exc())
            return {
                "github_code": {
                    "count": 0,
                    "embedding_providers": [],
                    "repos": [],
                    "error": str(e)
                }
            }
    
    def count(self):
        """
        Get the number of documents in the vector store
        
        Returns:
            Document count
        """
        try:
            return self.collection.count()
        except Exception as e:
            logger.error(f"Error getting document count: {e}")
            return 0


def add_code_files_batch(ids, contents, metadatas, embedding_provider=None):
    """
    Add a batch of code files to the GitHub vector store
    
    Args:
        ids: List of document IDs
        contents: List of file contents
        metadatas: List of metadata dictionaries
        embedding_provider: Name of embedding provider to use
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Get the collection
        collection = get_github_vector_store()
        if not collection:
            logger.error("Failed to get GitHub vector store")
            return False
        
        # Set up embedding function if specified
        if embedding_provider:
            # In a full implementation, we'd switch embedding functions based on the provider
            # For now, just use the default
            logger.info(f"Using embedding provider: {embedding_provider}")
            
        # Add to collection
        return collection.add(
            ids=ids,
            documents=contents,
            metadatas=metadatas
        )
    except Exception as e:
        logger.error(f"Error adding code files to GitHub vector store: {e}")
        logger.error(traceback.format_exc())
        return False 