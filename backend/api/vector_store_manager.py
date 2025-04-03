import chromadb
from pathlib import Path
from typing import Dict, List, Optional, Any
import json
from datetime import datetime

class VectorStoreManager:
    def __init__(self):
        self.base_dir = Path(__file__).parent.parent / "vector_store"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize ChromaDB clients for different collections
        self.github_client = chromadb.PersistentClient(path=str(self.base_dir / "chromadb_github"))
        self.document_client = chromadb.PersistentClient(path=str(self.base_dir / "chromadb_document"))
        self.summary_client = chromadb.PersistentClient(path=str(self.base_dir / "chromadb_summary"))
        
        # Create or get collections
        self.github_collection = self.github_client.get_or_create_collection("github_files")
        self.document_collection = self.document_client.get_or_create_collection("documents")
        self.summary_collection = self.summary_client.get_or_create_collection("conversation_summaries")

    def add_github_file(self, file_path: str, content: str, metadata: Dict[str, Any]) -> str:
        """Add a GitHub file to the vector store"""
        doc_id = f"doc_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file_path}"
        
        self.github_collection.add(
            documents=[content],
            metadatas=[metadata],
            ids=[doc_id]
        )
        return doc_id

    def search_github_files(self, query: str, n_results: int = 5) -> List[Dict[str, Any]]:
        """Search GitHub files using similarity search"""
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

    def add_document(self, content: str, metadata: Dict[str, Any]) -> str:
        """Add a document to the vector store"""
        doc_id = f"doc_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        self.document_collection.add(
            documents=[content],
            metadatas=[metadata],
            ids=[doc_id]
        )
        return doc_id

    def search_documents(self, query: str, n_results: int = 5) -> List[Dict[str, Any]]:
        """Search documents using hybrid search"""
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

    def add_conversation_summary(self, thread_id: str, summary: str, metadata: Dict[str, Any]) -> str:
        """Add a conversation summary to the vector store"""
        summary_id = f"sum_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{thread_id}"
        
        self.summary_collection.add(
            documents=[summary],
            metadatas=[metadata],
            ids=[summary_id]
        )
        return summary_id

    def search_conversation_summaries(self, query: str, n_results: int = 5) -> List[Dict[str, Any]]:
        """Search conversation summaries"""
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

    def delete_document(self, collection_name: str, doc_id: str) -> None:
        """Delete a document from a specific collection"""
        collection = getattr(self, f"{collection_name}_collection")
        collection.delete(ids=[doc_id]) 