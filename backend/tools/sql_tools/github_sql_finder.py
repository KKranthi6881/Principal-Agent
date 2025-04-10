"""
GitHub SQL Finder

This module provides functionality to search for SQL files in GitHub repositories
using vector search.
"""

import os
import logging
import re
from typing import Dict, List, Set, Tuple, Optional, Any

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class GitHubSQLFinder:
    """
    GitHub SQL Finder class for searching SQL files in GitHub repositories
    """
    
    def __init__(self, vector_store_path: Optional[str] = None):
        """
        Initialize the GitHub SQL Finder
        
        Args:
            vector_store_path: Path to vector store (optional)
        """
        self.vector_store = None
        self.vector_store_path = vector_store_path
    
    def initialize(self) -> bool:
        """
        Initialize the vector store
        
        Returns:
            True if successful, False otherwise
        """
        try:
            # Import here to avoid circular imports
            from vector_store.github_vectorstore import get_github_vector_store
            
            self.vector_store = get_github_vector_store()
            if self.vector_store:
                logger.info(f"Successfully initialized GitHub vector store with {self.vector_store.count()} documents")
                return True
            else:
                logger.error("Failed to initialize GitHub vector store")
                return False
        except Exception as e:
            logger.error(f"Error initializing GitHub vector store: {str(e)}")
            return False
    
    def search_sql_files(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Search for SQL files in GitHub repositories
        
        Args:
            query: Search query
            limit: Maximum number of results
            
        Returns:
            List of SQL files with metadata
        """
        # Make sure vector store is initialized
        if not self.vector_store:
            if not self.initialize():
                return []
        
        try:
            # Add SQL file filter to query if not already present
            if 'extension:' not in query and '.sql' not in query:
                query = f"{query} extension:sql"
            
            # Search the vector store
            results = self.vector_store.query(query, n_results=limit)
            
            # Process results
            formatted_results = []
            
            # Check the structure of results and handle it appropriately
            if not results:
                return []
                
            # Check if 'metadatas' is a list of dictionaries or a list of lists
            if 'metadatas' in results:
                metadatas = results['metadatas']
                documents = results.get('documents', [])
                
                # Handle case where metadatas is a list of lists
                if metadatas and isinstance(metadatas, list):
                    if metadatas and isinstance(metadatas[0], list):
                        # It's a list of lists (older ChromaDB format)
                        metadatas = metadatas[0] if metadatas else []
                        documents = documents[0] if documents and isinstance(documents, list) and documents and isinstance(documents[0], list) else []
                
                for i, metadata in enumerate(metadatas):
                    if not metadata:
                        continue
                        
                    # Check if this is actually a SQL file
                    file_path = metadata.get('file_path', '')
                    file_ext = metadata.get('file_extension', '')
                    
                    # Skip non-SQL files
                    if not file_path.lower().endswith('.sql') and not file_ext.lower() == 'sql':
                        continue
                    
                    # Get content
                    content = documents[i] if i < len(documents) else ''
                    
                    # Get repository URL properly
                    repo_url = metadata.get('repo_url', '')
                    
                    # Build proper URL with file path
                    url = f"{repo_url}/blob/main/{file_path}" if repo_url else None
                    
                    # Create formatted result with consistent keys
                    formatted_result = {
                        'file_path': file_path,
                        'content': content,
                        'url': url,
                        'github_repo': repo_url,
                        'path': file_path,  # Add for backward compatibility with older code
                        'dialect': self._detect_dialect(file_path, content)
                    }
                    
                    formatted_results.append(formatted_result)
            
            logger.info(f"Found {len(formatted_results)} SQL files in search results")
            return formatted_results
            
        except Exception as e:
            logger.error(f"Error searching for SQL files: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return []
    
    def search_for_table(self, table_name: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Search for SQL files that reference a specific table
        
        Args:
            table_name: Table name to search for
            limit: Maximum number of results
            
        Returns:
            List of SQL files with metadata
        """
        query = f"extension:sql {table_name}"
        # Additional DBT-specific patterns
        dbt_ref_query = f'ref("{table_name}") OR ref(\'{table_name}\')'
        source_query = f'source OR table:{table_name} OR "{table_name}" OR \'{table_name}\''
        
        # Combine queries
        combined_query = f"{query} {dbt_ref_query} {source_query}"
        
        return self.search_sql_files(combined_query, limit)
    
    def search_for_column(self, table_name: str, column_name: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Search for SQL files that reference a specific column in a table
        
        Args:
            table_name: Table name
            column_name: Column name
            limit: Maximum number of results
            
        Returns:
            List of SQL files with metadata
        """
        # Generate different ways the column might be referenced in SQL
        column_patterns = []
        
        # If table name is provided, add table-qualified patterns
        if table_name:
            column_patterns.extend([
                f"{table_name}.{column_name}",  # direct reference
                f'"{table_name}"."{column_name}"',  # quoted reference (double quotes)
                f"'{table_name}'.'{column_name}'",  # quoted reference (single quotes)
                f"{table_name}.{column_name} as",  # column alias pattern
                f"from {table_name}",  # from clause containing the table
            ])
        
        # Add common patterns for column references
        column_patterns.extend([
            f"select {column_name}",  # direct in select list
            f"SELECT {column_name}",  # uppercase variant
            f"as {column_name}",  # column alias
            f"AS {column_name}",  # uppercase alias
            f", {column_name}",  # column in list
            f"{column_name} =",  # column in where/join clause
            f"{column_name},",  # column in select list
            f"{column_name} as",  # column with alias
            f"{column_name} from"  # column before from clause
        ])
        
        # Additional patterns for SQL frameworks like DBT
        column_patterns.extend([
            f"field('{column_name}'",  # dbt field reference
            f"\"column\": \"{column_name}\"",  # JSON column reference
            f"column: {column_name}",  # YAML column reference
            f"`{column_name}`",  # backtick quoting (MySQL, BigQuery)
            f"[{column_name}]"  # bracket quoting (SQL Server)
        ])
        
        # Convert patterns to query with OR
        query = " OR ".join([f'"{pattern}"' for pattern in column_patterns])
        
        # Add simple column name search at the end
        query = f"extension:sql ({query} OR {column_name})"
        
        # Run the search
        results = self.search_sql_files(query, limit)
        
        # Post-process to improve relevance
        if results:
            # Prioritize results that have the column name in a more specific context
            for result in results:
                # Check content for relevant patterns
                content = result.get("content", "").lower()
                if content:
                    # Calculate relevance score based on pattern matches
                    score = 0
                    
                    # Higher score for table-qualified references
                    if table_name and f"{table_name.lower()}.{column_name.lower()}" in content:
                        score += 5
                    
                    # Medium score for column in select list or join/where conditions
                    if any(pattern.lower() in content for pattern in [
                        f"select {column_name.lower()}",
                        f", {column_name.lower()},",
                        f"{column_name.lower()} as",
                        f"{column_name.lower()} =",
                        f"{column_name.lower()} from"
                    ]):
                        score += 3
                    
                    # Base score for any mention
                    score += 1
                    
                    # Store score in result
                    result["relevance_score"] = score
            
            # Sort by relevance score
            results.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
        
        return results
    
    def _detect_dialect(self, file_path: str, content: str, connector_tech_stack: str = None) -> str:
        """
        Detect SQL dialect from file path, content, and connector settings
        
        Args:
            file_path: Path to the SQL file
            content: SQL file content
            connector_tech_stack: Tech stack specified in the connector settings
            
        Returns:
            Detected dialect name
        """
        # If the connector has a specified tech stack, use it as the primary dialect
        if connector_tech_stack and connector_tech_stack in ['postgresql', 'mysql', 'snowflake', 'tsql', 'dbt']:
            return connector_tech_stack
        
        # Check file path for clues
        file_path_lower = file_path.lower()
        
        # Check for DBT
        if any(pattern in file_path_lower for pattern in ['/models/', '/dbt/', '/macros/', '/analysis/']):
            return 'dbt'
        
        # Check for Snowflake
        if '/snowflake/' in file_path_lower or 'snowflake_' in file_path_lower:
            return 'snowflake'
        
        # Check for PostgreSQL
        if any(pattern in file_path_lower for pattern in ['/postgres/', 'postgresql', '.pg.sql']):
            return 'postgresql'
            
        # Check for MySQL
        if '/mysql/' in file_path_lower or '.mysql.' in file_path_lower:
            return 'mysql'
            
        # Check for SQL Server
        if any(pattern in file_path_lower for pattern in ['/sqlserver/', 'tsql', 'mssql']):
            return 'tsql'
        
        # Check content for dialect-specific patterns
        content_lower = content.lower()[:4000] if content else ''  # Limit content to avoid performance issues
        
        # Check for DBT
        if '{{' in content_lower and ('ref(' in content_lower or 'source(' in content_lower):
            return 'dbt'
            
        # Check for Snowflake
        if any(pattern in content_lower for pattern in ['lateral flatten', '$$', 'copy into']):
            return 'snowflake'
            
        # Check for PostgreSQL
        if any(pattern in content_lower for pattern in ['with ordinality', 'returning', 'jsonb']):
            return 'postgresql'
            
        # Check for MySQL
        if any(pattern in content_lower for pattern in ['force index', 'using index', 'engine=innodb']):
            return 'mysql'
            
        # Check for SQL Server
        if any(pattern in content_lower for pattern in ['for system_time', 'output inserted', 'merge into']):
            return 'tsql'
            
        # Default to PostgreSQL
        return 'postgresql'

    def process_file(self, file_path: str, content: str, connector_tech_stack: str = None) -> Dict[str, Any]:
        """
        Process a SQL file to extract table references and structure.
        
        Args:
            file_path: Path to the SQL file
            content: SQL file content
            connector_tech_stack: Tech stack specified in the connector
            
        Returns:
            Dictionary with file information, table references, and structure
        """
        try:
            # Check if this is a SQL file
            if not self._is_sql_file(file_path):
                return None
            
            # Detect SQL dialect
            dialect = self._detect_dialect(file_path, content, connector_tech_stack)
            logger.info(f"Detected dialect '{dialect}' for file '{file_path}' (connector_tech_stack={connector_tech_stack})")
            
            # Extract references and structure
            references = self._extract_references(content, dialect)
            structure = self._extract_structure(content, dialect)
            
            # Return the file info with dialect
            return {
                'file_path': file_path,
                'dialect': dialect,
                'references': references,
                'structure': structure
            }
        except Exception as e:
            logger.error(f"Error processing SQL file '{file_path}': {str(e)}")
            return {
                'file_path': file_path,
                'dialect': connector_tech_stack or 'postgresql',
                'references': [],
                'structure': {}
            }

    def _is_sql_file(self, file_path: str) -> bool:
        """
        Check if a file is an SQL file based on its extension
        
        Args:
            file_path: Path to the file
            
        Returns:
            True if the file is an SQL file, False otherwise
        """
        # Check file extension
        if file_path.lower().endswith('.sql'):
            return True
        
        # Get the file extension
        file_ext = file_path.split('.')[-1].lower() if '.' in file_path else ''
        return file_ext == 'sql'

    def _extract_references(self, content: str, dialect: str = 'postgresql') -> List[Dict[str, str]]:
        """
        Extract table references from SQL content
        
        Args:
            content: SQL content
            dialect: SQL dialect (postgresql, snowflake, etc.)
            
        Returns:
            List of table references
        """
        references = []
        
        try:
            # Special handling for dbt dialect
            if dialect == 'dbt':
                # Look for ref() function calls
                ref_pattern = r'\{\{\s*ref\s*\(\s*[\'"](.*?)[\'"]\s*\)\s*\}\}'
                ref_matches = re.findall(ref_pattern, content)
                for ref in ref_matches:
                    references.append({
                        'table': ref,
                        'type': 'dbt_ref',
                        'schema': None
                    })
                    
                # Look for source() function calls
                source_pattern = r'\{\{\s*source\s*\(\s*[\'"](.*?)[\'"]\s*,\s*[\'"](.*?)[\'"]\s*\)\s*\}\}'
                source_matches = re.findall(source_pattern, content)
                for source in source_matches:
                    references.append({
                        'table': source[1],
                        'type': 'dbt_source',
                        'schema': source[0]  # source name is like a schema
                    })
                    
                # Also try to extract standard SQL references
                
            # For standard SQL dialects
            # (Keep existing code for non-dbt dialects)
            
            # Very simple regex pattern to find potential table references
            # This is a naive approach and might miss complex cases
            table_pattern = r'\bFROM\s+([a-zA-Z0-9_\.]+)|JOIN\s+([a-zA-Z0-9_\.]+)'
            matches = re.finditer(table_pattern, content, re.IGNORECASE)
            
            for match in matches:
                table_name = match.group(1) if match.group(1) else match.group(2)
                if not table_name:
                    continue
                    
                # Handle schema.table format
                if '.' in table_name:
                    schema, table = table_name.split('.', 1)
                    references.append({
                        'table': table,
                        'type': 'table',
                        'schema': schema
                    })
                else:
                    references.append({
                        'table': table_name,
                        'type': 'table',
                        'schema': None
                    })
        except Exception as e:
            # Log error but continue
            print(f"Error extracting references: {str(e)}")
        
        return references 

    def _extract_structure(self, content: str, dialect: str = 'postgresql') -> Dict[str, Any]:
        """
        Extract table structure from SQL content
        
        Args:
            content: SQL content
            dialect: SQL dialect (postgresql, snowflake, etc.)
            
        Returns:
            Dictionary with table structure information
        """
        structure = {
            'columns': [],
            'table_type': 'unknown',
        }
        
        try:
            # Extract column definitions
            # For dbt, we need to handle differently
            if dialect == 'dbt':
                # For DBT models, extract columns from the SELECT statement
                # This is a simplified approach
                structure['table_type'] = 'dbt_model'
                
                # See if it's an incremental model
                if '{{ config(' in content and 'incremental' in content:
                    structure['table_type'] = 'dbt_incremental'
                
                # Match column definitions in SELECT clauses
                # This regex tries to capture expressions with aliases
                column_pattern = r'SELECT\s+.*?\s+as\s+([a-zA-Z0-9_]+)|,\s*.*?\s+as\s+([a-zA-Z0-9_]+)'
                col_matches = re.finditer(column_pattern, content, re.IGNORECASE | re.DOTALL)
                
                for match in col_matches:
                    col_name = match.group(1) if match.group(1) else match.group(2)
                    if col_name:
                        structure['columns'].append({
                            'name': col_name,
                            'data_type': 'unknown',  # Hard to determine type in dbt
                            'description': ''
                        })
            else:
                # For regular SQL, try to extract from CREATE TABLE or similar
                if 'CREATE TABLE' in content.upper():
                    structure['table_type'] = 'table'
                elif 'CREATE VIEW' in content.upper():
                    structure['table_type'] = 'view'
                elif 'CREATE MATERIALIZED VIEW' in content.upper():
                    structure['table_type'] = 'materialized_view'
                
                # Basic pattern to match column definitions in CREATE statements
                # Note: This is a simplified approach and won't work for all SQL dialects
                column_pattern = r'`?([a-zA-Z0-9_]+)`?\s+([a-zA-Z0-9_]+(?:\([^)]+\))?)'
                col_matches = re.finditer(column_pattern, content)
                
                for match in col_matches:
                    structure['columns'].append({
                        'name': match.group(1),
                        'data_type': match.group(2),
                        'description': ''
                    })
                    
                # If no columns found with the above pattern, try a more general approach
                if not structure['columns']:
                    # Try to extract from SELECT statements (for views and CTEs)
                    column_pattern = r'SELECT\s+.*?\s+as\s+([a-zA-Z0-9_]+)|,\s*.*?\s+as\s+([a-zA-Z0-9_]+)'
                    col_matches = re.finditer(column_pattern, content, re.IGNORECASE | re.DOTALL)
                    
                    for match in col_matches:
                        col_name = match.group(1) if match.group(1) else match.group(2)
                        if col_name:
                            structure['columns'].append({
                                'name': col_name,
                                'data_type': 'unknown',
                                'description': ''
                            })
        except Exception as e:
            # Log error but continue
            print(f"Error extracting structure: {str(e)}")
        
        return structure 