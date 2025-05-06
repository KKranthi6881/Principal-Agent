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
import datetime
import uuid
import re
import json
import traceback
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
        # Create a task record with timestamp
        current_time = datetime.datetime.now().isoformat()
        self.task_id = self.task_db.create_task(
            task_type='lineage_extraction',
            connector_id=self.connector_id,
            repo_url=self.repo_url,
            tech_stack=self.tech_stack,
            metadata={
                'branch': self.branch,
                'chunk_size': self.chunk_size,
                'started_at': current_time,
                'display_name': self._get_repo_display_name(),
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
        
    def _get_repo_display_name(self) -> str:
        """Extract a display name from the repository URL"""
        try:
            parsed = urlparse(self.repo_url)
            if not parsed.path:
                return self.repo_url
                
            # Remove .git extension if present
            path = parsed.path
            if path.endswith('.git'):
                path = path[:-4]
                
            # Get the last part of the path as repo name
            parts = path.strip('/').split('/')
            if len(parts) >= 1:
                return parts[-1]
            return self.repo_url
        except Exception:
            return self.repo_url
    
    def _process_repository_thread(self):
        """
        Thread function for processing repository
        This runs in a separate thread to avoid blocking the main application
        """
        try:
            # Update status - starting repository clone
            self.task_db.update_task(
                self.task_id,
                status='running',
                progress=5,
                current_step='cloning_repository',
                metadata={
                    **(self.task_db.get_task(self.task_id).get('metadata', {}) or {}),
                    'current_operation': 'Cloning repository...',
                    'last_updated': datetime.datetime.now().isoformat()
                }
            )
            
            # Clone the repository
            success, self.temp_dir, error = self._clone_repository()
            
            if not success:
                logger.error(f"Failed to clone repository: {error}")
                self.task_db.update_task(
                    self.task_id,
                    status='failed',
                    error=f"Failed to clone repository: {error}",
                    metadata={
                        **(self.task_db.get_task(self.task_id).get('metadata', {}) or {}),
                        'failure_reason': 'clone_failed',
                        'error_details': error,
                        'completed_at': datetime.datetime.now().isoformat()
                    }
                )
                return
            
            # Update status - finding SQL files
            self.task_db.update_task(
                self.task_id,
                status='running',
                progress=15,
                current_step='finding_sql_files',
                metadata={
                    **(self.task_db.get_task(self.task_id).get('metadata', {}) or {}),
                    'current_operation': 'Preparing file chunks for processing...',
                    'last_updated': datetime.datetime.now().isoformat()
                }
            )
            
            # Find SQL files
            sql_files = self._find_sql_files(self.temp_dir)
            
            if not sql_files:
                logger.info(f"No SQL files found in repository: {self.repo_url}")
                self.task_db.update_task(
                    self.task_id,
                    status='completed',
                    progress=100,
                    total_items=0,
                    processed_items=0,
                    successful_items=0,
                    failed_items=0,
                    metadata={
                        **(self.task_db.get_task(self.task_id).get('metadata', {}) or {}),
                        'current_operation': 'Completed - No SQL files found',
                        'last_updated': datetime.datetime.now().isoformat(),
                        'completed_at': datetime.datetime.now().isoformat()
                    }
                )
                # Clean up
                shutil.rmtree(self.temp_dir, ignore_errors=True)
                return
            
            # Update task with total file count and progress
            self.task_db.update_task(
                self.task_id,
                total_items=len(sql_files),
                progress=20,
                current_step='preparing_chunks',
                metadata={
                    **(self.task_db.get_task(self.task_id).get('metadata', {}) or {}),
                    'current_operation': f'Preparing to process {len(sql_files)} SQL files',
                    'sql_file_count': len(sql_files),
                    'last_updated': datetime.datetime.now().isoformat()
                }
            )
            
            # Divide files into chunks
            file_chunks = self._create_chunks(sql_files)
            
            # Process each chunk
            processed_count = 0
            total_count = len(sql_files)
            successful_items = 0
            failed_items = 0
            
            for chunk_number, file_chunk in enumerate(file_chunks):
                # Calculate progress (25% to 75% range for processing chunks)
                progress = 25 + (chunk_number / len(file_chunks) * 50)
                
                # Update task status before processing chunk
                self.task_db.update_task(
                    self.task_id,
                    status='running',
                    progress=int(progress),
                    current_step=f'processing_chunk_{chunk_number+1}_of_{len(file_chunks)}',
                    processed_items=processed_count,
                    successful_items=successful_items,
                    failed_items=failed_items,
                    metadata={
                        **(self.task_db.get_task(self.task_id).get('metadata', {}) or {}),
                        'current_operation': f'Processing chunk {chunk_number+1} of {len(file_chunks)}',
                        'last_updated': datetime.datetime.now().isoformat()
                    }
                )
                
                # Create chunk record
                chunk_id = self.task_db.create_task_chunk(
                    task_id=self.task_id,
                    chunk_number=chunk_number,
                    total_chunks=len(file_chunks),
                    item_count=len(file_chunk),
                    metadata={
                        'files': [os.path.relpath(f, self.temp_dir) for f in file_chunk],
                        'started_at': datetime.datetime.now().isoformat()
                    }
                )
                
                # Process the chunk
                chunk_results = self._process_chunk(chunk_id, file_chunk)
                processed_count += len(file_chunk)
                successful_items += chunk_results.get('successful', 0)
                failed_items += chunk_results.get('failed', 0)
            
            # Update that we're generating comprehensive lineage
            self.task_db.update_task(
                self.task_id,
                status='running',
                progress=80,
                current_step='generating_comprehensive_lineage',
                processed_items=processed_count,
                successful_items=successful_items,
                failed_items=failed_items,
                metadata={
                    **(self.task_db.get_task(self.task_id).get('metadata', {}) or {}),
                    'current_operation': 'Generating comprehensive lineage data...',
                    'last_updated': datetime.datetime.now().isoformat()
                }
            )
            
            # Generate comprehensive lineage for all tables
            try:
                self._generate_comprehensive_lineage()
            except Exception as e:
                logger.error(f"Error generating comprehensive lineage: {str(e)}")
                # Still continue to completion, just log the error
            
            # All processing complete - update task status
            self.task_db.update_task(
                self.task_id,
                status='completed',
                progress=100,
                current_step='completed',
                processed_items=processed_count,
                successful_items=successful_items,
                failed_items=failed_items,
                metadata={
                    **(self.task_db.get_task(self.task_id).get('metadata', {}) or {}),
                    'current_operation': 'Processing complete',
                    'completed_at': datetime.datetime.now().isoformat(),
                    'last_updated': datetime.datetime.now().isoformat()
                }
            )
            
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
                error=f"Error processing repository: {str(e)}",
                metadata={
                    **(self.task_db.get_task(self.task_id).get('metadata', {}) or {}),
                    'current_operation': 'Failed due to unexpected error',
                    'error_details': str(e),
                    'error_traceback': traceback.format_exc(),
                    'completed_at': datetime.datetime.now().isoformat(),
                    'last_updated': datetime.datetime.now().isoformat()
                }
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
            
            # Extract repo owner and name from URL
            parsed_url = urlparse(self.repo_url)
            path_parts = parsed_url.path.strip('/').split('/')
            
            if len(path_parts) >= 2:
                owner = path_parts[0]
                repo = path_parts[1]
                if repo.endswith('.git'):
                    repo = repo[:-4]
                
                # Format URL with token if available
                if token:
                    auth_url = f"https://{token}@github.com/{owner}/{repo}.git"
                    repo_url_to_use = auth_url
                else:
                    repo_url_to_use = self.repo_url
                
                # First try: Detect default branch without specifying a branch
                logger.info(f"Attempting to clone repository with default branch detection")
                initial_cmd = ['git', 'clone', repo_url_to_use, temp_dir]
                result = subprocess.run(initial_cmd, capture_output=True, text=True)
                
                # If default branch clone succeeded
                if result.returncode == 0:
                    logger.info(f"Successfully cloned {self.repo_url} using default branch to {temp_dir}")
                    return True, temp_dir, None
                
                # If default branch clone failed, try with specific branch if provided
                if self.branch:
                    logger.info(f"Default branch clone failed, trying with specified branch: {self.branch}")
                    # Remove directory contents if it exists
                    if os.path.exists(temp_dir):
                        shutil.rmtree(temp_dir)
                        os.makedirs(temp_dir)
                    
                    branch_cmd = ['git', 'clone', '--branch', self.branch, repo_url_to_use, temp_dir]
                    result = subprocess.run(branch_cmd, capture_output=True, text=True)
                    
                    if result.returncode == 0:
                        logger.info(f"Successfully cloned {self.repo_url} with branch {self.branch} to {temp_dir}")
                        return True, temp_dir, None
                
                # If all else fails, try to list remote branches and clone with one of them
                logger.info("Trying to detect available branches")
                list_cmd = ['git', 'ls-remote', '--heads', repo_url_to_use]
                list_result = subprocess.run(list_cmd, capture_output=True, text=True)
                
                if list_result.returncode == 0:
                    # Parse branches from the output
                    branches = []
                    for line in list_result.stdout.splitlines():
                        if 'refs/heads/' in line:
                            branch_name = line.split('refs/heads/')[1].strip()
                            branches.append(branch_name)
                    
                    logger.info(f"Detected branches: {branches}")
                    
                    # Try common branch names first, then others
                    priority_branches = ['main', 'master', 'dev', 'develop', 'trunk']
                    for branch_name in priority_branches:
                        if branch_name in branches:
                            # Remove directory contents if it exists
                            if os.path.exists(temp_dir):
                                shutil.rmtree(temp_dir)
                                os.makedirs(temp_dir)
                            
                            branch_cmd = ['git', 'clone', '--branch', branch_name, repo_url_to_use, temp_dir]
                            result = subprocess.run(branch_cmd, capture_output=True, text=True)
                            
                            if result.returncode == 0:
                                logger.info(f"Successfully cloned {self.repo_url} with branch {branch_name} to {temp_dir}")
                                return True, temp_dir, None
                    
                    # If none of the priority branches worked, try the first available branch
                    if branches:
                        # Remove directory contents if it exists
                        if os.path.exists(temp_dir):
                            shutil.rmtree(temp_dir)
                            os.makedirs(temp_dir)
                        
                        first_branch = branches[0]
                        branch_cmd = ['git', 'clone', '--branch', first_branch, repo_url_to_use, temp_dir]
                        result = subprocess.run(branch_cmd, capture_output=True, text=True)
                        
                        if result.returncode == 0:
                            logger.info(f"Successfully cloned {self.repo_url} with branch {first_branch} to {temp_dir}")
                            return True, temp_dir, None
            else:
                # Fallback to original URL with simple clone
                cmd = ['git', 'clone', self.repo_url, temp_dir]
                result = subprocess.run(cmd, capture_output=True, text=True)
                
                if result.returncode == 0:
                    logger.info(f"Successfully cloned {self.repo_url} to {temp_dir}")
                    return True, temp_dir, None
            
            # If we reached here, all attempts failed
            error_msg = f"Git clone failed: {result.stderr}"
            logger.error(error_msg)
            return False, temp_dir, error_msg
            
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
    
    def _process_chunk(self, chunk_id: str, files: List[str]) -> Dict[str, int]:
        """
        Process a chunk of files
        
        Args:
            chunk_id: Chunk ID
            files: List of file paths in this chunk
            
        Returns:
            Dictionary with success/failure counts
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
                
                # Use dialect-specific extraction for all supported dialects (PostgreSQL, T-SQL, DBT, etc.)
                if dialect_handler and hasattr(dialect_handler, 'extract_lineage'):
                    try:
                        # Extract lineage using dialect-specific implementation
                        dialect_lineage = dialect_handler.extract_lineage(sql_code, github_path)
                        logger.info(f"Extracted {self.tech_stack} dialect lineage for {github_path}: {len(str(dialect_lineage))} bytes")
                        
                        # Process the lineage information
                        if dialect_lineage:
                            # Handle table-level lineage
                            if "table_lineage" in dialect_lineage:
                                # Get target table from dialect lineage if available
                                if dialect_lineage["table_lineage"].get("target_table") and not table_lineage.get("target_table"):
                                    table_lineage["target_table"] = dialect_lineage["table_lineage"]["target_table"]
                                    logger.info(f"Using {self.tech_stack} target table: {dialect_lineage['table_lineage']['target_table']}")
                                
                                # Get source tables from dialect lineage if available
                                if dialect_lineage["table_lineage"].get("source_tables"):
                                    if not table_lineage.get("source_tables"):
                                        table_lineage["source_tables"] = dialect_lineage["table_lineage"]["source_tables"]
                                    else:
                                        # Merge source tables, avoiding duplicates
                                        existing_sources = {s.get('name') if isinstance(s, dict) else s: s 
                                                          for s in table_lineage["source_tables"]}
                                        
                                        for source in dialect_lineage["table_lineage"]["source_tables"]:
                                            source_name = source.get('name') if isinstance(source, dict) else source
                                            if source_name and source_name not in existing_sources:
                                                table_lineage["source_tables"].append(source)
                                
                                logger.info(f"Found {len(dialect_lineage['table_lineage'].get('source_tables', []))} {self.tech_stack} source tables")
                            
                            # Handle column-level lineage (new format for PostgreSQL and T-SQL dialects)
                            if "column_lineage" in dialect_lineage:
                                logger.info(f"Found column-level lineage in {self.tech_stack} dialect")
                                
                                # Process target columns
                                if dialect_lineage["column_lineage"].get("target_columns"):
                                    column_lineage["target_columns"] = dialect_lineage["column_lineage"]["target_columns"]
                                    logger.info(f"Found {len(column_lineage['target_columns'])} target columns")
                                
                                # Process source columns
                                if dialect_lineage["column_lineage"].get("source_columns"):
                                    column_lineage["source_columns"] = dialect_lineage["column_lineage"]["source_columns"]
                                    logger.info(f"Found {len(column_lineage['source_columns'])} source columns")
                                
                                # Process column relationships
                                if dialect_lineage["column_lineage"].get("column_relationships"):
                                    column_lineage["column_relationships"] = dialect_lineage["column_lineage"]["column_relationships"]
                                    logger.info(f"Found {len(column_lineage['column_relationships'])} column relationships")
                                
                                # Process column-level lineage mapping (column-to-column dependencies)
                                if dialect_lineage["column_lineage"].get("column_level_lineage"):
                                    column_lineage["column_level_lineage"] = dialect_lineage["column_lineage"]["column_level_lineage"]
                            
                            # Handle older DBT format (for backward compatibility)
                            if "columns" in dialect_lineage:
                                logger.info(f"Found {len(dialect_lineage.get('columns', []))} columns in {self.tech_stack} lineage (legacy format)")
                                if not column_lineage.get("columns"):
                                    column_lineage["columns"] = []
                                column_lineage["columns"] = dialect_lineage["columns"]
                            
                            # Handle old-style column relationships (for backward compatibility)
                            if "column_level_lineage" in dialect_lineage:
                                legacy_cl = dialect_lineage.get("column_level_lineage", {})
                                
                                # Extract relationships from legacy format
                                relationships = []
                                if legacy_cl.get("relationships"):
                                    relationships = legacy_cl.get("relationships")
                                elif legacy_cl.get("column_relationships"):
                                    relationships = legacy_cl.get("column_relationships")
                                
                                if relationships:
                                    logger.info(f"Found {len(relationships)} column relationships in legacy format")
                                    if not column_lineage.get("column_relationships"):
                                        column_lineage["column_relationships"] = []
                                    column_lineage["column_relationships"].extend(relationships)
                                
                                # Make the legacy lineage available
                                column_lineage["column_level_lineage"] = legacy_cl
                    
                    except Exception as e:
                        logger.error(f"Error processing {self.tech_stack} lineage: {str(e)}", exc_info=True)
                
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
                    
                    # Process columns and relationships directly rather than relying on store_lineage
                    columns_created = 0
                    column_ids = {}
                    
                    # Process target columns first
                    if column_lineage and column_lineage.get("target_columns"):
                        logger.info(f"Processing {len(column_lineage.get('target_columns', []))} target columns")
                        for column in column_lineage.get("target_columns", []):
                            try:
                                # Extract column properties
                                if isinstance(column, dict):
                                    column_name = column.get("name") or column.get("column_name")
                                    data_type = column.get("data_type", "unknown")
                                    description = column.get("description", "")
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
                                    logger.info(f"Creating column: {column_name} in table {target_table}")
                                    # Create column and store ID
                                    column_id = self.lineage_db.create_or_get_column(
                                        table_id=table_id,
                                        column_name=column_name,
                                        data_type=data_type,
                                        description=description,
                                        is_primary_key=is_primary,
                                        is_foreign_key=is_foreign,
                                        github_path=github_path
                                    )
                                    
                                    # Store column ID with both simple and qualified names
                                    column_ids[column_name] = column_id
                                    column_ids[f"{column_table}.{column_name}"] = column_id
                                    columns_created += 1
                            except Exception as e:
                                logger.warning(f"Error creating column {column_name}: {str(e)}")
                    
                    # Then process column relationships
                    relationships_created = 0
                    if column_lineage and column_lineage.get("column_relationships"):
                        logger.info(f"Processing {len(column_lineage.get('column_relationships', []))} column relationships")
                        for rel in column_lineage.get("column_relationships", []):
                            try:
                                source_table_name = rel.get("source_table")
                                source_column_name = rel.get("source_column")
                                target_column_name = rel.get("target_column")
                                rel_type = rel.get("relationship_type", "dependency")
                                
                                if not source_column_name or not target_column_name:
                                    logger.warning(f"Skipping relationship with missing columns: {rel}")
                                    continue
                                
                                # Make sure we have source table ID
                                source_table_id = None
                                if source_table_name:
                                    # Check if source_table_name is a dict and extract the name
                                    if isinstance(source_table_name, dict) and "name" in source_table_name:
                                        source_table_name = source_table_name["name"]
                                    
                                    # Find or create source table
                                    source_table = self.lineage_db.get_table_by_name(source_table_name)
                                    if not source_table:
                                        # Create source table
                                        source_table_id = self.lineage_db.create_or_get_table(
                                            table_name=source_table_name,
                                            tech_stack=self.tech_stack,
                                            github_repo=self.repo_url,
                                            connector_id=self.connector_id
                                        )
                                    else:
                                        source_table_id = source_table["table_id"]
                                
                                    # Create or get source column
                                    source_column_id = self.lineage_db.create_or_get_column(
                                        table_id=source_table_id,
                                        column_name=source_column_name,
                                        github_path=github_path
                                    )
                                    
                                    # Get target column ID (try different ways)
                                    target_column_id = column_ids.get(target_column_name)
                                    if not target_column_id:
                                        # Try with qualified name
                                        target_column_id = column_ids.get(f"{target_table}.{target_column_name}")
                                    
                                    if not target_column_id:
                                        # Create target column if not already tracked
                                        target_column_id = self.lineage_db.create_or_get_column(
                                            table_id=table_id,
                                            column_name=target_column_name,
                                            github_path=github_path
                                        )
                                        column_ids[target_column_name] = target_column_id
                                    
                                    # Create the column-level relationship
                                    logger.info(f"Creating column relationship: {source_column_name} ({source_table_name}) -> {target_column_name} ({target_table})")
                                    self.lineage_db.create_or_get_relationship(
                                        source_table_id=source_table_id,
                                        target_table_id=table_id,
                                        relationship_type=rel_type,
                                        source_column_id=source_column_id,
                                        target_column_id=target_column_id,
                                        github_path=github_path
                                    )
                                    relationships_created += 1
                            except Exception as e:
                                logger.warning(f"Error creating column relationship: {str(e)}")
                    
                    # Create a lineage definition for visualization
                    lineage_def = {
                        "tables": [{
                            "id": table_id,
                            "name": target_table,
                            "columns": column_lineage.get("target_columns", [])
                        }],
                        "relationships": column_lineage.get("column_relationships", [])
                    }
                    
                    # Add source tables if available
                    if "source_tables" in table_lineage:
                        lineage_def["source_tables"] = table_lineage["source_tables"]
                    
                    # Store the lineage definition
                    lineage_id = self.lineage_db.add_lineage_definition(
                        root_table_id=table_id,
                        lineage_json=lineage_def,
                        tech_stack=self.tech_stack
                    )
                    
                    logger.info(f"Stored lineage for table {target_table} with ID {lineage_id}")
                    logger.info(f"Created {columns_created} columns and {relationships_created} relationships")
                    
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
                "failed_files": failed,
                "completed_at": datetime.datetime.now().isoformat()
            }
        )
        
        # Return success and failure counts for tracking
        return {
            "successful": successful,
            "failed": failed, 
            "tables_created": tables_created
        }
    
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
