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

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Create router
router = APIRouter(prefix="/api/lineage", tags=["lineage"])

# Initialize lineage database connection
lineage_db = LineageDB()

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
    total_files: int
    processed_files: int
    successful_files: int
    failed_files: int
    elapsed_seconds: float
    error: Optional[str] = None

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
    background_tasks: BackgroundTasks,
    connector_id: str = Path(..., description="GitHub connector ID"),
    tech_stack: Optional[str] = Query(None, description="Override tech stack (optional)"),
    branch: Optional[str] = Query("main", description="Branch to extract from")
):
    """
    Start a background task to extract lineage from a GitHub repository
    
    This will extract lineage from all SQL files in the repository and store it in the
    lineage database. The process runs in the background and can be monitored with
    the task status endpoint.
    """
    try:
        # Get connector details from database
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
        
        connector = dict(connector)
        conn.close()
        
        # Use tech stack from connector if not provided
        if not tech_stack:
            tech_stack = connector.get("tech_stack", "postgresql")
        
        # Get repository URL
        repo_url = connector.get("repo_url")
        if not repo_url:
            owner = connector.get("owner")
            if "repositories" in connector and connector["repositories"]:
                try:
                    repositories = json.loads(connector["repositories"])
                    if repositories and len(repositories) > 0:
                        repo_name = repositories[0]
                        repo_url = f"https://github.com/{owner}/{repo_name}"
                except:
                    pass
        
        if not repo_url:
            raise HTTPException(
                status_code=400,
                detail="No repository URL found for connector"
            )
        
        # Generate task ID
        task_id = f"{connector_id}_{int(time.time())}"
        
        # Start background task
        background_tasks.add_task(
            process_repository_for_lineage,
            connector_id=connector_id,
            repo_url=repo_url,
            tech_stack=tech_stack,
            branch=branch
        )
        
        return {
            "task_id": task_id,
            "status": "started",
            "message": f"Started lineage extraction for {repo_url}",
            "connector_id": connector_id,
            "tech_stack": tech_stack,
            "repo_url": repo_url
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting lineage extraction: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error starting lineage extraction: {str(e)}"
        )

@router.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_task_status(
    task_id: str = Path(..., description="Task ID")
):
    """
    Get the status of a lineage extraction task
    """
    try:
        task = get_lineage_task(task_id)
        
        if not task:
            raise HTTPException(
                status_code=404,
                detail=f"Task {task_id} not found"
            )
        
        return {
            "task_id": task_id,
            **task
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting task status: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error getting task status: {str(e)}"
        )

@router.get("/tasks", response_model=TaskListResponse)
async def get_all_tasks():
    """
    Get all lineage extraction tasks
    """
    try:
        tasks = get_all_lineage_tasks()
        
        # Add task IDs
        tasks_with_ids = []
        for i, task in enumerate(tasks):
            task_with_id = {
                "task_id": f"task_{i}",
                **task
            }
            tasks_with_ids.append(task_with_id)
        
        return {
            "tasks": tasks_with_ids
        }
    
    except Exception as e:
        logger.error(f"Error getting all tasks: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error getting all tasks: {str(e)}"
        )

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