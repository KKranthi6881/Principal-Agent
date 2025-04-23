"""
API for SQL lineage extraction and storage
"""

from fastapi import APIRouter, HTTPException, Body, Query, File, UploadFile, Path, Depends
from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Any
import json
import os
import uuid
import logging

# Import local modules
from tools.sql_tools.dialects import get_dialect_parser
from tools.sql_tools.lineage.sqlglot_lineage import SQLGlotLineageExtractor
from database.lineage_db import LineageDB

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