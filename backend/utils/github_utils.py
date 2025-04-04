"""
GitHub utilities for cloning, fetching, and processing repositories
"""
import os
import shutil
import tempfile
import subprocess
import logging
import hashlib
from typing import Dict, List, Optional, Set, Tuple, Any
import json
import sqlite3
import time
from urllib.parse import urlparse

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Path to metadata database
METADATA_DB = os.path.join('database', 'metadata.db')

def create_github_sync_table():
    """Create the github_sync_history table if it doesn't exist"""
    conn = sqlite3.connect(METADATA_DB)
    cursor = conn.cursor()
    
    # Create github_sync_history table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS github_sync_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        connector_id TEXT NOT NULL,
        repo_url TEXT NOT NULL,
        commit_hash TEXT NOT NULL,
        embedding_provider TEXT NOT NULL,
        files_processed INTEGER NOT NULL,
        sync_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        status TEXT NOT NULL,
        error_message TEXT
    )
    ''')
    
    # Create indexes
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_github_sync_connector_id ON github_sync_history(connector_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_github_sync_repo_url ON github_sync_history(repo_url)')
    
    conn.commit()
    conn.close()

def get_last_sync(connector_id: str, repo_url: str, embedding_provider: str) -> Optional[Dict[str, Any]]:
    """Get the last sync record for a repository"""
    conn = sqlite3.connect(METADATA_DB)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            '''
            SELECT * FROM github_sync_history 
            WHERE connector_id = ? AND repo_url = ? AND embedding_provider = ? AND status = 'completed'
            ORDER BY sync_timestamp DESC LIMIT 1
            ''', 
            (connector_id, repo_url, embedding_provider)
        )
        
        result = cursor.fetchone()
        if result:
            return dict(result)
        return None
    except sqlite3.Error as e:
        logger.error(f"Database error: {str(e)}")
        return None
    finally:
        conn.close()

def record_sync_start(connector_id: str, repo_url: str, embedding_provider: str) -> int:
    """Record the start of a sync operation"""
    conn = sqlite3.connect(METADATA_DB)
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            '''
            INSERT INTO github_sync_history 
            (connector_id, repo_url, commit_hash, embedding_provider, files_processed, status, error_message)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', 
            (connector_id, repo_url, '', embedding_provider, 0, 'in_progress', None)
        )
        
        sync_id = cursor.lastrowid
        conn.commit()
        return sync_id
    except sqlite3.Error as e:
        logger.error(f"Database error: {str(e)}")
        conn.rollback()
        return -1
    finally:
        conn.close()

def record_sync_completion(sync_id: int, commit_hash: str, files_processed: int, status: str = 'completed', error_message: Optional[str] = None):
    """Record the completion of a sync operation"""
    conn = sqlite3.connect(METADATA_DB)
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            '''
            UPDATE github_sync_history 
            SET commit_hash = ?, files_processed = ?, status = ?, error_message = ?, sync_timestamp = CURRENT_TIMESTAMP
            WHERE id = ?
            ''', 
            (commit_hash, files_processed, status, error_message, sync_id)
        )
        
        conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Database error: {str(e)}")
        conn.rollback()
    finally:
        conn.close()

def clone_repository(repo_url: str, branch: str = 'main') -> Tuple[bool, str, Optional[str]]:
    """
    Clone a GitHub repository to a temporary directory
    
    Args:
        repo_url: The repository URL to clone
        branch: The branch to clone (default: 'main')
        
    Returns:
        Tuple of (success, temp_dir, error_message)
    """
    # Create a temporary directory
    temp_dir = tempfile.mkdtemp()
    
    try:
        # Clone the repository
        logger.info(f"Cloning {repo_url} to {temp_dir}...")
        
        cmd = ['git', 'clone', '--depth', '1', '--branch', branch, repo_url, temp_dir]
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            # If branch doesn't exist, try with default branch
            if branch != 'main' and 'Remote branch not found' in result.stderr:
                logger.info(f"Branch {branch} not found, trying with 'main'...")
                # Clean up the failed clone
                shutil.rmtree(temp_dir, ignore_errors=True)
                temp_dir = tempfile.mkdtemp()
                
                cmd = ['git', 'clone', '--depth', '1', repo_url, temp_dir]
                result = subprocess.run(cmd, capture_output=True, text=True)
                
                if result.returncode != 0:
                    error_msg = f"Failed to clone repository: {result.stderr}"
                    logger.error(error_msg)
                    return False, temp_dir, error_msg
            else:
                error_msg = f"Failed to clone repository: {result.stderr}"
                logger.error(error_msg)
                return False, temp_dir, error_msg
        
        logger.info(f"Successfully cloned {repo_url}")
        return True, temp_dir, None
        
    except Exception as e:
        error_msg = f"Error cloning repository: {str(e)}"
        logger.error(error_msg)
        return False, temp_dir, error_msg

def get_current_commit_hash(repo_dir: str) -> Optional[str]:
    """Get the current commit hash of the repository"""
    try:
        cmd = ['git', '-C', repo_dir, 'rev-parse', 'HEAD']
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            commit_hash = result.stdout.strip()
            return commit_hash
        else:
            logger.error(f"Failed to get commit hash: {result.stderr}")
            return None
    except Exception as e:
        logger.error(f"Error getting commit hash: {str(e)}")
        return None

def fetch_repository(repo_dir: str, branch: str = 'main') -> Tuple[bool, Optional[str]]:
    """
    Fetch the latest changes from a repository
    
    Args:
        repo_dir: The repository directory
        branch: The branch to fetch (default: 'main')
        
    Returns:
        Tuple of (success, error_message)
    """
    try:
        # Fetch the latest changes
        logger.info(f"Fetching latest changes for {repo_dir}...")
        
        cmd = ['git', '-C', repo_dir, 'fetch', 'origin', branch]
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            error_msg = f"Failed to fetch repository: {result.stderr}"
            logger.error(error_msg)
            return False, error_msg
        
        # Reset to the latest commit
        cmd = ['git', '-C', repo_dir, 'reset', '--hard', f'origin/{branch}']
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            error_msg = f"Failed to reset repository: {result.stderr}"
            logger.error(error_msg)
            return False, error_msg
        
        logger.info(f"Successfully fetched latest changes")
        return True, None
        
    except Exception as e:
        error_msg = f"Error fetching repository: {str(e)}"
        logger.error(error_msg)
        return False, error_msg

def get_changed_files(repo_dir: str, previous_commit: str) -> Tuple[bool, List[str], Optional[str]]:
    """
    Get the list of files that have changed since the previous commit
    
    Args:
        repo_dir: The repository directory
        previous_commit: The previous commit hash
        
    Returns:
        Tuple of (success, changed_files, error_message)
    """
    try:
        # Get the list of changed files
        cmd = ['git', '-C', repo_dir, 'diff', '--name-only', previous_commit, 'HEAD']
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            error_msg = f"Failed to get changed files: {result.stderr}"
            logger.error(error_msg)
            return False, [], error_msg
        
        changed_files = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        logger.info(f"Found {len(changed_files)} changed files")
        return True, changed_files, None
        
    except Exception as e:
        error_msg = f"Error getting changed files: {str(e)}"
        logger.error(error_msg)
        return False, [], error_msg

def is_code_file(file_path: str) -> bool:
    """
    Check if a file is a code file based on its extension
    
    Args:
        file_path: The file path to check
        
    Returns:
        True if the file is a code file, False otherwise
    """
    # List of code file extensions to include
    code_extensions = {
        # Programming languages
        '.py', '.js', '.jsx', '.ts', '.tsx', '.java', '.c', '.cpp', '.cs', '.go', '.rs', 
        '.rb', '.php', '.swift', '.kt', '.scala', '.clj', '.cljs', '.cljc', '.edn',
        '.hs', '.fs', '.fsx', '.ml', '.mli', '.ex', '.exs', '.erl', '.hrl', 
        
        # Web
        '.html', '.htm', '.css', '.scss', '.sass', '.less', '.vue', '.svelte',
        
        # Data/Config
        '.json', '.yml', '.yaml', '.toml', '.xml', '.ini', '.csv',
        
        # SQL
        '.sql', '.sqlx',
        
        # Shell
        '.sh', '.bash', '.zsh', '.fish', '.bat', '.cmd', '.ps1',
        
        # Documentation
        '.md', '.rst', '.txt',
        
        # Others
        '.graphql', '.proto', '.dockerfile', '.tf', '.hcl'
    }
    
    # Get file extension
    _, ext = os.path.splitext(file_path.lower())
    
    # Check if file is a Dockerfile (without extension)
    if os.path.basename(file_path).lower() == 'dockerfile':
        return True
    
    return ext in code_extensions

def filter_code_files(file_paths: List[str]) -> List[str]:
    """
    Filter a list of file paths to include only code files
    
    Args:
        file_paths: The list of file paths to filter
        
    Returns:
        List of code file paths
    """
    return [path for path in file_paths if is_code_file(path)]

def read_file_content(file_path: str) -> Tuple[bool, str, Optional[str]]:
    """
    Read the content of a file
    
    Args:
        file_path: The file path to read
        
    Returns:
        Tuple of (success, content, error_message)
    """
    try:
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
        return True, content, None
    except Exception as e:
        error_msg = f"Error reading file {file_path}: {str(e)}"
        logger.error(error_msg)
        return False, "", error_msg

def get_file_hash(content: str) -> str:
    """
    Get the hash of a file's content
    
    Args:
        content: The file content
        
    Returns:
        The hash of the file content
    """
    return hashlib.sha256(content.encode('utf-8')).hexdigest()

def get_repo_name_from_url(repo_url: str) -> str:
    """
    Extract the repository name from a URL
    
    Args:
        repo_url: The repository URL
        
    Returns:
        The repository name
    """
    try:
        # Parse the URL
        parsed_url = urlparse(repo_url)
        
        # Get the path without the .git extension
        path = parsed_url.path.strip('/')
        if path.endswith('.git'):
            path = path[:-4]
        
        # Return the last part of the path as the repo name
        return path.split('/')[-1]
    except Exception:
        # If parsing fails, use a fallback approach
        parts = repo_url.strip('/').split('/')
        name = parts[-1]
        if name.endswith('.git'):
            name = name[:-4]
        return name

def get_all_code_files(repo_dir: str) -> List[str]:
    """
    Get all code files in a repository recursively
    
    Args:
        repo_dir: The repository directory
        
    Returns:
        List of code file paths (relative to repo_dir)
    """
    all_files = []
    
    for root, _, files in os.walk(repo_dir):
        for file in files:
            # Get path relative to repo_dir
            full_path = os.path.join(root, file)
            rel_path = os.path.relpath(full_path, repo_dir)
            
            # Skip .git directory
            if '.git/' in rel_path.replace('\\', '/'):
                continue
                
            all_files.append(rel_path)
    
    # Filter to include only code files
    return filter_code_files(all_files)

def process_repository(
    repo_url: str, 
    branch: str = 'main', 
    previous_commit: Optional[str] = None
) -> Tuple[bool, str, List[str], int, Optional[str]]:
    """
    Process a GitHub repository
    
    Args:
        repo_url: The repository URL to process
        branch: The branch to process (default: 'main')
        previous_commit: The previous commit hash for incremental processing
        
    Returns:
        Tuple of (success, commit_hash, processed_files, file_count, error_message)
    """
    success, temp_dir, error = clone_repository(repo_url, branch)
    
    if not success:
        return False, "", [], 0, error
    
    try:
        # Get current commit hash
        commit_hash = get_current_commit_hash(temp_dir)
        if not commit_hash:
            return False, "", [], 0, "Failed to get commit hash"
        
        files_to_process = []
        
        # If we have a previous commit, only process changed files
        if previous_commit and previous_commit != commit_hash:
            success, changed_files, error = get_changed_files(temp_dir, previous_commit)
            
            if not success:
                # Fallback to processing all files
                logger.warning(f"Failed to get changed files: {error}. Processing all files.")
                files_to_process = get_all_code_files(temp_dir)
            else:
                # Filter changed files to include only code files
                files_to_process = filter_code_files(changed_files)
        else:
            # First sync or forced full sync - process all files
            files_to_process = get_all_code_files(temp_dir)
        
        logger.info(f"Processing {len(files_to_process)} files")
        
        processed_files = []
        for rel_path in files_to_process:
            abs_path = os.path.join(temp_dir, rel_path)
            success, _, _ = read_file_content(abs_path)
            
            if success:
                processed_files.append(rel_path)
        
        return True, commit_hash, processed_files, len(processed_files), None
        
    except Exception as e:
        error_msg = f"Error processing repository: {str(e)}"
        logger.error(error_msg)
        return False, "", [], 0, error_msg
    finally:
        # Clean up
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception as e:
            logger.error(f"Error cleaning up temporary directory: {str(e)}")

def generate_file_id(repo_url: str, file_path: str, content_hash: str) -> str:
    """
    Generate a unique identifier for a file
    
    Args:
        repo_url: The repository URL
        file_path: The file path
        content_hash: The hash of the file content
        
    Returns:
        A unique identifier for the file
    """
    # Create a hash of the repo URL and file path
    repo_file_hash = hashlib.md5(f"{repo_url}:{file_path}".encode('utf-8')).hexdigest()
    
    # Combine with content hash to make it unique even if content changes
    return f"{repo_file_hash}_{content_hash[:8]}" 