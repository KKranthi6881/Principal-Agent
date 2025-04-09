"""
FastAPI Routes for LLM SQL Analysis

This module provides API routes for LLMs to interact with SQL analysis tools.
"""

import os
import json
import logging
from typing import Dict, List, Optional, Any, Union
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

# Configure logging - keep it minimal for production
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import the LLM interface
try:
    from tools.sql_tools.llm_interface import llm_interface
except ImportError:
    from backend.tools.sql_tools.llm_interface import llm_interface

# Create router
router = APIRouter(prefix="/api/llm/sql", tags=["llm"])

# Pydantic models
class TableLineageRequest(BaseModel):
    """Request model for table lineage tracing"""
    table_name: str = Field(..., description="Table name to trace lineage for")
    direction: str = Field("upstream", description="Direction: 'upstream' or 'downstream'")
    max_depth: int = Field(3, description="Maximum recursion depth")
    dialect: Optional[str] = Field(None, description="SQL dialect to use (dbt, postgresql, snowflake, mysql, tsql)")
    repo_url: Optional[str] = Field(None, description="Repository URL to help detect dialect if not specified")

class ColumnLineageRequest(BaseModel):
    """Request model for column lineage tracing"""
    table_name: str = Field(..., description="Table name")
    column_name: str = Field(..., description="Column name")
    direction: str = Field("upstream", description="Direction: 'upstream' or 'downstream'")
    max_depth: int = Field(3, description="Maximum recursion depth")
    dialect: Optional[str] = Field(None, description="SQL dialect to use (dbt, postgresql, snowflake, mysql, tsql)")
    repo_url: Optional[str] = Field(None, description="Repository URL to help detect dialect if not specified")

class SearchTableRequest(BaseModel):
    """Request model for table search"""
    table_name: str = Field(..., description="Table name to search for")
    limit: int = Field(5, description="Maximum number of results")

class SearchSQLRequest(BaseModel):
    """Request model for SQL search"""
    query: str = Field(..., description="Search query")
    limit: int = Field(5, description="Maximum number of results")

class DetectDialectRequest(BaseModel):
    """Request model for dialect detection"""
    repo_url: str = Field(..., description="Repository URL")

# API routes
@router.post("/table_lineage")
async def trace_table_lineage(request: TableLineageRequest):
    """
    Trace table lineage for LLM consumption
    
    This endpoint provides a simplified response format optimized for LLMs.
    """
    try:
        result = llm_interface.get_table_lineage(
            table_name=request.table_name,
            direction=request.direction,
            max_depth=request.max_depth,
            dialect=request.dialect,
            repo_url=request.repo_url
        )
        return result
    except Exception as e:
        logger.error(f"Error tracing table lineage: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error tracing table lineage: {str(e)}")

@router.post("/column_lineage")
async def trace_column_lineage(request: ColumnLineageRequest):
    """
    Trace column lineage for LLM consumption
    
    This endpoint provides a simplified response format optimized for LLMs.
    """
    try:
        result = llm_interface.get_column_lineage(
            table_name=request.table_name,
            column_name=request.column_name,
            direction=request.direction,
            max_depth=request.max_depth,
            dialect=request.dialect,
            repo_url=request.repo_url
        )
        return result
    except Exception as e:
        logger.error(f"Error tracing column lineage: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error tracing column lineage: {str(e)}")

@router.post("/search_table")
async def search_table(request: SearchTableRequest):
    """
    Search for tables in the codebase for LLM consumption
    
    This endpoint provides a simplified response format optimized for LLMs.
    """
    try:
        result = llm_interface.search_tables(
            table_name=request.table_name,
            limit=request.limit
        )
        return result
    except Exception as e:
        logger.error(f"Error searching for table: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error searching for table: {str(e)}")

@router.post("/search_sql")
async def search_sql(request: SearchSQLRequest):
    """
    Search for SQL files in the codebase for LLM consumption
    
    This endpoint provides a simplified response format optimized for LLMs.
    """
    try:
        result = llm_interface.search_sql(
            query=request.query,
            limit=request.limit
        )
        return result
    except Exception as e:
        logger.error(f"Error searching SQL: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error searching SQL: {str(e)}")

@router.post("/detect_dialect")
async def detect_dialect(request: DetectDialectRequest):
    """
    Detect SQL dialect from repository URL
    
    This endpoint is useful for determining the appropriate dialect to use for parsing.
    """
    try:
        result = llm_interface.detect_dialect(request.repo_url)
        return result
    except Exception as e:
        logger.error(f"Error detecting dialect: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error detecting dialect: {str(e)}")

# Add this router to the main app in backend/app.py
# app.include_router(llm_sql_api.router) 