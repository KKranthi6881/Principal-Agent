"""
SQL Analysis API

This module provides FastAPI endpoints for SQL analysis capabilities.
"""

from fastapi import APIRouter, HTTPException, Depends, Body, Query, UploadFile, File
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
import json

from tools.sql_tools.api import sql_api

router = APIRouter(prefix="/api/sql", tags=["sql"])

# Pydantic models for request/response
class DialectInfoResponse(BaseModel):
    """Response model for dialect info"""
    dialects: Dict[str, str]

class SQLCodeRequest(BaseModel):
    """Request model for SQL code analysis"""
    sql_code: str = Field(..., description="SQL code to analyze")
    dialect: Optional[str] = Field(None, description="SQL dialect (e.g., dbt, postgres, snowflake)")
    file_path: Optional[str] = Field(None, description="Path to the file")

class DependencyAnalysisResponse(BaseModel):
    """Response model for dependency analysis"""
    file_path: Optional[str] = None
    dialect: str
    target_table: Optional[str] = None
    source_tables: List[str] = []
    dependencies: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []

class LineageAnalysisResponse(BaseModel):
    """Response model for lineage analysis"""
    file_path: Optional[str] = None
    dialect: str
    target_table: Optional[str] = None
    source_tables: List[str] = []
    column_level_lineage: Dict[str, List[Dict[str, Any]]] = {}
    errors: List[Dict[str, Any]] = []

class TableSearchRequest(BaseModel):
    """Request model for table search"""
    table_name: str = Field(..., description="Table name to search for")
    limit: Optional[int] = Field(20, description="Maximum number of results")

class ColumnSearchRequest(BaseModel):
    """Request model for column search"""
    table_name: str = Field(..., description="Table name")
    column_name: str = Field(..., description="Column name")
    limit: Optional[int] = Field(20, description="Maximum number of results")

class SQLFileResponse(BaseModel):
    """Response model for SQL file search"""
    file_path: str
    content: str
    url: Optional[str] = None
    github_repo: Optional[str] = None
    dialect: Optional[str] = None

class SearchResponse(BaseModel):
    """Response model for search results"""
    query: str
    results: List[SQLFileResponse] = []
    count: int

class RepositoryAnalysisRequest(BaseModel):
    """Request model for repository analysis"""
    repo_url: str = Field(..., description="GitHub repository URL")
    dialect: Optional[str] = Field(None, description="SQL dialect to use")
    connector_id: Optional[str] = Field(None, description="Connector ID")

class ColumnLineageRequest(BaseModel):
    """Request model for column lineage tracing"""
    table_name: str = Field(..., description="Table name")
    column_name: str = Field(..., description="Column name")

class CompleteLineageRequest(BaseModel):
    """Request model for complete table lineage tracing"""
    table_name: str = Field(..., description="Table name to trace lineage for")
    direction: str = Field("upstream", description="Direction: 'upstream' or 'downstream'")
    max_depth: int = Field(10, description="Maximum recursion depth")
    dialect: Optional[str] = Field(None, description="SQL dialect to use (dbt, postgresql, snowflake, mysql, tsql)")
    repo_url: Optional[str] = Field(None, description="Repository URL to help detect dialect if not specified")

class CompleteColumnLineageRequest(BaseModel):
    """Request model for complete column lineage tracing"""
    table_name: str = Field(..., description="Table name")
    column_name: str = Field(..., description="Column name")
    direction: str = Field("upstream", description="Direction: 'upstream' or 'downstream'")
    max_depth: int = Field(10, description="Maximum recursion depth")
    dialect: Optional[str] = Field(None, description="SQL dialect to use (dbt, postgresql, snowflake, mysql, tsql)")
    repo_url: Optional[str] = Field(None, description="Repository URL to help detect dialect if not specified")

# API endpoints
@router.get("/dialects", response_model=DialectInfoResponse)
async def get_available_dialects():
    """Get available SQL dialects"""
    dialects = sql_api.list_available_dialects()
    return {"dialects": dialects}

@router.post("/dependencies", response_model=DependencyAnalysisResponse)
async def analyze_dependencies(request: SQLCodeRequest):
    """Analyze SQL code for dependencies"""
    try:
        result = sql_api.extract_dependencies(
            request.sql_code, 
            request.dialect, 
            request.file_path
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error analyzing dependencies: {str(e)}")

@router.post("/lineage", response_model=LineageAnalysisResponse)
async def analyze_lineage(request: SQLCodeRequest):
    """Analyze SQL code for lineage"""
    try:
        result = sql_api.extract_lineage(
            request.sql_code, 
            request.dialect, 
            request.file_path
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error analyzing lineage: {str(e)}")

@router.post("/search/table", response_model=SearchResponse)
async def search_for_table(request: TableSearchRequest):
    """Search for SQL files that reference a specific table"""
    try:
        results = sql_api.search_for_table(request.table_name, request.limit)
        return {
            "query": f"table:{request.table_name}",
            "results": results,
            "count": len(results)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error searching for table: {str(e)}")

@router.post("/search/column", response_model=SearchResponse)
async def search_for_column(request: ColumnSearchRequest):
    """Search for SQL files that reference a specific column"""
    try:
        results = sql_api.search_for_column(request.table_name, request.column_name, request.limit)
        return {
            "query": f"table:{request.table_name} column:{request.column_name}",
            "results": results,
            "count": len(results)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error searching for column: {str(e)}")

@router.post("/search/query", response_model=SearchResponse)
async def search_sql_files(query: str = Body(..., embed=True), limit: int = Body(20, embed=True)):
    """Search for SQL files based on a query"""
    try:
        results = sql_api.search_for_sql_files(query, limit)
        return {
            "query": query,
            "results": results,
            "count": len(results)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error searching for SQL files: {str(e)}")

@router.post("/file/upload")
async def analyze_uploaded_file(
    file: UploadFile = File(...),
    dialect: Optional[str] = None
):
    """Analyze an uploaded SQL file"""
    try:
        # Save the uploaded file temporarily
        file_content = await file.read()
        file_path = file.filename
        sql_code = file_content.decode('utf-8')
        
        # Process the file
        dependencies = sql_api.extract_dependencies(sql_code, dialect, file_path)
        lineage = sql_api.extract_lineage(sql_code, dialect, file_path)
        
        # Return combined results
        return {
            "file_name": file_path,
            "dialect": dialect or sql_api.detect_dialect(sql_code, file_path),
            "dependencies": dependencies,
            "lineage": lineage
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error analyzing uploaded file: {str(e)}")

@router.post("/repository/analyze")
async def analyze_repository(request: RepositoryAnalysisRequest):
    """Analyze SQL files in a GitHub repository"""
    try:
        # Get connector_id from the request
        connector_id = request.connector_id if hasattr(request, 'connector_id') else None
        tech_stack = None
        
        # If connector_id is provided, get the tech_stack from the connector
        if connector_id:
            try:
                from api.github_connectors_api import get_db_connection
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM github_connectors WHERE id = ?", (connector_id,))
                connector = cursor.fetchone()
                conn.close()
                
                if connector and 'tech_stack' in connector:
                    tech_stack = connector['tech_stack']
            except Exception as e:
                # Log the error but continue with default tech_stack
                print(f"Error retrieving connector tech_stack: {str(e)}")
        
        # Use the dialect from the request or tech_stack from the connector
        dialect = request.dialect or tech_stack
        
        results = sql_api.analyze_repository(request.repo_url, dialect, tech_stack)
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error analyzing repository: {str(e)}")

@router.post("/column/lineage")
async def trace_column_lineage(request: ColumnLineageRequest):
    """Trace lineage for a specific column"""
    try:
        results = sql_api.trace_column_lineage(request.table_name, request.column_name)
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error tracing column lineage: {str(e)}")

@router.post("/table/complete-lineage")
async def trace_complete_lineage(request: CompleteLineageRequest):
    """
    Trace complete lineage for a table through all levels of dependencies
    
    This endpoint recursively follows table dependencies either upstream
    (from target to sources) or downstream (from source to targets).
    """
    try:
        if request.direction not in ["upstream", "downstream"]:
            raise HTTPException(
                status_code=400, 
                detail="Direction must be either 'upstream' or 'downstream'"
            )
        
        # Determine dialect to use
        dialect = request.dialect
        if not dialect and request.repo_url:
            dialect = sql_api.detect_dialect_from_repo_url(request.repo_url)
            logger.info(f"Auto-detected dialect {dialect} from repo URL: {request.repo_url}")
        
        result = sql_api.trace_complete_lineage(
            request.table_name,
            request.direction,
            request.max_depth,
            dialect
        )
        
        if "error" in result:
            raise HTTPException(status_code=500, detail=result["error"])
            
        return result
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Error tracing complete lineage: {str(e)}"
        )

@router.post("/column/complete-lineage")
async def trace_complete_column_lineage(request: CompleteColumnLineageRequest):
    """
    Trace complete lineage for a specific column through all levels of dependencies
    
    This endpoint recursively follows column dependencies either upstream
    (from target to sources) or downstream (from source to targets).
    """
    try:
        if request.direction not in ["upstream", "downstream"]:
            raise HTTPException(
                status_code=400, 
                detail="Direction must be either 'upstream' or 'downstream'"
            )
        
        # Determine dialect to use
        dialect = request.dialect
        if not dialect and request.repo_url:
            dialect = sql_api.detect_dialect_from_repo_url(request.repo_url)
            logger.info(f"Auto-detected dialect {dialect} from repo URL: {request.repo_url}")
        
        result = sql_api.trace_column_complete_lineage(
            request.table_name,
            request.column_name,
            request.direction,
            request.max_depth,
            dialect
        )
        
        if "error" in result:
            raise HTTPException(status_code=500, detail=result["error"])
            
        return result
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Error tracing complete column lineage: {str(e)}"
        ) 