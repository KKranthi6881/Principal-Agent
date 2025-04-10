#!/usr/bin/env python3
"""
GitHub SQL Integration Demo

This script demonstrates the integration of SQL analysis tools with GitHub repository tools
to analyze SQL code in GitHub repositories. It combines:
1. SQL lineage and dependency analysis from sql_tools
2. GitHub repository file access from github_wrapper

The workflow:
1. User asks a question about SQL tables or files
2. SQL tools analyze the query and find relevant files in GitHub
3. The script automatically fetches and displays the file contents using GitHub API
"""

import os
import sys
import json
import sqlite3
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add backend directory to path
backend_dir = Path(__file__).parent.parent
if str(backend_dir) not in sys.path:
    sys.path.append(str(backend_dir))

# Import SQL analysis tools
from tools.sql_tools.llm_interface import llm_interface

# Import GitHub tools
from tools.github.github_wrapper import GitHubAPIWrapper

# Import decryption function
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
        # For testing, we can use the credentials directly
        use_direct_decrypt = True
        
        if use_direct_decrypt:
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

def extract_repo_info_from_url(github_url: str) -> Dict[str, str]:
    """
    Extract repository information from a GitHub URL
    
    Args:
        github_url: GitHub URL
        
    Returns:
        Dictionary with owner, repo name, and file path
    """
    # Example URL: https://github.com/dbt-labs/dbt-cloud-snowflake-demo-template.git/blob/main/models/staging/tpch/stg_tpch_orders.sql
    # or: https://github.com/dbt-labs/dbt-cloud-snowflake-demo-template/blob/main/models/staging/tpch/stg_tpch_orders.sql
    
    if not github_url:
        return {"owner": None, "repo": None, "path": None}
    
    # Remove trailing .git if present
    if ".git/blob/" in github_url:
        github_url = github_url.replace(".git/blob/", "/blob/")
    
    # Split URL to extract components
    try:
        parts = github_url.split("github.com/")[1].split("/blob/")
        repo_parts = parts[0].split("/")
        owner = repo_parts[0]
        repo = repo_parts[1]
        
        # Extract the file path
        path = parts[1]
        if path.startswith("/"):
            path = path[1:]
        if path.startswith("main/"):
            path = path[5:]  # Remove "main/"
        
        return {"owner": owner, "repo": repo, "path": path}
    except Exception as e:
        logger.error(f"Error extracting repo info from URL {github_url}: {str(e)}")
        return {"owner": None, "repo": None, "path": None}

def fetch_file_from_github(wrapper: GitHubAPIWrapper, file_path: str) -> str:
    """
    Fetch file contents from GitHub
    
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

def extract_github_urls_from_results(results: Dict[str, Any]) -> List[Dict[str, str]]:
    """
    Extract GitHub URLs from search results or lineage results
    
    Args:
        results: Results from SQL analysis tools
        
    Returns:
        List of dictionaries with file info
    """
    urls = []
    
    # Check if it's a search result
    if "results" in results:
        for result in results.get("results", []):
            url = result.get("url")
            if url:
                repo_info = extract_repo_info_from_url(url)
                if repo_info["path"]:
                    urls.append({
                        "url": url,
                        "file_path": repo_info["path"],
                        "name": result.get("file_path", "").split("/")[-1] if result.get("file_path") else repo_info["path"].split("/")[-1],
                        "owner": repo_info["owner"],
                        "repo": repo_info["repo"]
                    })
    
    # Check if it's a lineage result
    elif "levels" in results:
        # Process level 0 - the main table
        for item in results.get("levels", {}).get("0", []):
            url = item.get("url")
            if url:
                repo_info = extract_repo_info_from_url(url)
                if repo_info["path"]:
                    urls.append({
                        "url": url,
                        "file_path": repo_info["path"],
                        "name": item.get("name", "").split("/")[-1] if item.get("name") else repo_info["path"].split("/")[-1],
                        "owner": repo_info["owner"],
                        "repo": repo_info["repo"],
                        "level": 0
                    })
        
        # Process level 1 - the dependencies
        for item in results.get("levels", {}).get("1", []):
            url = item.get("url")
            if url:
                repo_info = extract_repo_info_from_url(url)
                if repo_info["path"]:
                    urls.append({
                        "url": url,
                        "file_path": repo_info["path"],
                        "name": item.get("name", "").split("/")[-1] if item.get("name") else repo_info["path"].split("/")[-1],
                        "owner": repo_info["owner"],
                        "repo": repo_info["repo"],
                        "level": 1
                    })
    
    return urls

class GitHubSQLDemo:
    """
    Demonstration of how to combine SQL tools with GitHub tools
    """
    
    def __init__(self):
        """Initialize the demo"""
        self.sql_interface = llm_interface
        self.github_wrapper = None
        self.memory = {}  # Simple memory to store context between calls
        
        # Initialize GitHub wrapper
        credentials = get_github_credentials()
        if credentials:
            self.github_wrapper = initialize_github_wrapper(credentials)
        else:
            logger.error("Failed to get GitHub credentials")
    
    def process_question(self, question: str) -> str:
        """
        Process a question using SQL tools and GitHub wrapper
        
        Args:
            question: User's question
            
        Returns:
            Response with SQL analysis and file contents
        """
        if not self.github_wrapper:
            return "GitHub wrapper not initialized. Cannot access repository files."
        
        question = question.lower().strip()
        
        print(f"\n[USER QUESTION]: {question}")
        print("\n[AGENT THINKING]:")
        
        # Process question about table lineage
        if "where does" in question and "come from" in question:
            result = self._process_table_lineage_question(question)
            urls = extract_github_urls_from_results(result)
            return self._generate_response_with_github_files(result, urls)
        
        # Process question about SQL implementation
        elif "show" in question and "sql" in question:
            result = self._process_show_sql_question(question)
            urls = extract_github_urls_from_results(result)
            return self._generate_response_with_github_files(result, urls)
        
        # Process question about column lineage
        elif "column" in question and ("where" in question or "how" in question or "lineage" in question):
            result = self._process_column_lineage_question(question)
            urls = extract_github_urls_from_results(result)
            return self._generate_response_with_github_files(result, urls)
        
        # Process general search query
        else:
            print(f"  - Treating as a general search query")
            search_terms = question.replace("?", "").split()
            query = " ".join([term for term in search_terms if len(term) > 3])
            
            # Search for SQL files
            search_result = self.sql_interface.search_sql(query, limit=5)
            urls = extract_github_urls_from_results(search_result)
            return self._generate_response_with_github_files(search_result, urls, is_search=True)
    
    def _process_table_lineage_question(self, question: str) -> Dict[str, Any]:
        """Process a question about table lineage"""
        # Extract table name
        table_name = self._extract_table_name(question)
        if not table_name:
            return {"error": "I couldn't identify a specific table in your question."}
        
        print(f"  - User is asking about upstream lineage for table: {table_name}")
        
        # First search for the table
        search_result = self.sql_interface.search_tables(table_name, limit=3)
        
        if search_result.get("files_found", 0) == 0:
            return {"error": f"I couldn't find any files related to table '{table_name}' in the codebase."}
        
        # Get the repo URL from search results
        repo_url = None
        if search_result.get("results") and len(search_result["results"]) > 0:
            repo_url = search_result["results"][0].get("repo")
            print(f"  - Found table in repository: {repo_url}")
            
            # Store this in memory for future questions
            self.memory["current_repo"] = repo_url
            self.memory["current_table"] = table_name
        
        # Trace upstream lineage
        print(f"  - Tracing upstream lineage for table '{table_name}'...")
        return self.sql_interface.get_table_lineage(
            table_name=table_name,
            direction="upstream",
            max_depth=2,
            repo_url=repo_url
        )
    
    def _process_show_sql_question(self, question: str) -> Dict[str, Any]:
        """Process a question about SQL implementation"""
        # Extract table name
        table_name = self._extract_table_name(question)
        if not table_name and "current_table" in self.memory:
            table_name = self.memory["current_table"]
            print(f"  - Using current table from memory: {table_name}")
        
        if not table_name:
            return {"error": "I couldn't identify a specific table in your question."}
        
        print(f"  - User is asking to see SQL implementation for table: {table_name}")
        
        # Search for the table
        return self.sql_interface.search_tables(table_name, limit=1)
    
    def _process_column_lineage_question(self, question: str) -> Dict[str, Any]:
        """Process a question about column lineage"""
        # Extract table and column names
        table_name, column_name = self._extract_table_column(question)
        
        if not table_name or not column_name:
            if "current_table" in self.memory:
                table_name = self.memory["current_table"]
                print(f"  - Using current table from memory: {table_name}")
            else:
                return {"error": "I couldn't identify a specific table and column in your question."}
        
        print(f"  - User is asking about column lineage for: {table_name}.{column_name}")
        
        # Get repo URL from memory if available
        repo_url = self.memory.get("current_repo")
        
        # Trace column lineage
        print(f"  - Tracing column lineage for {table_name}.{column_name}...")
        return self.sql_interface.get_column_lineage(
            table_name=table_name,
            column_name=column_name,
            direction="upstream",
            max_depth=2,
            repo_url=repo_url
        )
    
    def _generate_response_with_github_files(self, results: Dict[str, Any], urls: List[Dict[str, str]], 
                                            is_search: bool = False) -> str:
        """Generate response with GitHub file contents"""
        if "error" in results:
            return results["error"]
        
        # If there are no URLs to fetch, return a simple response
        if not urls:
            if is_search:
                return "I couldn't find any SQL files matching your query in the GitHub repository."
            else:
                return "I found information about your query, but couldn't find the corresponding files in the GitHub repository."
        
        # Build the response based on the results and GitHub files
        if is_search:
            # For search results
            response = f"I found {len(urls)} SQL files that match your query. Here are the files with their contents:\n\n"
            
            for i, url_info in enumerate(urls, 1):
                file_path = url_info["file_path"]
                file_content = fetch_file_from_github(self.github_wrapper, file_path)
                
                response += f"**File {i}: {file_path}**\n"
                response += f"URL: {url_info['url']}\n\n"
                response += "```sql\n"
                response += file_content[:1000] + ("..." if len(file_content) > 1000 else "")
                response += "\n```\n\n"
        
        elif "table" in results:
            # For table lineage results
            table_name = results["table"]
            
            response = f"# Table: {table_name}\n\n"
            
            # First get the main table's SQL definition
            main_files = [url for url in urls if url.get("level") == 0]
            if main_files:
                file_path = main_files[0]["file_path"]
                file_content = fetch_file_from_github(self.github_wrapper, file_path)
                
                response += f"## Definition\n\n"
                response += f"File: {file_path}\n\n"
                response += "```sql\n"
                response += file_content
                response += "\n```\n\n"
            
            # Then list the dependencies
            dep_files = [url for url in urls if url.get("level") == 1]
            if dep_files:
                response += f"## Dependencies\n\n"
                response += f"The table '{table_name}' depends on the following tables:\n\n"
                
                for i, url_info in enumerate(dep_files, 1):
                    file_path = url_info["file_path"]
                    file_content = fetch_file_from_github(self.github_wrapper, file_path)
                    
                    response += f"### {i}. {url_info['name']}\n\n"
                    response += f"File: {file_path}\n"
                    response += f"URL: {url_info['url']}\n\n"
                    response += "```sql\n"
                    response += file_content[:500] + ("..." if len(file_content) > 500 else "")
                    response += "\n```\n\n"
            
            if not main_files and not dep_files:
                response += "I couldn't retrieve the SQL definitions for this table and its dependencies.\n"
        
        elif "column" in results:
            # For column lineage results
            table_name = results["table"]
            column_name = results["column"]
            
            response = f"# Column: {table_name}.{column_name}\n\n"
            
            if urls:
                response += f"## SQL Definitions\n\n"
                
                for i, url_info in enumerate(urls, 1):
                    file_path = url_info["file_path"]
                    file_content = fetch_file_from_github(self.github_wrapper, file_path)
                    
                    level_str = "Main table" if url_info.get("level") == 0 else "Dependency"
                    response += f"### {i}. {url_info['name']} ({level_str})\n\n"
                    response += f"File: {file_path}\n"
                    response += f"URL: {url_info['url']}\n\n"
                    response += "```sql\n"
                    response += file_content[:500] + ("..." if len(file_content) > 500 else "")
                    response += "\n```\n\n"
            else:
                response += f"I couldn't retrieve the SQL definitions for this column.\n"
        
        else:
            # For other types of results
            response = "I found the following SQL files:\n\n"
            
            for i, url_info in enumerate(urls, 1):
                file_path = url_info["file_path"]
                file_content = fetch_file_from_github(self.github_wrapper, file_path)
                
                response += f"**File {i}: {file_path}**\n"
                response += f"URL: {url_info['url']}\n\n"
                response += "```sql\n"
                response += file_content[:1000] + ("..." if len(file_content) > 1000 else "")
                response += "\n```\n\n"
        
        return response
    
    def _extract_table_name(self, question: str) -> str:
        """Extract table name from question"""
        # Simple pattern matching
        patterns = [
            "table", "from", "for", "about", "in", "does"
        ]
        
        words = question.split()
        for i, word in enumerate(words):
            if word in patterns and i < len(words) - 1:
                # Check next word as potential table name
                candidate = words[i + 1].strip(",.'\"()")
                if len(candidate) > 2 and candidate not in ["the", "and", "come", "where", "what"]:
                    return candidate
        
        # Check for specific patterns with table names
        if "where does" in question and "come from" in question:
            parts = question.split("where does")[1].split("come from")[0].strip()
            if parts:
                return parts
        
        return None
    
    def _extract_table_column(self, question: str) -> tuple:
        """Extract table and column names from question"""
        # Simple pattern matching
        table_name = None
        column_name = None
        
        # Look for table.column pattern
        words = question.split()
        for word in words:
            if '.' in word:
                parts = word.strip(",.'\"()").split('.')
                if len(parts) == 2:
                    table_name = parts[0]
                    column_name = parts[1]
                    return table_name, column_name
        
        # Look for "column X in table Y" pattern
        if "column" in question and "in" in question:
            column_idx = question.find("column")
            in_idx = question.find("in", column_idx)
            
            if column_idx >= 0 and in_idx > column_idx:
                column_part = question[column_idx + 7:in_idx].strip()
                table_part = question[in_idx + 3:].strip().split()[0].strip(",.'\"()")
                
                return table_part, column_part
        
        # Look for "column X" pattern
        if "column" in question:
            column_idx = question.find("column")
            if column_idx >= 0 and column_idx + 7 < len(question):
                column_part = question[column_idx + 7:].strip().split()[0].strip(",.'\"()")
                return table_name, column_part
        
        return table_name, column_name

def main():
    """Main function to run the GitHub SQL demo"""
    demo = GitHubSQLDemo()
    
    # Sample questions to demonstrate
    questions = [
        "Where does the table fct_order_items come from?",
        "Can you show me the SQL for stg_tpch_orders?",
        "What is the lineage of order_key column in fct_order_items?",
        "Find SQL files with JOIN operations"
    ]
    
    # Process each question
    for question in questions:
        response = demo.process_question(question)
        print("\n[AGENT RESPONSE]:")
        print(response)
        print("\n" + "=" * 80)
    
    # Interactive mode
    while True:
        try:
            question = input("\nEnter your question (or 'quit' to exit): ")
            if question.lower() in ["quit", "exit", "q"]:
                break
            
            response = demo.process_question(question)
            print("\n[AGENT RESPONSE]:")
            print(response)
            print("\n" + "=" * 80)
        except KeyboardInterrupt:
            print("\nExiting...")
            break

if __name__ == "__main__":
    main() 