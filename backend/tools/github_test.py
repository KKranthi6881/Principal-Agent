#!/usr/bin/env python3
"""
GitHub Toolset Test Script

This script demonstrates how to use the GitHub toolset to read code from repositories
using credentials stored in the metadata database.
"""

import os
import sys
import sqlite3
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add backend directory to path
backend_dir = Path(__file__).parent.parent
if str(backend_dir) not in sys.path:
    sys.path.append(str(backend_dir))

# Try to import PyGithub (needed for wrapper to work)
try:
    from github import Github, Auth
    logger.info("Successfully imported PyGithub")
except ImportError:
    logger.error("PyGithub is not installed. Please install it with 'pip install PyGithub'")
    sys.exit(1)

# Import GitHub tools
from tools.github.github_wrapper import GitHubAPIWrapper


# Import decryption function or define our own
try:
    from api.github_connectors_api import decrypt_token, get_db_connection
    logger.info("Successfully imported functions from github_connectors_api")
except ImportError:
    logger.info("Could not import from github_connectors_api, defining functions locally")
    
    def get_encryption_key():
        import base64
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
        
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
        from cryptography.fernet import Fernet
        key = get_encryption_key()
        return Fernet(key)

    def decrypt_token(encrypted_token: str) -> str:
        """Decrypt a GitHub token"""
        if not encrypted_token:
            return None
        try:
            cipher = get_cipher()
            return cipher.decrypt(encrypted_token.encode()).decode()
        except Exception as e:
            logger.error(f"Error decrypting token: {str(e)}")
            return None
    
    def get_db_connection():
        """Get a connection to the metadata database"""
        # Use absolute path to database
        db_path = os.path.join('/Users/Kranthi_1/Principal-Agent/backend/database', 'metadata.db')
        logger.info(f"Using database path: {db_path}")
        
        # Check if the file exists and is readable
        if not os.path.exists(db_path):
            raise FileNotFoundError(f"Database file not found: {db_path}")
        if not os.access(db_path, os.R_OK):
            raise PermissionError(f"Cannot read database file: {db_path}")
            
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn

def get_github_credentials() -> Dict[str, Any]:
    """
    Retrieve GitHub credentials from the metadata database
    
    Returns:
        Dict containing GitHub credentials
    """
    try:
        # For testing, we can also directly use the credentials we know
        use_hardcoded = False
        use_direct_decrypt = True
        
        if use_hardcoded:
            # Use GitHub personal access token for testing
            # You would replace this with an actual token you create
            github_credentials = {
                'github_token': 'YOUR_GITHUB_TOKEN_HERE',  # Replace with actual token
                'github_repository': 'dbt-labs/dbt-cloud-snowflake-demo-template',
                'github_username': 'github_user',  # Add a username
                'active_branch': 'main',
                'github_base_branch': 'main'
            }
            logger.info(f"Using hardcoded credentials for repository: {github_credentials['github_repository']}")
            return github_credentials
            
        elif use_direct_decrypt:
            # Try to decrypt the token directly
            # This is the encrypted token we got from the database
            encrypted_token = "gAAAAABn7zfxsh-WDrU5Rxd6Dnwo3Xlew6qrIpQuqpDVoTY3eOQ_daodnxXxT8nMHBZRtaWJsRPzvtp_LkPeB0k_nPsKmyO09dHQU4zhHB9Oynmq-fix4pP_yokJR573AExB9Tc50ry6"
            
            decrypted_token = decrypt_token(encrypted_token)
            if not decrypted_token:
                logger.error("Failed to decrypt token")
                return None
                
            # Using owner from the database record
            github_credentials = {
                'github_token': decrypted_token,
                'github_repository': 'dbt-labs/dbt-cloud-snowflake-demo-template',
                'github_username': 'dbt-labs',  # Using the owner as username
                'active_branch': 'main',
                'github_base_branch': 'main'
            }
            logger.info(f"Using credentials with decrypted token for repository: {github_credentials['github_repository']}")
            return github_credentials
        
        # Otherwise, try to get from database
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get first active GitHub connector
        cursor.execute("SELECT * FROM github_connectors WHERE active = 1 LIMIT 1")
        connector = cursor.fetchone()
        
        if not connector:
            logger.error("No active GitHub connector found in the database")
            return None
        
        connector_dict = dict(connector)
        
        # Decrypt token
        token = decrypt_token(connector_dict.get('token'))
        
        # Parse repositories from JSON
        repositories = []
        if connector_dict.get('repositories'):
            try:
                repositories = json.loads(connector_dict['repositories'])
            except:
                repositories = []
        
        owner = connector_dict.get('owner')
        
        github_credentials = {
            'github_token': token,
            'github_repository': f"{owner}/{repositories[0]}" if repositories and owner else None,
            'github_username': owner,  # Use the owner as the username
            'active_branch': connector_dict.get('default_branch', 'main'),
            'github_base_branch': connector_dict.get('default_branch', 'main')
        }
        
        logger.info(f"Retrieved credentials for repository: {github_credentials['github_repository']}")
        return github_credentials
    
    except Exception as e:
        logger.error(f"Error retrieving GitHub credentials: {str(e)}")
        return None

def initialize_github_wrapper(credentials: Dict[str, Any]) -> Optional[GitHubAPIWrapper]:
    """
    Initialize GitHub API wrapper with credentials
    
    Args:
        credentials: Dictionary of GitHub credentials
        
    Returns:
        Initialized GitHubAPIWrapper or None if initialization fails
    """
    try:
        wrapper = GitHubAPIWrapper(**credentials)
        logger.info(f"Successfully initialized GitHub wrapper for repository: {credentials['github_repository']}")
        return wrapper
    except Exception as e:
        logger.error(f"Error initializing GitHub wrapper: {str(e)}")
        return None

def read_file_from_github(wrapper: GitHubAPIWrapper, file_path: str) -> str:
    """
    Read a file from GitHub repository
    
    Args:
        wrapper: GitHub API wrapper
        file_path: Path to the file in the repository
        
    Returns:
        File content as string
    """
    try:
        content = wrapper.read_file(file_path)
        return content
    except Exception as e:
        logger.error(f"Error reading file {file_path}: {str(e)}")
        return f"Error: {str(e)}"

def list_files_in_repository(wrapper: GitHubAPIWrapper) -> str:
    """
    List files in the repository
    
    Args:
        wrapper: GitHub API wrapper
        
    Returns:
        List of files as string
    """
    try:
        files = wrapper.list_files_in_main_branch()
        return files
    except Exception as e:
        logger.error(f"Error listing files: {str(e)}")
        return f"Error: {str(e)}"

def search_code_in_repository(wrapper: GitHubAPIWrapper, query: str) -> str:
    """
    Search code in the repository
    
    Args:
        wrapper: GitHub API wrapper
        query: Search query
        
    Returns:
        Search results as string
    """
    try:
        results = wrapper.search_code(query)
        return results
    except Exception as e:
        logger.error(f"Error searching code: {str(e)}")
        return f"Error: {str(e)}"

def get_repository_info(wrapper: GitHubAPIWrapper) -> str:
    """
    Get information about the repository
    
    Args:
        wrapper: GitHub API wrapper
        
    Returns:
        Repository information as string
    """
    try:
        # Get repository instance
        repo = wrapper.github_repo_instance
        if not repo:
            return "Repository information not available"
            
        # Build repository info string
        info = [
            f"Repository: {repo.full_name}",
            f"Description: {repo.description or 'No description'}",
            f"Default Branch: {repo.default_branch}",
            f"Stars: {repo.stargazers_count}",
            f"Forks: {repo.forks_count}",
            f"Open Issues: {repo.open_issues_count}",
            f"Created: {repo.created_at}",
            f"Last Updated: {repo.updated_at}",
            f"Language: {repo.language or 'Not specified'}",
            f"URL: {repo.html_url}"
        ]
        
        # Get branches
        branches = [branch.name for branch in repo.get_branches()]
        info.append(f"Branches: {', '.join(branches[:5])}" + (", ..." if len(branches) > 5 else ""))
        
        return "\n".join(info)
    except Exception as e:
        logger.error(f"Error getting repository info: {str(e)}")
        return f"Error: {str(e)}"

def main():
    """Main function to run the GitHub toolset test"""
    
    # Get GitHub credentials from database
    credentials = get_github_credentials()
    if not credentials:
        logger.error("Failed to retrieve GitHub credentials")
        return
    
    # Initialize GitHub wrapper
    wrapper = initialize_github_wrapper(credentials)
    if not wrapper:
        logger.error("Failed to initialize GitHub wrapper")
        return
    
    # Get repository information
    print("\n=== Repository Information ===")
    repo_info = get_repository_info(wrapper)
    print(repo_info)
    
    # Test listing repository files
    print("\n=== Repository Files ===")
    files_output = list_files_in_repository(wrapper)
    file_count = int(files_output.split('\n')[0]) if files_output and '\n' in files_output else 0
    print(f"Found {file_count} files in repository")
    
    # Get list of files (skip the first line which is the count)
    files_list = files_output.split('\n')[1:] if files_output and '\n' in files_output else []
    
    # Find SQL files to display
    sql_files = [file for file in files_list if file.endswith('.sql')][:3]  # Get first 3 SQL files
    
    # Read and display content of SQL files
    for sql_file in sql_files:
        print(f"\n=== File: {sql_file} ===")
        content = read_file_from_github(wrapper, sql_file)
        print(content[:500] + "..." if len(content) > 500 else content)  # Limit output to 500 chars
    
    '''
    # Test search functionality
    print("\n=== Search: 'SELECT' ===")
    search_results = search_code_in_repository(wrapper, "SELECT")
    print(search_results) '''
    
    # Test search functionality for specific table name
    print("\n=== Search: 'fct_orders' ===")
    search_results = search_code_in_repository(wrapper, "fct_order_items")
    print(search_results)

if __name__ == "__main__":
    main() 