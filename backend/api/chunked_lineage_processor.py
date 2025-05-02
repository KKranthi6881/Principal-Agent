"""
Chunked processing system for lineage extraction from large repositories
"""

import os
import shutil
import tempfile
import time
import asyncio
import logging
import threading
from typing import Dict, List, Any, Optional, Tuple, Set
import subprocess
from urllib.parse import urlparse

# Import local modules
from database.task_db import TaskDB
from database.lineage_db import LineageDB
from tools.sql_tools.dialects import get_dialect_parser
from tools.sql_tools.lineage.sqlglot_lineage import SQLGlotLineageExtractor
from tools.sql_tools.dbt_column_extractor import DBTColumnExtractor
from utils.connector_utils import get_db_connection, decrypt_token

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Initialize databases
task_db = TaskDB()
lineage_db = LineageDB()

# Default chunk size (files per chunk)
DEFAULT_CHUNK_SIZE = 50

class ChunkedLineageProcessor:
    """
    Processor for handling large repository lineage extraction in chunks
    """
    
    def __init__(self, connector_id: str, repo_url: str, tech_stack: str, branch: str = "main", 
                 chunk_size: int = DEFAULT_CHUNK_SIZE):
        self.connector_id = connector_id
        self.repo_url = repo_url
        self.tech_stack = tech_stack
        self.branch = branch
        self.chunk_size = chunk_size
        self.temp_dir = None
        self.task_id = None
        
        # Initialize database connections
        self.task_db = TaskDB()
        self.lineage_db = LineageDB()
    
    async def process(self) -> str:
        """
        Process the repository in chunks
        
        Returns:
            Task ID
        """
        # Create a task record
        self.task_id = self.task_db.create_task(
            task_type='lineage_extraction',
            connector_id=self.connector_id,
            repo_url=self.repo_url,
            tech_stack=self.tech_stack,
            metadata={
                'branch': self.branch,
                'chunk_size': self.chunk_size
            }
        )
        
        # Update task status to running
        self.task_db.update_task(self.task_id, status='running')
        
        # Start a background thread for processing
        thread = threading.Thread(
            target=self._process_repository_thread,
            args=()
        )
        thread.daemon = True
        thread.start()
        
        return self.task_id
    
    def _process_repository_thread(self):
        """
        Thread function for processing repository
        This runs in a separate thread to avoid blocking the main application
        """
        try:
            # Clone the repository
            success, self.temp_dir, error = self._clone_repository()
            
            if not success:
                logger.error(f"Failed to clone repository: {error}")
                self.task_db.update_task(
                    self.task_id,
                    status='failed',
                    error=f"Failed to clone repository: {error}"
                )
                return
            
            # Find SQL files
            sql_files = self._find_sql_files(self.temp_dir)
            
            if not sql_files:
                logger.info(f"No SQL files found in repository: {self.repo_url}")
                self.task_db.update_task(
                    self.task_id,
                    status='completed',
                    total_items=0,
                    processed_items=0,
                    successful_items=0,
                    failed_items=0
                )
                # Clean up
                shutil.rmtree(self.temp_dir, ignore_errors=True)
                return
            
            # Update task with total file count
            self.task_db.update_task(
                self.task_id,
                total_items=len(sql_files)
            )
            
            # Divide files into chunks
            file_chunks = self._create_chunks(sql_files)
            
            # Process each chunk
            chunk_tasks = []
            for chunk_number, file_chunk in enumerate(file_chunks):
                chunk_id = self.task_db.create_task_chunk(
                    task_id=self.task_id,
                    chunk_number=chunk_number,
                    total_chunks=len(file_chunks),
                    item_count=len(file_chunk),
                    metadata={
                        'files': [os.path.relpath(f, self.temp_dir) for f in file_chunk]
                    }
                )
                
                # Process the chunk
                self._process_chunk(chunk_id, file_chunk)
            
            # All chunks completed, update task status
            self.task_db.update_task(
                self.task_id,
                status='completed'
            )
            
            # Generate comprehensive lineage for all tables
            try:
                self._generate_comprehensive_lineage()
            except Exception as e:
                logger.error(f"Error generating comprehensive lineage: {str(e)}")
            
            # Clean up
            try:
                shutil.rmtree(self.temp_dir, ignore_errors=True)
                logger.info(f"Cleaned up temporary directory: {self.temp_dir}")
            except Exception as e:
                logger.error(f"Error cleaning up temporary directory: {str(e)}")
                
        except Exception as e:
            logger.error(f"Error processing repository: {str(e)}")
            self.task_db.update_task(
                self.task_id,
                status='failed',
                error=f"Error processing repository: {str(e)}"
            )
            
            # Clean up
            if self.temp_dir and os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def _clone_repository(self) -> Tuple[bool, str, Optional[str]]:
        """
        Clone the repository to a temporary directory
        
        Returns:
            Tuple of (success, temp_dir, error_message)
        """
        # Create a temporary directory for the repository
        temp_dir = tempfile.mkdtemp(prefix="lineage_extraction_")
        
        try:
            # Get GitHub token
            token = self._get_github_token()
            
            # Clone command
            if token:
                # Use token for authentication
                # Extract repo owner and name from URL
                parsed_url = urlparse(self.repo_url)
                path_parts = parsed_url.path.strip('/').split('/')
                if len(path_parts) >= 2:
                    owner = path_parts[0]
                    repo = path_parts[1]
                    if repo.endswith('.git'):
                        repo = repo[:-4]
                    
                    # Format URL with token
                    auth_url = f"https://{token}@github.com/{owner}/{repo}.git"
                    cmd = ['git', 'clone', '--branch', self.branch, auth_url, temp_dir]
                else:
                    # Fallback to original URL
                    cmd = ['git', 'clone', '--branch', self.branch, self.repo_url, temp_dir]
            else:
                # Clone without token
                cmd = ['git', 'clone', '--branch', self.branch, self.repo_url, temp_dir]
            
            # Execute clone command
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                # Try again with 'main' branch if it failed and we're using a different branch
                if self.branch != 'main':
                    logger.warning(f"Failed to clone branch {self.branch}, trying 'main' branch")
                    cmd = [part if part != self.branch else 'main' for part in cmd]
                    result = subprocess.run(cmd, capture_output=True, text=True)
                    
                    if result.returncode != 0:
                        # Try 'master' branch as a last resort
                        logger.warning(f"Failed to clone 'main' branch, trying 'master' branch")
                        cmd = [part if part != 'main' else 'master' for part in cmd]
                        result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                error_msg = f"Git clone failed: {result.stderr}"
                logger.error(error_msg)
                return False, temp_dir, error_msg
            
            logger.info(f"Successfully cloned {self.repo_url} to {temp_dir}")
            return True, temp_dir, None
            
        except Exception as e:
            error_msg = f"Error cloning repository: {str(e)}"
            logger.error(error_msg)
            return False, temp_dir, error_msg
    
    def _get_github_token(self) -> Optional[str]:
        """
        Get GitHub token for the connector
        
        Returns:
            GitHub token or None
        """
        try:
            # Connect to metadata database
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Get connector
            cursor.execute("SELECT token FROM github_connectors WHERE id = ?", (self.connector_id,))
            connector = cursor.fetchone()
            
            if not connector or not connector['token']:
                return None
            
            # Decrypt token
            token = decrypt_token(connector['token'])
            
            conn.close()
            return token
        
        except Exception as e:
            logger.error(f"Error getting GitHub token: {str(e)}")
            return None
    
    def _find_sql_files(self, directory: str) -> List[str]:
        """
        Find SQL files in the repository
        
        Args:
            directory: Repository directory
            
        Returns:
            List of SQL file paths
        """
        sql_files = []
        exclude_dirs = {'.git', 'node_modules', 'venv', '.venv', 'env', '.env'}
        
        for root, dirs, files in os.walk(directory):
            # Skip excluded directories
            dirs[:] = [d for d in dirs if d not in exclude_dirs]
            
            for file in files:
                if file.endswith('.sql'):
                    sql_files.append(os.path.join(root, file))
        
        logger.info(f"Found {len(sql_files)} SQL files in {directory}")
        return sql_files
    
    def _create_chunks(self, files: List[str]) -> List[List[str]]:
        """
        Create chunks of files for processing
        
        Args:
            files: List of file paths
            
        Returns:
            List of file path chunks
        """
        chunks = []
        for i in range(0, len(files), self.chunk_size):
            chunks.append(files[i:i + self.chunk_size])
        
        logger.info(f"Divided {len(files)} files into {len(chunks)} chunks of size {self.chunk_size}")
        return chunks
    
    def _process_chunk(self, chunk_id: str, files: List[str]):
        """
        Process a chunk of files
        
        Args:
            chunk_id: Chunk ID
            files: List of file paths in this chunk
        """
        # Update chunk status
        self.task_db.update_task_chunk(chunk_id, status='processing')
        
        successful = 0
        failed = 0
        tables_created = 0
        
        # Initialize dialect handlers - first try the specified tech stack
        dialect_handler = get_dialect_parser(self.tech_stack)
        if not dialect_handler:
            logger.warning(f"Unsupported tech stack: {self.tech_stack}. Using SQL dialect.")
            dialect_handler = get_dialect_parser("sql")  # Fallback to generic SQL
        
        # For DBT tech stack, ensure we also have a backup PostgreSQL handler
        postgres_handler = None
        if self.tech_stack.lower() == "dbt":
            postgres_handler = get_dialect_parser("postgresql")
        
        # Create lineage extractor
        lineage_extractor = SQLGlotLineageExtractor()
        
        # Process each file in the chunk
        for file_path in files:
            try:
                # Extract relative path for GitHub reference
                github_path = os.path.relpath(file_path, self.temp_dir).replace('\\', '/')
                
                # Read file content
                with open(file_path, 'r', encoding='utf-8') as f:
                    sql_code = f.read()
                
                # Parse SQL
                sql_ast = None
                errors = []
                
                # First try with the primary dialect
                if dialect_handler:
                    # Check the method signature to determine the right number of arguments
                    import inspect
                    try:
                        parse_method = dialect_handler.parse_sql
                        parse_sig = inspect.signature(parse_method)
                        
                        # If parse_sql accepts a file_path parameter, pass it
                        if len(parse_sig.parameters) > 2:  # self + sql_code + file_path
                            logger.info(f"Parsing {github_path} with {self.tech_stack} dialect (with file path)")
                            sql_ast, errors = dialect_handler.parse_sql(sql_code, github_path)
                        else:  # Only accepts self + sql_code
                            logger.info(f"Parsing {github_path} with {self.tech_stack} dialect (without file path)")
                            sql_ast, errors = dialect_handler.parse_sql(sql_code)
                    except Exception as sig_error:
                        logger.error(f"Error inspecting dialect method signature: {str(sig_error)}")
                        # Try plain version as fallback
                        try:
                            sql_ast, errors = dialect_handler.parse_sql(sql_code)
                        except Exception as parse_error:
                            errors.append(f"Error parsing SQL: {str(parse_error)}")
                
                # For DBT, if parsing failed, try with PostgreSQL dialect as fallback
                if (not sql_ast or errors) and postgres_handler and self.tech_stack.lower() == "dbt":
                    logger.info(f"Trying PostgreSQL dialect as fallback for {github_path}")
                    try:
                        # Also check signature for PostgreSQL handler
                        parse_method = postgres_handler.parse_sql
                        parse_sig = inspect.signature(parse_method)
                        
                        if len(parse_sig.parameters) > 2:
                            backup_ast, backup_errors = postgres_handler.parse_sql(sql_code, github_path)
                        else:
                            backup_ast, backup_errors = postgres_handler.parse_sql(sql_code)
                            
                        if backup_ast and (not backup_errors or len(backup_errors) < len(errors)):
                            sql_ast = backup_ast
                            errors = backup_errors
                            logger.info(f"Successfully parsed {github_path} with PostgreSQL dialect")
                    except Exception as fallback_error:
                        logger.error(f"Error using PostgreSQL fallback: {str(fallback_error)}")
                
                if errors:
                    logger.warning(f"Errors parsing {github_path}: {errors}")
                    # Don't fail completely if there are errors but we still have an AST
                    if not sql_ast:
                        failed += 1
                        continue
                
                if not sql_ast:
                    logger.warning(f"Failed to parse {github_path}")
                    failed += 1
                    continue
                
                # Extract lineage - first try with SQLGlot extractor
                table_lineage = lineage_extractor.extract_table_lineage(sql_ast, github_path)
                column_lineage = lineage_extractor.extract_column_lineage(sql_ast, github_path)
                
                # Additional extraction for DBT files using dialect-specific extractor
                if self.tech_stack.lower() == "dbt" and dialect_handler and hasattr(dialect_handler, 'extract_lineage'):
                    try:
                        dbt_lineage = dialect_handler.extract_lineage(sql_code, github_path)
                        logger.info(f"Extracted DBT lineage for {github_path}: {len(str(dbt_lineage))} bytes")
                        
                        # Merge or override lineage data for DBT
                        if dbt_lineage:
                            # Get target table from DBT lineage if available
                            if dbt_lineage.get("target_table") and not table_lineage.get("target_table"):
                                table_lineage["target_table"] = dbt_lineage["target_table"]
                                logger.info(f"Using DBT target table: {dbt_lineage['target_table']}")
                            
                            # Get source tables from DBT lineage if available
                            if dbt_lineage.get("source_tables"):
                                if not table_lineage.get("source_tables"):
                                    table_lineage["source_tables"] = dbt_lineage["source_tables"]
                                else:
                                    # Merge source tables
                                    existing_sources = {s.get('name'): s for s in table_lineage["source_tables"] if s.get('name')}
                                    for source in dbt_lineage["source_tables"]:
                                        source_name = source.get('name')
                                        if source_name and source_name not in existing_sources:
                                            table_lineage["source_tables"].append(source)
                                
                                logger.info(f"Found {len(dbt_lineage['source_tables'])} DBT source tables")
                            
                            # For column lineage, prefer DBT's extraction since it handles macros better
                            if dbt_lineage.get("columns"):
                                logger.info(f"Found {len(dbt_lineage['columns'])} columns in DBT lineage")
                                if not column_lineage:
                                    column_lineage = {"columns": []}
                                column_lineage["columns"] = dbt_lineage["columns"]
                            
                            # Get column relationships
                            if dbt_lineage.get("column_level_lineage"):
                                # Extract column relationships from DBT lineage
                                cl_lineage = dbt_lineage.get("column_level_lineage", {})
                                
                                # Try to find column relationships
                                relationships = []
                                if cl_lineage.get("relationships"):
                                    relationships = cl_lineage.get("relationships")
                                elif cl_lineage.get("column_relationships"):
                                    relationships = cl_lineage.get("column_relationships")
                                
                                if relationships:
                                    logger.info(f"Found {len(relationships)} column relationships in DBT lineage")
                                    if not column_lineage.get("column_relationships"):
                                        column_lineage["column_relationships"] = []
                                    column_lineage["column_relationships"].extend(relationships)
                    except Exception as dbt_err:
                        logger.warning(f"Error extracting DBT lineage for {github_path}: {str(dbt_err)}")
                
                # Store lineage in database
                lineage_info = {
                    "table_lineage": table_lineage,
                    "column_lineage": column_lineage
                }
                
                # Determine target table name - using multiple strategies
                target_table = None
                
                # 1. Try to get from table_lineage
                if table_lineage and table_lineage.get("target_table"):
                    target_table = table_lineage.get("target_table")
                
                # 2. If not found, try to infer from file path for DBT models
                if not target_table and github_path:
                    if '/models/' in github_path and github_path.endswith('.sql'):
                        # Extract model name from file path (last part without extension)
                        base_name = os.path.basename(github_path)
                        if base_name.endswith('.sql'):
                            base_name = base_name[:-4]  # Remove .sql extension
                        target_table = base_name
                        
                        if not table_lineage:
                            table_lineage = {}
                        table_lineage["target_table"] = target_table
                        logger.info(f"Inferred target table {target_table} from file path {github_path}")
                
                # Store target table if found
                table_id = None
                if target_table:
                    logger.info(f"Found target table: {target_table}")
                    
                    # Create or get table record
                    table_id = self.lineage_db.create_or_get_table(
                        table_name=target_table,
                        tech_stack=self.tech_stack,
                        github_path=github_path,
                        github_repo=self.repo_url,
                        connector_id=self.connector_id
                    )
                    
                    tables_created += 1
                    
                    # Store lineage
                    lineage_id = self.lineage_db.store_lineage(
                        table_id=table_id,
                        lineage_data=lineage_info,
                        github_path=github_path
                    )
                    
                    logger.info(f"Stored lineage for table {target_table} with ID {lineage_id}")
                    
                    # Process columns if available from column lineage
                    columns_created = 0
                    column_ids = {}
                    
                    # Handle columns from standard column lineage
                    if column_lineage:
                        # Try different possible structures based on extractor used
                        column_list = None
                        if column_lineage.get("columns"):
                            column_list = column_lineage.get("columns")
                        elif column_lineage.get("target_columns"):
                            column_list = column_lineage.get("target_columns")
                        elif column_lineage.get("column_level_lineage"):
                            column_list = column_lineage.get("column_level_lineage").get("target_columns", [])
                        
                        if column_list:
                            logger.info(f"Found {len(column_list)} columns for table {target_table}")
                            for column in column_list:
                                # Handle different column data structures
                                column_name = None
                                if isinstance(column, dict):
                                    column_name = column.get("name") or column.get("column_name")
                                    data_type = column.get("data_type", "unknown")
                                    description = column.get("description") or column.get("business_description", "")
                                    is_primary = column.get("is_primary_key", False)
                                    is_foreign = column.get("is_foreign_key", False)
                                    # Get column table if available - override with target_table if not specified
                                    column_table = column.get("table") or target_table
                                elif isinstance(column, str):
                                    column_name = column
                                    data_type = "unknown"
                                    description = ""
                                    is_primary = False
                                    is_foreign = False
                                    column_table = target_table
                                
                                if column_name:
                                    # Enhanced logging for column metadata
                                    logger.debug(f"Processing column: {column_name} (table: {target_table}, type: {data_type})")
                                    
                                    column_id = self.lineage_db.create_or_get_column(
                                        table_id=table_id,
                                        column_name=column_name,
                                        data_type=data_type,
                                        description=description,
                                        is_primary_key=is_primary,
                                        is_foreign_key=is_foreign,
                                        github_path=github_path
                                    )
                                    columns_created += 1
                                    # Store by both name and qualified name (table.column) for more reliable lookups
                                    column_ids[column_name] = column_id
                                    column_ids[f"{column_table}.{column_name}"] = column_id
                    
                    # Also process column-level lineage relationships if present
                    if column_lineage and column_lineage.get("column_relationships"):
                        logger.info(f"Processing {len(column_lineage.get('column_relationships'))} column relationships")
                        for rel in column_lineage.get("column_relationships", []):
                            source_table = rel.get("source_table")
                            source_column = rel.get("source_column")
                            target_column = rel.get("target_column")
                            rel_type = rel.get("relationship_type", "dependency")
                            
                            # Skip relationships with missing data
                            if not source_column or not target_column:
                                logger.warning(f"Skipping incomplete relationship: {rel}")
                                continue
                            
                            # Set default source table if not provided
                            if not source_table:
                                # For DBT models, check if source_column has a table prefix (e.g. 'customers.id')
                                if '.' in source_column and self.tech_stack.lower() == "dbt":
                                    parts = source_column.split('.')
                                    source_table = parts[0]
                                    source_column = parts[1]
                                    logger.debug(f"Extracted source table {source_table} from qualified column {source_column}")
                            
                            logger.debug(f"Processing relationship: {source_table}.{source_column} -> {target_table}.{target_column}")
                            
                            try:
                                # First, ensure the source table exists
                                source_table_id = None
                                if source_table:
                                    source_table_id = self.lineage_db.create_or_get_table(
                                        table_name=source_table,
                                        tech_stack=self.tech_stack,
                                        github_repo=self.repo_url,
                                        connector_id=self.connector_id
                                    )
                                    
                                    # Then create source column
                                    source_column_id = self.lineage_db.create_or_get_column(
                                        table_id=source_table_id,
                                        column_name=source_column,
                                        github_path=github_path
                                    )
                                else:
                                    # For columns without a source table, we still want to track them
                                    # but can't create a proper source column ID
                                    logger.debug(f"Source table missing for column {source_column}")
                                    source_column_id = None
                                
                                # Try different ways to find the target column ID
                                target_column_id = column_ids.get(target_column)
                                if not target_column_id:
                                    # Try with qualified name
                                    target_column_id = column_ids.get(f"{target_table}.{target_column}")
                                
                                if not target_column_id:
                                    # Create target column if not already tracked
                                    target_column_id = self.lineage_db.create_or_get_column(
                                        table_id=table_id,
                                        column_name=target_column,
                                        github_path=github_path
                                    )
                                    column_ids[target_column] = target_column_id
                                    column_ids[f"{target_table}.{target_column}"] = target_column_id
                                
                                # Only create relationship if we have both columns
                                if source_column_id and target_column_id:
                                    # Create the column-level relationship
                                    self.lineage_db.create_or_get_relationship(
                                    source_table_id=source_table_id,
                                    target_table_id=table_id,
                                    relationship_type=rel_type,
                                    source_column_id=source_column_id,
                                    target_column_id=target_column_id,
                                    github_path=github_path
                                    )
                                    logger.debug(f"Created column relationship: {source_column} -> {target_column}")
                            except Exception as rel_err:
                                logger.warning(f"Error creating column relationship: {str(rel_err)}")
                    
                    logger.info(f"Created/updated {columns_created} columns for table {target_table}")
                
                # Even if we don't have a target table, we might have source tables to track
                if table_lineage and table_lineage.get("source_tables"):
                    for source in table_lineage.get("source_tables", []):
                        source_name = source.get("name")
                        source_schema = source.get("schema")
                        if source_name and source_name != target_table:
                            # Create source table record
                            try:
                                source_id = self.lineage_db.create_or_get_table(
                                    table_name=source_name,
                                    schema_name=source_schema,
                                    tech_stack=self.tech_stack,
                                    github_repo=self.repo_url,
                                    connector_id=self.connector_id
                                )
                                
                                # If we have a target table, create a relationship
                                if table_id and source_id:
                                    self.lineage_db.create_or_get_relationship(
                                        source_table_id=source_id,
                                        target_table_id=table_id,
                                        relationship_type="dependency",
                                        github_path=github_path
                                    )
                            except Exception as rel_err:
                                logger.warning(f"Error creating relationship: {str(rel_err)}")
                
                successful += 1
                
            except Exception as e:
                logger.error(f"Error processing {file_path}: {str(e)}")
                failed += 1
            
            # Update progress
            self.task_db.increment_chunk_progress(chunk_id)
            self.task_db.increment_task_progress(self.task_id, processed=1, 
                                                successful=1 if successful > 0 else 0, 
                                                failed=1 if failed > 0 else 0)
            
            # Short sleep to prevent CPU overload
            time.sleep(0.01)
        
        # Update chunk status and metadata
        self.task_db.update_task_chunk(
            chunk_id, 
            status='completed',
            metadata={
                "tables_created": tables_created,
                "successful_files": successful,
                "failed_files": failed
            }
        )
    
    def _generate_comprehensive_lineage(self):
        """
        Generate comprehensive lineage for all tables
        """
        try:
            conn = self.lineage_db._get_connection()
            cursor = conn.cursor()
            
            # Make sure repo_url is not None to avoid SQL issues
            repo_url = self.repo_url if self.repo_url else ''
            
            cursor.execute(
                """SELECT * FROM tables 
                   WHERE tech_stack = ? AND (github_repo = ? OR github_repo IS NULL)""",
                (self.tech_stack, repo_url)
            )
            repo_tables = cursor.fetchall()
            conn.close()
            
            logger.info(f"Generating comprehensive lineage for {len(repo_tables)} tables")
            
            # Generate lineage for each table
            for table in repo_tables:
                table_dict = dict(table)
                table_id = table_dict['table_id']
                github_path = table_dict['github_path']
                
                try:
                    # Generate and store comprehensive lineage
                    lineage_id = self.lineage_db.generate_comprehensive_lineage(
                        root_table_id=table_id,
                        tech_stack=self.tech_stack,
                        github_path=github_path
                    )
                    logger.info(f"Generated comprehensive lineage for {table_dict['table_name']} with ID {lineage_id}")
                except Exception as e:
                    logger.warning(f"Error generating lineage for table {table_dict['table_name']}: {str(e)}")
            
            logger.info("Comprehensive lineage generation completed successfully")
        except Exception as e:
            logger.error(f"Error during comprehensive lineage generation: {str(e)}")
            raise
