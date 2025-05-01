"""
API for accessing local GitHub repository files.
This allows frontend to access cloned repositories directly from the backend storage.
"""
import os
import json
from typing import Dict, List, Optional, Any
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
import pathlib
import glob

# Router for GitHub local repo API
router = APIRouter(prefix="/api/github/local", tags=["github"])

# Path to cloned repositories
REPOS_DIR = os.path.join('storage', 'repos')

class FileInfo(BaseModel):
    """File information model for file tree"""
    name: str
    path: str
    type: str
    size: Optional[int] = None
    sha: Optional[str] = None

class FileTreeResponse(BaseModel):
    """Response model for file tree"""
    files: List[FileInfo]

class FileContentResponse(BaseModel):
    """Response model for file content"""
    content: str
    encoding: str = "utf-8"
    size: int
    path: str
    name: str

@router.get("/repos", response_model=List[Dict[str, str]])
async def list_local_repos():
    """List all locally cloned repositories"""
    repos = []
    try:
        # Check if the repos directory exists
        if not os.path.exists(REPOS_DIR):
            return []
        
        # List all directories in the repos directory (each is a cloned repo)
        for repo_dir in glob.glob(os.path.join(REPOS_DIR, "*")):
            if os.path.isdir(repo_dir):
                # Extract owner, repo, and branch from directory name
                # Format: owner_repo_id_branch
                dir_name = os.path.basename(repo_dir)
                parts = dir_name.split('_')
                
                if len(parts) >= 4:
                    owner = parts[0]
                    repo = parts[1]
                    # Last part is always the branch
                    branch = parts[-1] 
                    
                    # Build repo info
                    repo_info = {
                        "owner": owner,
                        "repo": repo,
                        "full_name": f"{owner}/{repo}",
                        "branch": branch,
                        "local_path": repo_dir,
                        "dir_name": dir_name
                    }
                    repos.append(repo_info)
        
        return repos
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing repositories: {str(e)}")

@router.get("/files", response_model=FileTreeResponse)
async def get_files(
    repo: str = Query(..., description="Repository name (e.g., 'owner/repo')"),
    path: str = Query("", description="Path within repository")
):
    """
    Get files from a local repository at a specific path.
    
    Args:
        repo: Repository name in format 'owner/repo'
        path: Path within repository
    """
    try:
        # Clean path parameter
        clean_path = path.lstrip('/').rstrip('/')
        print(f"[DEBUG] Incoming repo param: {repo}")
        print(f"[DEBUG] Incoming path param: {path}")
        
        # Parse owner and repo
        if "/" in repo:
            owner, repo_name = repo.split("/", 1)
        else:
            raise HTTPException(status_code=400, detail="Repository must be in format 'owner/repo'")
        glob_pattern = os.path.join(REPOS_DIR, f"{owner}_{repo_name}_*")
        print(f"[DEBUG] Computed glob pattern: {glob_pattern}")
        
        # Find matching repo directory
        repo_dirs = glob.glob(glob_pattern)
        print(f"[DEBUG] glob.glob result: {repo_dirs}")
        
        if not repo_dirs:
            print(f"[DEBUG] No matching repo dirs found for {repo}")
            raise HTTPException(status_code=404, detail=f"Repository {owner}/{repo_name} not found locally")
        
        # Use the first match (we should ideally match by branch too)
        repo_dir = repo_dirs[0]
        print(f"[DEBUG] Using repo_dir: {repo_dir}")
        
        # Build the full path to the directory
        full_path = os.path.join(repo_dir, clean_path) if clean_path else repo_dir
        print(f"[DEBUG] Resolved full_path: {full_path}")
        
        if not os.path.exists(full_path):
            print(f"[DEBUG] Path does not exist: {full_path}")
            raise HTTPException(status_code=404, detail=f"Path {clean_path} not found in repository")
        
        files = []
        
        # If it's a directory, list contents
        if os.path.isdir(full_path):
            for item in os.listdir(full_path):
                item_path = os.path.join(full_path, item)
                rel_path = os.path.join(clean_path, item) if clean_path else item
                
                # Create file info
                file_info = FileInfo(
                    name=item,
                    path=rel_path,
                    type="dir" if os.path.isdir(item_path) else "file",
                    size=os.path.getsize(item_path) if os.path.isfile(item_path) else None
                )
                files.append(file_info)
                
        # If it's a file, return file info
        elif os.path.isfile(full_path):
            # Extract file name and directory
            dir_name, file_name = os.path.split(clean_path)
            
            file_info = FileInfo(
                name=file_name,
                path=clean_path,
                type="file",
                size=os.path.getsize(full_path)
            )
            files.append(file_info)
        
        return FileTreeResponse(files=files)
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching files: {str(e)}")

@router.get("/content", response_model=FileContentResponse)
async def get_file_content(
    repo: str = Query(..., description="Repository name (e.g., 'owner/repo')"),
    path: str = Query(..., description="Path to file within repository")
):
    """
    Get content of a file from a local repository.
    
    Args:
        repo: Repository name in format 'owner/repo'
        path: Path to file within repository
    """
    try:
        # Clean path parameter
        clean_path = path.lstrip('/')
        
        # Parse owner and repo
        if "/" in repo:
            owner, repo_name = repo.split("/", 1)
        else:
            raise HTTPException(status_code=400, detail="Repository must be in format 'owner/repo'")
        
        # Find matching repo directory
        repo_dirs = glob.glob(os.path.join(REPOS_DIR, f"{owner}_{repo_name}_*"))
        
        if not repo_dirs:
            raise HTTPException(status_code=404, detail=f"Repository {owner}/{repo_name} not found locally")
        
        # Use the first match
        repo_dir = repo_dirs[0]
        
        # Build the full path to the file
        full_path = os.path.join(repo_dir, clean_path)
        
        if not os.path.exists(full_path) or not os.path.isfile(full_path):
            raise HTTPException(status_code=404, detail=f"File {clean_path} not found in repository")
        
        # Read file content
        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
            # Get file size
            size = os.path.getsize(full_path)
            
            # Get file name
            file_name = os.path.basename(full_path)
            
            return FileContentResponse(
                content=content,
                size=size,
                path=clean_path,
                name=file_name
            )
        except UnicodeDecodeError:
            # For binary files, just report that it's not displayable
            return FileContentResponse(
                content="[Binary file not displayable in text format]",
                size=os.path.getsize(full_path),
                path=clean_path,
                name=os.path.basename(full_path)
            )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching file content: {str(e)}")
