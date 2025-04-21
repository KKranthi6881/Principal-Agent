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
    
    def __init__(self, vector_store_path: Optional[str] = None, github_wrapper=None):
        """
        Initialize the GitHub SQL Finder
        
        Args:
            vector_store_path: Path to vector store (optional)
            github_wrapper: GitHub API wrapper instance (optional)
        """
        self.vector_store = None
        self.vector_store_path = vector_store_path
        self.github_wrapper = github_wrapper
    
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
                logger.error("Failed to initialize GitHub vector store for search")
                return []
        
        try:
            # Detect query type and enhance the query
            query_type = self._detect_query_type(query)
            enhanced_query = self._enhance_query(query, query_type)
            
            # Add SQL file filter to query if not already present
            if 'extension:' not in enhanced_query and '.sql' not in enhanced_query:
                enhanced_query = f"{enhanced_query} extension:sql"
            
            # Log the query being used
            logger.info(f"Searching vector store with query: '{enhanced_query}'")
            
            # Search the vector store
            results = self.vector_store.query(enhanced_query, n_results=limit)
            
            # Process results
            formatted_results = []
            
            # Check the structure of results and handle it appropriately
            if not results:
                logger.warning("Vector store returned empty results")
                # Try fallback search if primary search fails
                return self._perform_fallback_search(query, limit)
            
            # Check the structure of results and handle it appropriately
            if 'metadatas' in results:
                metadatas = results['metadatas']
                documents = results.get('documents', [])
                
                logger.info(f"Found {len(metadatas)} metadata items and {len(documents)} document items")
                
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
                    if not repo_url:
                        # Try alternative field names
                        repo_url = metadata.get('github_repo', metadata.get('repository_url', ''))
                    
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
            # Alternative structure handling
            elif isinstance(results, list):
                logger.info("Vector store returned list format")
                # Assume direct list of results
                for result in results:
                    if isinstance(result, dict):
                        file_path = result.get('file_path', result.get('path', ''))
                        
                        # Skip non-SQL files
                        if not file_path.lower().endswith('.sql'):
                            continue
                        
                        content = result.get('content', result.get('text', ''))
                        
                        # Create formatted result
                        formatted_result = {
                            'file_path': file_path,
                            'content': content,
                            'url': result.get('url', ''),
                            'github_repo': result.get('repo_url', result.get('github_repo', '')),
                            'path': file_path,
                            'dialect': self._detect_dialect(file_path, content)
                        }
                        
                        formatted_results.append(formatted_result)
            
            logger.info(f"Found {len(formatted_results)} SQL files in search results")
            
            # If we found no results, return a helpful error 
            if not formatted_results:
                logger.warning(f"No SQL files found matching query: {query}")
                return [{
                    "error": f"No SQL files found matching query: {query}", 
                    "suggestion": "Try a more general query or check if the SQL files exist in the repository"
                }]
                
            return formatted_results
            
        except Exception as e:
            logger.error(f"Error searching for SQL files: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return [{"error": f"Error searching for SQL files: {str(e)}"}]
    
    def search_for_table(self, table_name: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Search for SQL files that reference a specific table
        
        Args:
            table_name: Table name to search for
            limit: Maximum number of results
            
        Returns:
            List of SQL files with metadata
        """
        # Clean the table name (remove schema prefix if present)
        clean_table = table_name.split('.')[-1] if '.' in table_name else table_name
        
        # Try to detect if this is a DBT model
        is_dbt_model = clean_table.startswith('fct_') or clean_table.startswith('dim_') or clean_table.startswith('stg_')
        
        if is_dbt_model:
            # For DBT models, search for ref('model_name') pattern and the table name
            query = f"ref('{clean_table}') OR name: {clean_table} OR {clean_table}"
        else:
            # For regular tables, search for direct references
            query = f"\"{clean_table}\" table OR FROM {clean_table}"
        
        # Use the enhanced search
        return self.search_with_fallback(query, limit)
    
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
        try:
            if not self.vector_store:
                # Initialize SQL finder if not already done
                self.initialize()
                if not self.vector_store:
                    return []
            
            # Build query parts
            query_parts = []
            
            # Add table.column format if table is provided
            if table_name:
                query_parts.append(f'"{table_name}.{column_name}"')
                # Add DBT-specific patterns if likely a DBT environment
                if table_name.startswith('fct_') or table_name.startswith('dim_') or table_name.startswith('stg_'):
                    query_parts.append(f'"ref(\'{table_name}\')".{column_name}')
            
            # Add column definition patterns
            query_parts.append(f'"{column_name}" as')
            query_parts.append(f'select {column_name}')
            
            # Combine with OR
            query = " OR ".join(query_parts)
            
            # Use the enhanced search with fallback
            return self.search_with_fallback(query, limit)
            
        except Exception as e:
            logger.error(f"Error searching for column {column_name}: {str(e)}")
            return []
    
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

    def _detect_query_type(self, query: str) -> str:
        """
        Detect the type of query to optimize search strategy.
        
        Args:
            query: The search query string
            
        Returns:
            Query type string: 'file_path', 'column', 'dbt_model', or 'generic'
        """
        # File path detection
        if query.endswith('.sql') or '/' in query or '\\' in query or 'models/' in query:
            return 'file_path'
        
        # Column detection (including table.column format)
        if '.' in query and not query.startswith('/') and not query.startswith('.'):
            parts = query.split('.')
            if len(parts) == 2 and all(re.match(r'^[a-zA-Z0-9_]+$', part) for part in parts):
                return 'column'
        
        # Check for DBT model naming patterns
        if query.startswith('fct_') or query.startswith('dim_') or query.startswith('stg_'):
            return 'dbt_model'
            
        # Default to generic search
        return 'generic'

    def _enhance_query(self, query: str, query_type: str) -> str:
        """
        Enhance query based on detected type to improve search results.
        
        Args:
            query: Original search query
            query_type: Type of query ('file_path', 'column', 'dbt_model', or 'generic')
            
        Returns:
            Enhanced query string
        """
        if query_type == 'file_path':
            # For file paths, focus on exact path matching plus content
            filename = os.path.basename(query)
            return f'path:"{query}" OR filename:"{filename}"'
            
        elif query_type == 'column':
            # For columns, search for column definitions and usage
            if '.' in query:
                table, column = query.split('.', 1)
                return f'"{table}" near:"{column}" OR "SELECT {column}" OR "{column} as" OR "column: {column}"'
            else:
                return f'"{query}" as OR SELECT {query} OR column:{query}'
                
        elif query_type == 'dbt_model':
            # For DBT models, search for both the model name and related patterns
            return f'"{query}" model OR "name: {query}" OR "ref(\'{query}\')"'
            
        # Return original query for generic searches with minor enhancements
        return f'{query} definition OR {query} usage OR {query} table OR {query} column'
    
    def search_with_fallback(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Search with fallback strategies if primary search returns few results.
        
        Args:
            query: Search query
            limit: Maximum number of results
            
        Returns:
            List of search results
        """
        # Try primary search first
        results = self.search_sql_files(query, limit)
        
        # If we got enough results, return them
        if len(results) >= min(3, limit):
            return results
            
        # If few results, try alternative search strategies
        alt_queries = self._generate_alternative_queries(query)
        
        additional_results = []
        for alt_query in alt_queries:
            alt_results = self.search_sql_files(alt_query, limit - len(results))
            # Filter out duplicates
            for result in alt_results:
                if not any(r.get('path') == result.get('path') for r in results + additional_results):
                    additional_results.append(result)
                    if len(results) + len(additional_results) >= limit:
                        break
        
        # Combine results
        return results + additional_results[:limit-len(results)]
    
    def _generate_alternative_queries(self, query: str) -> List[str]:
        """
        Generate alternative queries for fallback search.
        
        Args:
            query: Original search query
            
        Returns:
            List of alternative search queries
        """
        alternatives = []
        
        # Try removing special characters
        clean_query = re.sub(r'[^a-zA-Z0-9_\s]', ' ', query)
        if clean_query != query:
            alternatives.append(clean_query)
        
        # Try breaking into parts for multi-part queries
        parts = re.split(r'[/._\-]', query)
        if len(parts) > 1:
            for part in parts:
                if len(part) > 3:  # Skip very short parts
                    alternatives.append(part)
        
        # For file paths, extract just the filename
        if '/' in query or '\\' in query:
            filename = os.path.basename(query)
            alternatives.append(filename)
            # Also try without extension
            name_without_ext = os.path.splitext(filename)[0]
            alternatives.append(name_without_ext)
        
        return alternatives
    
    def _perform_fallback_search(self, query: str, limit: int) -> List[Dict[str, Any]]:
        """
        Perform fallback search when primary search returns no results.
        
        Args:
            query: Original search query
            limit: Maximum number of results
            
        Returns:
            List of search results
        """
        logger.info(f"Performing fallback search for query: '{query}'")
        
        # Generate alternative queries
        alt_queries = self._generate_alternative_queries(query)
        
        all_results = []
        for alt_query in alt_queries:
            # Add SQL file filter if not already present
            if 'extension:' not in alt_query and '.sql' not in alt_query:
                alt_query = f"{alt_query} extension:sql"
                
            logger.info(f"Trying fallback query: '{alt_query}'")
            
            try:
                # Search with alternative query
                results = self.vector_store.query(alt_query, n_results=limit)
                
                if results and isinstance(results, dict) and 'metadatas' in results:
                    metadatas = results['metadatas']
                    documents = results.get('documents', [])
                    
                    # Handle case where metadatas is a list of lists
                    if metadatas and isinstance(metadatas, list):
                        if metadatas and isinstance(metadatas[0], list):
                            # It's a list of lists (older ChromaDB format)
                            metadatas = metadatas[0] if metadatas else []
                            documents = documents[0] if documents and isinstance(documents, list) and documents and isinstance(documents[0], list) else []
                    
                    # Format results
                    formatted_results = self._format_search_results(metadatas, documents)
                    
                    # Add to all results, avoiding duplicates
                    for result in formatted_results:
                        if not any(r.get('path') == result.get('path') for r in all_results):
                            all_results.append(result)
                            if len(all_results) >= limit:
                                return all_results
            except Exception as e:
                logger.warning(f"Error in fallback search with query '{alt_query}': {str(e)}")
        
        return all_results
    
    def _format_search_results(self, metadatas, documents) -> List[Dict[str, Any]]:
        """
        Format search results into a standard structure.
        
        Args:
            metadatas: Metadata from search results
            documents: Documents from search results
            
        Returns:
            Formatted search results
        """
        formatted_results = []
        
        for i, metadata in enumerate(metadatas):
            if not metadata:
                continue
                
            content = documents[i] if i < len(documents) else ""
            
            # Extract required fields
            file_path = metadata.get('path', metadata.get('file_path', ''))
            github_url = metadata.get('github_url', '')
            
            # Skip if no path
            if not file_path:
                continue
                
            # Create result entry
            result = {
                'path': file_path,
                'content': content,
                'github_url': github_url
            }
            
            # Copy additional metadata fields
            for key, value in metadata.items():
                if key not in result and key not in ['path', 'file_path']:
                    result[key] = value
            
            formatted_results.append(result)
            
        return formatted_results