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
GITHUB_VECTOR_STORE_PATH = os.path.join("vector_store", "chromadb_github")

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
            
        # Check if the collection has data, add demo data if empty
        if collection.count() == 0:
            logger.warning("Collection is empty, it may have been deleted. Adding demo data...")
            _populate_demo_github_data(collection)
            
        return collection
    except Exception as e:
        logger.error(f"Error getting GitHub vector store: {e}")
        logger.error(traceback.format_exc())
        return None

def _populate_demo_github_data(collection):
    """Add demo GitHub data to the collection"""
    try:
        # Sample GitHub files to add
        sample_files = [
            {
                "id": "gh_1",
                "content": "def calculate_discount(price, quantity, discount_percent):\n    return price * quantity * (discount_percent / 100)",
                "metadata": {
                    "repo": "demo-repository",
                    "path": "utils/pricing.py",
                    "language": "python",
                    "url": "https://github.com/demo/repo/blob/main/utils/pricing.py"
                }
            },
            {
                "id": "gh_2",
                "content": "CREATE OR REPLACE TABLE analytics.fct_order_items AS SELECT * FROM raw_data.orders",
                "metadata": {
                    "repo": "analytics-dbt",
                    "path": "models/fct_order_items.sql",
                    "language": "sql",
                    "file_extension": ".sql",
                    "url": "https://github.com/demo/analytics-dbt/blob/main/models/fct_order_items.sql"
                }
            }
        ]
        
        # Add documents
        ids = []
        documents = []
        metadatas = []
        
        for file in sample_files:
            ids.append(file["id"])
            documents.append(file["content"])
            metadatas.append(file["metadata"])
        
        # Add to collection
        collection.add(
            ids=ids,
            documents=documents,
            metadatas=metadatas
        )
        
        logger.info(f"Added {len(ids)} demo documents to GitHub vector store")
        return True
    except Exception as e:
        logger.error(f"Error populating demo GitHub data: {e}")
        logger.error(traceback.format_exc())
        return False 