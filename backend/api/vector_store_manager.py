import chromadb
from pathlib import Path
from typing import Dict, List, Optional, Any
import json
import logging
from datetime import datetime
import os

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class VectorStoreManager:
    def __init__(self):
        self.base_dir = Path(__file__).parent.parent / "vector_store"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        
        # Create directories for each ChromaDB collection
        self.github_dir = self.base_dir / "chromadb_github"
        self.document_dir = self.base_dir / "chromadb_document"
        self.summary_dir = self.base_dir / "chromadb_summary"
        
        self.github_dir.mkdir(parents=True, exist_ok=True)
        self.document_dir.mkdir(parents=True, exist_ok=True)
        self.summary_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Initialized vector store directories at {self.base_dir}")
        
        # Initialize ChromaDB clients for different collections
        try:
            self.github_client = chromadb.PersistentClient(path=str(self.github_dir))
            self.github_collection = self.github_client.get_or_create_collection("github_files")
            logger.info(f"GitHub vector store initialized at {self.github_dir}")
        except Exception as e:
            logger.error(f"Error initializing GitHub vector store: {str(e)}")
            self.github_client = None
            self.github_collection = None
        
        try:
            self.document_client = chromadb.PersistentClient(path=str(self.document_dir))
            self.document_collection = self.document_client.get_or_create_collection("documents")
            logger.info(f"Document vector store initialized at {self.document_dir}")
        except Exception as e:
            logger.error(f"Error initializing document vector store: {str(e)}")
            self.document_client = None
            self.document_collection = None
        
        try:
            self.summary_client = chromadb.PersistentClient(path=str(self.summary_dir))
            self.summary_collection = self.summary_client.get_or_create_collection("conversation_summaries")
            logger.info(f"Summary vector store initialized at {self.summary_dir}")
        except Exception as e:
            logger.error(f"Error initializing summary vector store: {str(e)}")
            self.summary_client = None
            self.summary_collection = None

    def add_github_file(self, file_path: str, content: str, metadata: Dict[str, Any]) -> str:
        """Add a GitHub file to the vector store"""
        if not self.github_collection:
            logger.error("GitHub collection not initialized")
            return None
            
        doc_id = f"doc_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file_path}"
        
        try:
            self.github_collection.add(
                documents=[content],
                metadatas=[metadata],
                ids=[doc_id]
            )
            return doc_id
        except Exception as e:
            logger.error(f"Error adding GitHub file: {str(e)}")
            return None

    def search_github_files(self, query: str, n_results: int = 5) -> List[Dict[str, Any]]:
        """Search GitHub files using similarity search"""
        if not self.github_collection:
            logger.error("GitHub collection not initialized")
            return []
            
        try:
            results = self.github_collection.query(
                query_texts=[query],
                n_results=n_results
            )
            
            return [
                {
                    "id": id,
                    "content": doc,
                    "metadata": meta,
                    "distance": dist
                }
                for id, doc, meta, dist in zip(
                    results["ids"][0],
                    results["documents"][0],
                    results["metadatas"][0],
                    results["distances"][0]
                )
            ]
        except Exception as e:
            logger.error(f"Error searching GitHub files: {str(e)}")
            return []

    def add_document(self, content: str, metadata: Dict[str, Any]) -> str:
        """Add a document to the vector store"""
        if not self.document_collection:
            logger.error("Document collection not initialized")
            return None
            
        doc_id = f"doc_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        try:
            self.document_collection.add(
                documents=[content],
                metadatas=[metadata],
                ids=[doc_id]
            )
            return doc_id
        except Exception as e:
            logger.error(f"Error adding document: {str(e)}")
            return None

    def search_documents(self, query: str, n_results: int = 5) -> List[Dict[str, Any]]:
        """Search documents using hybrid search"""
        if not self.document_collection:
            logger.error("Document collection not initialized")
            return []
            
        try:
            results = self.document_collection.query(
                query_texts=[query],
                n_results=n_results
            )
            
            return [
                {
                    "id": id,
                    "content": doc,
                    "metadata": meta,
                    "distance": dist
                }
                for id, doc, meta, dist in zip(
                    results["ids"][0],
                    results["documents"][0],
                    results["metadatas"][0],
                    results["distances"][0]
                )
            ]
        except Exception as e:
            logger.error(f"Error searching documents: {str(e)}")
            return []

    def add_conversation_summary(self, thread_id: str, summary: str, metadata: Dict[str, Any]) -> str:
        """Add a conversation summary to the vector store"""
        if not self.summary_collection:
            logger.error("Summary collection not initialized")
            return None
            
        summary_id = f"sum_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{thread_id}"
        
        try:
            self.summary_collection.add(
                documents=[summary],
                metadatas=[metadata],
                ids=[summary_id]
            )
            return summary_id
        except Exception as e:
            logger.error(f"Error adding conversation summary: {str(e)}")
            return None

    def search_conversation_summaries(self, query: str, n_results: int = 5) -> List[Dict[str, Any]]:
        """Search conversation summaries"""
        if not self.summary_collection:
            logger.error("Summary collection not initialized")
            return []
            
        try:
            results = self.summary_collection.query(
                query_texts=[query],
                n_results=n_results
            )
            
            return [
                {
                    "id": id,
                    "content": doc,
                    "metadata": meta,
                    "distance": dist
                }
                for id, doc, meta, dist in zip(
                    results["ids"][0],
                    results["documents"][0],
                    results["metadatas"][0],
                    results["distances"][0]
                )
            ]
        except Exception as e:
            logger.error(f"Error searching conversation summaries: {str(e)}")
            return []

    def delete_document(self, collection_name: str, doc_id: str) -> None:
        """Delete a document from a specific collection"""
        collection = getattr(self, f"{collection_name}_collection")
        if collection:
            collection.delete(ids=[doc_id]) 