"""
SQL Analysis API

This module provides a unified API for SQL analysis capabilities including
parsing, dependency extraction, and lineage analysis.
"""

import os
import logging
import json
from typing import Dict, List, Set, Tuple, Optional, Any
import re

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
        self.github_wrapper = None
        self.github_sql_finder = None
        self.lineage_extractor = None
        self.dependency_tool = None
        self.dialect_cache = {}  # Cache for dialect parsers
        
        # Initialize components that don't require GitHub
        self._initialize_base_components()
    
    def _initialize_base_components(self):
        """Initialize components that don't require GitHub integration"""
        try:
            # Import here to avoid circular imports
            from .lineage import SQLGlotLineageExtractor
            self.lineage_extractor = SQLGlotLineageExtractor()
            
            # Initialize GitHub SQL finder without wrapper
            from .github_sql_finder import GitHubSQLFinder
            self.github_sql_finder = GitHubSQLFinder(self.vector_store_path)
            self.github_sql_finder.initialize()
            
            logger.info("Initialized base SQL API components")
            
        except Exception as e:
            logger.error(f"Error initializing base components: {str(e)}")
            raise
    
    def initialize_with_github(self, github_wrapper):
        """
        Initialize the API with a GitHub wrapper
        
        Args:
            github_wrapper: Initialized GitHubAPIWrapper instance
        """
        try:
            self.github_wrapper = github_wrapper
            
            # Re-initialize GitHub SQL finder with wrapper
            if self.github_sql_finder:
                self.github_sql_finder = GitHubSQLFinder(
                    self.vector_store_path, 
                    github_wrapper=github_wrapper
                )
                self.github_sql_finder.initialize()
            
            # Initialize dependency tool
            from .dependency_analyzer import SQLDependencyTool
            self.dependency_tool = SQLDependencyTool(
                vector_store_path=self.vector_store_path,
                github_wrapper=github_wrapper
            )
            
            # Initialize the dependency tool
            if hasattr(self.dependency_tool, 'initialize'):
                self.dependency_tool.initialize()
            
            logger.info("Successfully initialized SQL API with GitHub wrapper")
            
        except Exception as e:
            logger.error(f"Error initializing SQL API with GitHub: {str(e)}")
            raise

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
            # Use dependency tool if available
            if self.dependency_tool and hasattr(self.dependency_tool, 'search_for_table'):
                logger.info(f"Using dependency_tool to search for table: {table_name}")
                return self.dependency_tool.search_for_table(table_name, limit)
                
            # Fallback to GitHub SQL finder if available
            if self.github_sql_finder and hasattr(self.github_sql_finder, 'search_for_table'):
                logger.info(f"Using github_sql_finder to search for table: {table_name}")
                results = self.github_sql_finder.search_for_table(table_name, limit)
                
                # Format results to match expected output format if needed
                if isinstance(results, list):
                    return {"files_found": len(results), "results": results}
                return results
            
            # Fallback to direct GitHub search if available
            if self.github_wrapper:
                logger.info(f"Using github_wrapper to search for table: {table_name}")
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
            
            # No search method available
            return {"error": "No table search method available", "files_found": 0, "results": []}
            
        except Exception as e:
            logger.error(f"Error searching for table {table_name}: {str(e)}")
            return {"error": str(e), "files_found": 0, "results": []}
    
    def search_for_column(self, table_name: str, column_name: str, limit: int = 20) -> Dict[str, Any]:
        """
        Search for SQL files that reference a specific column in a table
        
        Args:
            table_name: Table name
            column_name: Column name
            limit: Maximum number of results
            
        Returns:
            List of matching SQL files with metadata
        """
        try:
            # Use dependency tool if available
            if self.dependency_tool and hasattr(self.dependency_tool, 'search_for_column'):
                logger.info(f"Using dependency_tool to search for column: {column_name} in table: {table_name}")
                return self.dependency_tool.search_for_column(table_name, column_name, limit)
            
            # Use github_sql_finder if available
            if self.github_sql_finder and hasattr(self.github_sql_finder, 'search_for_column'):
                logger.info(f"Using github_sql_finder to search for column: {column_name}")
                results = self.github_sql_finder.search_for_column(table_name, column_name, limit)
                
                # Format results to match expected output format if needed
                if isinstance(results, list):
                    return {"files_found": len(results), "results": results}
                return results
            
            # Fallback to general search
            if self.github_sql_finder and hasattr(self.github_sql_finder, 'search_sql_files'):
                query = f"{column_name}"
                if table_name:
                    query = f"{table_name}.{column_name}"
                    
                results = self.github_sql_finder.search_sql_files(query, limit)
                
                # Format results if needed
                if isinstance(results, list):
                    return {"files_found": len(results), "results": results}
                return results
            
            # No search method available
            return {"error": "No column search method available", "files_found": 0, "results": []}
            
        except Exception as e:
            logger.error(f"Error searching for column {table_name}.{column_name}: {str(e)}")
            return {"error": str(e), "files_found": 0, "results": []}
    
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
    
    def analyze_repository(self, repo_url: str, dialect: Optional[str] = None, tech_stack: Optional[str] = None) -> Dict[str, Any]:
        """
        Analyze SQL files in a GitHub repository
        
        Args:
            repo_url: GitHub repository URL
            dialect: SQL dialect to use (if None, will be auto-detected for each file)
            tech_stack: Tech stack specified in connector settings
            
        Returns:
            Dictionary with analysis results
        """
        try:
            # Use tech_stack if provided as the default dialect
            default_dialect = tech_stack or dialect
            
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
                # Use tech_stack as the primary dialect choice if available
                file_dialect = default_dialect or file_info.get("dialect") or self.detect_dialect(file_content, file_path)
                
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
                "tech_stack": tech_stack,
                "file_count": len(results),
                "results": results
            }
            
        except Exception as e:
            logger.error(f"Error analyzing repository: {str(e)}")
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
            if not self.dependency_tool:
                # Try to get dependency tool as fallback
                if not hasattr(self, 'github_sql_finder') or not self.github_sql_finder:
                    logger.info("Using dependency_tool to search for column: %s in table: %s", column_name, table_name)
                    # This is the alternate GitHub search path
                    return self._search_column_fallback(table_name, column_name)
                else:
                    logger.error("No dependency tool available for column lineage tracing")
                    return {"error": "No dependency tool available for column lineage"}
            
            lineage_result = self.dependency_tool.get_column_lineage(
                target_table=table_name or "",
                column_name=column_name,
                depth=5
            )
            
            logger.info("Received column lineage result with keys: %s", lineage_result.keys() if isinstance(lineage_result, dict) else "Not a dict")
            
            if not lineage_result or (isinstance(lineage_result, dict) and "error" in lineage_result):
                logger.info("Trying fallback search for column '%s'", column_name)
                return self._search_column_fallback(table_name, column_name)
                
            return lineage_result
            
        except Exception as e:
            logger.error("Error in column lineage tracing: %s", str(e))
            # Try fallback search method if lineage fails
            logger.info("Trying fallback search for column '%s'", column_name)
            return self._search_column_fallback(table_name, column_name)
            
    def _search_column_fallback(self, table_name: str, column_name: str):
        """
        Fallback search method for column when lineage tracing fails
        
        Args:
            table_name: Table name (can be empty)
            column_name: Column name to search for
            
        Returns:
            Search results dictionary
        """
        logger.info("Using dependency_tool to search for column: %s in table: %s", column_name, table_name)
        
        # Build advanced search query for column
        search_query = self._build_column_search_query(column_name)
        
        # Execute search
        if self.github_sql_finder:
            results = self.github_sql_finder.search_sql_files(search_query)
            
            # Filter results to prioritize relevant matches
            if results:
                # Try to find files where the column appears in meaningful context
                filtered_results = []
                for file in results:
                    if isinstance(file, dict) and "content" in file:
                        content = file["content"]
                        # Check for patterns that suggest column definition or usage
                        if self._is_column_relevant(content, column_name):
                            filtered_results.append(file)
                
                if filtered_results:
                    return {
                        "search_results": filtered_results,
                        "column_name": column_name,
                        "table_name": table_name or "unknown",
                        "search_method": "vector_search"
                    }
            
            return {
                "search_results": results,
                "column_name": column_name,
                "table_name": table_name or "unknown",
                "search_method": "vector_search"
            }
        else:
            return {"error": "GitHub SQL finder not initialized", "column_name": column_name}
    
    def _build_column_search_query(self, column_name: str) -> str:
        """
        Build a comprehensive search query for column searches
        
        Args:
            column_name: Column name to search for
            
        Returns:
            Enhanced search query string
        """
        # Create combinations of patterns that might identify column definitions or usage
        patterns = [
            f'"{column_name}" as',
            f'select {column_name}',
            f'definition',
            f'usage',
            f'table',
            f'column'
        ]
        
        # Build OR query with all combinations
        query_parts = []
        for i in range(0, len(patterns), 2):
            if i + 1 < len(patterns):
                query_parts.append(f"{patterns[i]} OR {patterns[i+1]} {column_name}")
        
        # Add extension filter
        query = " OR ".join(query_parts) + " extension:sql"
        return query
    
    def _is_column_relevant(self, content: str, column_name: str) -> bool:
        """
        Check if a file's content is relevant to the column we're searching for
        
        Args:
            content: File content to check
            column_name: Column name we're searching for
            
        Returns:
            True if the content is relevant to the column
        """
        if not content:
            return False
            
        # Define patterns that suggest column definition or meaningful usage
        patterns = [
            # Column definition patterns
            rf"CREATE\s+TABLE.*{column_name}",
            rf"{column_name}\s+AS\s+",
            rf"SELECT.*{column_name}\s+AS",
            rf"SELECT.*AS\s+{column_name}",
            rf"{column_name}\s+[A-Za-z0-9_]+\s*[,)]",  # Column in table definition
            
            # Column usage patterns
            rf"WHERE\s+.*{column_name}\s*=",
            rf"GROUP\s+BY\s+.*{column_name}",
            rf"ORDER\s+BY\s+.*{column_name}",
            rf"JOIN\s+.*ON\s+.*{column_name}\s*=",
        ]
        
        # Check each pattern
        for pattern in patterns:
            if re.search(pattern, content, re.IGNORECASE | re.DOTALL):
                return True
                
        return False
    
    def trace_column_complete_lineage(self, table_name: str, column_name: str, direction="upstream", max_depth=5):
        """
        Trace complete column lineage with multiple strategies
        
        Args:
            table_name: Table name (can be empty)
            column_name: Column name to trace
            direction: Direction of lineage (upstream/downstream)
            max_depth: Maximum depth to traverse
            
        Returns:
            Dictionary with complete lineage information
        """
        # First try the regular lineage method
        lineage_result = self.trace_column_lineage(table_name, column_name)
        
        # If that didn't work, try direct file search
        if not lineage_result or (isinstance(lineage_result, dict) and "error" in lineage_result):
            search_results = self._search_column_fallback(table_name, column_name)
            
            # Transform search results into a lineage-like structure
            files = search_results.get("search_results", [])
            lineage_structure = {
                "column_name": column_name,
                "table_name": table_name or "unknown",
                "files_found": len(files),
                "lineage_method": "search_based",
                "sources": []
            }
            
            # Extract potential source columns from files
            for file in files:
                if isinstance(file, dict) and "content" in file:
                    source_columns = self._extract_potential_source_columns(file["content"], column_name)
                    if source_columns:
                        file_info = {
                            "file_path": file.get("path", "unknown"),
                            "github_url": file.get("github_url", ""),
                            "source_columns": source_columns
                        }
                        lineage_structure["sources"].append(file_info)
            
            return lineage_structure
            
        # Return the original lineage result if it worked
        return lineage_result
        
    def _extract_potential_source_columns(self, content: str, target_column: str) -> List[Dict[str, str]]:
        """
        Extract potential source columns used to compute the target column
        
        Args:
            content: SQL content to analyze
            target_column: Target column name
            
        Returns:
            List of potential source columns
        """
        source_columns = []
        
        # Look for common patterns where the target column is defined
        patterns = [
            # SELECT col1 + col2 AS target_column
            rf"SELECT\s+(.{{1,100}})\s+AS\s+{target_column}",
            # target_column = col1 + col2
            rf"{target_column}\s*=\s*(.{{1,100}})[,\n]"
        ]
        
        for pattern in patterns:
            matches = re.finditer(pattern, content, re.IGNORECASE | re.DOTALL)
            for match in matches:
                if match.group(1):
                    # Extract potential column names from the expression
                    expr = match.group(1)
                    # Look for word-like tokens that could be column names
                    potential_columns = re.findall(r'[a-zA-Z][a-zA-Z0-9_]*', expr)
                    for col in potential_columns:
                        # Skip common SQL keywords and functions
                        if col.lower() not in ["select", "from", "where", "and", "or", "sum", "count", "avg", "min", "max"]:
                            source_columns.append({
                                "name": col,
                                "table": "unknown", # We don't know the table
                                "confidence": "medium"
                            })
        
        return source_columns
    
    def trace_complete_lineage(self, table_name: str, direction: str = "upstream", 
                              max_depth: int = 5, dialect: Optional[str] = None) -> Dict[str, Any]:
        """
        Trace complete lineage for a table in either upstream or downstream direction
        
        Args:
            table_name: Target table name
            direction: "upstream" or "downstream"
            max_depth: Maximum depth to trace
            dialect: SQL dialect to use
            
        Returns:
            Dict with complete lineage information
        """
        # Validate direction
        if direction not in ["upstream", "downstream"]:
            return {"error": f"Invalid direction: {direction}. Must be 'upstream' or 'downstream'"}
        
        # Import dependency tool if not already available
        if not self.dependency_tool:
            try:
                from .dependency_analyzer import SQLDependencyTool
                self.dependency_tool = SQLDependencyTool(self.vector_store_path)
                self.dependency_tool.initialize()
            except Exception as e:
                logger.error(f"Error initializing dependency tool: {str(e)}")
                return {"error": f"Error initializing dependency tool: {str(e)}"}
        
        try:
            # Use dialect-specific dependency analyzer if specified
            if dialect:
                self.dependency_tool.dependency_analyzer = self.dependency_tool.dependency_analyzer.__class__(dialect=dialect)
            
            # Trace dependencies using the dependency tool
            if direction == "upstream":
                dependencies = self.dependency_tool.trace_table_dependencies(
                    target_table=table_name,
                    depth=max_depth,
                    dialect=dialect
                )
            else:
                # Not implemented in this version
                return {"error": "Downstream tracing not yet implemented"}
            
            # If there was an error, return it
            if "error" in dependencies:
                return dependencies
            
            # Extract files by level
            files_by_level = {}
            
            # Extract sources and targets from dependencies
            source_targets = {}
            for dep in dependencies.get("upstream_dependencies", []):
                source = dep.get("source")
                target = dep.get("target")
                depth = dep.get("depth", 0)
                
                # Create level entry if it doesn't exist
                if depth not in files_by_level:
                    files_by_level[depth] = []
                
                # Extract file details
                for file_detail in dep.get("file_details", []):
                    # Create file info with necessary details
                    file_info = {
                        "file_path": file_detail.get("path", ""),
                        "url": file_detail.get("github_url", ""),
                        "github_repo": file_detail.get("github_repo", ""),
                        "dialect": file_detail.get("dialect", "unknown"),
                        "target_table": target,
                        "source_tables": [source]
                    }
                    
                    # Add to files by level
                    files_by_level[depth].append(file_info)
                    
                    # Update source-target mapping
                    key = f"{source}_{target}"
                    if key not in source_targets:
                        source_targets[key] = {
                            "source": source,
                            "target": target,
                            "files": []
                        }
                    source_targets[key]["files"].append(file_detail.get("path", ""))
            
            # Also include the source files from the dependency tool
            source_files = dependencies.get("source_files", [])
            
            # Calculate maximum depth reached
            max_depth_reached = max(files_by_level.keys()) if files_by_level else 0
            
            # Get a list of all files
            all_files = set()
            for level, files in files_by_level.items():
                for file in files:
                    all_files.add(file["file_path"])
            
            # Create summary
            summary = dependencies.get("summary", {})
            
            # Create the complete result
            result = {
                "table_name": table_name,
                "direction": direction,
                "max_depth": max_depth,
                "max_depth_reached": max_depth_reached,
                "files_by_level": files_by_level,
                "source_targets": list(source_targets.values()),
                "total_files": len(all_files),
                "dialect_used": dialect or self.dependency_tool.dependency_analyzer.dialect,
                "source_files": source_files,
                "summary": summary
            }
            
            # Generate a natural language summary
            nl_summary = f"Analysis of {table_name} {direction} dependencies:\n"
            nl_summary += f"- Found {len(all_files)} relevant SQL files\n"
            nl_summary += f"- Traced dependencies across {max_depth_reached} levels\n"
            
            if summary:
                nl_summary += f"- Identified {summary.get('unique_source_tables', 0)} source tables\n"
                nl_summary += f"- Found in {len(summary.get('github_repos', []))} GitHub repositories\n"
            
            # Add a list of all repositories
            if summary and summary.get("github_repos"):
                nl_summary += "\nFound in repositories:\n"
                for repo in summary["github_repos"]:
                    nl_summary += f"- {repo}\n"
            
            result["summary"] = nl_summary
            
            # Try to extract additional information from source files
            if not files_by_level and source_files:
                # If we didn't find any structured dependencies but have source files,
                # create a simple level 0 with these files
                files_by_level[0] = []
                
                for sf in source_files:
                    files_by_level[0].append({
                        "file_path": sf.get("path", ""),
                        "url": sf.get("url", ""),
                        "github_repo": sf.get("github_repo", ""),
                        "dialect": sf.get("dialect", "unknown"),
                        "target_table": table_name,
                        "source_tables": []  # Unknown sources
                    })
                
                result["files_by_level"] = files_by_level
                result["max_depth_reached"] = 0
            
            return result
            
        except Exception as e:
            logger.error(f"Error tracing complete lineage: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return {"error": f"Error tracing complete lineage: {str(e)}"}

    def summarize_sql_file(self, content: str) -> str:
        """Generate a brief summary of SQL file contents"""
        try:
            # Remove comments and empty lines
            clean_content = "\n".join(
                line.strip() 
                for line in content.split("\n") 
                if line.strip() and not line.strip().startswith("--")
            )
            
            # Extract key components
            components = []
            
            if "CREATE TABLE" in clean_content.upper():
                components.append("Creates table")
            if "INSERT INTO" in clean_content.upper():
                components.append("Inserts data")
            if "UPDATE" in clean_content.upper():
                components.append("Updates data")
            if "DELETE" in clean_content.upper():
                components.append("Deletes data")
            if "WITH" in clean_content.upper():
                components.append("Uses CTEs")
            if "JOIN" in clean_content.upper():
                components.append("Performs joins")
            if "GROUP BY" in clean_content.upper():
                components.append("Aggregates data")
            
            if not components:
                components.append("Queries data")
                
            return "; ".join(components)
            
        except Exception as e:
            logger.error(f"Error summarizing SQL file: {str(e)}")
            return "Failed to generate summary"

    def detect_dialect_from_repo_url(self, repo_url: str) -> str:
        """
        Detect the appropriate SQL dialect based on repository URL patterns
        
        Args:
            repo_url: GitHub repository URL
            
        Returns:
            Detected dialect name (postgresql, snowflake, dbt, etc.)
        """
        if not repo_url:
            return "postgresql"  # Default dialect
            
        repo_url = repo_url.lower()
        
        # Check for DBT repositories
        if any(pattern in repo_url for pattern in ['/dbt-', '/dbt_', '/dbt/', 'dbt-labs', 'jaffle_shop']):
            # Use minimal logging for LLM-friendly output
            return "dbt"
        
        # Check for Snowflake repositories
        if any(pattern in repo_url for pattern in ['/snowflake-', '/snowflake_', '/snowflake/']):
            return "snowflake"
        
        # Check for PostgreSQL repositories
        if any(pattern in repo_url for pattern in ['/postgres-', '/postgres_', '/postgresql']):
            return "postgresql"
        
        # Check for MySQL repositories
        if any(pattern in repo_url for pattern in ['/mysql-', '/mysql_', '/mysql']):
            return "mysql"
        
        # Check for SQL Server repositories
        if any(pattern in repo_url for pattern in ['/sqlserver', '/tsql', '/mssql']):
            return "tsql"
            
        # Default to PostgreSQL
        return "postgresql"
    
    def detect_dialect_from_file_path(self, file_path: str) -> str:
        """
        Detect the appropriate SQL dialect based on file path patterns
        
        Args:
            file_path: Path to the SQL file
            
        Returns:
            Detected dialect name (postgresql, snowflake, dbt, etc.)
        """
        file_path = file_path.lower()
        
        # Check for DBT models
        if '/dbt/' in file_path or '/models/' in file_path or file_path.endswith('.sql') and ('/transform/' in file_path or '/transformations/' in file_path):
            return "dbt"
        
        # Check for Snowflake scripts
        if any(pattern in file_path for pattern in ['/snowflake/', '.snowflake.sql', 'snowflake_']):
            return "snowflake"
        
        # Check for PostgreSQL scripts
        if any(pattern in file_path for pattern in ['/postgres/', '.pg.sql', 'postgresql', '.pgsql']):
            return "postgresql"
        
        # Check for MySQL scripts
        if any(pattern in file_path for pattern in ['/mysql/', '.mysql.sql', 'mysql_']):
            return "mysql"
        
        # Check for SQL Server/TSQL scripts
        if any(pattern in file_path for pattern in ['/sqlserver/', '.tsql', '.mssql', 'sql-server']):
            return "tsql"
        
        # Default to PostgreSQL as the most common dialect
        return "postgresql"
    
# Define SQLAPI as an alias for SQLAnalysisAPI for backward compatibility
class SQLAPI(SQLAnalysisAPI):
    """
    Alias for SQLAnalysisAPI for backward compatibility
    """
    pass

# Singleton instance for easy access
sql_api = SQLAnalysisAPI() 