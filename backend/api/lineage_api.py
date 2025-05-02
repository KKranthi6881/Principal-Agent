"""
API for SQL lineage extraction and storage
"""

from fastapi import APIRouter, HTTPException, Body, Query, File, UploadFile, Path, Depends, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Any, Union
import json
import os
import uuid
import logging
import asyncio
import time
import sqlite3

# Import local modules
from tools.sql_tools.dialects import get_dialect_parser
from tools.sql_tools.lineage.sqlglot_lineage import SQLGlotLineageExtractor
from database.lineage_db import LineageDB
from api.lineage_tasks import process_repository_for_lineage, get_lineage_task, get_all_lineage_tasks
from api.chunked_lineage_processor import ChunkedLineageProcessor
from database.task_db import TaskDB

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Create router
router = APIRouter(prefix="/api/lineage", tags=["lineage"])

# Initialize database connections
lineage_db = LineageDB()
task_db = TaskDB()

# Pydantic models for request/response
class SQLParseRequest(BaseModel):
    """Request model for SQL parsing"""
    sql_code: str = Field(..., description="SQL code to parse")
    tech_stack: str = Field(..., description="Tech stack (tsql, dbt, mysql, postgresql, snowflake)")
    github_path: Optional[str] = Field(None, description="Path to the file in GitHub")
    connector_id: Optional[str] = Field(None, description="Connector ID from github_connectors")
    github_repo: Optional[str] = Field(None, description="GitHub repository URL")

class TableLineageRequest(BaseModel):
    """Request model for table lineage"""
    table_name: str = Field(..., description="Table name to analyze lineage for")
    tech_stack: str = Field(..., description="Tech stack (tsql, dbt, mysql, postgresql, snowflake)")
    include_columns: bool = Field(True, description="Whether to include column-level lineage")

class LineageResponse(BaseModel):
    """Response model for lineage information"""
    lineage_id: str
    table_name: str
    tech_stack: str
    lineage_json: Dict
    created_at: str

class TaskResponse(BaseModel):
    """Response model for task information"""
    task_id: str
    status: str
    connector_id: str
    repo_url: str
    tech_stack: str
    total_items: int
    processed_items: int
    successful_items: int
    failed_items: int
    elapsed_seconds: float
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    chunks: Optional[List[Dict[str, Any]]] = None

class TaskListResponse(BaseModel):
    """Response model for list of tasks"""
    tasks: List[TaskResponse]

# API endpoints
@router.post("/parse", response_model=Dict[str, Any])
async def parse_sql_for_lineage(request: SQLParseRequest):
    """
    Parse SQL code using the specified tech stack and extract lineage information
    """
    try:
        # Get the appropriate dialect handler
        dialect_handler = get_dialect_parser(request.tech_stack)
        if not dialect_handler:
            raise HTTPException(
                status_code=400, 
                detail=f"Unsupported tech stack: {request.tech_stack}"
            )
        
        # Parse SQL using the dialect handler
        sql_ast, errors = dialect_handler.parse_sql(request.sql_code)
        
        if errors:
            return {
                "success": False,
                "errors": errors,
                "tech_stack": request.tech_stack
            }
        
        if not sql_ast:
            return {
                "success": False,
                "errors": ["Failed to parse SQL code"],
                "tech_stack": request.tech_stack
            }
        
        # Extract lineage information
        lineage_extractor = SQLGlotLineageExtractor()
        table_lineage = lineage_extractor.extract_table_lineage(sql_ast, request.github_path)
        column_lineage = lineage_extractor.extract_column_lineage(sql_ast, request.github_path)
        
        # Store in lineage database
        lineage_info = {
            "table_lineage": table_lineage,
            "column_lineage": column_lineage
        }
        
        # Store target table if found
        table_id = None
        if table_lineage.get("target_table"):
            target_table = table_lineage["target_table"]
            
            # Check if table already exists
            existing_table = lineage_db.get_table_by_name(target_table, request.tech_stack)
            
            if existing_table:
                table_id = existing_table["table_id"]
            else:
                # Split into schema and table parts if applicable
                schema_name = None
                table_name = target_table
                
                if "." in target_table:
                    parts = target_table.split(".")
                    if len(parts) == 2:
                        schema_name, table_name = parts
                    elif len(parts) == 3:
                        database_name, schema_name, table_name = parts
                
                # Add the table to the database
                table_id = lineage_db.add_table(
                    table_name=table_name,
                    tech_stack=request.tech_stack,
                    github_path=request.github_path,
                    schema_name=schema_name,
                    connector_id=request.connector_id,
                    github_repo=request.github_repo
                )
            
            # Add a lineage definition
            if table_id:
                lineage_id = lineage_db.add_lineage_definition(
                    root_table_id=table_id,
                    lineage_json=lineage_info,
                    tech_stack=request.tech_stack
                )
                
                return {
                    "success": True,
                    "lineage_id": lineage_id,
                    "table_id": table_id,
                    "table_name": target_table,
                    "tech_stack": request.tech_stack,
                    "lineage_info": lineage_info
                }
        
        return {
            "success": True,
            "tech_stack": request.tech_stack,
            "lineage_info": lineage_info
        }
        
    except Exception as e:
        logger.error(f"Error parsing SQL: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error processing SQL: {str(e)}"
        )

@router.get("/table/{table_name}")
async def get_table_lineage(
    table_name: str = Path(..., description="Table name to get lineage for"),
    tech_stack: str = Query(..., description="Tech stack (tsql, dbt, mysql, postgresql, snowflake)"),
    include_columns: bool = Query(True, description="Whether to include column-level information")
):
    """
    Get lineage information for a table
    """
    try:
        # Find the table
        table = lineage_db.get_table_by_name(table_name, tech_stack)
        
        if not table:
            raise HTTPException(
                status_code=404,
                detail=f"Table '{table_name}' not found for tech stack '{tech_stack}'"
            )
        
        # Get lineage definition
        lineage_def = lineage_db.get_lineage_definition(table["table_id"])
        
        if not lineage_def:
            raise HTTPException(
                status_code=404,
                detail=f"No lineage information found for table '{table_name}'"
            )
        
        # Get relationships
        relationships = lineage_db.get_relationships_for_table(table["table_id"])
        
        # Get columns if requested
        columns = []
        if include_columns:
                        columns = lineage_db.get_columns_for_table(table["table_id"])
        
        return {
            "table": table,
            "lineage": lineage_def,
            "relationships": relationships,
            "columns": columns
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting table lineage: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error getting table lineage: {str(e)}"
        )

@router.get("/tech-stack/{tech_stack}")
async def get_lineage_by_tech_stack(
    tech_stack: str = Path(..., description="Tech stack (tsql, dbt, mysql, postgresql, snowflake)")
):
    """
    Get all lineage information for a specific tech stack
    """
    try:
        # Get all lineage definitions for this tech stack
        lineage_defs = lineage_db.get_lineage_by_tech_stack(tech_stack)
        
        if not lineage_defs:
            return {
                "tech_stack": tech_stack,
                "count": 0,
                "lineage_definitions": []
            }
        
        return {
            "tech_stack": tech_stack,
            "count": len(lineage_defs),
            "lineage_definitions": lineage_defs
        }
    
    except Exception as e:
        logger.error(f"Error getting lineage by tech stack: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error getting lineage by tech stack: {str(e)}"
        )

@router.get("/lineage/{lineage_id}")
async def get_lineage_by_id(
    lineage_id: str = Path(..., description="Lineage ID")
):
    """
    Get a specific lineage definition by ID
    """
    try:
        # Get the lineage definition
        lineage_def = lineage_db.get_lineage_definition(lineage_id=lineage_id)
        
        if not lineage_def:
            raise HTTPException(
                status_code=404,
                detail=f"Lineage definition with ID {lineage_id} not found"
            )
        
        return lineage_def
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting lineage definition: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error getting lineage definition: {str(e)}"
        )

@router.post("/github-connector/{connector_id}/parse")
async def parse_from_github_connector(
    connector_id: str = Path(..., description="GitHub connector ID"),
    tech_stack: str = Query(None, description="Override tech stack (optional)"),
    file_path: str = Query(None, description="Specific file path to parse (optional)")
):
    """
    Parse SQL files from a GitHub connector
    """
    try:
        # Get the connector details
        conn = sqlite3.connect(os.path.join('database', 'metadata.db'))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM github_connectors WHERE id = ?", (connector_id,))
        connector = cursor.fetchone()
        
        if not connector:
            raise HTTPException(
                status_code=404,
                detail=f"GitHub connector with ID {connector_id} not found"
            )
        
        # Use connector's tech stack if not overridden
        connector_dict = dict(connector)
        connector_tech_stack = tech_stack or connector_dict.get('tech_stack') or 'postgresql'
        
        # Get the GitHub file content
        from tools.sql_tools.github_sql_finder import GitHubSQLFinder
        
        vector_store_path = os.path.join(os.getcwd(), "vector_store", "chromadb_github")
        sql_finder = GitHubSQLFinder(vector_store_path)
        
        # Initialize the finder
        sql_finder.initialize()
        
        # Find SQL files
        if file_path:
            # Search for a specific file
            sql_files = sql_finder.search_sql_files(file_path, limit=1)
        else:
            # Search for all SQL files
            sql_files = sql_finder.search_sql_files("SELECT * FROM", limit=100)
        
        if not sql_files:
            return {
                "success": False,
                "message": "No SQL files found",
                "connector_id": connector_id,
                "tech_stack": connector_tech_stack
            }
        
        # Process each SQL file
        processed_files = []
        
        for sql_file in sql_files:
            if not isinstance(sql_file, dict) or not sql_file.get('content'):
                continue
            
            try:
                # Use dialect handler to parse the SQL
                dialect_handler = get_dialect_parser(connector_tech_stack)
                if not dialect_handler:
                    logger.warning(f"Unsupported tech stack: {connector_tech_stack}")
                    continue
                
                # Parse SQL using the dialect handler
                sql_ast, errors = dialect_handler.parse_sql(sql_file['content'])
                
                if errors or not sql_ast:
                    processed_files.append({
                        "file_path": sql_file.get('path'),
                        "success": False,
                        "errors": errors or ["Failed to parse SQL code"]
                    })
                    continue
                
                # Extract lineage information
                lineage_extractor = SQLGlotLineageExtractor()
                table_lineage = lineage_extractor.extract_table_lineage(sql_ast, sql_file.get('path'))
                column_lineage = lineage_extractor.extract_column_lineage(sql_ast, sql_file.get('path'))
                
                lineage_info = {
                    "table_lineage": table_lineage,
                    "column_lineage": column_lineage
                }
                
                # Store target table if found
                table_id = None
                lineage_id = None
                
                if table_lineage.get("target_table"):
                    target_table = table_lineage["target_table"]
                    
                    # Check if table already exists
                    existing_table = lineage_db.get_table_by_name(target_table, connector_tech_stack)
                    
                    if existing_table:
                        table_id = existing_table["table_id"]
                    else:
                        # Split into schema and table parts if applicable
                        schema_name = None
                        database_name = None
                        table_name = target_table
                        
                        if "." in target_table:
                            parts = target_table.split(".")
                            if len(parts) == 2:
                                schema_name, table_name = parts
                            elif len(parts) == 3:
                                database_name, schema_name, table_name = parts
                        
                        # Add the table to the database
                        table_id = lineage_db.add_table(
                            table_name=table_name,
                            tech_stack=connector_tech_stack,
                            github_path=sql_file.get('path'),
                            schema_name=schema_name,
                            database_name=database_name,
                            connector_id=connector_id,
                            github_repo=connector_dict.get('repo_url')
                        )
                    
                    # Add a lineage definition
                    if table_id:
                        lineage_id = lineage_db.add_lineage_definition(
                            root_table_id=table_id,
                            lineage_json=lineage_info,
                            tech_stack=connector_tech_stack
                        )
                
                processed_files.append({
                    "file_path": sql_file.get('path'),
                    "success": True,
                    "target_table": table_lineage.get("target_table"),
                    "table_id": table_id,
                    "lineage_id": lineage_id
                })
                
            except Exception as e:
                logger.error(f"Error processing file {sql_file.get('path')}: {str(e)}")
                processed_files.append({
                    "file_path": sql_file.get('path'),
                    "success": False,
                    "error": str(e)
                })
        
        return {
            "success": True,
            "connector_id": connector_id,
            "tech_stack": connector_tech_stack,
            "files_processed": len(processed_files),
            "results": processed_files
        }
        
    except Exception as e:
        logger.error(f"Error parsing from GitHub connector: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error parsing from GitHub connector: {str(e)}"
        )

@router.post("/github-connector/{connector_id}/extract-lineage", response_model=Dict[str, Any])
async def extract_lineage_from_github(
    connector_id: str = Path(..., description="GitHub connector ID"),
    tech_stack: Optional[str] = Query(None, description="Override tech stack (optional)"),
    branch: Optional[str] = Query("main", description="Branch to extract from"),
    chunk_size: Optional[int] = Query(50, description="Number of files per processing chunk")
):
    """
    Start a background task to extract lineage from a GitHub repository
    
    This will extract lineage from all SQL files in the repository and store it in the
    lineage database. The extraction will run in the background and can be monitored
    using the /task/{task_id} endpoint.
    
    Args:
        connector_id: GitHub connector ID
        tech_stack: Override tech stack (optional)
        branch: Branch to extract from
        chunk_size: Number of files per processing chunk (default: 50)
    """
    try:
        # Get the GitHub connector
        conn = sqlite3.connect(os.path.join('database', 'metadata.db'))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM github_connectors WHERE id = ?", (connector_id,))
        connector = cursor.fetchone()
        
        if not connector:
            raise HTTPException(status_code=404, detail=f"GitHub connector {connector_id} not found")
        
        # Convert to dict
        connector_dict = dict(connector)
        
        # Determine the repository URL
        repo_url = connector_dict.get('repo_url')
        
        if not repo_url and connector_dict.get('repositories'):
            # Try to construct a URL from owner/repo or organization/repo
            repositories = json.loads(connector_dict['repositories'])
            if repositories and len(repositories) > 0:
                owner = connector_dict.get('owner')
                organization = connector_dict.get('organization')
                
                # Use first repository for now
                repo_name = repositories[0]
                
                if owner:
                    repo_url = f"https://github.com/{owner}/{repo_name}"
                elif organization:
                    repo_url = f"https://github.com/{organization}/{repo_name}"
        
        if not repo_url:
            raise HTTPException(
                status_code=400, 
                detail="Unable to determine repository URL from connector settings"
            )
        
        # Use connector's tech stack if not overridden
        if not tech_stack:
            tech_stack = connector_dict.get('tech_stack', 'postgresql')
        
        # Use connector's branch if provided
        if not branch and connector_dict.get('default_branch'):
            branch = connector_dict.get('default_branch')
        
        # Create and start the chunked processor
        processor = ChunkedLineageProcessor(
            connector_id=connector_id,
            repo_url=repo_url,
            tech_stack=tech_stack,
            branch=branch,
            chunk_size=chunk_size
        )
        
        # Start processing in background
        task_id = await processor.process()
        
        return {
            "success": True,
            "task_id": task_id,
            "message": f"Started lineage extraction for {repo_url}",
            "tech_stack": tech_stack,
            "branch": branch,
            "chunk_size": chunk_size
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting lineage extraction: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail=f"Error starting lineage extraction: {str(e)}"
        )

@router.get("/task/{task_id}", response_model=TaskResponse)
async def get_task_status(
    task_id: str = Path(..., description="Task ID")
):
    """
    Get the status of a lineage extraction task
    """
    try:
        # Get task status from the task database
        task_status = task_db.get_task(task_id)
        
        if not task_status:
            # Try the old method as fallback for compatibility
            legacy_task = get_lineage_task(task_id)
            if not legacy_task:
                raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
            
            # Convert legacy task format to new format
            return {
                "task_id": task_id,
                "status": legacy_task["status"],
                "connector_id": legacy_task["connector_id"],
                "repo_url": legacy_task["repo_url"],
                "tech_stack": legacy_task["tech_stack"],
                "total_items": legacy_task["total_files"],
                "processed_items": legacy_task["processed_files"],
                "successful_items": legacy_task["successful_files"],
                "failed_items": legacy_task["failed_files"],
                "elapsed_seconds": time.time() - legacy_task["start_time"],
                "error": legacy_task.get("error"),
                "metadata": {},
                "chunks": []
            }
        
        # Calculate progress percentage
        progress = 0
        if task_status["total_items"] > 0:
            progress = (task_status["processed_items"] / task_status["total_items"]) * 100
            
        # Make sure elapsed_seconds is properly calculated if it's missing
        if "elapsed_seconds" not in task_status or task_status["elapsed_seconds"] == 0:
            if "created_at" in task_status:
                task_status["elapsed_seconds"] = time.time() - task_status["created_at"]
        
        # Format the response
        return {
            "task_id": task_status["task_id"],
            "status": task_status["status"],
            "connector_id": task_status["connector_id"],
            "repo_url": task_status["repo_url"],
            "tech_stack": task_status["tech_stack"],
            "total_items": task_status["total_items"],
            "processed_items": task_status["processed_items"],
            "successful_items": task_status["successful_items"],
            "failed_items": task_status["failed_items"],
            "elapsed_seconds": task_status["elapsed_seconds"],
            "error": task_status.get("error"),
            "metadata": task_status.get("metadata", {}),
            "chunks": task_status.get("chunks", [])
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting task status: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting task status: {str(e)}")

@router.get("/tasks", response_model=TaskListResponse)
async def get_all_tasks(
    limit: Optional[int] = Query(20, description="Maximum number of tasks to return"),
    status: Optional[str] = Query(None, description="Filter by status (pending, running, completed, failed)")
):
    """
    Get all lineage extraction tasks
    """
    try:
        # Get tasks from the task database
        db_tasks = task_db.list_tasks(status=status, task_type="lineage_extraction", limit=limit)
        
        # Also get legacy tasks for compatibility
        legacy_tasks = get_all_lineage_tasks()
        
        # Format tasks
        formatted_tasks = []
        
        # Process new-style tasks
        for task in db_tasks:
            # Calculate progress percentage
            progress = 0
            if task["total_items"] > 0:
                progress = (task["processed_items"] / task["total_items"]) * 100
                
            # Make sure elapsed_seconds is properly calculated if it's missing
            if "elapsed_seconds" not in task or task["elapsed_seconds"] == 0:
                if "created_at" in task:
                    task["elapsed_seconds"] = time.time() - task["created_at"]
            
            formatted_tasks.append({
                "task_id": task["task_id"],
                "status": task["status"],
                "connector_id": task["connector_id"],
                "repo_url": task["repo_url"],
                "tech_stack": task["tech_stack"],
                "total_items": task["total_items"],
                "processed_items": task["processed_items"],
                "successful_items": task["successful_items"],
                "failed_items": task["failed_items"],
                "elapsed_seconds": task["elapsed_seconds"],
                "error": task.get("error"),
                "metadata": task.get("metadata", {}),
                "chunks": task.get("chunks", [])
            })
        
        # Process legacy tasks (older format)
        current_time = time.time()
        for task in legacy_tasks:
            # Skip if this task ID is already in the formatted list
            if any(t["task_id"] == task.get("task_id") for t in formatted_tasks):
                continue
                
            elapsed_seconds = current_time - task["start_time"]
            
            formatted_tasks.append({
                "task_id": task.get("task_id", f"legacy_{int(time.time())}"),
                "status": task["status"],
                "connector_id": task["connector_id"],
                "repo_url": task["repo_url"],
                "tech_stack": task["tech_stack"],
                "total_items": task["total_files"],
                "processed_items": task["processed_files"],
                "successful_items": task["successful_files"],
                "failed_items": task["failed_files"],
                "elapsed_seconds": elapsed_seconds,
                "error": task.get("error"),
                "metadata": {},
                "chunks": []
            })
        
        # Sort by creation time (newest first)
        formatted_tasks.sort(key=lambda x: x.get("elapsed_seconds", 0), reverse=True)
        
        # Apply limit
        formatted_tasks = formatted_tasks[:limit]
        
        return {"tasks": formatted_tasks}
    except Exception as e:
        logger.error(f"Error getting all tasks: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting all tasks: {str(e)}")

@router.get("/export/{table_name}", response_model=Dict[str, Any])
async def export_lineage_json(
    table_name: str = Path(..., description="Table name to export lineage for"),
    tech_stack: str = Query(..., description="Tech stack (tsql, dbt, mysql, postgresql, snowflake)")
):
    """
    Export complete lineage information as JSON with GitHub file references
    
    This endpoint provides a comprehensive lineage graph that includes table metadata,
    relationships, and GitHub file links for visualization in a UI.
    """
    try:
        # Find the table
        table = lineage_db.get_table_by_name(table_name, tech_stack)
        
        if not table:
            raise HTTPException(
                status_code=404,
                detail=f"Table '{table_name}' not found for tech stack '{tech_stack}'"
            )
        
        # Export the complete lineage
        lineage_json = lineage_db.export_lineage_to_json(root_table_id=table["table_id"])
        
        if not lineage_json:
            raise HTTPException(
                status_code=404,
                detail=f"No lineage information found for table '{table_name}'"
            )
        
        return lineage_json
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error exporting lineage JSON: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error exporting lineage JSON: {str(e)}"
        )

@router.get("/export-columns/{table_name}", response_model=Dict[str, Any])
async def export_column_lineage_json(
    table_name: str = Path(..., description="Table name to export column lineage for"),
    tech_stack: str = Query(..., description="Tech stack (tsql, dbt, mysql, postgresql, snowflake)")
):
    """
    Export column-level lineage information as JSON with GitHub file references
    
    This endpoint provides detailed column-level lineage for visualization in a UI,
    showing how data flows from source columns to target columns.
    """
    try:
        # Find the table
        table = lineage_db.get_table_by_name(table_name, tech_stack)
        
        if not table:
            raise HTTPException(
                status_code=404,
                detail=f"Table '{table_name}' not found for tech stack '{tech_stack}'"
            )
        
        # Export the complete lineage
        lineage_json = lineage_db.export_lineage_to_json(root_table_id=table["table_id"])
        
        if not lineage_json:
            raise HTTPException(
                status_code=404,
                detail=f"No lineage information found for table '{table_name}'"
            )
        
        # Format the response specifically for column-level visualization
        result = {
            "table_id": lineage_json["root_table_id"],
            "table_name": lineage_json["root_table_name"],
            "tech_stack": lineage_json["tech_stack"],
            "tables": lineage_json["tables"],
            "column_relationships": lineage_json["column_relationships"],
            "github_links": {}
        }
        
        # Extract GitHub links from tables
        for table in lineage_json["tables"]:
            if "github_url" in table and table["github_url"]:
                result["github_links"][table["table_id"]] = {
                    "table_name": table["table_name"],
                    "github_path": table.get("github_path"),
                    "github_url": table["github_url"]
                }
        
        # Add column metadata if available
        if "column_metadata" in lineage_json:
            result["column_metadata"] = lineage_json["column_metadata"]
        
        return result
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error exporting column lineage JSON: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error exporting column lineage JSON: {str(e)}"
        )

@router.get("/by-path", response_model=Dict[str, Any])
async def get_lineage_by_github_path(
    github_path: str = Query(..., description="GitHub path to get lineage for")
):
    """
    Get lineage definition by GitHub path
    
    This endpoint retrieves lineage information for a file based on its GitHub path.
    It's useful for the repository browser to display lineage visualization for SQL files.
    """
    try:
        # Use the LineageDB method to get lineage by GitHub path
        lineage_def = lineage_db.get_lineage_by_github_path(github_path)
        
        if not lineage_def:
            # Not raising an exception as not all files have lineage
            return {
                "success": False,
                "message": f"No lineage data found for GitHub path: {github_path}"
            }
        
        return {
            "success": True,
            "lineage_id": lineage_def["lineage_id"],
            "table_name": lineage_def["table_name"],
            "tech_stack": lineage_def["tech_stack"],
            "lineage_json": lineage_def["lineage_json"],
            "github_path": github_path,
            "created_at": lineage_def["created_at"]
        }
    
    except Exception as e:
        logger.error(f"Error retrieving lineage by GitHub path: {str(e)}")
        return {
            "success": False,
            "message": f"Error retrieving lineage data: {str(e)}"
        }

@router.get("/export-file/{tech_stack}", response_model=Dict[str, Any])
async def export_lineage_to_file(
    tech_stack: str = Path(..., description="Tech stack to export (tsql, dbt, mysql, postgresql, snowflake)"),
    table_name: str = Query(None, description="Optional table name to filter by"),
    output_dir: str = Query("exports", description="Directory to save the JSON file to"),
    filename: str = Query(None, description="Optional filename for the exported JSON")
):
    """
    Export lineage data to a JSON file for external visualization tools
    
    This endpoint saves the lineage data to a JSON file that can be used by external
    visualization tools. The file is saved to the specified directory (default is 'exports').
    """
    try:
        # If table name is provided, get its ID
        root_table_id = None
        if table_name:
            table = lineage_db.get_table_by_name(table_name, tech_stack)
            if not table:
                raise HTTPException(
                    status_code=404,
                    detail=f"Table '{table_name}' not found for tech stack '{tech_stack}'"
                )
            root_table_id = table["table_id"]
        
        # Export lineage data to file
        file_path = lineage_db.save_lineage_to_json_file(
            root_table_id=root_table_id,
            tech_stack=tech_stack if not root_table_id else None,
            output_dir=output_dir,
            filename=filename
        )
        
        if not file_path:
            if root_table_id:
                raise HTTPException(
                    status_code=404,
                    detail=f"No lineage data found for table ID {root_table_id}"
                )
            else:
                raise HTTPException(
                    status_code=404,
                    detail=f"No lineage data found for tech stack {tech_stack}"
                )
        
        return {
            "success": True,
            "tech_stack": tech_stack,
            "table_name": table_name,
            "file_path": file_path,
            "message": f"Lineage data exported successfully to {file_path}"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error exporting lineage data to file: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error exporting lineage data to file: {str(e)}"
        )