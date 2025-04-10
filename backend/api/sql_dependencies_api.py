"""
API for SQL dependencies
"""

from fastapi import APIRouter, HTTPException, Depends, Query, Path, Body
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import logging
import os

from tools.sql.dependency_analyzer import SQLDependencyTool

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Create router
router = APIRouter(prefix="/api/dependencies", tags=["dependencies"])

# Initialize the SQL dependency tool with the correct path
vector_store_path = os.path.join(os.getcwd(), "vector_store", "chromadb_github")
dependency_tool = SQLDependencyTool(vector_store_path)
# Initialize immediately to ensure the vector store is connected
logger.info(f"Initializing SQL dependency tool with vector store path: {vector_store_path}")
dependency_tool.initialize()
logger.info("SQL dependency tool initialized with vector store")


# Model schemas
class TableDependencyRequest(BaseModel):
    """Request model for table dependency analysis"""
    target_table: str = Field(..., description="Target table name")
    depth: int = Field(10, description="Maximum depth to traverse")
    dialect: Optional[str] = Field(None, description="SQL dialect to use")


class ColumnLineageRequest(BaseModel):
    """Request model for column lineage analysis"""
    target_table: str = Field(..., description="Target table name")
    column_name: str = Field(..., description="Target column name")
    depth: int = Field(10, description="Maximum depth to traverse")


class VisualizationRequest(BaseModel):
    """Request model for dependency visualization"""
    target_table: str = Field(..., description="Target table name")
    output_format: str = Field("json", description="Output format (json, graphviz, etc.)")


@router.post("/table")
async def analyze_table_dependencies(request: TableDependencyRequest):
    """
    Analyze dependencies for a target table
    """
    try:
        # Trace dependencies
        result = dependency_tool.trace_table_dependencies(
            target_table=request.target_table,
            depth=request.depth,
            dialect=request.dialect
        )
        
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
            
        return result
    except Exception as e:
        logger.error(f"Error analyzing table dependencies: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error analyzing dependencies: {str(e)}")


@router.post("/column")
async def analyze_column_lineage(request: ColumnLineageRequest):
    """
    Analyze lineage for a specific column
    """
    try:
        # Get column lineage
        result = dependency_tool.get_column_lineage(
            target_table=request.target_table,
            column_name=request.column_name,
            depth=request.depth
        )
        
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
            
        return result
    except Exception as e:
        logger.error(f"Error analyzing column lineage: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error analyzing column lineage: {str(e)}")


@router.post("/visualize")
async def visualize_dependencies(request: VisualizationRequest):
    """
    Visualize table dependencies
    """
    try:
        # Generate visualization
        result = dependency_tool.visualize_dependencies(
            target_table=request.target_table,
            output_format=request.output_format
        )
        
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
            
        return result
    except Exception as e:
        logger.error(f"Error visualizing dependencies: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error visualizing dependencies: {str(e)}")


@router.get("/search")
async def search_dependencies(
    query: str = Query(..., description="Search query"),
    limit: int = Query(20, description="Maximum number of results")
):
    """
    Search for SQL files based on a query
    """
    try:
        # Search for SQL files
        results = dependency_tool.sql_finder.search_sql_files(
            query=query,
            limit=limit
        )
        
        if isinstance(results, list) and len(results) > 0 and "error" in results[0]:
            raise HTTPException(status_code=404, detail=results[0]["error"])
            
        return {
            "query": query,
            "count": len(results),
            "results": results
        }
    except Exception as e:
        logger.error(f"Error searching for SQL files: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error searching for SQL files: {str(e)}")


@router.get("/dialect/{table_name}")
async def get_dialect_for_table(
    table_name: str = Path(..., description="Table name to detect dialect for")
):
    """
    Detect SQL dialect for a table based on its SQL files
    """
    try:
        # Search for SQL files for this table
        sql_files = dependency_tool.sql_finder.search_for_table(
            table_name=table_name,
            limit=10
        )
        
        if isinstance(sql_files, list) and len(sql_files) > 0 and "error" in sql_files[0]:
            raise HTTPException(status_code=404, detail=sql_files[0]["error"])
        
        if not sql_files:
            raise HTTPException(status_code=404, detail=f"No SQL files found for table {table_name}")
            
        # Count dialects
        dialect_counts = {}
        for file in sql_files:
            dialect = file.get("dialect", "unknown")
            dialect_counts[dialect] = dialect_counts.get(dialect, 0) + 1
        
        # Find most common dialect
        most_common_dialect = max(dialect_counts.items(), key=lambda x: x[1])[0] if dialect_counts else "unknown"
        
        return {
            "table_name": table_name,
            "detected_dialect": most_common_dialect,
            "dialect_counts": dialect_counts,
            "file_count": len(sql_files)
        }
    except Exception as e:
        logger.error(f"Error detecting dialect: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error detecting dialect: {str(e)}")


@router.post("/downstream/{table_name}")
async def analyze_downstream_dependencies(
    table_name: str,
    depth: int = Query(10, description="Maximum depth to traverse")
):
    """
    Analyze downstream dependencies for a source table
    """
    try:
        # Trace dependencies
        result = dependency_tool.trace_table_dependencies(
            target_table=table_name,
            depth=depth
        )
        
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        
        # Get downstream dependencies
        downstream_info = dependency_tool.dependency_analyzer.find_downstream_dependencies(
            source_table=table_name,
            max_depth=depth
        )
        
        return downstream_info
    except Exception as e:
        logger.error(f"Error analyzing downstream dependencies: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error analyzing downstream dependencies: {str(e)}") 