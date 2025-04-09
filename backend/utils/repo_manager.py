"""
Repository manager for maintaining persistent clones of GitHub repositories
"""
import os
import shutil
import logging
import hashlib
import subprocess
from typing import Tuple, Optional, List, Dict, Any
from urllib.parse import urlparse
import time
import pathlib

# Set up logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Base directory for storing persistent repository clones
# Use absolute path for reliability
BASE_DIR = pathlib.Path(__file__).parent.parent.absolute()
REPO_STORAGE_BASE = os.path.join(BASE_DIR, 'storage', 'repos')

def get_repo_storage_path(repo_url: str, branch: str = 'main') -> str:
    """
    Get the storage path for a repository
    
    Args:
        repo_url: The repository URL
        branch: The branch name
        
    Returns:
        The path where the repository should be stored
    """
    # Create a hash of the repo URL to use as the directory name
    repo_hash = hashlib.md5(repo_url.encode()).hexdigest()
    
    # Extract repo owner and name if possible
    try:
        parsed_url = urlparse(repo_url)
        path_parts = parsed_url.path.strip('/').split('/')
        
        if len(path_parts) >= 2:
            owner = path_parts[-2]
            name = path_parts[-1]
            if name.endswith('.git'):
                name = name[:-4]
            
            # Use a more readable directory name
            dir_name = f"{owner}_{name}_{repo_hash[:8]}_{branch}"
        else:
            dir_name = f"{repo_hash}_{branch}"
    except:
        # Fallback to just using the hash
        dir_name = f"{repo_hash}_{branch}"
    
    # Ensure the base directory exists
    os.makedirs(REPO_STORAGE_BASE, exist_ok=True)
    
    return os.path.join(REPO_STORAGE_BASE, dir_name)

def has_local_repo(repo_url: str, branch: str = 'main') -> bool:
    """
    Check if a repository has already been cloned locally
    
    Args:
        repo_url: The repository URL
        branch: The branch name
        
    Returns:
        True if the repository exists locally, False otherwise
    """
    repo_path = get_repo_storage_path(repo_url, branch)
    
    # Check if the directory exists and is a git repo
    if os.path.exists(repo_path) and os.path.exists(os.path.join(repo_path, '.git')):
        return True
    
    return False

def clone_repository(repo_url: str, branch: str = 'main') -> Tuple[bool, str, Optional[str]]:
    """
    Clone a repository to the persistent storage
    
    Args:
        repo_url: The repository URL
        branch: The branch name
        
    Returns:
        Tuple of (success, repo_path, error_message)
    """
    repo_path = get_repo_storage_path(repo_url, branch)
    
    # If the repository already exists, just return the path
    if has_local_repo(repo_url, branch):
        logger.info(f"Repository {repo_url} already exists at {repo_path}")
        return True, repo_path, None
    
    # Create parent directory if it doesn't exist
    os.makedirs(REPO_STORAGE_BASE, exist_ok=True)
    
    # Remove any existing directory (might be a failed clone)
    if os.path.exists(repo_path):
        shutil.rmtree(repo_path, ignore_errors=True)
    
    try:
        # Clone the repository
        logger.info(f"Cloning {repo_url} to {repo_path}...")
        
        cmd = ['git', 'clone', '--branch', branch, repo_url, repo_path]
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            # If branch doesn't exist, try with default branch
            if branch != 'main' and 'Remote branch not found' in result.stderr:
                logger.info(f"Branch {branch} not found, trying with 'main'...")
                
                # Clean up failed clone
                if os.path.exists(repo_path):
                    shutil.rmtree(repo_path, ignore_errors=True)
                
                # Clone without specifying branch
                cmd = ['git', 'clone', repo_url, repo_path]
                result = subprocess.run(cmd, capture_output=True, text=True)
                
                if result.returncode != 0:
                    error_msg = f"Failed to clone repository: {result.stderr}"
                    logger.error(error_msg)
                    return False, repo_path, error_msg
            else:
                error_msg = f"Failed to clone repository: {result.stderr}"
                logger.error(error_msg)
                return False, repo_path, error_msg
        
        logger.info(f"Successfully cloned {repo_url} to {repo_path}")
        return True, repo_path, None
        
    except Exception as e:
        error_msg = f"Error cloning repository: {str(e)}"
        logger.error(error_msg)
        return False, repo_path, error_msg

def update_repository(repo_path: str, branch: str = 'main') -> Tuple[bool, Optional[str]]:
    """
    Update a local repository with the latest changes
    
    Args:
        repo_path: The repository path
        branch: The branch name
        
    Returns:
        Tuple of (success, error_message)
    """
    try:
        # Fetch the latest changes
        logger.info(f"Fetching latest changes for {repo_path}...")
        
        # Try to switch to the correct branch first
        cmd = ['git', '-C', repo_path, 'checkout', branch]
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            logger.warning(f"Failed to switch to branch {branch}: {result.stderr}")
            
            # Try to fetch all branches
            cmd = ['git', '-C', repo_path, 'fetch', 'origin']
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                error_msg = f"Failed to fetch repository: {result.stderr}"
                logger.error(error_msg)
                return False, error_msg
            
            # Try to checkout the branch again after fetching
            cmd = ['git', '-C', repo_path, 'checkout', branch]
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                error_msg = f"Failed to checkout branch {branch}: {result.stderr}"
                logger.error(error_msg)
                return False, error_msg
        
        # Pull the latest changes
        cmd = ['git', '-C', repo_path, 'pull', 'origin', branch]
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            error_msg = f"Failed to pull latest changes: {result.stderr}"
            logger.error(error_msg)
            return False, error_msg
        
        logger.info(f"Successfully updated repository at {repo_path}")
        return True, None
        
    except Exception as e:
        error_msg = f"Error updating repository: {str(e)}"
        logger.error(error_msg)
        return False, error_msg

def get_current_commit_hash(repo_path: str) -> Optional[str]:
    """
    Get the current commit hash of the repository
    
    Args:
        repo_path: The repository path
        
    Returns:
        The commit hash, or None if there was an error
    """
    try:
        cmd = ['git', '-C', repo_path, 'rev-parse', 'HEAD']
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

def get_changed_files(repo_path: str, previous_commit: str) -> Tuple[bool, List[str], Optional[str]]:
    """
    Get the list of files that have changed since the previous commit
    
    Args:
        repo_path: The repository path
        previous_commit: The previous commit hash
        
    Returns:
        Tuple of (success, changed_files, error_message)
    """
    try:
        # Get the list of changed files
        cmd = ['git', '-C', repo_path, 'diff', '--name-only', previous_commit, 'HEAD']
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            error_msg = f"Failed to get changed files: {result.stderr}"
            logger.error(error_msg)
            return False, [], error_msg
        
        changed_files = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        logger.info(f"Found {len(changed_files)} changed files since {previous_commit[:8]}")
        return True, changed_files, None
        
    except Exception as e:
        error_msg = f"Error getting changed files: {str(e)}"
        logger.error(error_msg)
        return False, [], error_msg

def get_deleted_files(repo_path: str, previous_commit: str) -> Tuple[bool, List[str], Optional[str]]:
    """
    Get the list of files that have been deleted since the previous commit
    
    Args:
        repo_path: The repository path
        previous_commit: The previous commit hash
        
    Returns:
        Tuple of (success, deleted_files, error_message)
    """
    try:
        # Get the list of deleted files
        cmd = ['git', '-C', repo_path, 'diff', '--diff-filter=D', '--name-only', previous_commit, 'HEAD']
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            error_msg = f"Failed to get deleted files: {result.stderr}"
            logger.error(error_msg)
            return False, [], error_msg
        
        deleted_files = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        logger.info(f"Found {len(deleted_files)} deleted files since {previous_commit[:8]}")
        return True, deleted_files, None
        
    except Exception as e:
        error_msg = f"Error getting deleted files: {str(e)}"
        logger.error(error_msg)
        return False, [], error_msg

def get_repository_size(repo_path: str) -> int:
    """
    Get the size of the repository in bytes
    
    Args:
        repo_path: The repository path
        
    Returns:
        The size of the repository in bytes
    """
    total_size = 0
    
    for dirpath, _, filenames in os.walk(repo_path):
        for filename in filenames:
            file_path = os.path.join(dirpath, filename)
            total_size += os.path.getsize(file_path)
    
    return total_size

def clean_old_repositories(max_age_days: int = 30, max_total_size_gb: float = 10):
    """
    Clean up old repositories that haven't been accessed recently
    
    Args:
        max_age_days: Maximum age in days to keep repositories that haven't been accessed
        max_total_size_gb: Maximum total size in GB to keep
    """
    if not os.path.exists(REPO_STORAGE_BASE):
        return
    
    # Get all repository directories
    repo_dirs = []
    
    for dirname in os.listdir(REPO_STORAGE_BASE):
        repo_path = os.path.join(REPO_STORAGE_BASE, dirname)
        if os.path.isdir(repo_path) and os.path.exists(os.path.join(repo_path, '.git')):
            # Get the last accessed time
            last_accessed = os.path.getatime(repo_path)
            size = get_repository_size(repo_path)
            
            repo_dirs.append({
                'path': repo_path,
                'last_accessed': last_accessed,
                'size': size
            })
    
    # Calculate total size
    total_size = sum(repo['size'] for repo in repo_dirs)
    total_size_gb = total_size / (1024**3)
    
    # Current time
    current_time = time.time()
    
    # Clean up old repositories
    repos_to_delete = []
    
    # First, mark repositories older than max_age_days
    for repo in repo_dirs:
        age_days = (current_time - repo['last_accessed']) / (60 * 60 * 24)
        if age_days > max_age_days:
            repos_to_delete.append(repo)
    
    # If we're still over the size limit, sort by last accessed time and delete oldest
    if total_size_gb > max_total_size_gb:
        # Sort remaining repositories by last accessed time
        remaining_repos = [r for r in repo_dirs if r not in repos_to_delete]
        remaining_repos.sort(key=lambda r: r['last_accessed'])
        
        # Delete oldest repositories until we're under the size limit
        current_size_gb = total_size_gb
        for repo in remaining_repos:
            if current_size_gb <= max_total_size_gb:
                break
            
            repos_to_delete.append(repo)
            current_size_gb -= repo['size'] / (1024**3)
    
    # Delete the repositories
    for repo in repos_to_delete:
        try:
            logger.info(f"Cleaning up old repository: {repo['path']}")
            shutil.rmtree(repo['path'], ignore_errors=True)
        except Exception as e:
            logger.error(f"Error cleaning up repository {repo['path']}: {str(e)}") 