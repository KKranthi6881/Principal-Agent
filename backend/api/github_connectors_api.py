"""
API for GitHub connector configurations
"""
import os
import uuid
import json
from typing import Dict, List, Optional, Any
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
import sqlite3
import requests
from cryptography.fernet import Fernet
import base64
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from urllib.parse import urlparse

# Router for GitHub connectors API
router = APIRouter(prefix="/api/settings", tags=["github"])

# Path to metadata database
METADATA_DB = os.path.join('database', 'metadata.db')

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
def get_db_connection():
    """Get a connection to the metadata database"""
    conn = sqlite3.connect(METADATA_DB)
    conn.row_factory = sqlite3.Row
    return conn

def encrypt_token(token: str) -> str:
    """Encrypt a GitHub token"""
    if not token:
        return None
    cipher = get_cipher()
    return cipher.encrypt(token.encode()).decode()

def decrypt_token(encrypted_token: str) -> str:
    """Decrypt a GitHub token"""
    if not encrypted_token:
        return None
    cipher = get_cipher()
    return cipher.decrypt(encrypted_token.encode()).decode()

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

class GitHubConnectorList(BaseModel):
    """GitHub connector list response"""
    connectors: List[GitHubConnectorResponse]

class TestConnectionResponse(BaseModel):
    """Test connection response model"""
    success: bool
    message: str
    details: Optional[Dict[str, Any]] = None

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
async def create_github_connector(connector: GitHubConnectorCreate):
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
            organization, default_branch, active, created_at, updated_at, repo_url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, ?)
            """,
            (
                connector_id, connector.name, connector.description, connector.github_type,
                connector.api_url, encrypted_token, connector.owner, repositories_json,
                connector.organization, connector.default_branch, connector.active, connector.repo_url
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
        
        return {
            **created_connector,
            'has_token': has_token
        }
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
async def update_github_connector(connector_id: str, connector: GitHubConnectorUpdate):
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
            raise HTTPException(status_code=404, detail=f"GitHub connector with ID {connector_id} not found")
        
        existing_connector = dict(existing_connector)
        
        # If token is being updated, encrypt it
        token_update = None
        if connector.token:
            # Test connection with new token before updating
            test_connector = GitHubConnectorCreate(
                name=connector.name or existing_connector['name'],
                github_type=connector.github_type or existing_connector['github_type'],
                api_url=connector.api_url or existing_connector['api_url'],
                token=connector.token,
                owner=connector.owner or existing_connector['owner'],
                organization=connector.organization or existing_connector['organization'],
                repositories=connector.repositories or (
                    json.loads(existing_connector['repositories']) 
                    if existing_connector.get('repositories') else None
                )
            )
            test_result = await test_github_connection(test_connector)
            if not test_result.success:
                raise HTTPException(status_code=400, detail=f"GitHub connection failed: {test_result.message}")
            
            token_update = encrypt_token(connector.token)
        
        # Convert repositories list to JSON if provided
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
        
        return {
            **updated_connector,
            'has_token': has_token
        }
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
        base_url = connector.api_url if connector.github_type == 'enterprise' else 'https://api.github.com'
        
        # Setup headers
        headers = {
            'Authorization': f'token {connector.token}',
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'DataArchitect-App'
        }
        
        # Try to get user info as a basic authentication test
        user_url = f"{base_url}/user"
        response = requests.get(user_url, headers=headers)
        
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