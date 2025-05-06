"""
API for GitHub connector configurations
"""
import os
import uuid
import re
import json
from typing import Dict, List, Optional, Any
from fastapi import APIRouter, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel, Field
import sqlite3
import requests
from cryptography.fernet import Fernet
import base64
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from urllib.parse import urlparse
from utils.repo_manager import clone_repository
import logging

# Set up logging
logger = logging.getLogger(__name__)

# Router for GitHub connectors API
router = APIRouter(prefix="/api/settings", tags=["github"])

# Import shared utilities
from utils.connector_utils import get_db_connection, decrypt_token, get_github_connector

# Path to metadata database
METADATA_DB = os.path.join('database', 'metadata.db')

# Import chunked lineage processor after utils to avoid circular imports
from api.chunked_lineage_processor import ChunkedLineageProcessor

# Encryption key generation (using same approach as in llm_providers_api.py)
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

# Helper functions
def normalize_enterprise_api_url(api_url: str) -> str:
    """
    Ensure the provided API URL is a valid GitHub Enterprise API base URL.
    Returns the normalized URL or raises ValueError if invalid.
    """
    if not api_url:
        raise ValueError("API URL is required for enterprise GitHub.")
    
    # Make sure URL starts with http:// or https://
    if not api_url.startswith('http://') and not api_url.startswith('https://'):
        api_url = f"https://{api_url}"
    
    parsed = urlparse(api_url)
    
    # Basic URL validation
    if parsed.netloc == '' or parsed.scheme == '':
        raise ValueError(f"Malformed API URL: '{api_url}'. Please provide a valid URL including the domain.")
    
    # Only check for repository URL pattern if the path is more than just a domain
    # Simple domains like 'github.mycompany.com' should be accepted
    if parsed.path and parsed.path != '/':
        # Check if it's a repository URL rather than a base domain
        repo_path_pattern = re.compile(r'/[\w.-]+/[\w.-]+(\.git)?/?$')
        if parsed.path.endswith('.git') or repo_path_pattern.search(parsed.path):
            raise ValueError(f"API URL appears to be a repository URL. Please provide the base API URL (e.g., https://<your-gh-enterprise-domain>)")
    
    # Normalize by removing trailing slashes
    normalized_url = api_url.rstrip('/')
    
    # Automatically add /api/v3 if missing
    if not normalized_url.endswith('/api/v3'):
        # Don't duplicate /api/v3 if parts of it are already there
        if normalized_url.endswith('/api'):
            normalized_url = f"{normalized_url}/v3"
        else:
            normalized_url = f"{normalized_url}/api/v3"
    
    return normalized_url

def encrypt_token(token: str) -> str:
    """Encrypt a GitHub token"""
    if not token:
        return None
    cipher = get_cipher()
    return cipher.encrypt(token.encode()).decode()

# Pydantic models for request/response
class GitHubConnectorCreate(BaseModel):
    """GitHub connector creation model"""
    name: str
    description: Optional[str] = None
    github_type: str = Field(..., description="Type of GitHub: 'public' or 'enterprise'")
    api_url: Optional[str] = Field(None, description="API URL for enterprise GitHub")
    token: str
    owner: Optional[str] = None
    repositories: Optional[List[str]] = None
    organization: Optional[str] = None
    default_branch: Optional[str] = "main"
    active: bool = True
    repo_url: Optional[str] = Field(None, description="Direct GitHub repository URL")
    tech_stack: Optional[str] = Field("postgresql", description="Tech stack for SQL parsing: postgresql, mysql, snowflake, tsql, dbt")

class GitHubConnectorResponse(BaseModel):
    """GitHub connector response model"""
    id: str
    name: str
    description: Optional[str] = None
    github_type: str
    api_url: Optional[str] = None
    has_token: bool
    owner: Optional[str] = None
    repositories: Optional[List[str]] = None
    organization: Optional[str] = None
    default_branch: Optional[str] = "main"
    active: bool = True
    created_at: str
    updated_at: str
    repo_url: Optional[str] = None
    tech_stack: Optional[str] = "postgresql"

class GitHubConnectorUpdate(BaseModel):
    """GitHub connector update model"""
    name: Optional[str] = None
    description: Optional[str] = None
    github_type: Optional[str] = None
    api_url: Optional[str] = None
    token: Optional[str] = None
    owner: Optional[str] = None
    repositories: Optional[List[str]] = None
    organization: Optional[str] = None
    default_branch: Optional[str] = None
    active: Optional[bool] = None
    repo_url: Optional[str] = None
    tech_stack: Optional[str] = None

class GitHubConnectorList(BaseModel):
    """GitHub connector list response"""
    connectors: List[GitHubConnectorResponse]

class TestConnectionResponse(BaseModel):
    """Test connection response model"""
    success: bool
    message: str
    details: Optional[Dict[str, Any]] = None

# Function to clone a GitHub repository locally
def clone_github_repository(connector: Dict[str, Any]) -> Dict[str, Any]:
    """
    Helper function to clone a GitHub repository locally
    """
    try:
        # Determine the repository URL and branch
        repo_url = None
        branch = connector.get("default_branch", "main")
        
        # Direct repository URL (highest priority)
        if connector.get("repo_url"):
            repo_url = connector["repo_url"]
        # Owner and repositories
        elif connector.get("owner") and connector.get("repositories") and len(connector["repositories"]) > 0:
            owner = connector["owner"]
            repo_name = connector["repositories"][0]  # Take the first repo for now
            repo_url = f"https://github.com/{owner}/{repo_name}"
        # Organization repositories (would need to be enhanced to handle multiple)
        elif connector.get("organization") and connector.get("repositories") and len(connector["repositories"]) > 0:
            org = connector["organization"]
            repo_name = connector["repositories"][0]  # Take the first repo for now
            repo_url = f"https://github.com/{org}/{repo_name}"
        
        if not repo_url:
            logger.error(f"No repository URL could be determined from connector settings")
            return {
                "status": "error",
                "message": "No repository URL could be determined"
            }
            
        logger.info(f"Cloning repository: {repo_url}, branch: {branch}")
        repo_path = clone_repository(repo_url, branch)
        
        if repo_path:
            logger.info(f"Successfully cloned repository to {repo_path}")
            return {
                "status": "success",
                "message": f"Repository cloned successfully to {repo_path}",
                "repo_path": repo_path
            }
        else:
            logger.error(f"Failed to clone repository: {repo_url}")
            return {
                "status": "error",
                "message": f"Failed to clone repository: {repo_url}"
            }
    except Exception as e:
        logger.error(f"Error cloning repository: {str(e)}")
        return {
            "status": "error",
            "message": f"Error cloning repository: {str(e)}"
        }

# Function to trigger lineage extraction
def trigger_lineage_extraction(connector_id: str, connector: Dict[str, Any]) -> Dict[str, Any]:
    """
    Helper function to trigger lineage extraction in the background
    """
    try:
        # First, ensure the repository is cloned locally
        clone_result = clone_github_repository(connector)
        if clone_result["status"] == "error":
            logger.warning(f"Could not clone repository before lineage extraction: {clone_result['message']}")
            # Continue anyway, the lineage extraction might have its own cloning mechanism
        
        # Construct URL for the lineage extraction endpoint
        base_url = "http://localhost:8000"  # Adjust as needed for production
        url = f"{base_url}/api/lineage/github-connector/{connector_id}/extract-lineage"
        
        # Use tech_stack from connector
        tech_stack = connector.get("tech_stack", "postgresql")
        
        # Make the request
        response = requests.post(
            url,
            json={"tech_stack": tech_stack}
        )
        
        if response.status_code == 200:
            return {
                "status": "success",
                "message": "Lineage extraction started in the background"
            }
        else:
            logger.error(f"Error triggering lineage extraction: {response.status_code} - {response.text}")
            return {
                "status": "error",
                "message": f"Failed to start lineage extraction: {response.text}"
            }
    except Exception as e:
        logger.error(f"Error triggering lineage extraction: {str(e)}")
        return {
            "status": "error",
            "message": f"Error triggering lineage extraction: {str(e)}"
        }

# Sync repository and extract lineage
@router.post("/github_connectors/{connector_id}/sync", response_model=Dict[str, Any])
async def sync_github_connector(
    connector_id: str,
    tech_stack: Optional[str] = Query(None, description="Override tech stack (optional)"),
    branch: Optional[str] = Query(None, description="Branch to extract from"),
    chunk_size: Optional[int] = Query(50, description="Number of files per processing chunk")
):
    """
    Sync a GitHub connector by cloning the repository and extracting lineage
    
    This endpoint performs both the cloning and lineage extraction in a non-blocking
    asynchronous manner. Progress can be monitored via the task status endpoint.
    """
    try:
        # Get the GitHub connector
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM github_connectors WHERE id = ?", (connector_id,))
        connector = cursor.fetchone()
        
        if not connector:
            raise HTTPException(status_code=404, detail=f"GitHub connector {connector_id} not found")
        
        # Convert to dict
        connector_dict = dict(connector)
        conn.close()
        
        # Determine the repository URL
        repo_url = connector_dict.get('repo_url')
        
        if not repo_url and connector_dict.get('repositories'):
            # Try to construct a URL from owner/repo or organization/repo
            repositories = json.loads(connector_dict['repositories'])
            if repositories and len(repositories) > 0:
                owner = connector_dict.get('owner')
                organization = connector_dict.get('organization')
                
                # Use first repository for now
                repo_name = repositories[0]
                
                if owner:
                    repo_url = f"https://github.com/{owner}/{repo_name}"
                elif organization:
                    repo_url = f"https://github.com/{organization}/{repo_name}"
        
        if not repo_url:
            raise HTTPException(
                status_code=400, 
                detail="Unable to determine repository URL from connector settings"
            )
        
        # Use connector's tech stack if not overridden
        if not tech_stack:
            tech_stack = connector_dict.get('tech_stack', 'postgresql')
        
        # Use connector's branch if provided and not overridden
        if not branch and connector_dict.get('default_branch'):
            branch = connector_dict.get('default_branch')
        elif not branch:
            branch = "main"  # Default branch
        
        # Create and start the chunked processor
        processor = ChunkedLineageProcessor(
            connector_id=connector_id,
            repo_url=repo_url,
            tech_stack=tech_stack,
            branch=branch,
            chunk_size=chunk_size
        )
        
        # Start processing in background
        task_id = await processor.process()
        
        return {
            "success": True,
            "task_id": task_id,
            "message": f"Started synchronization and lineage extraction for {repo_url}",
            "tech_stack": tech_stack,
            "branch": branch,
            "chunk_size": chunk_size
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error syncing GitHub connector: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail=f"Error syncing GitHub connector: {str(e)}"
        )

# API endpoints
@router.get("/github_connectors", response_model=GitHubConnectorList)
async def get_github_connectors():
    """
    Get all GitHub connectors
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get all GitHub connectors
        cursor.execute("SELECT * FROM github_connectors ORDER BY created_at DESC")
        connectors = []
        
        for row in cursor.fetchall():
            connector = dict(row)
            # Don't send actual token, just whether it exists
            has_token = bool(connector.get('token'))
            connector.pop('token', None)
            
            # Parse repositories list from JSON
            if connector.get('repositories'):
                try:
                    connector['repositories'] = json.loads(connector['repositories'])
                except:
                    connector['repositories'] = []
                    
            connectors.append({
                **connector,
                'has_token': has_token
            })
        
        conn.close()
        
        return {"connectors": connectors}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting GitHub connectors: {str(e)}")

@router.post("/github_connectors", response_model=GitHubConnectorResponse)
async def create_github_connector(connector: GitHubConnectorCreate, background_tasks: BackgroundTasks):
    """
    Create a new GitHub connector
    """
    try:
        # Validate GitHub connection before saving
        test_result = await test_github_connection(connector)
        if not test_result.success:
            raise HTTPException(status_code=400, detail=f"GitHub connection failed: {test_result.message}")
        
        # Encrypt token
        encrypted_token = encrypt_token(connector.token)
        
        # Convert repositories list to JSON if provided
        repositories_json = None
        if connector.repositories:
            repositories_json = json.dumps(connector.repositories)
        
        # Create new connector in database
        conn = get_db_connection()
        cursor = conn.cursor()
        
        connector_id = str(uuid.uuid4())
        cursor.execute(
            """
            INSERT INTO github_connectors
            (id, name, description, github_type, api_url, token, owner, repositories, 
            organization, default_branch, active, created_at, updated_at, repo_url, tech_stack)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, ?, ?)
            """,
            (
                connector_id, connector.name, connector.description, connector.github_type,
                connector.api_url, encrypted_token, connector.owner, repositories_json,
                connector.organization, connector.default_branch, connector.active, connector.repo_url,
                connector.tech_stack
            )
        )
        
        conn.commit()
        
        # Fetch the created connector
        cursor.execute("SELECT * FROM github_connectors WHERE id = ?", (connector_id,))
        created_connector = dict(cursor.fetchone())
        
        conn.close()
        
        # Don't send actual token, just whether it exists
        has_token = bool(created_connector.get('token'))
        created_connector.pop('token', None)
        
        # Parse repositories list from JSON
        if created_connector.get('repositories'):
            try:
                created_connector['repositories'] = json.loads(created_connector['repositories'])
            except:
                created_connector['repositories'] = []
        
        # Prepare connector data
        connector_data = {
            **created_connector,
            'has_token': has_token
        }
        
        # Clone the repository in the background
        background_tasks.add_task(clone_github_repository, connector_data)
        
        # Trigger lineage extraction in the background if active
        if connector.active:
            background_tasks.add_task(trigger_lineage_extraction, connector_id, connector_data)
        
        return connector_data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating GitHub connector: {str(e)}")

@router.get("/github_connectors/{connector_id}", response_model=GitHubConnectorResponse)
async def get_github_connector(connector_id: str):
    """
    Get a specific GitHub connector
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM github_connectors WHERE id = ?", (connector_id,))
        connector = cursor.fetchone()
        
        if not connector:
            raise HTTPException(status_code=404, detail=f"GitHub connector with ID {connector_id} not found")
        
        connector = dict(connector)
        
        # Don't send actual token, just whether it exists
        has_token = bool(connector.get('token'))
        connector.pop('token', None)
        
        # Parse repositories list from JSON
        if connector.get('repositories'):
            try:
                connector['repositories'] = json.loads(connector['repositories'])
            except:
                connector['repositories'] = []
        
        conn.close()
        
        return {
            **connector,
            'has_token': has_token
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting GitHub connector: {str(e)}")

@router.put("/github_connectors/{connector_id}", response_model=GitHubConnectorResponse)
async def update_github_connector(connector_id: str, connector: GitHubConnectorUpdate, background_tasks: BackgroundTasks):
    """
    Update a GitHub connector
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if connector exists
        cursor.execute("SELECT * FROM github_connectors WHERE id = ?", (connector_id,))
        existing_connector = cursor.fetchone()
        
        if not existing_connector:
            conn.close()
            raise HTTPException(status_code=404, detail=f"GitHub connector with ID {connector_id} not found")
        
        # Handle token update
        token_update = None
        if connector.token:
            # Validate GitHub connection before saving
            test_data = GitHubConnectorCreate(
                name=existing_connector['name'],
                github_type=existing_connector['github_type'],
                token=connector.token,
                api_url=connector.api_url if connector.api_url is not None else existing_connector['api_url'],
                owner=connector.owner if connector.owner is not None else existing_connector['owner'],
                repositories=connector.repositories if connector.repositories is not None else json.loads(existing_connector['repositories']) if existing_connector['repositories'] else None,
                organization=connector.organization if connector.organization is not None else existing_connector['organization'],
                default_branch=connector.default_branch if connector.default_branch is not None else existing_connector['default_branch'],
                active=connector.active if connector.active is not None else existing_connector['active'],
                repo_url=connector.repo_url if connector.repo_url is not None else existing_connector['repo_url']
            )
            
            test_result = await test_github_connection(test_data)
            if not test_result.success:
                conn.close()
                raise HTTPException(status_code=400, detail=f"GitHub connection failed: {test_result.message}")
            
            # Encrypt the token
            token_update = encrypt_token(connector.token)
            
        # Handle repositories update
        repositories_json = None
        if connector.repositories is not None:
            repositories_json = json.dumps(connector.repositories)
        
        # Build update query dynamically
        update_fields = []
        params = []
        
        if connector.name is not None:
            update_fields.append("name = ?")
            params.append(connector.name)
        
        if connector.description is not None:
            update_fields.append("description = ?")
            params.append(connector.description)
        
        if connector.github_type is not None:
            update_fields.append("github_type = ?")
            params.append(connector.github_type)
        
        if connector.api_url is not None:
            update_fields.append("api_url = ?")
            params.append(connector.api_url)
        
        if token_update is not None:
            update_fields.append("token = ?")
            params.append(token_update)
        
        if connector.owner is not None:
            update_fields.append("owner = ?")
            params.append(connector.owner)
        
        if repositories_json is not None:
            update_fields.append("repositories = ?")
            params.append(repositories_json)
        
        if connector.organization is not None:
            update_fields.append("organization = ?")
            params.append(connector.organization)
        
        if connector.default_branch is not None:
            update_fields.append("default_branch = ?")
            params.append(connector.default_branch)
        
        if connector.active is not None:
            update_fields.append("active = ?")
            params.append(connector.active)
        
        if connector.repo_url is not None:
            update_fields.append("repo_url = ?")
            params.append(connector.repo_url)
            
        if connector.tech_stack is not None:
            update_fields.append("tech_stack = ?")
            params.append(connector.tech_stack)
        
        update_fields.append("updated_at = CURRENT_TIMESTAMP")
        
        # If no updates, return the existing connector
        if not update_fields:
            has_token = bool(existing_connector.get('token'))
            existing_connector.pop('token', None)
            
            # Parse repositories list from JSON
            if existing_connector.get('repositories'):
                try:
                    existing_connector['repositories'] = json.loads(existing_connector['repositories'])
                except:
                    existing_connector['repositories'] = []
            
            return {
                **existing_connector,
                'has_token': has_token
            }
        
        # Update the connector
        query = f"UPDATE github_connectors SET {', '.join(update_fields)} WHERE id = ?"
        params.append(connector_id)
        
        cursor.execute(query, params)
        conn.commit()
        
        # Fetch the updated connector
        cursor.execute("SELECT * FROM github_connectors WHERE id = ?", (connector_id,))
        updated_connector = dict(cursor.fetchone())
        
        conn.close()
        
        # Don't send actual token, just whether it exists
        has_token = bool(updated_connector.get('token'))
        updated_connector.pop('token', None)
        
        # Parse repositories list from JSON
        if updated_connector.get('repositories'):
            try:
                updated_connector['repositories'] = json.loads(updated_connector['repositories'])
            except:
                updated_connector['repositories'] = []
        
        # Prepare response
        connector_data = {
            **updated_connector,
            'has_token': has_token
        }
        
        return connector_data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating GitHub connector: {str(e)}")

@router.delete("/github_connectors/{connector_id}")
async def delete_github_connector(connector_id: str):
    """
    Delete a GitHub connector
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if connector exists
        cursor.execute("SELECT id FROM github_connectors WHERE id = ?", (connector_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail=f"GitHub connector with ID {connector_id} not found")
        
        # Delete the connector
        cursor.execute("DELETE FROM github_connectors WHERE id = ?", (connector_id,))
        conn.commit()
        conn.close()
        
        return {"message": f"GitHub connector with ID {connector_id} deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting GitHub connector: {str(e)}")

@router.post("/github_connectors/test", response_model=TestConnectionResponse)
async def test_connection(connector: GitHubConnectorCreate):
    """
    Test GitHub connection
    """
    return await test_github_connection(connector)

async def test_github_connection(connector: GitHubConnectorCreate) -> TestConnectionResponse:
    """
    Test GitHub connection helper function
    """
    try:
        # Log request details for debugging (excluding token for security)
        sanitized_connector = connector.dict()
        sanitized_connector['token'] = '***REDACTED***' if sanitized_connector.get('token') else None
        print(f"Testing GitHub connection with: {sanitized_connector}")
        
        # Extract owner and repository from repo_url if provided
        if connector.github_type == 'public' and connector.repo_url:
            try:
                parsed_url = urlparse(connector.repo_url)
                if parsed_url.netloc == 'github.com':
                    path_parts = parsed_url.path.strip('/').split('/')
                    if len(path_parts) >= 2:
                        # Set owner from URL if not already provided
                        if not connector.owner:
                            connector.owner = path_parts[0]
                        
                        # Set repositories from URL if not already provided
                        repo_name = path_parts[1]
                        if repo_name.endswith('.git'):
                            repo_name = repo_name[:-4]  # Remove .git suffix
                            
                        if not connector.repositories:
                            connector.repositories = [repo_name]
            except Exception as e:
                # Log but continue with the test
                print(f"Error parsing repository URL: {str(e)}")
                
        # Determine base URL based on GitHub type
        # Normalize and validate API URL for enterprise
        if connector.github_type == 'enterprise':
            try:
                base_url = normalize_enterprise_api_url(connector.api_url)
            except ValueError as url_err:
                return TestConnectionResponse(
                    success=False,
                    message=f"Invalid Enterprise GitHub API URL: {url_err}",
                    details=None
                )
        else:
            base_url = 'https://api.github.com'
        
        # Setup headers
        headers = {
            'Authorization': f'token {connector.token}',
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'DataArchitect-App'
        }
        
        # Log the API endpoint and headers (excluding Auth token)
        print(f"Making GitHub API request to: {base_url}/user")
        sanitized_headers = headers.copy()
        sanitized_headers['Authorization'] = 'token ***REDACTED***'
        print(f"Headers: {sanitized_headers}")
        
        # Try to get user info as a basic authentication test
        user_url = f"{base_url}/user"
        response = requests.get(user_url, headers=headers)
        
        # Log response status and beginning of response body
        print(f"GitHub API response status: {response.status_code}")
        print(f"GitHub API response body (truncated): {response.text[:100] if response.text else 'Empty response'}")
        
        if response.status_code != 200:
            return TestConnectionResponse(
                success=False,
                message=f"Failed to authenticate with GitHub: {response.status_code} - {response.text}",
                details=None
            )
        
        user_data = response.json()
        
        # Get repositories or organizations based on provided details
        repo_details = None
        
        # If organization is provided, check if it exists
        if connector.organization:
            org_url = f"{base_url}/orgs/{connector.organization}"
            org_response = requests.get(org_url, headers=headers)
            
            if org_response.status_code != 200:
                return TestConnectionResponse(
                    success=False,
                    message=f"Organization '{connector.organization}' not found or not accessible.",
                    details=None
                )
            
            # Get organization's repositories
            repos_url = f"{base_url}/orgs/{connector.organization}/repos"
            repos_response = requests.get(repos_url, headers=headers)
            
            if repos_response.status_code == 200:
                repo_details = {
                    "type": "organization",
                    "name": connector.organization,
                    "repositories": [repo["name"] for repo in repos_response.json()]
                }
        
        # If owner is provided, check repositories
        elif connector.owner:
            repos_url = f"{base_url}/users/{connector.owner}/repos"
            repos_response = requests.get(repos_url, headers=headers)
            
            if repos_response.status_code == 200:
                repo_details = {
                    "type": "user",
                    "name": connector.owner,
                    "repositories": [repo["name"] for repo in repos_response.json()]
                }
        
        # If specific repositories are provided, check each one
        elif connector.repositories:
            valid_repos = []
            invalid_repos = []
            
            for repo in connector.repositories:
                # Extract owner and repo name
                if '/' in repo:
                    owner, repo_name = repo.split('/', 1)
                else:
                    owner = user_data["login"]  # Default to authenticated user
                    repo_name = repo
                
                repo_url = f"{base_url}/repos/{owner}/{repo_name}"
                repo_response = requests.get(repo_url, headers=headers)
                
                if repo_response.status_code == 200:
                    valid_repos.append(repo)
                else:
                    invalid_repos.append(repo)
            
            if invalid_repos:
                return TestConnectionResponse(
                    success=False,
                    message=f"Some repositories were not found or not accessible: {', '.join(invalid_repos)}",
                    details={
                        "valid_repositories": valid_repos,
                        "invalid_repositories": invalid_repos
                    }
                )
            
            repo_details = {
                "type": "specific_repos",
                "repositories": valid_repos
            }
        
        # If no specific organization, owner, or repositories provided, list authenticated user's repos
        if not repo_details:
            repos_url = f"{base_url}/user/repos"
            repos_response = requests.get(repos_url, headers=headers)
            
            if repos_response.status_code == 200:
                repo_details = {
                    "type": "authenticated_user",
                    "name": user_data["login"],
                    "repositories": [repo["name"] for repo in repos_response.json()]
                }
        
        return TestConnectionResponse(
            success=True,
            message="Successfully connected to GitHub",
            details={
                "user": {
                    "login": user_data["login"],
                    "name": user_data.get("name"),
                    "email": user_data.get("email")
                },
                "repositories": repo_details
            }
        )
    except Exception as e:
        return TestConnectionResponse(
            success=False,
            message=f"Error testing GitHub connection: {str(e)}",
            details=None
        ) 