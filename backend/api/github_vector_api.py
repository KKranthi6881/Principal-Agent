"""
API for GitHub vector store operations
"""
import os
import sys
import json
import time
import tempfile
import asyncio
import subprocess
import shutil
from typing import Dict, List, Optional, Any
import logging
from fastapi import APIRouter, HTTPException, BackgroundTasks, Query, Depends
from pydantic import BaseModel, Field
import sqlite3
import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from utils import github_utils
from utils import repo_manager
from api.github_connectors_api import get_db_connection

# Set up logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Add the parent directory to the Python path if needed
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# Try importing from vector_store, with fallback functions if module isn't found
try:
    sys.path.append(parent_dir)
    from vector_store.github_vectorstore import get_github_vector_store, decrypt_api_key, add_code_files_batch
    logger.info("Successfully imported vector_store functions")
except ImportError as e:
    logger.error(f"Error importing vector_store: {e}")
    # Define fallback functions if the module isn't available
    def get_github_vector_store():
        """Fallback function to create the vector store"""
        logger.warning("Using fallback vector store implementation")
        try:
            # Create the vector store directory
            vector_store_path = os.path.join(parent_dir, "vector_store", "chromadb_github")
            os.makedirs(vector_store_path, exist_ok=True)
            
            # Import and initialize ChromaDB
            import chromadb
            from chromadb.utils import embedding_functions
            
            # Create the client and collection
            chroma_client = chromadb.PersistentClient(path=vector_store_path)
            
            try:
                collection = chroma_client.get_collection("github_code")
                logger.info(f"Found existing GitHub vector store with {collection.count()} documents")
            except Exception:
                # Create new collection
                embedding_func = embedding_functions.DefaultEmbeddingFunction()
                collection = chroma_client.create_collection(
                    name="github_code",
                    embedding_function=embedding_func
                )
                logger.info("Created new GitHub vector store collection")
                
            return collection
        except Exception as e:
            logger.error(f"Error in fallback vector store: {e}")
            return None
    
    def decrypt_api_key(encrypted_key):
        """Fallback decryption function"""
        logger.warning("Using dummy decrypt_api_key function")
        return encrypted_key  # Return as-is in fallback mode

    def add_code_files_batch(ids, contents, metadatas, embedding_provider=None):
        """Fallback function to add code files in batch"""
        logger.warning("Using fallback add_code_files_batch implementation")
        try:
            collection = get_github_vector_store()
            if not collection:
                logger.error("Failed to get GitHub vector store")
                return False
                
            # Add documents to collection
            collection.add(
                ids=ids,
                documents=contents,
                metadatas=metadatas
            )
            
            logger.info(f"Added {len(ids)} documents to GitHub vector store using fallback function")
            return True
        except Exception as e:
            logger.error(f"Error in fallback add_code_files_batch: {e}")
            return False

# Create router
router = APIRouter(prefix="/api/github", tags=["github"])

# Create GitHub sync table
github_utils.create_github_sync_table()

# Pydantic models
class SyncRequest(BaseModel):
    """GitHub repository sync request"""
    connector_id: str
    repo_url: str
    embedding_provider: str = Field(..., description="One of: openai-small, openai-large, ollama")
    force_full_sync: bool = False
    branch: Optional[str] = "main"

class SyncResponse(BaseModel):
    """GitHub repository sync response"""
    sync_id: int
    connector_id: str
    repo_url: str
    embedding_provider: str
    status: str
    message: str

class SyncStatus(BaseModel):
    """GitHub repository sync status"""
    sync_id: int
    connector_id: str
    repo_url: str
    embedding_provider: str
    commit_hash: str
    files_processed: int
    status: str
    error_message: Optional[str] = None
    sync_timestamp: str

class SyncStatusList(BaseModel):
    """List of GitHub repository sync statuses"""
    syncs: List[SyncStatus]

class DeleteVectorsRequest(BaseModel):
    """GitHub repository vectors delete request"""
    connector_id: str
    repo_url: str
    embedding_provider: str

class DeleteVectorsResponse(BaseModel):
    """GitHub repository vectors delete response"""
    success: bool
    message: str

class VectorStoreStats(BaseModel):
    """GitHub vector store statistics"""
    collections: Dict[str, Any]
    total_documents: int
    total_repositories: int

# Running syncs tracking
running_syncs = {}

async def sync_repository_task(
    sync_id: int,
    connector_id: str,
    repo_url: str,
    embedding_provider: str,
    force_full_sync: bool,
    branch: str
):
    """
    Background task to sync a GitHub repository to the vector store
    
    Args:
        sync_id: The sync ID
        connector_id: The connector ID
        repo_url: The repository URL
        embedding_provider: The embedding provider to use
        force_full_sync: Whether to force a full sync
        branch: The branch to sync
    """
    try:
        # Get vector store
        vector_store = get_github_vector_store()
        if not vector_store:
            error_msg = "Failed to initialize vector store"
            logger.error(error_msg)
            github_utils.record_sync_completion(sync_id, '', 0, 'failed', error_msg)
            return
        
        # Get last sync for incremental update
        previous_commit = None
        if not force_full_sync:
            last_sync = github_utils.get_last_sync(connector_id, repo_url, embedding_provider)
            if last_sync:
                previous_commit = last_sync['commit_hash']
                logger.info(f"Found previous sync with commit hash: {previous_commit[:8]} for {repo_url}")
        
        # Get or clone the repository using repo manager (persistent storage)
        if repo_manager.has_local_repo(repo_url, branch):
            # Repository exists, update it
            logger.info(f"Repository {repo_url} exists locally. Updating...")
            repo_path = repo_manager.get_repo_storage_path(repo_url, branch)
            success, error = repo_manager.update_repository(repo_path, branch)
            
            if not success:
                logger.error(f"Failed to update repository: {error}")
                # Try cloning again if update fails
                success, repo_path, error = repo_manager.clone_repository(repo_url, branch)
                if not success:
                    github_utils.record_sync_completion(sync_id, '', 0, 'failed', error)
                    return
        else:
            # Repository doesn't exist, clone it
            logger.info(f"Repository {repo_url} doesn't exist locally. Cloning...")
            success, repo_path, error = repo_manager.clone_repository(repo_url, branch)
            if not success:
                github_utils.record_sync_completion(sync_id, '', 0, 'failed', error)
                return
        
        logger.info(f"Using repository at path: {repo_path}")
        
        # Get current commit hash
        current_commit = repo_manager.get_current_commit_hash(repo_path)
        if not current_commit:
            error_msg = "Failed to get current commit hash"
            logger.error(error_msg)
            github_utils.record_sync_completion(sync_id, '', 0, 'failed', error_msg)
            return
        
        logger.info(f"Current commit hash: {current_commit[:8]}")
        
        # Check if already synced to this commit
        if previous_commit and previous_commit == current_commit and not force_full_sync:
            logger.info(f"Repository already synced to commit {current_commit[:8]}. No changes detected.")
            github_utils.record_sync_completion(
                sync_id, current_commit, 0, 'completed', 'No changes detected since last sync')
            return
        
        # Determine files to process
        files_to_process = []
        deleted_files = []
        
        if previous_commit and not force_full_sync:
            # Incremental sync - only process changed files
            success, changed_files, error = repo_manager.get_changed_files(repo_path, previous_commit)
            
            if success:
                # Filter changed files to include only code files
                files_to_process = github_utils.filter_code_files(changed_files)
                logger.info(f"Incremental sync: Found {len(files_to_process)} changed code files to process")
                
                # Get deleted files to remove from vector store
                success, deleted_files, error = repo_manager.get_deleted_files(repo_path, previous_commit)
                if success:
                    deleted_files = github_utils.filter_code_files(deleted_files)
                    logger.info(f"Incremental sync: Found {len(deleted_files)} deleted code files to remove")
            else:
                # Fallback to full sync if getting changed files fails
                logger.warning(f"Failed to get changed files: {error}. Falling back to full sync.")
                files_to_process = github_utils.get_all_code_files(repo_path)
                logger.info(f"Full sync fallback: Processing {len(files_to_process)} code files")
        else:
            # First sync or forced full sync - process all files
            files_to_process = github_utils.get_all_code_files(repo_path)
            logger.info(f"Full sync: Processing {len(files_to_process)} code files")
        
        # Process deleted files first (remove them from vector store)
        for file_path in deleted_files:
            try:
                vector_store.delete_by_file_path(repo_url, file_path)
                logger.info(f"Removed deleted file from vector store: {file_path}")
            except Exception as e:
                logger.error(f"Error removing deleted file {file_path} from vector store: {str(e)}")
        
        # Now process files to add/update
        if not files_to_process:
            logger.info("No files to process")
            github_utils.record_sync_completion(
                sync_id, current_commit, 0, 'completed', 'No files to process')
            return
        
        # Extract repository metadata
        repo_name = github_utils.get_repo_name_from_url(repo_url)
        repo_owner = repo_url.split('/')[-2] if '/' in repo_url else 'unknown'
        
        # Process files in batches to avoid memory issues
        batch_size = 50
        processed_count = 0
        
        for i in range(0, len(files_to_process), batch_size):
            if i > 0:
                logger.info(f"Processing batch {i//batch_size + 1}/{(len(files_to_process) + batch_size - 1)//batch_size}")
                
            batch_files = files_to_process[i:i+batch_size]
            
            ids = []
            contents = []
            metadatas = []
            
            for file_path in batch_files:
                abs_path = os.path.join(repo_path, file_path)
                success, content, error = github_utils.read_file_content(abs_path)
                
                if success and content:
                    # Generate file metadata
                    content_hash = github_utils.get_file_hash(content)
                    file_id = github_utils.generate_file_id(repo_url, file_path, content_hash)
                    
                    # Get file extension for language detection
                    _, ext = os.path.splitext(file_path)
                    if ext:
                        ext = ext[1:]  # Remove the dot
                    
                    # Create metadata with enhanced information about file path
                    metadata = {
                        "repo_url": repo_url,
                        "repo_name": repo_name,
                        "repo_owner": repo_owner,
                        "file_path": file_path,
                        "file_name": os.path.basename(file_path),
                        "file_extension": ext,
                        "content_hash": content_hash,
                        "commit_hash": current_commit,
                        "connector_id": connector_id,
                        "sync_id": sync_id,
                        # Add directory information for better filtering
                        "directory": os.path.dirname(file_path) or "root",
                        # Add embedding provider info to metadata for filtering
                        "embedding_provider": embedding_provider
                    }
                    
                    ids.append(file_id)
                    contents.append(content)
                    metadatas.append(metadata)
            
            if ids:
                # Add batch to vector store
                success = add_code_files_batch(ids, contents, metadatas, embedding_provider)
                if success:
                    processed_count += len(ids)
                    logger.info(f"Added {len(ids)} documents to vector store (total: {processed_count})")
                else:
                    logger.error(f"Failed to add documents to vector store")
        
        # Record completion
        github_utils.record_sync_completion(
            sync_id, current_commit, processed_count, 'completed')
        
        # Run cleanup operation for old repositories
        try:
            repo_manager.clean_old_repositories()
        except Exception as e:
            logger.warning(f"Error during repository cleanup: {str(e)}")
    except Exception as e:
        error_msg = f"Error syncing repository: {str(e)}"
        logger.error(error_msg)
        github_utils.record_sync_completion(
            sync_id, '', 0, 'failed', error_msg)
    finally:
        # Remove from running syncs
        if sync_id in running_syncs:
            del running_syncs[sync_id]

@router.post("/sync", response_model=SyncResponse)
async def sync_repository(request: SyncRequest, background_tasks: BackgroundTasks):
    """
    Sync a GitHub repository to the vector store
    
    This endpoint triggers a background task to sync the repository.
    Use the /sync/{sync_id} endpoint to check the status of the sync.
    """
    # Check if embedding provider is valid
    if request.embedding_provider not in ["openai-small", "openai-large", "ollama"]:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid embedding provider. Must be one of: openai-small, openai-large, ollama")
    
    # Pre-check for API key availability if using OpenAI
    if request.embedding_provider.startswith("openai"):
        # Connect to database to check for OpenAI API key
        conn = get_db_connection()
        api_key = None
        
        try:
            # First try the llm_provider_configs table
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("SELECT api_key, api_key_encrypted FROM llm_provider_configs WHERE provider_id = ? AND active = ?", ("openai", 1))
            result = cursor.fetchone()
            
            if result and result['api_key']:
                # Check if key is encrypted and decrypt if needed
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
                
                if is_encrypted:
                    decrypted_key = decrypt_api_key(raw_key)
                    if decrypted_key:
                        api_key = decrypted_key
                        logger.info("Found and decrypted OpenAI API key in llm_provider_configs table")
                    else:
                        logger.warning("Failed to decrypt OpenAI API key from llm_provider_configs table")
                else:
                    api_key = raw_key
                    logger.info("Found unencrypted OpenAI API key in llm_provider_configs table")
            
            # If not found in the first table, try the second table
            if not api_key:
                # Make sure the llm_provider_config table exists
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
                
                cursor.execute("SELECT api_key FROM llm_provider_config WHERE provider_name = ?", ("openai",))
                result = cursor.fetchone()
                
                if result and result['api_key']:
                    api_key = result['api_key']
                    logger.info("Found OpenAI API key in llm_provider_config table")
            
            # Check environment variable as last resort
            if not api_key:
                api_key = os.environ.get("OPENAI_API_KEY")
                if api_key:
                    logger.info("Found OpenAI API key in environment variables")
            
            if not api_key:
                conn.close()
                raise HTTPException(
                    status_code=400,
                    detail="OpenAI API key is required for OpenAI embeddings. Please configure an OpenAI provider in Settings > LLM Providers."
                )
            
        except HTTPException:
            conn.close()
            raise
        except Exception as e:
            conn.close()
            logger.error(f"Error checking OpenAI API key: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Error checking OpenAI API key: {str(e)}"
            )
    
    # Check if connector exists
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM github_connectors WHERE id = ?", (request.connector_id,))
    connector = cursor.fetchone()
    
    if not connector:
        conn.close()
        raise HTTPException(status_code=404, detail=f"GitHub connector with ID {request.connector_id} not found")
    
    # Check if repository URL is valid
    if not request.repo_url.startswith(("http://", "https://")):
        conn.close()
        raise HTTPException(status_code=400, detail="Repository URL must start with http:// or https://")
    
    # Record sync start
    sync_id = github_utils.record_sync_start(
        request.connector_id, request.repo_url, request.embedding_provider)
    
    if sync_id == -1:
        conn.close()
        raise HTTPException(status_code=500, detail="Failed to start sync")
    
    # Add to running syncs
    running_syncs[sync_id] = {
        "connector_id": request.connector_id,
        "repo_url": request.repo_url,
        "embedding_provider": request.embedding_provider,
        "start_time": time.time()
    }
    
    # Start background task
    background_tasks.add_task(
        sync_repository_task,
        sync_id,
        request.connector_id,
        request.repo_url,
        request.embedding_provider,
        request.force_full_sync,
        request.branch or "main"
    )
    
    conn.close()
    
    return {
        "sync_id": sync_id,
        "connector_id": request.connector_id,
        "repo_url": request.repo_url,
        "embedding_provider": request.embedding_provider,
        "status": "in_progress",
        "message": "Sync started"
    }

@router.get("/sync/{sync_id}", response_model=SyncStatus)
async def get_sync_status(sync_id: int):
    """
    Get the status of a GitHub repository sync
    """
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT * FROM github_sync_history WHERE id = ?", (sync_id,))
        sync = cursor.fetchone()
        
        if not sync:
            conn.close()
            raise HTTPException(status_code=404, detail=f"Sync with ID {sync_id} not found")
        
        # Convert to dict and map 'id' to 'sync_id'
        sync_dict = dict(sync)
        sync_dict['sync_id'] = sync_dict.pop('id')
        return sync_dict
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=500, detail=f"Error getting sync status: {str(e)}")
    finally:
        conn.close()

@router.get("/syncs", response_model=SyncStatusList)
async def get_syncs(
    connector_id: Optional[str] = None,
    repo_url: Optional[str] = None,
    embedding_provider: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 10
):
    """
    Get the list of GitHub repository syncs
    """
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    try:
        # Build WHERE clause
        where_clauses = []
        params = []
        
        if connector_id:
            where_clauses.append("connector_id = ?")
            params.append(connector_id)
        
        if repo_url:
            where_clauses.append("repo_url = ?")
            params.append(repo_url)
        
        if embedding_provider:
            where_clauses.append("embedding_provider = ?")
            params.append(embedding_provider)
        
        if status:
            where_clauses.append("status = ?")
            params.append(status)
        
        # Build query
        query = "SELECT * FROM github_sync_history"
        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)
        
        query += " ORDER BY sync_timestamp DESC LIMIT ?"
        params.append(limit)
        
        # Execute query
        cursor.execute(query, params)
        syncs = []
        
        # Map 'id' to 'sync_id' to match the expected response model
        for row in cursor.fetchall():
            sync_dict = dict(row)
            sync_dict['sync_id'] = sync_dict.pop('id')
            syncs.append(sync_dict)
        
        return {"syncs": syncs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting syncs: {str(e)}")
    finally:
        conn.close()

@router.post("/delete", response_model=DeleteVectorsResponse)
async def delete_vectors(request: DeleteVectorsRequest):
    """
    Delete vectors for a GitHub repository from the vector store
    """
    # Check if embedding provider is valid
    if request.embedding_provider not in ["openai-small", "openai-large", "ollama"]:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid embedding provider. Must be one of: openai-small, openai-large, ollama")
    
    # Pre-check for API key availability if using OpenAI
    if request.embedding_provider.startswith("openai"):
        # Connect to database to check for OpenAI API key
        conn = get_db_connection()
        api_key = None
        
        try:
            # First try the llm_provider_configs table
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("SELECT api_key, api_key_encrypted FROM llm_provider_configs WHERE provider_id = ? AND active = ?", ("openai", 1))
            result = cursor.fetchone()
            
            if result and result['api_key']:
                # Check if key is encrypted and decrypt if needed
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
                
                if is_encrypted:
                    decrypted_key = decrypt_api_key(raw_key)
                    if decrypted_key:
                        api_key = decrypted_key
                        logger.info("Found and decrypted OpenAI API key in llm_provider_configs table")
                    else:
                        logger.warning("Failed to decrypt OpenAI API key from llm_provider_configs table")
                else:
                    api_key = raw_key
                    logger.info("Found unencrypted OpenAI API key in llm_provider_configs table")
            
            # If not found in the first table, try the second table
            if not api_key:
                # Make sure the llm_provider_config table exists
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
                
                cursor.execute("SELECT api_key FROM llm_provider_config WHERE provider_name = ?", ("openai",))
                result = cursor.fetchone()
                
                if result and result['api_key']:
                    api_key = result['api_key']
                    logger.info("Found OpenAI API key in llm_provider_config table")
            
            # Check environment variable as last resort
            if not api_key:
                api_key = os.environ.get("OPENAI_API_KEY")
                if api_key:
                    logger.info("Found OpenAI API key in environment variables")
            
            if not api_key:
                conn.close()
                raise HTTPException(
                    status_code=400,
                    detail="OpenAI API key is required for OpenAI embeddings. Please configure an OpenAI provider in Settings > LLM Providers."
                )
            
        except HTTPException:
            conn.close()
            raise
        except Exception as e:
            conn.close()
            logger.error(f"Error checking OpenAI API key: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Error checking OpenAI API key: {str(e)}"
            )
    
    # Check if connector exists
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM github_connectors WHERE id = ?", (request.connector_id,))
    connector = cursor.fetchone()
    
    if not connector:
        conn.close()
        raise HTTPException(status_code=404, detail=f"GitHub connector with ID {request.connector_id} not found")
    
    conn.close()
    
    # Delete from vector store
    try:
        vector_store = get_github_vector_store()
        success = vector_store.delete_by_repo_url(request.repo_url, request.embedding_provider)
        
        if success:
            return {
                "success": True,
                "message": f"Vectors for {request.repo_url} deleted successfully"
            }
        else:
            return {
                "success": False,
                "message": f"Failed to delete vectors for {request.repo_url}"
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting vectors: {str(e)}")

@router.get("/stats", response_model=VectorStoreStats)
async def get_vector_store_stats(embedding_provider: Optional[str] = None):
    """
    Get statistics about the GitHub vector store
    """
    try:
        vector_store = get_github_vector_store()
        stats = vector_store.get_stats(embedding_provider)
        
        # Calculate totals
        total_documents = 0
        repositories = set()
        
        for collection_stats in stats.values():
            total_documents += collection_stats.get("count", 0)
            
            if "repos" in collection_stats:
                repositories.update(collection_stats["repos"])
        
        return {
            "collections": stats,
            "total_documents": total_documents,
            "total_repositories": len(repositories)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting vector store stats: {str(e)}")

@router.get("/providers")
async def get_embedding_providers():
    """
    Get the list of available embedding providers
    """
    return {
        "providers": [
            {
                "id": "openai-small",
                "name": "OpenAI text-embedding-3-small",
                "description": "Smaller, cost-effective OpenAI embedding model"
            },
            {
                "id": "openai-large",
                "name": "OpenAI text-embedding-3-large",
                "description": "Larger, more powerful OpenAI embedding model"
            },
            {
                "id": "ollama",
                "name": "Ollama nomic-embed-text",
                "description": "Local Ollama embedding model"
            }
        ]
    }

@router.get("/repo_storage", response_model=dict)
async def get_repo_storage_status():
    """
    Get statistics about the repository storage
    """
    try:
        # Check if the storage directory exists
        if not os.path.exists(repo_manager.REPO_STORAGE_BASE):
            return {
                "status": "not_found",
                "message": f"Repository storage directory does not exist: {repo_manager.REPO_STORAGE_BASE}",
                "repos": [],
                "total_size": 0,
                "total_count": 0
            }
        
        # Get all repository directories
        repo_stats = []
        total_size = 0
        
        for dirname in os.listdir(repo_manager.REPO_STORAGE_BASE):
            repo_path = os.path.join(repo_manager.REPO_STORAGE_BASE, dirname)
            if os.path.isdir(repo_path) and os.path.exists(os.path.join(repo_path, '.git')):
                # Get repository size
                size = repo_manager.get_repository_size(repo_path)
                size_mb = size / (1024 * 1024)
                total_size += size
                
                # Try to get the remote URL
                try:
                    result = subprocess.run(['git', '-C', repo_path, 'config', '--get', 'remote.origin.url'], 
                                          capture_output=True, text=True)
                    url = result.stdout.strip() if result.returncode == 0 else "Unknown"
                except Exception:
                    url = "Unknown"
                
                # Try to get the current branch
                try:
                    result = subprocess.run(['git', '-C', repo_path, 'rev-parse', '--abbrev-ref', 'HEAD'], 
                                          capture_output=True, text=True)
                    branch = result.stdout.strip() if result.returncode == 0 else "Unknown"
                except Exception:
                    branch = "Unknown"
                
                # Try to get the last commit timestamp
                try:
                    result = subprocess.run(['git', '-C', repo_path, 'log', '-1', '--format=%at'], 
                                          capture_output=True, text=True)
                    if result.returncode == 0:
                        timestamp = int(result.stdout.strip())
                        last_commit = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(timestamp))
                    else:
                        last_commit = "Unknown"
                except Exception:
                    last_commit = "Unknown"
                
                repo_stats.append({
                    "name": dirname,
                    "url": url,
                    "branch": branch,
                    "size_mb": round(size_mb, 2),
                    "last_commit": last_commit,
                    "last_accessed": time.strftime('%Y-%m-%d %H:%M:%S', 
                                               time.localtime(os.path.getatime(repo_path)))
                })
        
        # Sort by size (largest first)
        repo_stats.sort(key=lambda r: r["size_mb"], reverse=True)
        
        return {
            "status": "ok",
            "message": f"Found {len(repo_stats)} repositories",
            "storage_path": repo_manager.REPO_STORAGE_BASE,
            "repos": repo_stats,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "total_size_gb": round(total_size / (1024 * 1024 * 1024), 2),
            "total_count": len(repo_stats)
        }
    except Exception as e:
        logger.error(f"Error getting repository storage status: {str(e)}")
        return {
            "status": "error",
            "message": f"Error getting repository storage status: {str(e)}",
            "repos": [],
            "total_size": 0,
            "total_count": 0
        } 