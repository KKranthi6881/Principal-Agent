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
                "levels": {}
            }
            
            # Process dependencies by level
            for level, deps in result.get("dependencies_by_level", {}).items():
                level_tables = []
                
                for dep in deps:
                    table_info = {
                        "name": dep.get("table", ""),
                        "file_path": dep.get("file_path", ""),
                        "dependencies": dep.get("dependencies", []),
                        "used_by": dep.get("used_by", "")
                    }
                    
                    # Only include file URL if available
                    if "file_url" in dep and dep["file_url"]:
                        table_info["file_url"] = dep["file_url"]
                    
                    level_tables.append(table_info)
                
                llm_result["levels"][level] = level_tables
            
            # Add column information if available
            if "column_lineage" in result:
                llm_result["columns"] = result["column_lineage"]
            
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

# Create a singleton instance
llm_interface = SQLLLMInterface() 