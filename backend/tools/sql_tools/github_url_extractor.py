"""
GitHub URL Extractor

This module provides functionality to extract and standardize GitHub URLs,
including handling both public GitHub and enterprise GitHub custom domains.
"""

import re
from typing import Dict, List, Any, Optional
from urllib.parse import urlparse


class GitHubURLExtractor:
    """
    Class for extracting GitHub URL information and generating standardized URLs.
    """
    
    def __init__(self, github_url: str = ""):
        """Initialize GitHub URL extractor.

        Args:
            github_url: GitHub URL
        """
        self.github_url = self._ensure_clean_github_url(github_url) if github_url else ""

    @staticmethod
    def _ensure_clean_github_url(github_url: str) -> str:
        """Ensure that the GitHub URL is clean.

        Args:
            github_url: GitHub URL

        Returns:
            Clean GitHub URL
        """
        if not github_url:
            return github_url

        # Remove trailing .git suffix
        if github_url.endswith(".git"):
            github_url = github_url[:-4]

        # Remove .git from the middle of URLs
        github_url = re.sub(r'(https://[^/]+/[^/]+/[^/]+)\.git(/blob/|/tree/)', r'\1\2', github_url)
        github_url = re.sub(r'(https://[^/]+/[^/]+/[^/]+)\.git(/.*)', r'\1\2', github_url)

        return github_url
    
    @classmethod
    def extract_github_info(cls, github_url: str) -> Dict[str, str]:
        """Extract GitHub info.

        Args:
            github_url: GitHub URL

        Returns:
            GitHub info
        """
        if not github_url:
            return {}
            
        try:
            # Clean the URL first
            github_url = cls._ensure_clean_github_url(github_url)
            
            # Create an instance and extract the information
            extractor = cls(github_url)
            result = extractor.extract()
            
            # Ensure we return a dictionary even if extract fails
            if not isinstance(result, dict):
                return {}
                
            return result
        except Exception:
            # Return empty dict on any error
            return {}
    
    @staticmethod
    def format_github_url(owner: str, repo: str, branch: str = "main", path: str = "") -> str:
        """
        Format a GitHub URL from its components.
        
        Args:
            owner: Repository owner/organization
            repo: Repository name
            branch: Branch name (default: main)
            path: File path within the repository
            
        Returns:
            Formatted GitHub URL
        """
        # Ensure repo doesn't have .git suffix
        if repo.endswith(".git"):
            repo = repo[:-4]
        
        # Build the basic URL
        url = f"https://github.com/{owner}/{repo}"
        
        # Add branch and path if available
        if branch:
            url += f"/blob/{branch}"
            if path:
                url += f"/{path}"
        
        return url
    
    @staticmethod
    def _get_raw_content_url(github_url: str) -> str:
        """
        Convert a GitHub URL to its raw content URL.
        
        Args:
            github_url: GitHub URL
            
        Returns:
            Raw content URL
        """
        if not github_url:
            return ""
        
        # Clean the URL first
        github_url = GitHubURLExtractor._ensure_clean_github_url(github_url)
        
        # Replace github.com with raw.githubusercontent.com
        # and replace /blob/ with /
        if "github.com" in github_url and "/blob/" in github_url:
            return github_url.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")
        
        return github_url
    
    @staticmethod
    def generate_urls_by_table(dependencies: List[Dict[str, Any]]) -> Dict[str, List[str]]:
        """
        Generate a mapping of tables to their GitHub URLs
        
        Args:
            dependencies: List of dependencies with file_details
            
        Returns:
            Dict mapping table names to lists of GitHub URLs
        """
        urls_by_table = {}
        
        # Process all dependencies
        for dep in dependencies:
            source = dep.get("source", "")
            target = dep.get("target", "")
            
            # Add source table
            if source and source not in urls_by_table:
                urls_by_table[source] = []
                
            # Add target table
            if target and target not in urls_by_table:
                urls_by_table[target] = []
                
            # Add URLs for this dependency
            file_details = dep.get("file_details", [])
            
            # Handle the case where file_details might be a string instead of a list
            if isinstance(file_details, str):
                # Skip this dependency if file_details is a string
                continue
                
            for file_detail in file_details:
                # Skip if file_detail is not a dictionary
                if not isinstance(file_detail, dict):
                    continue
                    
                # Try to find a suitable URL from the file detail
                url = ""
                
                # Case 1: Ready-made GitHub URL
                if file_detail.get("github_url"):
                    url = GitHubURLExtractor._ensure_clean_github_url(file_detail.get("github_url", ""))
                
                # Case 2: URL under a different key
                elif file_detail.get("url"):
                    url = GitHubURLExtractor._ensure_clean_github_url(file_detail.get("url", ""))
                
                # Case 3: Try to construct from repo components
                elif all([
                    file_detail.get("repo_owner"),
                    file_detail.get("repo_name"),
                    file_detail.get("file_path")
                ]):
                    # Build base repo URL
                    owner = file_detail.get("repo_owner", "")
                    repo = file_detail.get("repo_name", "")
                    branch = file_detail.get("repo_branch", "main")
                    file_path = file_detail.get("file_path", "")
                    
                    # Construct base repo URL
                    repo_url = f"https://github.com/{owner}/{repo}"
                    
                    # Construct the full file URL
                    url = GitHubURLExtractor.format_github_file_url(repo_url, file_path, branch)
                
                if url:
                    # Add URL to source table
                    if source and url not in urls_by_table[source]:
                        urls_by_table[source].append(url)
                    
                    # Add URL to target table
                    if target and url not in urls_by_table[target]:
                        urls_by_table[target].append(url)
        
        return urls_by_table 

    def extract(self) -> Dict[str, str]:
        """Extract components from a GitHub URL.
        
        Returns:
            Dictionary containing components of GitHub URL:
            - owner: Repository owner/organization
            - repo: Repository name
            - branch: Branch name (default: main)
            - path: File path within repository
            - raw_url: URL to raw content (for files)
        """
        if not self.github_url:
            return {}
            
        try:
            # Parse the URL
            parsed_url = urlparse(self.github_url)
            
            # Get the path components
            path_parts = parsed_url.path.strip('/').split('/')
            
            if len(path_parts) < 2:
                # Not enough components to be a valid GitHub repo URL
                return {}
                
            # Extract basic components
            owner = path_parts[0]
            repo = path_parts[1]
            
            # Remove any .git suffix from repo name
            if repo.endswith(".git"):
                repo = repo[:-4]
            
            # Initialize with defaults
            result = {
                "owner": owner,
                "repo": repo,
                "branch": "main",
                "path": "",
                "raw_url": ""
            }
            
            # Check if we have a branch and path
            if len(path_parts) > 3 and path_parts[2] in ["blob", "tree"]:
                # Format: github.com/owner/repo/blob/branch/path
                result["branch"] = path_parts[3]
                if len(path_parts) > 4:
                    result["path"] = '/'.join(path_parts[4:])
                    
                    # Generate raw content URL if it's a blob (file)
                    if path_parts[2] == "blob":
                        # For GitHub.com use raw.githubusercontent.com
                        if parsed_url.netloc == "github.com":
                            raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{result['branch']}/{result['path']}"
                        # For enterprise GitHub instances
                        else:
                            raw_url = f"https://{parsed_url.netloc}/raw/{owner}/{repo}/{result['branch']}/{result['path']}"
                        result["raw_url"] = raw_url
            
            # Add the original domain to the result for reference
            result["domain"] = parsed_url.netloc
            
            # Reconstruct clean URLs to ensure consistency
            result["repo_url"] = f"https://{parsed_url.netloc}/{owner}/{repo}"
            
            if result["path"]:
                # Construct proper file URL
                result["file_url"] = f"{result['repo_url']}/blob/{result['branch']}/{result['path']}"
                    
            return result
            
        except Exception:
            # Return empty dict on any parsing error
            return {} 

    @staticmethod
    def format_github_file_url(repo_url: str, file_path: str, branch: str = "main") -> str:
        """
        Formats a GitHub file URL by correctly combining repository URL and file path.
        
        Args:
            repo_url: GitHub repository URL
            file_path: Path to the file within the repository
            branch: Branch name (default: main)
            
        Returns:
            Properly formatted GitHub file URL
        """
        # Clean the repo URL first (remove any .git suffix)
        repo_url = GitHubURLExtractor._ensure_clean_github_url(repo_url)
        
        # Remove any trailing slashes
        repo_url = repo_url.rstrip('/')
        file_path = file_path.lstrip('/')
        
        # Format the complete URL with the correct path structure
        return f"{repo_url}/blob/{branch}/{file_path}" 