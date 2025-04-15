"""
LLM Interface for SQL Analysis Tools

This module provides a clean interface for LLMs to interact with SQL analysis tools,
returning simplified outputs suitable for LLM consumption.
"""

import os
import json
import logging
from typing import Dict, List, Optional, Any, Union

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import the SQL API
try:
    from .api import sql_api
except ImportError:
    from backend.tools.sql_tools.api import sql_api

class SQLLLMInterface:
    """
    LLM-friendly interface for SQL analysis tools
    """
    
    def __init__(self):
        """Initialize the LLM interface"""
        self.sql_api = sql_api
        self.github_wrapper = None
        self.vector_store_path = None
    
    def initialize_with_github(self, github_wrapper):
        """
        Initialize the interface with a GitHub wrapper
        
        Args:
            github_wrapper: Initialized GitHubAPIWrapper instance
        """
        self.github_wrapper = github_wrapper
        # Initialize SQL API with GitHub wrapper
        if hasattr(self.sql_api, 'initialize_with_github'):
            self.sql_api.initialize_with_github(github_wrapper)
        logger.info("Initialized SQL LLM Interface with GitHub wrapper")
    
    def get_table_lineage(self, table_name: str, direction: str = "upstream", 
                          max_depth: int = 5, dialect: Optional[str] = None,
                          repo_url: Optional[str] = None) -> Dict[str, Any]:
        """
        Get table lineage in LLM-friendly format
        
        Args:
            table_name: Name of the table
            direction: "upstream" or "downstream"
            max_depth: Maximum depth to trace
            dialect: SQL dialect to use
            repo_url: Repository URL for automatic dialect detection
            
        Returns:
            Simplified lineage information
        """
        try:
            # Auto-detect dialect if repo_url is provided
            if repo_url and not dialect:
                dialect = self.sql_api.detect_dialect_from_repo_url(repo_url)
            
            # Get full lineage
            result = self.sql_api.trace_complete_lineage(table_name, direction, max_depth, dialect)
            
            # Create simplified result for LLM consumption
            llm_result = {
                "table": table_name,
                "direction": direction,
                "dialect_used": result.get("dialect_used", "unknown"),
                "summary": result.get("summary", ""),
                "total_files": result.get("total_files", 0),
                "max_depth_reached": result.get("max_depth_reached", 0),
                "levels": {},
                "source_files": []  # Add source files list
            }
            
            # Process files by level
            for level, files in result.get("files_by_level", {}).items():
                level_info = []
                
                for file_info in files:
                    info = {
                        "file_path": file_info.get("file_path", ""),
                        "url": file_info.get("url", ""),
                        "github_repo": file_info.get("github_repo", ""),
                        "dialect": file_info.get("dialect", "unknown"),
                        "target_table": file_info.get("target_table", ""),
                        "source_tables": file_info.get("source_tables", [])
                    }
                    
                    # Add content snippet if available
                    if "content" in file_info:
                        content = file_info["content"]
                        info["content_snippet"] = content[:500] + "..." if len(content) > 500 else content
                    
                    # Add column dependencies if available
                    if "column_dependencies" in file_info:
                        info["column_dependencies"] = file_info["column_dependencies"]
                    
                    level_info.append(info)
                
                llm_result["levels"][level] = level_info
            
            # Add original source files from the dependency analysis for context
            if "source_files" in result:
                llm_result["source_files"] = result["source_files"]
            
            # Add dependency chain for easy visualization
            dependency_chain = []
            tables_by_level = {}
            
            for level, files in result.get("files_by_level", {}).items():
                tables_at_level = set()
                for file_info in files:
                    tables_at_level.add(file_info.get("target_table", ""))
                    tables_at_level.update(file_info.get("source_tables", []))
                tables_by_level[level] = list(tables_at_level)
            
            # Build the chain from target to sources
            current_table = table_name
            current_level = 0
            while current_level in tables_by_level:
                tables = tables_by_level[current_level]
                if tables:
                    dependency_chain.append({
                        "level": current_level,
                        "tables": tables
                    })
                current_level += 1
            
            llm_result["dependency_chain"] = dependency_chain
            
            # Add a natural language summary
            summary_lines = []
            summary_lines.append(f"Analysis of {table_name} {direction} dependencies:")
            summary_lines.append(f"- Found {llm_result['total_files']} relevant SQL files")
            summary_lines.append(f"- Traced dependencies across {llm_result['max_depth_reached']} levels")
            
            if dependency_chain:
                summary_lines.append("\nDependency chain:")
                for level in dependency_chain:
                    tables = level["tables"]
                    summary_lines.append(f"Level {level['level']}: {', '.join(tables)}")
            
            # Add description of available sources
            if llm_result["source_files"]:
                source_count = len(llm_result["source_files"])
                summary_lines.append(f"\nSource information:")
                summary_lines.append(f"- {source_count} source files containing the table or its dependencies")
                for i, src in enumerate(llm_result["source_files"][:3]):  # Show first 3
                    summary_lines.append(f"  - {src.get('path', 'unknown')} ({src.get('dialect', 'sql')})")
                if source_count > 3:
                    summary_lines.append(f"  - Plus {source_count - 3} more files")
            
            llm_result["natural_language_summary"] = "\n".join(summary_lines)
            
            return llm_result
            
        except Exception as e:
            logger.error(f"Error in get_table_lineage: {str(e)}")
            return {"error": str(e)}
    
    def get_column_lineage(self, table_name: str, column_name: str, 
                           direction: str = "upstream", max_depth: int = 5,
                           dialect: Optional[str] = None, 
                           repo_url: Optional[str] = None) -> Dict[str, Any]:
        """
        Get column lineage in LLM-friendly format
        
        Args:
            table_name: Name of the table
            column_name: Name of the column
            direction: "upstream" or "downstream"
            max_depth: Maximum depth to trace
            dialect: SQL dialect to use
            repo_url: Repository URL for automatic dialect detection
            
        Returns:
            Simplified column lineage information
        """
        try:
            # Auto-detect dialect if repo_url is provided
            if repo_url and not dialect:
                dialect = self.sql_api.detect_dialect_from_repo_url(repo_url)
            
            # Get full column lineage
            result = self.sql_api.trace_column_complete_lineage(
                table_name, column_name, direction, max_depth, dialect
            )
            
            # Create simplified result for LLM consumption
            llm_result = {
                "table": table_name,
                "column": column_name,
                "direction": direction,
                "dialect_used": result.get("dialect_used", "unknown"),
                "summary": result.get("summary", ""),
                "column_chain": result.get("column_chain", []),
                "levels": {}
            }
            
            # Process dependencies by level
            for level, deps in result.get("dependencies_by_level", {}).items():
                level_columns = []
                
                for dep in deps:
                    column_info = {
                        "column": dep.get("column", ""),
                        "table": dep.get("table", ""),
                        "file_path": dep.get("file_path", "")
                    }
                    
                    # Only include file URL if available
                    if "file_url" in dep and dep["file_url"]:
                        column_info["file_url"] = dep["file_url"]
                    
                    # Add source columns if available
                    if "source_columns" in dep:
                        column_info["source_columns"] = dep["source_columns"]
                    
                    level_columns.append(column_info)
                
                llm_result["levels"][level] = level_columns
            
            return llm_result
            
        except Exception as e:
            logger.error(f"Error in get_column_lineage: {str(e)}")
            return {"error": str(e)}
    
    def search_tables(self, table_name: str, limit: int = 5) -> Dict[str, Any]:
        """
        Search for tables in the codebase
        
        Args:
            table_name: Name of the table to search for
            limit: Maximum number of results
            
        Returns:
            Simplified search results
        """
        try:
            results = self.sql_api.search_for_table(table_name, limit)
            
            # Create simplified result for LLM consumption
            llm_result = {
                "table": table_name,
                "files_found": len(results),
                "results": []
            }
            
            for result in results:
                file_info = {
                    "file_path": result.get("file_path", ""),
                    "dialect": result.get("dialect", "unknown"),
                    "repo": result.get("github_repo", "")
                }
                
                # Only include URL if available
                if "url" in result and result["url"]:
                    file_info["url"] = result["url"]
                
                # Add a summary of the content (first 200 chars)
                content = result.get("content", "")
                if content:
                    file_info["content_summary"] = content[:200] + "..." if len(content) > 200 else content
                
                llm_result["results"].append(file_info)
            
            return llm_result
            
        except Exception as e:
            logger.error(f"Error in search_tables: {str(e)}")
            return {"error": str(e)}
    
    def search_sql(self, query: str, limit: int = 5) -> Dict[str, Any]:
        """
        Search for SQL files in the codebase
        
        Args:
            query: Search query
            limit: Maximum number of results
            
        Returns:
            Simplified search results
        """
        try:
            results = self.sql_api.search_for_sql_files(query, limit)
            
            # Create simplified result for LLM consumption
            llm_result = {
                "query": query,
                "files_found": len(results),
                "results": []
            }
            
            for result in results:
                file_info = {
                    "file_path": result.get("file_path", ""),
                    "dialect": result.get("dialect", "unknown"),
                    "repo": result.get("github_repo", "")
                }
                
                # Only include URL if available
                if "url" in result and result["url"]:
                    file_info["url"] = result["url"]
                
                # Add a summary of the content (first 200 chars)
                content = result.get("content", "")
                if content:
                    file_info["content_summary"] = content[:200] + "..." if len(content) > 200 else content
                
                llm_result["results"].append(file_info)
            
            return llm_result
            
        except Exception as e:
            logger.error(f"Error in search_sql: {str(e)}")
            return {"error": str(e)}
    
    def detect_dialect(self, repo_url: str) -> Dict[str, str]:
        """
        Detect SQL dialect from repository URL
        
        Args:
            repo_url: Repository URL
            
        Returns:
            Detected dialect information
        """
        try:
            dialect = self.sql_api.detect_dialect_from_repo_url(repo_url)
            return {
                "repo_url": repo_url,
                "detected_dialect": dialect
            }
        except Exception as e:
            logger.error(f"Error in detect_dialect: {str(e)}")
            return {"error": str(e)}
    
    def search_columns(self, column_name: str, limit: int = 5) -> Dict[str, Any]:
        """
        Search for columns across all tables in the codebase
        
        Args:
            column_name: Name of the column to search for
            limit: Maximum number of results
            
        Returns:
            Simplified search results
        """
        try:
            # Use column search with empty table name for global search
            results = self.sql_api.search_for_column("", column_name, limit)
            
            # Create simplified result for LLM consumption
            llm_result = {
                "column": column_name,
                "files_found": len(results),
                "results": []
            }
            
            # Extract likely tables containing this column
            tables_containing_column = set()
            
            for result in results:
                file_info = {
                    "file_path": result.get("file_path", ""),
                    "dialect": result.get("dialect", "unknown"),
                    "repo": result.get("github_repo", "")
                }
                
                # Only include URL if available
                if "url" in result and result["url"]:
                    file_info["url"] = result["url"]
                
                # Add a summary of the content (first 200 chars)
                content = result.get("content", "")
                if content:
                    file_info["content_summary"] = content[:200] + "..." if len(content) > 200 else content
                    
                    # Try to extract table name from the content
                    table_name = self._extract_table_for_column(content, column_name, result.get("file_path", ""))
                    if table_name:
                        file_info["likely_table"] = table_name
                        tables_containing_column.add(table_name)
                
                llm_result["results"].append(file_info)
            
            # Add list of likely tables
            llm_result["likely_tables"] = list(tables_containing_column)
            
            return llm_result
            
        except Exception as e:
            logger.error(f"Error in search_columns: {str(e)}")
            return {"error": str(e)}
    
    def _extract_table_for_column(self, content: str, column_name: str, file_path: str = "") -> Optional[str]:
        """
        Extract the likely table name for a column from SQL content
        
        Args:
            content: SQL content
            column_name: Column name to find
            file_path: File path (optional, used for context)
            
        Returns:
            Likely table name or None
        """
        # First try to find the table name from the file path (DBT convention)
        if file_path:
            # Extract file name without extension
            file_name = file_path.split('/')[-1]
            if file_name.endswith('.sql'):
                file_name = file_name[:-4]
                
            # Check for DBT model naming conventions
            if any(prefix in file_name for prefix in ['stg_', 'fct_', 'dim_', 'int_']):
                return file_name
        
        # Try to extract from SQL content
        # Lowercase for consistent matching
        content_lower = content.lower()
        column_lower = column_name.lower()
        
        # Look for explicit table.column references
        table_column_pattern = rf'([a-zA-Z0-9_]+)\.{column_lower}'
        import re
        matches = re.findall(table_column_pattern, content_lower)
        if matches:
            return matches[0]
        
        # Look for table in CREATE TABLE statements
        create_patterns = [
            'create table ',
            'create or replace table ',
            'create view '
        ]
        
        for pattern in create_patterns:
            if pattern in content_lower:
                idx = content_lower.find(pattern) + len(pattern)
                end_idx = content_lower.find('(', idx)
                if end_idx == -1:
                    end_idx = content_lower.find('\n', idx)
                if end_idx == -1:
                    end_idx = len(content_lower)
                
                table_name = content_lower[idx:end_idx].strip()
                # Remove schema prefixes if present
                if '.' in table_name:
                    table_name = table_name.split('.')[-1]
                
                return table_name
        
        # Fallback: Use file name as table name
        if file_path:
            return file_path.split('/')[-1].split('.')[0]
                
        return None

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
            # First try using the SQL API if available
            if self.sql_api:
                return self.sql_api.search_for_table(table_name, limit)
                
            # Fallback to direct search if no API
            if self.github_wrapper:
                # Search for SQL files containing the table name
                query = f"SELECT * FROM {table_name}"
                results = self.github_wrapper.search_code(query, file_extensions=[".sql"])
                
                if not results:
                    # Try alternative patterns
                    patterns = [
                        f"CREATE TABLE.*{table_name}",
                        f"INSERT INTO.*{table_name}",
                        f"UPDATE.*{table_name}",
                        f"DELETE FROM.*{table_name}",
                        f"MERGE INTO.*{table_name}"
                    ]
                    
                    for pattern in patterns:
                        results = self.github_wrapper.search_code(pattern, file_extensions=[".sql"])
                        if results:
                            break
                
                # Format the results
                formatted_results = []
                for result in results[:limit]:
                    try:
                        content = self.github_wrapper.get_file_content(result["path"])
                        formatted_results.append({
                            "file_path": result["path"],
                            "url": result.get("url", ""),
                            "repo": result.get("repository", {}).get("full_name", ""),
                            "content": content,
                            "content_summary": self._extract_relevant_sql(content, table_name)
                        })
                    except Exception as e:
                        logger.error(f"Error getting content for file {result['path']}: {str(e)}")
                        continue
                
                return {
                    "files_found": len(formatted_results),
                    "results": formatted_results
                }
            
            return {"files_found": 0, "results": []}
            
        except Exception as e:
            logger.error(f"Error searching for table {table_name}: {str(e)}")
            return {"error": str(e)}
            
    def _extract_relevant_sql(self, content: str, table_name: str) -> str:
        """Extract relevant SQL statements containing the table name"""
        if not content:
            return ""
            
        # Split into statements
        statements = content.split(";")
        
        # Find statements containing the table name
        relevant = []
        for stmt in statements:
            if table_name.lower() in stmt.lower():
                relevant.append(stmt.strip())
                
        # Return the most relevant statements
        if relevant:
            return ";\n".join(relevant[:3]) + ";"  # Return top 3 most relevant statements
            
        # If no exact matches, return the first part of the file
        return content[:500] + "..." if len(content) > 500 else content

# Create a singleton instance
llm_interface = SQLLLMInterface() 