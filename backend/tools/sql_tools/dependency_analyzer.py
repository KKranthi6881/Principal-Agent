"""
SQL Dependency Analyzer Tool

This module coordinates the SQL dependency analysis process,
combining GitHub file search with SQL parsing to build 
comprehensive dependency graphs.
"""

import logging
import json
from typing import Dict, List, Any, Optional
import os
import networkx as nx
from pathlib import Path
import re
from urllib.parse import urlparse
import uuid

from .sql_dependency_analyzer import SQLDependencyAnalyzer
from .github_sql_finder import GitHubSQLFinder

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class SQLDependencyTool:
    """
    Main tool for analyzing SQL dependencies from GitHub repositories
    """
    
    def __init__(self, vector_store_path: str = None, github_wrapper = None):
        """
        Initialize the SQL Dependency Tool
        
        Args:
            vector_store_path: Path to the ChromaDB vector store
            github_wrapper: GitHub API wrapper instance (optional)
        """
        # If path is None, use default
        if vector_store_path is None:
            # Use the directory of this file to ensure we create in correct location
            current_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            vector_store_path = os.path.join(current_dir, "vector_store", "chromadb_github")
            
        logger.info(f"SQLDependencyTool initializing with vector_store_path: {vector_store_path}")
        
        # Initialize SQL finder with direct ChromaDB access and github wrapper if provided
        self.sql_finder = GitHubSQLFinder(vector_store_path, github_wrapper=github_wrapper)
        
        # Store the github wrapper
        self.github_wrapper = github_wrapper
        
        # Initialize dependency analyzer with default dialect
        self.dependency_analyzer = SQLDependencyAnalyzer(dialect="dbt")
        
        # Initialize the dependency graph
        self.dependency_graph = nx.DiGraph()
        
        # Cache for file content to avoid repeated processing
        self.file_cache = {}
        
    def initialize(self):
        """Initialize components and connections"""
        # Just call the GitHubSQLFinder initialize method
        success = self.sql_finder.initialize()
        if success:
            logger.info("SQL dependency tool initialized successfully")
        else:
            logger.error("Failed to initialize SQL dependency tool")
        return success
    
    def trace_table_dependencies(self, target_table: str, depth: int = 10, dialect: str = None) -> Dict[str, Any]:
        """
        Trace upstream dependencies for a target table
        
        Args:
            target_table: Target table name (e.g., 'schema.table_name' or just 'table_name')
            depth: Maximum depth to traverse
            dialect: SQL dialect to use for parsing
            
        Returns:
            Dict with dependency information
        """
        # Update dialect if specified
        if dialect:
            self.dependency_analyzer = SQLDependencyAnalyzer(dialect=dialect)
        
        # Step 1: Find all SQL files that reference this table
        sql_files = self.sql_finder.search_for_table(table_name=target_table)
        
        if not sql_files or (isinstance(sql_files, list) and len(sql_files) == 1 and "error" in sql_files[0]):
            return {
                "error": f"No SQL files found for table {target_table}",
                "target_table": target_table,
                "dependencies": []
            }
        
        # Log the search results to help with debugging
        logger.info(f"Found {len(sql_files)} SQL files for table {target_table}")
        
        # Ensure the SQL files have correct structure (content, path, etc.)
        validated_sql_files = []
        for file in sql_files:
            if isinstance(file, dict) and "content" in file and "path" in file:
                validated_sql_files.append(file)
            elif isinstance(file, dict):
                # Try to fix missing fields if possible
                fixed_file = file.copy()
                
                # Ensure 'path' exists
                if "path" not in fixed_file and "file_path" in fixed_file:
                    fixed_file["path"] = fixed_file["file_path"]
                
                # Ensure 'content' exists - even if empty
                if "content" not in fixed_file:
                    fixed_file["content"] = ""
                    logger.warning(f"SQL file missing content: {fixed_file.get('path', 'unknown')}")
                
                validated_sql_files.append(fixed_file)
        
        logger.info(f"Validated {len(validated_sql_files)} SQL files for dependency analysis")
        
        # Step 2: Build a dependency graph from these files
        self.dependency_graph = self.dependency_analyzer.build_dependency_graph(validated_sql_files)
        
        # Step 3: Find upstream dependencies
        upstream_info = self.dependency_analyzer.find_upstream_dependencies(
            target_table=target_table,
            max_depth=depth
        )
        
        # Ensure there are at least some dependencies discovered
        if not upstream_info.get("upstream_dependencies"):
            logger.info(f"No upstream dependencies found for {target_table}. Trying to extract from raw files.")
            
            # Manually extract dependencies from files
            upstream_info["upstream_dependencies"] = []
            for file in validated_sql_files:
                file_path = file.get("path", "")
                content = file.get("content", "")
                
                # Use the dependency analyzer to extract tables from this file
                analysis = self.dependency_analyzer.analyze_sql(content, target_table)
                
                # Add any found dependencies
                for dep in analysis.get("dependencies", []):
                    source = dep.get("source")
                    if source and source != target_table:
                        upstream_info["upstream_dependencies"].append({
                            "source": source,
                            "target": target_table,
                            "depth": 0,
                            "files": [file_path],
                            "columns": dep.get("columns", [])
                        })
        
        # Step 4: Enrich the dependency information with file details
        enriched_dependencies = []
        
        # Import GitHub URL extractor
        try:
            from .github_url_extractor import GitHubURLExtractor
            url_extractor_available = True
        except ImportError:
            url_extractor_available = False
        
        # Create a direct mapping of files for quick lookup
        file_info_map = {file.get("path", ""): file for file in validated_sql_files if file.get("path")}
        
        # Collect all used files to ensure we don't miss any
        all_files_used = set()
        for dep in upstream_info.get("upstream_dependencies", []):
            for file_path in dep.get("files", []):
                all_files_used.add(file_path)
                
        # Create a fallback dependency if none exist
        if not upstream_info.get("upstream_dependencies"):
            # Add at least one dependency entry with the files that mention this table
            fallback_dep = {
                "source": "unknown_source",
                "target": target_table,
                "depth": 0,
                "files": [file.get("path", "") for file in validated_sql_files if file.get("path")]
            }
            upstream_info["upstream_dependencies"] = [fallback_dep]
        
        for dep in upstream_info.get("upstream_dependencies", []):
            source_table = dep["source"]
            target = dep["target"]
            files = dep.get("files", [])
            
            # Enrich with file details from our vector store
            file_details = []
            for file_path in files:
                # Try from cache first
                if file_path in self.file_cache:
                    file_details.append(self.file_cache[file_path])
                    continue
                    
                # Next try the file_info_map
                if file_path in file_info_map:
                    file_info = file_info_map[file_path]
                    
                    # Create base file info
                    file_detail = self._create_file_detail(file_path, file_info.get("content"))
                    
                    # Cache and add
                    self.file_cache[file_path] = file_detail
                    file_details.append(file_detail)
                else:
                    # Last resort: search for the file
                    match_found = False
                    for file_info in validated_sql_files:
                        if file_info.get("path") == file_path:
                            file_detail = self._create_file_detail(file_path, file_info.get("content"))
                            self.file_cache[file_path] = file_detail
                            file_details.append(file_detail)
                            match_found = True
                            break
                    
                    # If still not found, create a minimal entry
                    if not match_found:
                        minimal_detail = {
                            "path": file_path,
                            "file_name": os.path.basename(file_path),
                            "dialect": "sql",  # Assume SQL
                        }
                        file_details.append(minimal_detail)
            
            # Add enriched file details
            dep["file_details"] = file_details
            
            # Find additional SQL files for this dependency pair
            additional_files = self._find_additional_files_for_dependency(source_table, target)
            if additional_files:
                for add_file in additional_files:
                    # Check if already included
                    if not any(f.get("path") == add_file.get("path") for f in file_details):
                        add_file_detail = self._create_file_detail(add_file.get("path", ""), add_file.get("content"))
                        add_file_detail["is_additional"] = True
                        file_details.append(add_file_detail)
                        
                        # Update the cache
                        if add_file.get("path"):
                            self.file_cache[add_file.get("path")] = add_file_detail
            
            # Ensure GitHub URLs are present in all file details
            for file_detail in file_details:
                self._ensure_github_url(file_detail)
            
            enriched_dependencies.append(dep)
        
        # Ensure any remaining files from sql_files that weren't captured are included
        remaining_files = []
        for file_info in validated_sql_files:
            file_path = file_info.get("path", "")
            if file_path and file_path not in all_files_used:
                file_detail = self._create_file_detail(file_path, file_info.get("content"))
                self._ensure_github_url(file_detail)
                remaining_files.append(file_detail)
                all_files_used.add(file_path)
        
        # If we have remaining files, create a special dependency entry
        if remaining_files:
            remaining_dep = {
                "source": "additional_sources",
                "target": target_table,
                "depth": 0,
                "files": [f.get("path", "") for f in remaining_files],
                "file_details": remaining_files
            }
            enriched_dependencies.append(remaining_dep)
        
        # Generate URLs by table
        if url_extractor_available:
            try:
                urls_by_table = GitHubURLExtractor.generate_urls_by_table(enriched_dependencies)
            except:
                urls_by_table = self._generate_urls_by_table(enriched_dependencies)
        else:
            urls_by_table = self._generate_urls_by_table(enriched_dependencies)
        
        # Get a list of unique GitHub repos
        github_repos = set()
        for dep in enriched_dependencies:
            for file in dep.get("file_details", []):
                repo = file.get("github_repo", "")
                if repo:
                    github_repos.add(repo)
        
        # Generate summary
        summary = {
            "target_table": target_table,
            "total_dependencies": len(enriched_dependencies),
            "unique_source_tables": len(set(dep["source"] for dep in enriched_dependencies)),
            "max_depth": max([dep["depth"] for dep in enriched_dependencies]) if enriched_dependencies else 0,
            "file_count": len(upstream_info.get("all_files", [])),
            "dialect": self.dependency_analyzer.dialect,
            "github_repos": list(github_repos),
            "urls_by_table": urls_by_table
        }
        
        upstream_info["summary"] = summary
        
        # Include all original SQL files for LLM context
        upstream_info["source_files"] = [{
            "path": file.get("path", ""),
            "url": file.get("url", ""),
            "github_repo": file.get("github_repo", ""),
            "dialect": file.get("dialect", "sql"),
            "content_summary": file.get("content", "")[:500] + "..." if len(file.get("content", "")) > 500 else file.get("content", "")
        } for file in validated_sql_files]
        
        return upstream_info
    
    def _create_file_detail(self, file_path: str, content: str) -> Dict[str, Any]:
        """
        Create a file detail dictionary for a file.
        
        Args:
            file_path: Path to the file
            content: Content of the file
            
        Returns:
            Dictionary with file details
        """
        file_detail = {
            "id": str(uuid.uuid4()),
            "name": Path(file_path).name,
            "path": file_path,
            "content": content,
            "source": "github",
            "size": len(content),
            "score": 0,
            "last_modified": None,
            "created_at": None,
            "dependencies": [],
            "dependency_types": []
        }
        
        # Ensure that github_url is added to the file detail if applicable
        return self._ensure_github_url(file_detail)
    
    def _ensure_github_url(self, file_detail: Dict[str, Any], github_url: Optional[str] = None) -> Dict[str, Any]:
        """
        Ensure that a file detail has a GitHub URL.
        
        Args:
            file_detail: File detail to ensure has a GitHub URL
            github_url: GitHub URL to use (optional)
        
        Returns:
            Updated file detail
        """
        # Make a copy of the file detail to avoid modifying the original
        file_detail = dict(file_detail)
        
        # If no github_url is provided, use the one from the file detail
        if not github_url and "github_url" in file_detail:
            github_url = file_detail.get("github_url", "")
        
        # If we have a GitHub URL, ensure it's clean
        if github_url:
            try:
                from .github_url_extractor import GitHubURLExtractor
                # Use the GitHubURLExtractor to clean the URL
                github_url = GitHubURLExtractor._ensure_clean_github_url(github_url)
                # Update the file detail with the clean GitHub URL
                file_detail["github_url"] = github_url
                
                # Use GitHubURLExtractor to extract repository information
                repo_info = GitHubURLExtractor.extract_github_info(github_url)
                
                # Update file detail with repository information
                if repo_info:
                    file_detail["repo_owner"] = repo_info.get("owner", "")
                    file_detail["repo_name"] = repo_info.get("repo", "")
                    file_detail["repo_branch"] = repo_info.get("branch", "")
                    file_detail["file_path"] = repo_info.get("path", "")
                    
                    # If raw_url is available in repo_info, use it
                    if repo_info.get("raw_url"):
                        file_detail["raw_content_url"] = repo_info["raw_url"]
                    # Otherwise generate raw content URL if all necessary details are available
                    elif all([file_detail.get("repo_owner"), file_detail.get("repo_name"), 
                            file_detail.get("repo_branch"), file_detail.get("file_path")]):
                        raw_url_template = "https://raw.githubusercontent.com/{owner}/{name}/{branch}/{path}"
                        file_detail["raw_content_url"] = raw_url_template.format(
                            owner=file_detail["repo_owner"],
                            name=file_detail["repo_name"],
                            branch=file_detail["repo_branch"],
                            path=file_detail["file_path"]
                        )
            except (ImportError, Exception) as e:
                # Fallback URL cleaning if GitHubURLExtractor fails
                if github_url.endswith(".git"):
                    github_url = github_url[:-4]
                # Handle .git in the middle of URLs
                import re
                github_url = re.sub(r'(https://[^/]+/[^/]+/[^/]+)\.git(/.*)', r'\1\2', github_url)
                # Update the file detail with the clean GitHub URL
                file_detail["github_url"] = github_url
        
        return file_detail
    
    def _get_raw_content_url(self, github_url: str) -> str:
        """
        Convert a GitHub URL to a raw content URL.
        
        Args:
            github_url: URL to a GitHub file, e.g., https://github.com/owner/repo/blob/branch/path/to/file
            
        Returns:
            Raw content URL for accessing the file content directly
        """
        try:
            # Try to use GitHubURLExtractor for more robust handling
            from .github_url_extractor import GitHubURLExtractor
            github_info = GitHubURLExtractor.extract_github_info(github_url)
            if github_info.get("raw_url"):
                return github_info["raw_url"]
            
            # Fall back to direct conversion if raw_url wasn't generated
            parsed = urlparse(github_url)
            if parsed.netloc == "github.com" and "/blob/" in github_url:
                return github_url.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")
            elif "github" in parsed.netloc and "/blob/" in github_url:
                # Enterprise GitHub
                hostname = parsed.netloc
                path = parsed.path.replace("/blob/", "/")
                path_parts = path.split("/")
                if len(path_parts) >= 3:
                    owner = path_parts[1]
                    repo = path_parts[2]
                    rest_path = "/".join(path_parts[3:])
                    return f"https://{hostname}/raw/{owner}/{repo}/{rest_path}"
                
            return github_url
            
        except Exception:
            # Simple fallback conversion
            if "github.com" in github_url and "/blob/" in github_url:
                return github_url.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")
            return github_url
    
    def _find_additional_files_for_dependency(self, source_table: str, target_table: str) -> List[Dict[str, Any]]:
        """
        Find additional SQL files that contain both source and target tables
        
        Args:
            source_table: Source table name
            target_table: Target table name
            
        Returns:
            List of additional SQL files
        """
        # Query specifically for files that mention both tables
        query = f"SQL {source_table} {target_table}"
        try:
            results = self.sql_finder.search_sql_files(query=query, limit=5)
            if results and not isinstance(results, list) or (len(results) > 0 and "error" not in results[0]):
                return results
        except Exception:
            pass
        return []
    
    def _generate_urls_by_table(self, dependencies: List[Dict[str, Any]]) -> Dict[str, List[str]]:
        """
        Generate a mapping of tables to their GitHub URLs
        
        Args:
            dependencies: List of dependencies
            
        Returns:
            Dict mapping table names to lists of GitHub URLs
        """
        urls_by_table = {}
        
        # Try to import GitHubURLExtractor for URL cleaning
        try:
            from .github_url_extractor import GitHubURLExtractor
            url_extractor_available = True
        except ImportError:
            url_extractor_available = False
        
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
            for file_detail in dep.get("file_details", []):
                url = file_detail.get("github_url", "")
                if url:
                    # Clean URL to ensure consistency
                    if url_extractor_available:
                        # Use the GitHubURLExtractor to clean the URL
                        url = GitHubURLExtractor._ensure_clean_github_url(url)
                    else:
                        # Fallback URL cleaning
                        if url.endswith(".git"):
                            url = url[:-4]
                        # Handle .git in the middle of URLs
                        import re
                        url = re.sub(r'(https://[^/]+/[^/]+/[^/]+)\.git(/.*)', r'\1\2', url)
                    
                    # Add URL to source table
                    if source and url not in urls_by_table[source]:
                        urls_by_table[source].append(url)
                    
                    # Add URL to target table
                    if target and url not in urls_by_table[target]:
                        urls_by_table[target].append(url)
        
        return urls_by_table
    
    def get_column_lineage(self, target_table: str, column_name: str, depth: int = 10) -> Dict[str, Any]:
        """
        Get column-level lineage for a specific column
        
        Args:
            target_table: Target table name
            column_name: Target column name
            depth: Maximum depth to traverse
            
        Returns:
            Dict with column lineage information
        """
        # Find all SQL files that reference this column in this table
        sql_files = self.sql_finder.search_for_column(
            table_name=target_table,
            column_name=column_name
        )
        
        if not sql_files or "error" in sql_files[0]:
            return {
                "error": f"No SQL files found for column {column_name} in table {target_table}",
                "target_table": target_table,
                "target_column": column_name,
                "lineage": []
            }
        
        # Create a map for quick lookup
        file_info_map = {file.get("path", ""): file for file in sql_files if file.get("path")}
        
        # Build a dependency graph from these files
        self.dependency_graph = self.dependency_analyzer.build_dependency_graph(sql_files)
        
        # Find upstream dependencies
        upstream_info = self.dependency_analyzer.find_upstream_dependencies(
            target_table=target_table,
            max_depth=depth
        )
        
        # Import GitHub URL extractor
        try:
            from .github_url_extractor import GitHubURLExtractor
            url_extractor_available = True
        except ImportError:
            url_extractor_available = False
        
        # Create a fallback dependency if none exist
        if not upstream_info.get("upstream_dependencies"):
            # Add at least one dependency entry with the files that mention this column
            fallback_dep = {
                "source": "unknown_source",
                "target": target_table,
                "depth": 0,
                "files": [file.get("path", "") for file in sql_files if file.get("path")],
                "columns": [column_name]
            }
            upstream_info["upstream_dependencies"] = [fallback_dep]
        
        # Filter to only include dependencies that involve this column
        column_lineage = []
        for dep in upstream_info.get("upstream_dependencies", []):
            columns = dep.get("columns", [])
            if column_name in columns:
                # Enrich with file details
                file_paths = dep.get("files", [])
                file_details = []
                
                for file_path in file_paths:
                    # Try cached file info first
                    if file_path in self.file_cache:
                        file_details.append(self.file_cache[file_path])
                        continue
                        
                    # Use file_info_map next
                    if file_path in file_info_map:
                        file_info = file_info_map[file_path]
                        
                        # Create file detail
                        file_detail = self._create_file_detail(file_path, file_info.get("content"))
                        
                        # Add to cache and result
                        self.file_cache[file_path] = file_detail
                        file_details.append(file_detail)
                    else:
                        # Last resort: search for file
                        match_found = False
                        for file_info in sql_files:
                            if file_info.get("path") == file_path:
                                file_detail = self._create_file_detail(file_path, file_info.get("content"))
                                self.file_cache[file_path] = file_detail
                                file_details.append(file_detail)
                                match_found = True
                                break
                        
                        # If still not found, create minimal entry
                        if not match_found:
                            minimal_detail = {
                                "path": file_path,
                                "file_name": os.path.basename(file_path),
                                "dialect": "sql"  # Assume SQL
                            }
                            file_details.append(minimal_detail)
                
                # Add file details to dependency
                dep["file_details"] = file_details
                
                # Ensure GitHub URLs are present in all file details
                for file_detail in file_details:
                    self._ensure_github_url(file_detail)
                
                # Try to extract SQL statements that reference this column
                for file_detail in file_details:
                    if "content" in file_detail:
                        code_snippet = self._extract_column_reference_snippet(
                            file_detail["content"],
                            column_name,
                            target_table
                        )
                        if code_snippet:
                            file_detail["code_snippet"] = code_snippet
                
                column_lineage.append(dep)
        
        # If no lineage found, create a fallback entry
        if not column_lineage and sql_files:
            file_details = []
            for file_info in sql_files[:5]:  # Include up to 5 files
                file_path = file_info.get("path", "")
                if file_path:
                    # Create file detail
                    file_detail = self._create_file_detail(file_path, file_info.get("content"))
                    
                    # Ensure it has GitHub URL
                    self._ensure_github_url(file_detail)
                    
                    # Extract code snippet if content available
                    if "content" in file_info:
                        code_snippet = self._extract_column_reference_snippet(
                            file_info["content"],
                            column_name,
                            target_table
                        )
                        if code_snippet:
                            file_detail["code_snippet"] = code_snippet
                    
                    file_details.append(file_detail)
            
            # Create a fallback entry
            if file_details:
                fallback_dep = {
                    "source": "unknown_source",
                    "target": target_table,
                    "depth": 0,
                    "files": [f.get("path", "") for f in file_details],
                    "columns": [column_name],
                    "file_details": file_details
                }
                column_lineage = [fallback_dep]
        
        # Generate a comprehensive lineage map
        column_lineage_map = self._generate_column_lineage_map(target_table, column_name, column_lineage)
        
        # Generate URLs by table
        if url_extractor_available:
            try:
                urls_by_table = GitHubURLExtractor.generate_urls_by_table(column_lineage)
            except:
                urls_by_table = self._generate_urls_by_table(column_lineage)
        else:
            urls_by_table = self._generate_urls_by_table(column_lineage)
        
        return {
            "target_table": target_table,
            "target_column": column_name,
            "lineage": column_lineage,
            "lineage_map": column_lineage_map,
            "total_dependencies": len(column_lineage),
            "file_count": len(set(file for dep in column_lineage for file in dep.get("files", []))),
            "source_tables": list(set(dep["source"] for dep in column_lineage)),
            "urls_by_table": urls_by_table
        }
    
    def _extract_column_reference_snippet(self, sql_content: str, column_name: str, table_name: str = None) -> str:
        """
        Extract a relevant code snippet from SQL content that references the column
        
        Args:
            sql_content: SQL content
            column_name: Column name to search for
            table_name: Optional table name for context
            
        Returns:
            Relevant code snippet or empty string
        """
        if not sql_content or not column_name:
            return ""
            
        try:
            # Find snippets with column reference
            import re
            
            # Pattern to match the column name, potentially with table alias
            # e.g., column_name, table.column_name, t1.column_name, etc.
            pattern = r'(?:[a-zA-Z0-9_]+\.){0,1}' + re.escape(column_name) + r'\b'
            
            matches = list(re.finditer(pattern, sql_content, re.IGNORECASE))
            if not matches:
                return ""
                
            # Take the most relevant match (usually the first in a SELECT or calculation)
            match = matches[0]
            
            # Extract a context window around the match
            start = max(0, match.start() - 100)
            end = min(len(sql_content), match.end() + 100)
            
            # Try to extend to complete statements
            while start > 0 and sql_content[start] not in ";\n":
                start -= 1
                
            while end < len(sql_content) and sql_content[end] not in ";\n":
                end += 1
                
            snippet = sql_content[start:end].strip()
            
            # Highlight the column reference in the snippet
            highlighted_snippet = snippet.replace(
                match.group(0), 
                f"**{match.group(0)}**"  # Use markdown bold for highlighting
            )
            
            return highlighted_snippet
        except Exception:
            return ""
            
    def _generate_column_lineage_map(self, target_table: str, target_column: str, lineage: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Generate a comprehensive lineage map for the column
        
        Args:
            target_table: Target table name
            target_column: Target column name
            lineage: Column lineage data
            
        Returns:
            Dict with lineage map information
        """
        # Organize by source tables
        source_tables = {}
        
        for dep in lineage:
            source = dep.get("source", "")
            if not source:
                continue
                
            columns = dep.get("columns", [])
            if source not in source_tables:
                source_tables[source] = {
                    "columns": [],
                    "files": [],
                    "depth": dep.get("depth", 0)
                }
                
            # Add columns
            source_tables[source]["columns"].extend([col for col in columns if col not in source_tables[source]["columns"]])
            
            # Add files
            for file_detail in dep.get("file_details", []):
                file_url = file_detail.get("github_url", "")
                if file_url and file_url not in source_tables[source]["files"]:
                    source_tables[source]["files"].append(file_url)
        
        return {
            "target": {
                "table": target_table,
                "column": target_column
            },
            "source_tables": source_tables,
            "node_count": len(source_tables) + 1,  # +1 for target
            "edge_count": len(source_tables)
        }
    
    def visualize_dependencies(self, target_table: str, output_format: str = "json") -> Dict[str, Any]:
        """
        Visualize dependencies for a table
        
        Args:
            target_table: Target table name
            output_format: Output format (json, graphviz, etc.)
            
        Returns:
            Dict with visualization data
        """
        # Ensure we have dependencies to visualize
        if not self.dependency_graph:
            upstream_info = self.trace_table_dependencies(target_table)
            if "error" in upstream_info:
                return upstream_info
        
        # Extract subgraph for this target
        try:
            # Get all reachable nodes from the target (upstream)
            upstream_nodes = nx.ancestors(self.dependency_graph, target_table)
            upstream_nodes.add(target_table)
            
            # Create a subgraph with these nodes
            subgraph = self.dependency_graph.subgraph(upstream_nodes)
            
            # Convert to desired output format
            if output_format == "json":
                # Convert NetworkX graph to JSON-serializable format
                nodes = []
                for node in subgraph.nodes():
                    node_data = subgraph.nodes[node].copy()
                    node_data["id"] = node
                    node_data["label"] = node.split(".")[-1] if "." in node else node
                    nodes.append(node_data)
                
                edges = []
                for source, target, data in subgraph.edges(data=True):
                    edge_data = data.copy()
                    edge_data["source"] = source
                    edge_data["target"] = target
                    edge_data["label"] = f"{source} → {target}"
                    edges.append(edge_data)
                
                return {
                    "target_table": target_table,
                    "nodes": nodes,
                    "edges": edges,
                    "format": "json"
                }
            
            # Could add support for other formats (graphviz, mermaid, etc.)
            
            return {
                "error": f"Unsupported output format: {output_format}",
                "supported_formats": ["json"]
            }
            
        except Exception as e:
            logger.error(f"Error visualizing dependencies: {str(e)}")
            return {
                "error": f"Error visualizing dependencies: {str(e)}",
                "target_table": target_table
            }
    
    def save_dependency_graph(self, file_path: str) -> Dict[str, Any]:
        """
        Save the current dependency graph to a file
        
        Args:
            file_path: Path to save the graph
            
        Returns:
            Dict with result information
        """
        if not self.dependency_graph:
            return {"error": "No dependency graph available to save"}
        
        try:
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            # Save the graph
            if file_path.endswith(".json"):
                # Convert to JSON-serializable format
                graph_data = nx.node_link_data(self.dependency_graph)
                with open(file_path, 'w') as f:
                    json.dump(graph_data, f, indent=2)
            else:
                # Default to GraphML format
                nx.write_graphml(self.dependency_graph, file_path)
            
            return {
                "success": True,
                "file_path": file_path,
                "message": f"Dependency graph saved to {file_path}"
            }
            
        except Exception as e:
            logger.error(f"Error saving dependency graph: {str(e)}")
            return {
                "error": f"Error saving dependency graph: {str(e)}",
                "file_path": file_path
            }
    
    def search_for_table(self, table_name: str, limit: int = 5) -> Dict[str, Any]:
        """
        Search for SQL files containing the specified table
        
        Args:
            table_name: Name of the table to search for
            limit: Maximum number of results to return
            
        Returns:
            Dictionary containing search results with file paths and content
        """
        try:
            if not self.sql_finder:
                # Initialize SQL finder if not already done
                self.initialize()
                if not self.sql_finder:
                    return {"error": "Failed to initialize SQL finder", "files_found": 0, "results": []}
                
            # Search for the table using the SQL finder
            sql_files = self.sql_finder.search_for_table(table_name, limit)
            
            # Format the results
            if not sql_files:
                return {"files_found": 0, "results": []}
                
            # Handle error case
            if isinstance(sql_files, dict) and "error" in sql_files:
                return sql_files  # Pass through the error
                
            # Convert to standard format
            results = []
            for file in sql_files:
                if isinstance(file, dict):
                    results.append(file)
                    
            return {
                "files_found": len(results),
                "results": results
            }
        except Exception as e:
            logger.error(f"Error searching for table {table_name}: {str(e)}")
            return {"error": f"Error searching for table: {str(e)}", "files_found": 0, "results": []}
    
    def search_for_column(self, table_name: str, column_name: str, limit: int = 5) -> Dict[str, Any]:
        """
        Search for SQL files that reference a specific column in a table
        
        Args:
            table_name: Table name (optional, can be empty string)
            column_name: Column name to search for
            limit: Maximum number of results
            
        Returns:
            Dictionary containing search results
        """
        try:
            if not self.sql_finder:
                # Initialize SQL finder if not already done
                self.initialize()
                if not self.sql_finder:
                    return {"error": "Failed to initialize SQL finder", "files_found": 0, "results": []}
                
            # Search for the column using the SQL finder
            if hasattr(self.sql_finder, 'search_for_column'):
                sql_files = self.sql_finder.search_for_column(table_name, column_name, limit)
            else:
                # Fall back to general search if specific method not available
                query = f"{column_name}"
                if table_name:
                    query = f"{table_name}.{column_name}"
                sql_files = self.sql_finder.search_sql_files(query, limit)
            
            # Format the results
            if not sql_files:
                return {"files_found": 0, "results": []}
                
            # Handle error case
            if isinstance(sql_files, dict) and "error" in sql_files:
                return sql_files  # Pass through the error
                
            # Convert to standard format
            results = []
            for file in sql_files:
                if isinstance(file, dict):
                    results.append(file)
                    
            return {
                "files_found": len(results),
                "results": results
            }
        except Exception as e:
            logger.error(f"Error searching for column {column_name}: {str(e)}")
            return {"error": f"Error searching for column: {str(e)}", "files_found": 0, "results": []} 