"""
GitHub Vector Store using ChromaDB
"""
import os
import chromadb
from chromadb.config import Settings
import logging
from typing import Dict, List, Optional, Union, Any
import json
import sqlite3
import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

# Import LangChain embeddings
from langchain_openai import OpenAIEmbeddings
from langchain_ollama import OllamaEmbeddings
from langchain_core.embeddings import Embeddings

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Path to metadata database
METADATA_DB = os.path.join('database', 'metadata.db')

# Encryption key generation (same as in llm_providers_api.py)
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

# Create Fernet cipher using the key
def get_cipher():
    key = get_encryption_key()
    return Fernet(key)

# Decrypt an API key
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

class GitHubVectorStore:
    """
    Vector store for GitHub code files using ChromaDB
    """
    
    def __init__(self):
        """Initialize the GitHub vector store"""
        # Create ChromaDB directory if it doesn't exist
        vector_store_dir = os.path.join("vector_store", "chromadb_github")
        os.makedirs(vector_store_dir, exist_ok=True)
        
        # Initialize ChromaDB client
        self.client = chromadb.PersistentClient(
            path=vector_store_dir,
            settings=Settings(
                allow_reset=True,
                anonymized_telemetry=False
            )
        )
        
        # Initialize embedding models
        self.embedding_models = {}
        
        # Create or get collections for different embedding providers
        self._init_collections()
        
        logger.info(f"GitHub vector store initialized in {vector_store_dir}")
    
    def _get_openai_api_key(self) -> str:
        """Get OpenAI API key from the llm_provider_config table"""
        conn = None
        api_key = None
        
        try:
            logger.info("Attempting to retrieve OpenAI API key from database")
            conn = sqlite3.connect(METADATA_DB)
            
            # First try the llm_provider_configs table (new format)
            try:
                # Set row_factory to make results easier to access
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                cursor.execute(
                    "SELECT api_key, api_key_encrypted FROM llm_provider_configs WHERE provider_id = ? AND active = ?", 
                    ("openai", 1)
                )
                
                result = cursor.fetchone()
                if result and result['api_key']:
                    try:
                        # SQLite stores booleans as integers (0 or 1) or strings
                        is_encrypted_val = result['api_key_encrypted']
                        is_encrypted = False
                        
                        # Handle different boolean representations
                        if isinstance(is_encrypted_val, bool):
                            is_encrypted = is_encrypted_val
                        elif isinstance(is_encrypted_val, int):
                            is_encrypted = bool(is_encrypted_val)
                        elif isinstance(is_encrypted_val, str):
                            is_encrypted = is_encrypted_val.lower() in ('true', 't', 'yes', 'y', '1')
                        else:
                            # Default to True for safety
                            is_encrypted = True
                            
                        logger.debug(f"API key encryption status: {is_encrypted} (original value: {is_encrypted_val}, type: {type(is_encrypted_val).__name__})")
                    except (IndexError, KeyError):
                        # If api_key_encrypted column doesn't exist in the result
                        is_encrypted = True  # Default to encrypted for safety
                        logger.debug("Could not determine encryption status, assuming encrypted for safety")
                        
                    raw_key = result['api_key']
                    
                    # Decrypt if the key is encrypted
                    if is_encrypted:
                        logger.info("Decrypting OpenAI API key from llm_provider_configs table")
                        api_key = decrypt_api_key(raw_key)
                        if api_key:
                            logger.info("Successfully decrypted OpenAI API key")
                            return api_key
                        else:
                            logger.error("Failed to decrypt OpenAI API key")
                    else:
                        logger.info("Successfully retrieved unencrypted OpenAI API key from llm_provider_configs table")
                        return raw_key
            except Exception as e:
                logger.warning(f"Error querying llm_provider_configs table: {str(e)}")

            # If that fails, try the llm_provider_config table (older format)
            try:
                cursor = conn.cursor()
                
                # Create the table if it doesn't exist
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS llm_provider_config (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        provider_name TEXT NOT NULL,
                        api_key TEXT,
                        org_id TEXT,
                        base_url TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                conn.commit()
                
                # Query the provider_name column (not provider_id)
                cursor.execute(
                    "SELECT api_key FROM llm_provider_config WHERE provider_name = ?", 
                    ("openai",)
                )
                
                result = cursor.fetchone()
                if result and result['api_key']:
                    logger.info("Successfully retrieved OpenAI API key from llm_provider_config table")
                    # This table doesn't use encryption, so return as-is
                    return result['api_key']
            except Exception as e:
                logger.warning(f"Error querying llm_provider_config table: {str(e)}")
            
            # Fallback to environment variable if not found in database
            logger.warning("OpenAI API key not found in any database tables, trying environment variable")
            env_api_key = os.environ.get("OPENAI_API_KEY", "")
            
            if env_api_key and env_api_key.strip():
                logger.info("Found OpenAI API key in environment variable")
                return env_api_key.strip()
            
            logger.error("No OpenAI API key found in database or environment variables")
            return ""
            
        except Exception as e:
            logger.error(f"Error retrieving OpenAI API key: {str(e)}")
            
            # Last attempt: check environment variable
            env_api_key = os.environ.get("OPENAI_API_KEY", "")
            if env_api_key and env_api_key.strip():
                logger.info("Found OpenAI API key in environment variable (after exception)")
                return env_api_key.strip()
                
            return ""
        finally:
            if conn:
                conn.close()
    
    def _init_collections(self):
        """Initialize collections for different embedding providers"""
        # Get OpenAI API key from database
        openai_api_key = self._get_openai_api_key()
        
        # Create or get OpenAI collections
        self.openai_small_collection = self.client.get_or_create_collection(
            name="github_openai_small",
            metadata={"description": "GitHub code with OpenAI text-embedding-3-small"}
        )
        
        self.openai_large_collection = self.client.get_or_create_collection(
            name="github_openai_large",
            metadata={"description": "GitHub code with OpenAI text-embedding-3-large"}
        )
        
        # Create or get Ollama collection
        self.ollama_collection = self.client.get_or_create_collection(
            name="github_ollama",
            metadata={"description": "GitHub code with Ollama nomic-embed-text"}
        )
            
        logger.info("Collections initialized")
    
    def _get_embedding_model(self, embedding_provider: str) -> Optional[Embeddings]:
        """Get or create an embedding model based on the provider"""
        if embedding_provider in self.embedding_models:
            return self.embedding_models[embedding_provider]
        
        try:
            if embedding_provider == "openai-small":
                openai_api_key = self._get_openai_api_key()
                if not openai_api_key:
                    raise ValueError("OpenAI API key is required for OpenAI embeddings")
                
                model = OpenAIEmbeddings(
                    model="text-embedding-3-small",
                    openai_api_key=openai_api_key
                )
                self.embedding_models[embedding_provider] = model
                return model
                
            elif embedding_provider == "openai-large":
                openai_api_key = self._get_openai_api_key()
                if not openai_api_key:
                    raise ValueError("OpenAI API key is required for OpenAI embeddings")
                
                model = OpenAIEmbeddings(
                    model="text-embedding-3-large",
                    openai_api_key=openai_api_key
                )
                self.embedding_models[embedding_provider] = model
                return model
                
            elif embedding_provider == "ollama":
                ollama_url = os.environ.get("OLLAMA_URL", "http://localhost:11434")
                model = OllamaEmbeddings(
                    model="nomic-embed-text",
                    base_url=ollama_url
                )
                self.embedding_models[embedding_provider] = model
                return model
                
            else:
                raise ValueError(f"Unknown embedding provider: {embedding_provider}")
                
        except Exception as e:
            logger.error(f"Error creating embedding model for {embedding_provider}: {str(e)}")
            return None
    
    def _generate_embeddings(self, texts: List[str], embedding_provider: str) -> Optional[List[List[float]]]:
        """Generate embeddings for a list of texts"""
        embedding_model = self._get_embedding_model(embedding_provider)
        if not embedding_model:
            raise ValueError(f"Failed to initialize embedding model for {embedding_provider}")
        
        try:
            # Generate embeddings
            embeddings = embedding_model.embed_documents(texts)
            return embeddings
        except Exception as e:
            logger.error(f"Error generating embeddings: {str(e)}")
            raise ValueError(f"Failed to generate embeddings: {str(e)}")
    
    def get_collection(self, embedding_provider: str):
        """Get the appropriate collection based on the embedding provider"""
        if embedding_provider == "openai-small":
            return self.openai_small_collection
        elif embedding_provider == "openai-large":
            return self.openai_large_collection
        elif embedding_provider == "ollama":
            return self.ollama_collection
        else:
            raise ValueError(f"Unknown embedding provider: {embedding_provider}")
    
    def add_code_file(self, 
                     file_id: str,
                     file_content: str, 
                     metadata: Dict[str, Any], 
                     embedding_provider: str):
        """
        Add a code file to the vector store
        
        Args:
            file_id: Unique identifier for the file
            file_content: The code file content
            metadata: Metadata about the file (repo_url, file_path, etc.)
            embedding_provider: The embedding provider to use
        """
        collection = self.get_collection(embedding_provider)
        
        # Generate embeddings
        try:
            embeddings = self._generate_embeddings([file_content], embedding_provider)
            if not embeddings:
                return False
            
            # Add document to collection
            collection.add(
                ids=[file_id],
                documents=[file_content],
                embeddings=[embeddings[0]],
                metadatas=[metadata]
            )
            logger.info(f"Added {file_id} to {embedding_provider} collection")
            return True
        except Exception as e:
            logger.error(f"Error adding {file_id} to vector store: {str(e)}")
            return False
    
    def add_code_files_batch(self, 
                           ids: List[str],
                           contents: List[str], 
                           metadatas: List[Dict[str, Any]], 
                           embedding_provider: str):
        """
        Add multiple code files to the vector store in batch
        
        Args:
            ids: List of unique identifiers for the files
            contents: List of code file contents
            metadatas: List of metadata about the files
            embedding_provider: The embedding provider to use
        """
        collection = self.get_collection(embedding_provider)
        
        # Generate embeddings
        try:
            embeddings = self._generate_embeddings(contents, embedding_provider)
            if not embeddings:
                return False
            
            # Add documents to collection in batch
            collection.add(
                ids=ids,
                documents=contents,
                embeddings=embeddings,
                metadatas=metadatas
            )
            logger.info(f"Added {len(ids)} files to {embedding_provider} collection")
            return True
        except Exception as e:
            logger.error(f"Error adding files to vector store: {str(e)}")
            return False
    
    def delete_by_repo_url(self, repo_url: str, embedding_provider: str):
        """
        Delete all documents from a specific repository
        
        Args:
            repo_url: The repository URL to delete
            embedding_provider: The embedding provider to use
        """
        collection = self.get_collection(embedding_provider)
        
        try:
            collection.delete(
                where={"repo_url": repo_url}
            )
            logger.info(f"Deleted all files from {repo_url} in {embedding_provider} collection")
            return True
        except Exception as e:
            logger.error(f"Error deleting files from {repo_url}: {str(e)}")
            return False
    
    def search(self, 
              query: str, 
              embedding_provider: str, 
              repo_url: Optional[str] = None,
              n_results: int = 5):
        """
        Search for code files in the vector store
        
        Args:
            query: The search query
            embedding_provider: The embedding provider to use
            repo_url: Optional repository URL to filter results
            n_results: Number of results to return
            
        Returns:
            List of search results
        """
        collection = self.get_collection(embedding_provider)
        
        # Build where clause if repo_url is provided
        where_clause = {"repo_url": repo_url} if repo_url else None
        
        # Generate embedding for query
        try:
            query_embedding = self._generate_embeddings([query], embedding_provider)
            if not query_embedding:
                return None
            
            # Search the collection
            results = collection.query(
                query_embeddings=query_embedding,
                n_results=n_results,
                where=where_clause
            )
            return results
        except Exception as e:
            logger.error(f"Error searching vector store: {str(e)}")
            return None
    
    def get_stats(self, embedding_provider: str = None):
        """
        Get statistics about the vector store
        
        Args:
            embedding_provider: Optional embedding provider to filter stats
            
        Returns:
            Dictionary of statistics
        """
        stats = {}
        
        if embedding_provider:
            collections = [self.get_collection(embedding_provider)]
        else:
            collections = [
                self.openai_small_collection,
                self.openai_large_collection,
                self.ollama_collection
            ]
        
        for collection in collections:
            try:
                collection_stats = {
                    "name": collection.name,
                    "count": collection.count()
                }
                
                # Get unique repositories
                results = collection.get(limit=10000, include=["metadatas"])
                if results and "metadatas" in results:
                    repos = set()
                    for metadata in results["metadatas"]:
                        if metadata and "repo_url" in metadata:
                            repos.add(metadata["repo_url"])
                    
                    collection_stats["unique_repos"] = len(repos)
                    collection_stats["repos"] = list(repos)
                
                stats[collection.name] = collection_stats
            except Exception as e:
                logger.error(f"Error getting stats for {collection.name}: {str(e)}")
        
        return stats

# Singleton instance
_vector_store = None

def get_github_vector_store():
    """Get the GitHub vector store singleton instance"""
    global _vector_store
    if _vector_store is None:
        _vector_store = GitHubVectorStore()
    return _vector_store 