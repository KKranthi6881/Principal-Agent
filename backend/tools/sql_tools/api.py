"""
SQL Analysis API

This module provides a unified API for SQL analysis capabilities including
parsing, dependency extraction, and lineage analysis.
"""

import os
import logging
import json
from typing import Dict, List, Set, Tuple, Optional, Any

# Import dialect and lineage modules
from .dialects import get_dialect_parser, get_available_dialects
from .lineage import SQLGlotLineageExtractor
from .github_sql_finder import GitHubSQLFinder

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class SQLAnalysisAPI:
    """
    Unified API for SQL analysis capabilities
    """
    
    def __init__(self, vector_store_path: Optional[str] = None):
        """
        Initialize the SQL Analysis API
        
        Args:
            vector_store_path: Path to the vector store for GitHub SQL finder
        """
        self.vector_store_path = vector_store_path
        self.github_sql_finder = GitHubSQLFinder(vector_store_path)
        self.lineage_extractor = SQLGlotLineageExtractor()
        self.dialect_cache = {}  # Cache for dialect parsers
        
        # Initialize the GitHub SQL finder
        self.github_sql_finder.initialize()
    
    def get_dialect_parser(self, dialect_name: str) -> Any:
        """
        Get a dialect parser based on the dialect name
        
        Args:
            dialect_name: Name of the dialect
            
        Returns:
            Dialect parser instance or None if not found
        """
        # Check cache first
        if dialect_name in self.dialect_cache:
            return self.dialect_cache[dialect_name]
        
        # Create new parser
        parser = get_dialect_parser(dialect_name)
        if parser:
            self.dialect_cache[dialect_name] = parser
        
        return parser
    
    def list_available_dialects(self) -> Dict[str, str]:
        """
        List available SQL dialects
        
        Returns:
            Dictionary of {dialect_name: description}
        """
        return get_available_dialects()
    
    def detect_dialect(self, sql_code: str, file_path: Optional[str] = None) -> str:
        """
        Detect the SQL dialect from code and file path
        
        Args:
            sql_code: SQL code
            file_path: Path to the SQL file (optional)
            
        Returns:
            Detected dialect name
        """
        # Check file path for clues
        if file_path:
            file_path = file_path.lower()
            
            # Check for dbt
            if '/dbt/' in file_path or file_path.endswith('.dbt.sql'):
                return "dbt"
            
            # Check for dialect-specific directories
            if '/snowflake/' in file_path:
                return "snowflake"
            if '/redshift/' in file_path:
                return "redshift"
            if '/postgres/' in file_path or '/postgresql/' in file_path:
                return "postgres"
            if '/mysql/' in file_path:
                return "mysql"
            if '/tsql/' in file_path or '/mssql/' in file_path or '/sqlserver/' in file_path:
                return "tsql"
        
        # Check SQL code for dialect-specific syntax
        sql_code = sql_code.lower()
        
        # Look for dialect-specific patterns
        if '$$' in sql_code or 'lateral flatten' in sql_code:
            return "snowflake"
        if 'distkey' in sql_code or 'sortkey' in sql_code:
            return "redshift" 
        if 'for system_time' in sql_code or 'output inserted' in sql_code:
            return "tsql"
        if 'force index' in sql_code or 'using index' in sql_code:
            return "mysql"
        
        # Default to postgres as it's a common SQL dialect
        return "postgres"
    
    def extract_dependencies(self, sql_code: str, dialect: Optional[str] = None, 
                           file_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Extract dependencies from SQL code
        
        Args:
            sql_code: SQL code to analyze
            dialect: SQL dialect (if None, will be auto-detected)
            file_path: Path to the file (optional)
            
        Returns:
            Dictionary with extracted dependencies
        """
        # Detect dialect if not provided
        if not dialect:
            dialect = self.detect_dialect(sql_code, file_path)
        
        # Get dialect parser
        parser = self.get_dialect_parser(dialect)
        if not parser:
            return {
                "error": f"Dialect {dialect} not supported",
                "file_path": file_path,
                "dialect": dialect
            }
        
        # Extract dependencies
        return parser.extract_dependencies(sql_code, file_path)
    
    def extract_lineage(self, sql_code: str, dialect: Optional[str] = None,
                      file_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Extract lineage information from SQL code
        
        Args:
            sql_code: SQL code to analyze
            dialect: SQL dialect (if None, will be auto-detected)
            file_path: Path to the file (optional)
            
        Returns:
            Dictionary with extracted lineage information
        """
        # Detect dialect if not provided
        if not dialect:
            dialect = self.detect_dialect(sql_code, file_path)
        
        # Get dialect parser
        parser = self.get_dialect_parser(dialect)
        if not parser:
            return {
                "error": f"Dialect {dialect} not supported",
                "file_path": file_path,
                "dialect": dialect
            }
        
        # Extract lineage
        return parser.extract_lineage(sql_code, file_path)
    
    def search_for_sql_files(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Search for SQL files based on a query
        
        Args:
            query: Search query
            limit: Maximum number of results
            
        Returns:
            List of matching SQL files with metadata
        """
        return self.github_sql_finder.search_sql_files(query, limit)
    
    def search_for_table(self, table_name: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Search for SQL files that reference a specific table
        
        Args:
            table_name: Table name to search for
            limit: Maximum number of results
            
        Returns:
            List of matching SQL files with metadata
        """
        return self.github_sql_finder.search_for_table(table_name, limit)
    
    def search_for_column(self, table_name: str, column_name: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Search for SQL files that reference a specific column in a table
        
        Args:
            table_name: Table name
            column_name: Column name
            limit: Maximum number of results
            
        Returns:
            List of matching SQL files with metadata
        """
        return self.github_sql_finder.search_for_column(table_name, column_name, limit)
    
    def process_file(self, file_path: str, dialect: Optional[str] = None) -> Dict[str, Any]:
        """
        Process a local SQL file to extract dependencies and lineage
        
        Args:
            file_path: Path to the SQL file
            dialect: SQL dialect (if None, will be auto-detected)
            
        Returns:
            Dictionary with analysis results
        """
        try:
            # Check if file exists
            if not os.path.exists(file_path):
                return {
                    "error": f"File {file_path} not found",
                    "file_path": file_path
                }
            
            # Read file content
            with open(file_path, 'r', encoding='utf-8') as f:
                sql_code = f.read()
            
            # Detect dialect if not provided
            if not dialect:
                dialect = self.detect_dialect(sql_code, file_path)
            
            # Extract dependencies and lineage
            dependencies = self.extract_dependencies(sql_code, dialect, file_path)
            lineage = self.extract_lineage(sql_code, dialect, file_path)
            
            # Combine results
            return {
                "file_path": file_path,
                "dialect": dialect,
                "dependencies": dependencies,
                "lineage": lineage
            }
            
        except Exception as e:
            logger.error(f"Error processing file {file_path}: {str(e)}")
            return {
                "error": f"Error processing file: {str(e)}",
                "file_path": file_path
            }
    
    def analyze_repository(self, repo_url: str, dialect: Optional[str] = None) -> Dict[str, Any]:
        """
        Analyze SQL files in a GitHub repository
        
        Args:
            repo_url: GitHub repository URL
            dialect: SQL dialect to use (if None, will be auto-detected for each file)
            
        Returns:
            Dictionary with analysis results
        """
        try:
            # Search for SQL files in the repository
            sql_files = self.github_sql_finder.search_sql_files(f"repo:{repo_url} extension:sql", limit=100)
            
            if not sql_files or len(sql_files) == 0:
                return {
                    "error": f"No SQL files found in repository {repo_url}",
                    "repo_url": repo_url
                }
            
            # Analyze each file
            results = []
            for file_info in sql_files:
                file_path = file_info.get("path")
                file_content = file_info.get("content")
                file_dialect = dialect or file_info.get("dialect") or self.detect_dialect(file_content, file_path)
                
                # Extract dependencies and lineage
                dependency_info = self.extract_dependencies(file_content, file_dialect, file_path)
                lineage_info = self.extract_lineage(file_content, file_dialect, file_path)
                
                results.append({
                    "file_path": file_path,
                    "file_url": file_info.get("url"),
                    "dialect": file_dialect,
                    "dependencies": dependency_info,
                    "lineage": lineage_info
                })
            
            # Return combined results
            return {
                "repo_url": repo_url,
                "file_count": len(results),
                "results": results
            }
            
        except Exception as e:
            logger.error(f"Error analyzing repository {repo_url}: {str(e)}")
            return {
                "error": f"Error analyzing repository: {str(e)}",
                "repo_url": repo_url
            }
    
    def trace_column_lineage(self, table_name: str, column_name: str) -> Dict[str, Any]:
        """
        Trace lineage for a specific column
        
        Args:
            table_name: Table name
            column_name: Column name
            
        Returns:
            Dictionary with column lineage information
        """
        try:
            # Search for SQL files that reference this column
            sql_files = self.github_sql_finder.search_for_column(table_name, column_name)
            
            if not sql_files or len(sql_files) == 0:
                return {
                    "error": f"No SQL files found referencing column {column_name} in table {table_name}",
                    "table_name": table_name,
                    "column_name": column_name
                }
            
            # Extract lineage from each file
            lineage_results = []
            for file_info in sql_files:
                file_path = file_info.get("path")
                file_content = file_info.get("content")
                file_dialect = file_info.get("dialect") or self.detect_dialect(file_content, file_path)
                
                lineage_info = self.extract_lineage(file_content, file_dialect, file_path)
                
                # Check if this column is in the lineage
                if lineage_info.get("target_table") == table_name:
                    column_mappings = lineage_info.get("column_level_lineage", {})
                    if column_name in column_mappings:
                        lineage_results.append({
                            "file_path": file_path,
                            "file_url": file_info.get("url"),
                            "target_table": table_name,
                            "target_column": column_name,
                            "sources": column_mappings[column_name]
                        })
            
            return {
                "table_name": table_name,
                "column_name": column_name,
                "lineage_count": len(lineage_results),
                "lineage": lineage_results
            }
            
        except Exception as e:
            logger.error(f"Error tracing column lineage for {table_name}.{column_name}: {str(e)}")
            return {
                "error": f"Error tracing column lineage: {str(e)}",
                "table_name": table_name,
                "column_name": column_name
            }

    def trace_complete_lineage(self, table_name: str, direction: str = "upstream", max_depth: int = 10) -> Dict[str, Any]:
        """
        Trace complete lineage for a table recursively through all levels of dependencies
        
        Args:
            table_name: The table to trace lineage for
            direction: "upstream" (sources of this table) or "downstream" (tables that use this table)
            max_depth: Maximum depth to trace dependencies
            
        Returns:
            Dictionary with complete lineage information
        """
        try:
            logger.info(f"Tracing {direction} lineage for table {table_name} (max depth: {max_depth})")
            
            # Track visited tables to avoid cycles
            visited_tables = set()
            # Track the lineage graph
            lineage_graph = {
                "nodes": [],
                "edges": [],
                "files": {}
            }
            # Track dependencies by level
            dependencies_by_level = {}
            
            # Function to recursively trace dependencies
            def trace_recursive(current_table, current_depth=0, parent_table=None):
                # Stop if we've reached max depth or already visited this table
                if current_depth >= max_depth or current_table in visited_tables:
                    return
                
                # Mark this table as visited
                visited_tables.add(current_table)
                
                # Add this level to dependencies_by_level if needed
                if current_depth not in dependencies_by_level:
                    dependencies_by_level[current_depth] = []
                
                # Search for SQL files that reference this table
                query = f"table:{current_table}"
                sql_files = self.search_for_sql_files(query, limit=20)
                
                for file_info in sql_files:
                    file_path = file_info.get("path", "")
                    file_url = file_info.get("url", "")
                    file_content = file_info.get("content", "")
                    dialect = file_info.get("dialect") or self.detect_dialect(file_content, file_path)
                    
                    # Extract dependencies and lineage
                    if direction == "upstream":
                        # For upstream, we want to find sources referenced in this file
                        analysis = self.extract_dependencies(file_content, dialect, file_path)
                        
                        # Check if this file defines the current table (target table matches)
                        target_matches = analysis.get("target_table") == current_table
                        
                        # Get the source tables (upstream dependencies)
                        next_tables = analysis.get("source_tables", [])
                        
                        # Store dependency info
                        if target_matches and next_tables:
                            # Store file information
                            file_id = f"file_{len(lineage_graph['files'])}"
                            lineage_graph["files"][file_id] = {
                                "path": file_path,
                                "url": file_url,
                                "dialect": dialect,
                                "defines_table": current_table
                            }
                            
                            # Add file relationship to the current level
                            dependencies_by_level[current_depth].append({
                                "table": current_table,
                                "file_id": file_id,
                                "file_path": file_path,
                                "file_url": file_url,
                                "dependencies": next_tables
                            })
                            
                            # Add to the lineage graph
                            # Add node for current table if not already present
                            if current_table not in [node["id"] for node in lineage_graph["nodes"]]:
                                lineage_graph["nodes"].append({
                                    "id": current_table, 
                                    "label": current_table,
                                    "depth": current_depth
                                })
                            
                            # Add edges for each dependency
                            for dep_table in next_tables:
                                # Add node for dependency if not already present
                                if dep_table not in [node["id"] for node in lineage_graph["nodes"]]:
                                    lineage_graph["nodes"].append({
                                        "id": dep_table, 
                                        "label": dep_table,
                                        "depth": current_depth + 1
                                    })
                                
                                # Add edge
                                lineage_graph["edges"].append({
                                    "source": dep_table,
                                    "target": current_table,
                                    "file_id": file_id
                                })
                            
                            # Recursively trace dependencies
                            for dep_table in next_tables:
                                trace_recursive(dep_table, current_depth + 1, current_table)
                    
                    elif direction == "downstream":
                        # For downstream, we want to find tables that use the current table
                        analysis = self.extract_dependencies(file_content, dialect, file_path)
                        
                        # Check if this file references the current table (as a source)
                        source_tables = analysis.get("source_tables", [])
                        references_current = current_table in source_tables
                        
                        # Get the target table (downstream dependency)
                        target_table = analysis.get("target_table")
                        
                        # Store dependency info
                        if references_current and target_table:
                            # Store file information
                            file_id = f"file_{len(lineage_graph['files'])}"
                            lineage_graph["files"][file_id] = {
                                "path": file_path,
                                "url": file_url,
                                "dialect": dialect,
                                "uses_table": current_table
                            }
                            
                            # Add file relationship to the current level
                            dependencies_by_level[current_depth].append({
                                "table": current_table,
                                "file_id": file_id,
                                "file_path": file_path,
                                "file_url": file_url,
                                "used_by": target_table
                            })
                            
                            # Add to the lineage graph
                            # Add node for current table if not already present
                            if current_table not in [node["id"] for node in lineage_graph["nodes"]]:
                                lineage_graph["nodes"].append({
                                    "id": current_table, 
                                    "label": current_table,
                                    "depth": current_depth
                                })
                            
                            # Add node for target if not already present
                            if target_table not in [node["id"] for node in lineage_graph["nodes"]]:
                                lineage_graph["nodes"].append({
                                    "id": target_table, 
                                    "label": target_table,
                                    "depth": current_depth + 1
                                })
                            
                            # Add edge
                            lineage_graph["edges"].append({
                                "source": current_table,
                                "target": target_table,
                                "file_id": file_id
                            })
                            
                            # Recursively trace dependencies
                            trace_recursive(target_table, current_depth + 1, current_table)
            
            # Start tracing recursively from the initial table
            trace_recursive(table_name)
            
            # Generate column-level lineage for each table
            column_lineage = {}
            for node_id in [node["id"] for node in lineage_graph["nodes"]]:
                # Search for SQL files that reference this table
                query = f"table:{node_id}"
                sql_files = self.search_for_sql_files(query, limit=5)  # Limit to save resources
                
                table_columns = []
                for file_info in sql_files:
                    file_path = file_info.get("path", "")
                    file_content = file_info.get("content", "")
                    dialect = file_info.get("dialect") or self.detect_dialect(file_content, file_path)
                    
                    # Extract lineage
                    lineage_info = self.extract_lineage(file_content, dialect, file_path)
                    
                    # Get column mappings
                    if lineage_info.get("target_table") == node_id:
                        col_lineage = lineage_info.get("column_level_lineage", {})
                        for col, sources in col_lineage.items():
                            if col not in table_columns:
                                table_columns.append(col)
                
                # Store column information
                if table_columns:
                    column_lineage[node_id] = table_columns
            
            # Generate the final result
            result = {
                "table": table_name,
                "direction": direction,
                "depth_reached": max(dependencies_by_level.keys()) if dependencies_by_level else 0,
                "dependencies_by_level": dependencies_by_level,
                "lineage_graph": lineage_graph,
                "column_lineage": column_lineage,
                "total_files": len(lineage_graph["files"]),
                "total_tables": len(lineage_graph["nodes"])
            }
            
            # Add a summary for easy processing
            table_chain = []
            if direction == "upstream":
                # For upstream, we want to build a chain from the target back to sources
                levels = sorted(dependencies_by_level.keys())
                for level in levels:
                    level_tables = set()
                    for dep in dependencies_by_level[level]:
                        level_tables.add(dep["table"])
                        for src in dep.get("dependencies", []):
                            if src not in level_tables:
                                level_tables.add(src)
                    
                    table_chain.append(list(level_tables))
            else:
                # For downstream, we want to build a chain from the source to targets
                levels = sorted(dependencies_by_level.keys())
                for level in levels:
                    level_tables = set()
                    for dep in dependencies_by_level[level]:
                        level_tables.add(dep["table"])
                        if "used_by" in dep and dep["used_by"] not in level_tables:
                            level_tables.add(dep["used_by"])
                    
                    table_chain.append(list(level_tables))
            
            result["table_chain"] = table_chain
            
            # Create a text summary
            summary = f"Traced {direction} dependencies for table {table_name} to a depth of {result['depth_reached']}.\n"
            summary += f"Found {result['total_tables']} related tables across {result['total_files']} files.\n\n"
            
            if table_chain:
                if direction == "upstream":
                    summary += "Dependency chain (from target to sources):\n"
                    for i, level in enumerate(table_chain):
                        summary += f"Level {i}: {', '.join(level)}\n"
                else:
                    summary += "Usage chain (from source to targets):\n"
                    for i, level in enumerate(table_chain):
                        summary += f"Level {i}: {', '.join(level)}\n"
            
            result["summary"] = summary
            
            return result
            
        except Exception as e:
            logger.error(f"Error tracing {direction} lineage for table {table_name}: {str(e)}")
            return {
                "error": f"Error tracing lineage: {str(e)}",
                "table": table_name,
                "direction": direction
            }

    def trace_column_complete_lineage(self, table_name: str, column_name: str, 
                                     direction: str = "upstream", max_depth: int = 10) -> Dict[str, Any]:
        """
        Trace complete lineage for a specific column recursively through all dependencies
        
        Args:
            table_name: Table name
            column_name: Column name
            direction: "upstream" (sources of this column) or "downstream" (columns that use this column)
            max_depth: Maximum depth to trace dependencies
            
        Returns:
            Dictionary with complete column lineage information
        """
        try:
            logger.info(f"Tracing {direction} lineage for column {table_name}.{column_name} (max depth: {max_depth})")
            
            # Track visited columns to avoid cycles
            visited_columns = set()
            # Track the lineage graph
            lineage_graph = {
                "nodes": [],  # Table.column nodes
                "edges": [],  # Dependencies between columns
                "files": {}   # Files that define these dependencies
            }
            # Track column dependencies by level
            dependencies_by_level = {}
            
            # Function to recursively trace column dependencies
            def trace_column_recursive(current_table, current_column, current_depth=0, parent=None):
                # Stop if we've reached max depth
                if current_depth >= max_depth:
                    return
                
                # Create a unique ID for this column
                current_id = f"{current_table}.{current_column}"
                
                # Stop if we've already visited this column
                if current_id in visited_columns:
                    return
                
                # Mark this column as visited
                visited_columns.add(current_id)
                
                # Add this level to dependencies_by_level if needed
                if current_depth not in dependencies_by_level:
                    dependencies_by_level[current_depth] = []
                
                # Search for SQL files that reference this column in this table
                query = f"table:{current_table} column:{current_column}"
                sql_files = self.github_sql_finder.search_for_column(current_table, current_column, limit=20)
                
                for file_info in sql_files:
                    file_path = file_info.get("path", "")
                    file_url = file_info.get("url", "")
                    file_content = file_info.get("content", "")
                    dialect = file_info.get("dialect") or self.detect_dialect(file_content, file_path)
                    
                    # Extract lineage information
                    lineage_info = self.extract_lineage(file_content, dialect, file_path)
                    
                    if direction == "upstream":
                        # For upstream, we want to find sources of this column
                        
                        # Check if this file defines the current column
                        target_table = lineage_info.get("target_table")
                        if target_table == current_table:
                            # Check column-level lineage
                            column_mappings = lineage_info.get("column_level_lineage", {})
                            
                            if current_column in column_mappings:
                                # This file defines the column we're looking for
                                source_columns = column_mappings[current_column]
                                
                                # Store file information
                                file_id = f"file_{len(lineage_graph['files'])}"
                                lineage_graph["files"][file_id] = {
                                    "path": file_path,
                                    "url": file_url,
                                    "dialect": dialect,
                                    "defines_column": current_id
                                }
                                
                                # Add to dependencies for this level
                                dependencies_by_level[current_depth].append({
                                    "column": current_id,
                                    "file_id": file_id,
                                    "file_path": file_path,
                                    "file_url": file_url,
                                    "source_columns": source_columns
                                })
                                
                                # Add to the lineage graph
                                # Add node for current column if not already present
                                if current_id not in [node["id"] for node in lineage_graph["nodes"]]:
                                    lineage_graph["nodes"].append({
                                        "id": current_id,
                                        "table": current_table,
                                        "column": current_column,
                                        "depth": current_depth
                                    })
                                
                                # Add nodes and edges for each source column
                                for source in source_columns:
                                    source_table = source.get("table")
                                    source_column = source.get("column")
                                    
                                    if source_table and source_column:
                                        source_id = f"{source_table}.{source_column}"
                                        
                                        # Add node for source column if not already present
                                        if source_id not in [node["id"] for node in lineage_graph["nodes"]]:
                                            lineage_graph["nodes"].append({
                                                "id": source_id,
                                                "table": source_table,
                                                "column": source_column,
                                                "depth": current_depth + 1
                                            })
                                        
                                        # Add edge
                                        lineage_graph["edges"].append({
                                            "source": source_id,
                                            "target": current_id,
                                            "file_id": file_id
                                        })
                                        
                                        # Recursively trace dependencies
                                        trace_column_recursive(source_table, source_column, 
                                                            current_depth + 1, current_id)
                    
                    elif direction == "downstream":
                        # For downstream, we want to find columns that use this column
                        
                        # Check all column lineage in this file
                        target_table = lineage_info.get("target_table")
                        if target_table:
                            column_mappings = lineage_info.get("column_level_lineage", {})
                            
                            for target_column, sources in column_mappings.items():
                                # Check if any source references our current column
                                for source in sources:
                                    source_table = source.get("table")
                                    source_column = source.get("column")
                                    
                                    if source_table == current_table and source_column == current_column:
                                        # This target column uses our current column
                                        target_id = f"{target_table}.{target_column}"
                                        
                                        # Store file information
                                        file_id = f"file_{len(lineage_graph['files'])}"
                                        lineage_graph["files"][file_id] = {
                                            "path": file_path,
                                            "url": file_url,
                                            "dialect": dialect,
                                            "uses_column": current_id
                                        }
                                        
                                        # Add to dependencies for this level
                                        dependencies_by_level[current_depth].append({
                                            "column": current_id,
                                            "file_id": file_id,
                                            "file_path": file_path,
                                            "file_url": file_url,
                                            "used_by": target_id
                                        })
                                        
                                        # Add to the lineage graph
                                        # Add node for current column if not already present
                                        if current_id not in [node["id"] for node in lineage_graph["nodes"]]:
                                            lineage_graph["nodes"].append({
                                                "id": current_id,
                                                "table": current_table,
                                                "column": current_column,
                                                "depth": current_depth
                                            })
                                        
                                        # Add node for target column if not already present
                                        if target_id not in [node["id"] for node in lineage_graph["nodes"]]:
                                            lineage_graph["nodes"].append({
                                                "id": target_id,
                                                "table": target_table,
                                                "column": target_column,
                                                "depth": current_depth + 1
                                            })
                                        
                                        # Add edge
                                        lineage_graph["edges"].append({
                                            "source": current_id,
                                            "target": target_id,
                                            "file_id": file_id
                                        })
                                        
                                        # Recursively trace dependencies
                                        trace_column_recursive(target_table, target_column, 
                                                            current_depth + 1, current_id)
            
            # Start tracing recursively from the initial column
            trace_column_recursive(table_name, column_name)
            
            # Generate the final result
            result = {
                "table": table_name,
                "column": column_name,
                "direction": direction,
                "depth_reached": max(dependencies_by_level.keys()) if dependencies_by_level else 0,
                "dependencies_by_level": dependencies_by_level,
                "lineage_graph": lineage_graph,
                "total_files": len(lineage_graph["files"]),
                "total_columns": len(lineage_graph["nodes"])
            }
            
            # Add a summary for easy processing
            column_chain = []
            if direction == "upstream":
                # For upstream, we want to build a chain from the target back to sources
                levels = sorted(dependencies_by_level.keys())
                for level in levels:
                    level_columns = []
                    for dep in dependencies_by_level[level]:
                        col_id = dep["column"]
                        if col_id not in level_columns:
                            level_columns.append(col_id)
                        
                        for src_col in dep.get("source_columns", []):
                            src_table = src_col.get("table")
                            src_column = src_col.get("column")
                            if src_table and src_column:
                                src_id = f"{src_table}.{src_column}"
                                if src_id not in level_columns:
                                    level_columns.append(src_id)
                    
                    column_chain.append(level_columns)
            else:
                # For downstream, we want to build a chain from the source to targets
                levels = sorted(dependencies_by_level.keys())
                for level in levels:
                    level_columns = []
                    for dep in dependencies_by_level[level]:
                        col_id = dep["column"]
                        if col_id not in level_columns:
                            level_columns.append(col_id)
                        
                        if "used_by" in dep:
                            used_by = dep["used_by"]
                            if used_by not in level_columns:
                                level_columns.append(used_by)
                    
                    column_chain.append(level_columns)
            
            result["column_chain"] = column_chain
            
            # Create a text summary
            summary = f"Traced {direction} dependencies for column {table_name}.{column_name} to a depth of {result['depth_reached']}.\n"
            summary += f"Found {result['total_columns']} related columns across {result['total_files']} files.\n\n"
            
            if column_chain:
                if direction == "upstream":
                    summary += "Column dependency chain (from target to sources):\n"
                    for i, level in enumerate(column_chain):
                        summary += f"Level {i}: {', '.join(level)}\n"
                else:
                    summary += "Column usage chain (from source to targets):\n"
                    for i, level in enumerate(column_chain):
                        summary += f"Level {i}: {', '.join(level)}\n"
            
            result["summary"] = summary
            
            return result
            
        except Exception as e:
            logger.error(f"Error tracing {direction} lineage for column {table_name}.{column_name}: {str(e)}")
            return {
                "error": f"Error tracing column lineage: {str(e)}",
                "table": table_name,
                "column": column_name,
                "direction": direction
            }

# Singleton instance for easy access
sql_api = SQLAnalysisAPI() 