"""
Background tasks for lineage extraction and processing
"""

import os
import time
import tempfile
import shutil
import threading
import logging
from typing import Dict, Any, List, Optional
import json
import sqlite3
import requests
from urllib.parse import urlparse
import subprocess
from tools.sql_tools.dbt_column_extractor import DBTColumnExtractor

# Import local modules
from tools.sql_tools.dialects import get_dialect_parser
from tools.sql_tools.lineage.sqlglot_lineage import SQLGlotLineageExtractor
from database.lineage_db import LineageDB

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Global storage for task status
# In a production app, this would be in a database or Redis
_TASKS: Dict[str, Dict[str, Any]] = {}

def get_lineage_task(task_id: str) -> Optional[Dict[str, Any]]:
    """
    Get task status for a specific task
    """
    return _TASKS.get(task_id)

def get_all_lineage_tasks() -> List[Dict[str, Any]]:
    """
    Get all lineage tasks
    """
    return list(_TASKS.values())

def add_task(task_id: str, connector_id: str, repo_url: str, tech_stack: str) -> Dict[str, Any]:
    """
    Add a new task to the tasks map
    """
    task = {
        "status": "running",
        "start_time": time.time(),
        "connector_id": connector_id,
        "repo_url": repo_url,
        "tech_stack": tech_stack,
        "total_files": 0,
        "processed_files": 0,
        "successful_files": 0,
        "failed_files": 0,
        "elapsed_seconds": 0.0,
        "error": None
    }
    _TASKS[task_id] = task
    return task

def update_task(task_id: str, **kwargs) -> Optional[Dict[str, Any]]:
    """
    Update a task with new values
    """
    if task_id not in _TASKS:
        return None
    
    for key, value in kwargs.items():
        if key in _TASKS[task_id]:
            _TASKS[task_id][key] = value
    
    # Update elapsed time
    _TASKS[task_id]["elapsed_seconds"] = time.time() - _TASKS[task_id]["start_time"]
    
    return _TASKS[task_id]

def update_task_progress(task_id: str, processed: int = 0, successful: int = 0, failed: int = 0) -> Optional[Dict[str, Any]]:
    """
    Update task progress counters
    """
    if task_id not in _TASKS:
        return None
    
    _TASKS[task_id]["processed_files"] += processed
    _TASKS[task_id]["successful_files"] += successful
    _TASKS[task_id]["failed_files"] += failed
    _TASKS[task_id]["elapsed_seconds"] = time.time() - _TASKS[task_id]["start_time"]
    
    return _TASKS[task_id]

def finalize_task(task_id: str, success: bool, error: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Mark a task as completed or failed
    """
    if task_id not in _TASKS:
        return None
    
    _TASKS[task_id]["status"] = "completed" if success else "failed"
    _TASKS[task_id]["error"] = error
    _TASKS[task_id]["elapsed_seconds"] = time.time() - _TASKS[task_id]["start_time"]
    
    # Clean up older tasks if there are more than 10
    if len(_TASKS) > 10:
        # Keep only the 10 most recent tasks
        tasks_by_start_time = sorted(_TASKS.items(), key=lambda x: x[1]["start_time"], reverse=True)
        for old_task_id, _ in tasks_by_start_time[10:]:
            del _TASKS[old_task_id]
    
    return _TASKS[task_id]

async def process_repository_for_lineage(connector_id: str, repo_url: str, tech_stack: str, branch: str = "main"):
    """
    Process a GitHub repository for lineage extraction
    
    This function clones the repository, finds SQL files, parses them,
    extracts lineage information, and stores it in the lineage database.
    
    Args:
        connector_id: GitHub connector ID
        repo_url: GitHub repository URL
        tech_stack: Tech stack for SQL parsing
        branch: Branch to check out
    """
    task_id = f"{connector_id}_{int(time.time())}"
    task = add_task(task_id, connector_id, repo_url, tech_stack)
    
    # Create a temporary directory for the repository
    temp_dir = None
    
    try:
        # Create temporary directory
        temp_dir = tempfile.mkdtemp(prefix="lineage_")
        logger.info(f"Created temporary directory: {temp_dir}")
        
        # Clone the repository
        try:
            # Get token for private repos
            token = get_github_token(connector_id)
            
            # Format the URL with token if available
            clone_url = repo_url
            if token and "github.com" in repo_url:
                parsed_url = urlparse(repo_url)
                clone_url = f"https://{token}@{parsed_url.netloc}{parsed_url.path}"
            
            # Clone the repository
            logger.info(f"Cloning repository: {repo_url} (branch: {branch}) to {temp_dir}")
            subprocess.run(
                ["git", "clone", "--depth", "1", "--branch", branch, clone_url, temp_dir],
                check=True,
                capture_output=True
            )
            logger.info(f"Repository cloned successfully")
        except subprocess.CalledProcessError as e:
            logger.error(f"Error cloning repository: {e}")
            # If shallow clone failed with specific branch, try without branch
            try:
                subprocess.run(
                    ["git", "clone", "--depth", "1", clone_url, temp_dir],
                    check=True,
                    capture_output=True
                )
                logger.info(f"Repository cloned successfully without branch specification")
            except subprocess.CalledProcessError as e:
                logger.error(f"Error cloning repository (second attempt): {e}")
                finalize_task(
                    task_id,
                    success=False,
                    error=f"Failed to clone repository: {str(e)}"
                )
                return
        
        # Find SQL files
        sql_files = find_sql_files(temp_dir)
        logger.info(f"Found {len(sql_files)} SQL files")
        
        if not sql_files:
            finalize_task(
                task_id,
                success=True,
                error="No SQL files found in repository"
            )
            return
        
        # Update task with total files
        update_task(task_id, total_files=len(sql_files))
        
        # Initialize lineage DB connection
        lineage_db = LineageDB()
        
        # Get dialect handler
        dialect_handler = get_dialect_parser(tech_stack)
        if not dialect_handler:
            logger.warning(f"Unsupported tech stack: {tech_stack}. Lineage extraction will be skipped.")
            finalize_task(
                task_id,
                success=True,  # Mark as success but with a warning
                error=f"Unsupported tech stack: {tech_stack}. Please use one of: postgresql, mysql, snowflake, tsql"
            )
            return
        
        # Initialize lineage extractor
        lineage_extractor = SQLGlotLineageExtractor()
        
        # Process each SQL file
        for file_path in sql_files:
            try:
                relative_path = os.path.relpath(file_path, temp_dir)
                logger.info(f"Processing file: {relative_path}")
                
                # Read the file
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    sql_code = f.read()
                
                # Parse SQL
                sql_ast, errors = dialect_handler.parse_sql(sql_code, file_path=relative_path)
                
                if not sql_ast:
                    logger.warning(f"Failed to parse {relative_path}: {errors}")
                    update_task_progress(task_id, processed=1, failed=1)
                    continue
                
                # Successful parse but misleading error message
                if errors and any("Parse successful" in err for err in errors):
                    logger.info(f"Successfully parsed {relative_path} with dialect: {tech_stack}")
                elif errors:
                    logger.warning(f"Parsed {relative_path} with warnings: {errors}")

                # Try direct extraction from dialect handler first
                try:
                    dialect_lineage = dialect_handler.extract_lineage(sql_code, relative_path)
                    
                    # Debug logging for column extraction
                    logger.info(f"Dialect lineage keys: {list(dialect_lineage.keys()) if dialect_lineage else None}")
                    if dialect_lineage and 'columns' in dialect_lineage:
                        logger.info(f"Found {len(dialect_lineage['columns'])} columns in dialect_lineage")
                    else:
                        logger.info("No 'columns' key found in dialect_lineage")
                    
                    # If we get a valid target table from dialect extraction
                    if dialect_lineage and dialect_lineage.get("target_table"):
                        target_table = dialect_lineage["target_table"]
                        logger.info(f"Found target table from dialect extraction: {target_table}")
                        
                        # Check if table already exists
                        existing_table = lineage_db.get_table_by_name(target_table, tech_stack)
                        
                        if existing_table:
                            table_id = existing_table["table_id"]
                            logger.info(f"Using existing table {target_table} with ID {table_id}")
                        else:
                            # Add new table
                            table_id = lineage_db.add_table(
                                table_name=target_table,
                                tech_stack=tech_stack,
                                github_path=relative_path,
                                connector_id=connector_id,
                                github_repo=repo_url
                            )
                            logger.info(f"Added new table {target_table} with ID {table_id}")
                        
                        # Process source tables
                        for source_table in dialect_lineage.get("source_tables", []):
                            if not source_table:
                                continue
                            
                            # Extract table name from dictionary if needed
                            if isinstance(source_table, dict):
                                source_table_name = source_table.get("name")
                                if not source_table_name:
                                    continue
                            else:
                                source_table_name = source_table
                            
                            # Check if source table already exists
                            existing_source = lineage_db.get_table_by_name(source_table_name, tech_stack)
                            
                            if existing_source:
                                source_id = existing_source["table_id"]
                                logger.info(f"Using existing source table {source_table_name} with ID {source_id}")
                            else:
                                # Add new source table
                                source_id = lineage_db.add_table(
                                    table_name=source_table_name,
                                    tech_stack=tech_stack,
                                    github_path=None,
                                    connector_id=connector_id,
                                    github_repo=repo_url
                                )
                                logger.info(f"Added new source table {source_table_name} with ID {source_id}")
                            
                            # Add relationship
                            try:
                                relationship_id = lineage_db.add_relationship(
                                    source_table_id=source_id,
                                    target_table_id=table_id,
                                    relationship_type="depends_on",
                                    github_path=relative_path
                                )
                                logger.info(f"Added relationship: {source_table_name} -> {target_table}")
                            except Exception as rel_e:
                                logger.warning(f"Failed to add relationship: {str(rel_e)}")
                        
                        update_task_progress(task_id, processed=1, successful=1)
                        continue  # Skip the rest of processing for this file
                except Exception as e:
                    logger.error(f"Error with dialect extraction: {str(e)}", exc_info=True)
                    # Continue with generic lineage extraction
                    pass

                # Extract lineage information using SQLGlot extractor
                table_lineage = lineage_extractor.extract_table_lineage(sql_ast, relative_path)
                column_lineage = lineage_extractor.extract_column_lineage(sql_ast, relative_path)
                
                logger.info(f"Extracted lineage for {relative_path}: {table_lineage}")
                
                # Store lineage information
                if table_lineage and "target_table" in table_lineage and table_lineage["target_table"]:
                    target_table_info = table_lineage["target_table"]
                    
                    # If target_table is a string, convert it to a dict
                    if isinstance(target_table_info, str):
                        target_table = target_table_info
                        target_schema = None
                        target_database = None
                    else:
                        target_table = target_table_info.get("name")
                        target_schema = target_table_info.get("schema")
                        target_database = target_table_info.get("database")
                    
                    if not target_table:
                        # If we didn't get a target table from lineage extraction, try to infer it from the file path
                        base_name = os.path.basename(relative_path)
                        if base_name.endswith('.sql'):
                            base_name = base_name[:-4]
                        target_table = base_name
                        logger.info(f"Inferred target table from filename: {target_table}")
                    
                    # Check if table already exists
                    existing_table = lineage_db.get_table_by_name(target_table, tech_stack)
                    
                    if existing_table:
                        table_id = existing_table["table_id"]
                        logger.info(f"Using existing table {target_table} with ID {table_id}")
                    else:
                        # Add new table
                        table_id = lineage_db.add_table(
                            table_name=target_table,
                            tech_stack=tech_stack,
                            github_path=relative_path,
                            schema_name=target_schema,
                            database_name=target_database,
                            connector_id=connector_id,
                            github_repo=repo_url
                        )
                        logger.info(f"Added new table {target_table} with ID {table_id}")
                    
                    # Process source tables
                    for source_table_info in table_lineage.get("source_tables", []):
                        # Extract source table details
                        if isinstance(source_table_info, str):
                            source_table = source_table_info
                            source_schema = None
                            source_database = None
                        else:
                            source_table = source_table_info.get("name")
                            source_schema = source_table_info.get("schema")
                            source_database = source_table_info.get("database")
                        
                        if not source_table:
                            continue  # Skip if no source table name
                        
                        logger.info(f"Processing source table: {source_table}")
                        
                        # Check if source table already exists
                        existing_source = lineage_db.get_table_by_name(source_table, tech_stack)
                        
                        if existing_source:
                            source_id = existing_source["table_id"]
                            logger.info(f"Using existing source table {source_table} with ID {source_id}")
                        else:
                            # Add new source table
                            source_id = lineage_db.add_table(
                                table_name=source_table,
                                tech_stack=tech_stack,
                                github_path=None,  # Source tables might be in another file
                                schema_name=source_schema,
                                database_name=source_database,
                                connector_id=connector_id,
                                github_repo=repo_url
                            )
                            logger.info(f"Added new source table {source_table} with ID {source_id}")
                        
                        # Add relationship
                        try:
                            relationship_id = lineage_db.add_relationship(
                                source_table_id=source_id,
                                target_table_id=table_id,
                                relationship_type="depends_on",
                                github_path=relative_path,
                                sql_snippet=sql_code[:100] if sql_code else None  # Add sql_snippet parameter
                            )
                            logger.info(f"Added relationship: {source_table} -> {target_table}")
                        except Exception as rel_e:
                            logger.warning(f"Failed to add relationship: {str(rel_e)}")
                    
                    # Process column lineage from SQL files
                    if column_lineage and "target_columns" in column_lineage:
                        for column_info in column_lineage.get("target_columns", []):
                            column_name = column_info.get("name")
                            if not column_name:
                                continue
                            
                            # Add the column to the table
                            try:
                                column_id = lineage_db.add_column(
                                    table_id=table_id,
                                    column_name=column_name,
                                    data_type=column_info.get("data_type"),
                                    business_description=column_info.get("description"),
                                    is_primary_key=column_info.get("is_primary_key", False),
                                    is_foreign_key=column_info.get("is_foreign_key", False)
                                )
                                logger.info(f"Added column {column_name} to table {target_table} from SQL extraction")
                            except Exception as col_e:
                                logger.warning(f"Failed to add column {column_name}: {str(col_e)}")
                    
                    # Process column information from YAML files in dialect_lineage
                    if dialect_lineage and "columns" in dialect_lineage:
                        for column_info in dialect_lineage.get("columns", []):
                            column_name = column_info.get("column_name")
                            table_name = column_info.get("table_name")
                            
                            if not column_name:
                                continue
                                
                            # Important: Map columns to the current target table regardless of their extracted table_name
                            # This ensures columns are properly associated with their tables in the database
                            logger.info(f"Processing column {column_name} for table {target_table}")
                                
                            # Add the column to the table
                            try:
                                column_id = lineage_db.add_column(
                                    table_id=table_id,
                                    column_name=column_name,
                                    data_type=column_info.get("data_type"),
                                    business_description=column_info.get("description"),
                                    is_primary_key=column_info.get("is_primary_key", False),
                                    is_foreign_key=column_info.get("is_foreign_key", False)
                                )
                                logger.info(f"Added column {column_name} to table {target_table} from YAML extraction")
                            except Exception as col_e:
                                logger.warning(f"Failed to add column {column_name}: {str(col_e)}")
                    
                    update_task_progress(task_id, processed=1, successful=1)
                else:
                    # If we didn't get a target table from lineage extraction, try to infer it from the file path
                    base_name = os.path.basename(relative_path)
                    if base_name.endswith('.sql'):
                        base_name = base_name[:-4]
                    target_table = base_name
                    logger.info(f"Inferred target table from filename as fallback: {target_table}")
                    
                    # Check if table already exists
                    existing_table = lineage_db.get_table_by_name(target_table, tech_stack)
                    
                    if existing_table:
                        table_id = existing_table["table_id"]
                        logger.info(f"Using existing table {target_table} with ID {table_id}")
                    else:
                        # Add new table
                        table_id = lineage_db.add_table(
                            table_name=target_table,
                            tech_stack=tech_stack,
                            github_path=relative_path,
                            connector_id=connector_id,
                            github_repo=repo_url
                        )
                        logger.info(f"Added new table {target_table} with ID {table_id}")
                    
                    update_task_progress(task_id, processed=1, successful=1)
            except Exception as e:
                logger.error(f"Error processing file {file_path}: {str(e)}")
                update_task_progress(task_id, processed=1, failed=1)
        
        # Mark task as completed
        finalize_task(task_id, success=True)
        
    except Exception as e:
        logger.error(f"Error processing repository: {str(e)}")
        finalize_task(task_id, success=False, error=str(e))
    
    finally:
        # Clean up temporary directory
        if temp_dir and os.path.exists(temp_dir):
            # Process all DBT files to ensure columns are properly extracted
            if tech_stack.lower() == 'dbt':
                try:
                    logger.info(f"Running enhanced DBT column extraction on {temp_dir}")
                    # Get absolute path to database file
                    db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'database/lineage.db')
                    if not os.path.exists(db_path):
                        logger.error(f"Database file not found at {db_path}")
                    else:
                        logger.info(f"Using database at {db_path}")
                        column_extractor = DBTColumnExtractor(db_path=db_path)
                        column_extractor.process_all_dbt_files(temp_dir, force_refresh=True)
                        logger.info(f"Enhanced DBT column extraction completed successfully")
                except Exception as ext_err:
                    logger.error(f"Error during enhanced column extraction: {str(ext_err)}")
            
            try:
                # Clean up temporary directory
                shutil.rmtree(temp_dir)
                logger.info(f"Cleaned up temporary directory: {temp_dir}")
            except Exception as e:
                logger.error(f"Error cleaning up temporary directory: {str(e)}")

def find_sql_files(directory: str) -> List[str]:
    """
    Find SQL files in a directory recursively
    """
    sql_files = []
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith('.sql'):
                sql_files.append(os.path.join(root, file))
    return sql_files

def get_github_token(connector_id: str) -> Optional[str]:
    """
    Get GitHub token for a connector
    """
    try:
        # Connect to metadata database
        conn = sqlite3.connect(os.path.join('database', 'metadata.db'))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Get connector
        cursor.execute("SELECT token FROM github_connectors WHERE id = ?", (connector_id,))
        connector = cursor.fetchone()
        
        if not connector or not connector['token']:
            return None
        
        # Decrypt token
        from api.github_connectors_api import decrypt_token
        token = decrypt_token(connector['token'])
        
        conn.close()
        return token
    
    except Exception as e:
        logger.error(f"Error getting GitHub token: {str(e)}")
        return None 