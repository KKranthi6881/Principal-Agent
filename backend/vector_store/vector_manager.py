"""
Vector store manager for handling vector databases
"""
import os
import logging
from typing import Any, Dict, List, Optional
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import OpenAIEmbeddings, OllamaEmbeddings
from langchain_core.documents import Document

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Check if the current file is inside the backend directory
current_path = os.path.dirname(os.path.abspath(__file__))
if 'backend' in current_path:
    # Ensure paths are relative to the backend directory
    backend_dir = current_path.split('backend')[0] + 'backend'
    os.chdir(backend_dir)
    logger.info(f"Working directory set to {os.getcwd()}")

class VectorManager:
    """
    Manager for vector store operations
    """
    
    def __init__(self, vector_store_path: str):
        """
        Initialize the vector manager
        
        Args:
            vector_store_path: Path to the vector store
        """
        # Ensure path is relative to the backend directory
        if not os.path.isabs(vector_store_path):
            if not vector_store_path.startswith("vector_store/"):
                vector_store_path = os.path.join("vector_store", vector_store_path)
            
        self.vector_store_path = vector_store_path
        logger.info(f"Vector store path: {self.vector_store_path}")
        
        self.vector_store = None
        self.embedding_model = None
        
        # Initialize immediately
        try:
            self.get_vector_store()
        except Exception as e:
            logger.error(f"Error initializing vector store: {e}")
        
    def get_embedding_model(self):
        """
        Get embedding model based on available providers
        
        Returns:
            Embedding model instance
        """
        if self.embedding_model:
            return self.embedding_model
            
        # Try Ollama first (local, no API key needed)
        try:
            logger.info("Attempting to initialize Ollama embeddings")
            self.embedding_model = OllamaEmbeddings(model="nomic-embed-text")
            logger.info("Using Ollama for embeddings")
            return self.embedding_model
        except Exception as e:
            logger.warning(f"Ollama not available: {e}")
        
        # Fall back to OpenAI if available
        try:
            logger.info("Attempting to initialize OpenAI embeddings")
            self.embedding_model = OpenAIEmbeddings(model="text-embedding-3-small")
            logger.info("Using OpenAI for embeddings")
            return self.embedding_model
        except Exception as e:
            logger.warning(f"OpenAI embeddings not available: {e}")
            
        logger.error("No embedding models available")
        return None
        
    def get_vector_store(self):
        """
        Get or create the vector store
        
        Returns:
            Vector store instance
        """
        if self.vector_store:
            return self.vector_store
            
        # Create directory if it doesn't exist
        os.makedirs(self.vector_store_path, exist_ok=True)
        logger.info(f"Vector store directory ensured: {self.vector_store_path}")
        
        embedding_model = self.get_embedding_model()
        if not embedding_model:
            logger.error("No embedding model available, cannot create vector store")
            return None
            
        try:
            # First try to load existing store
            logger.info(f"Attempting to load vector store from {self.vector_store_path}")
            self.vector_store = Chroma(
                persist_directory=self.vector_store_path,
                embedding_function=embedding_model
            )
            logger.info(f"Loaded vector store from {self.vector_store_path}")
            
            # If the store exists but is empty, return a warning
            if self.vector_store._collection.count() == 0:
                logger.warning(f"Vector store exists but is empty: {self.vector_store_path}")
                
            return self.vector_store
        except Exception as e:
            logger.error(f"Error loading vector store: {e}")
            return None
            
    def add_documents(self, documents, metadata=None):
        """Add documents to the vector store"""
        store = self.get_vector_store()
        if not store:
            return {"error": "Vector store not available"}
            
        try:
            store.add_documents(documents, metadata)
            return {"success": True, "count": len(documents)}
        except Exception as e:
            logger.error(f"Error adding documents to vector store: {e}")
            return {"error": str(e)}
    
    def similarity_search_with_metadata(self, query, k=5, filter=None):
        """
        Perform similarity search with metadata
        
        Args:
            query: Search query
            k: Number of results
            filter: Filter for search
            
        Returns:
            List of documents
        """
        store = self.get_vector_store()
        if not store:
            logger.error("Vector store not available for search")
            return []
            
        try:
            logger.info(f"Performing similarity search for: {query}")
            results = store.similarity_search_with_score(
                query=query,
                k=k,
                filter=filter
            )
            
            # Convert to Document objects with metadata
            documents = []
            for doc, score in results:
                logger.info(f"Found document with score {score}: {doc.metadata.get('source', 'unknown')}")
                documents.append(doc)
                
            return documents
        except Exception as e:
            logger.error(f"Error performing similarity search: {e}")
            return [] 