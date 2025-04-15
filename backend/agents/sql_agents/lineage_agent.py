"""
Lineage Agent module that defines the LineageAgent class
This agent analyzes SQL code to extract table and column lineage
"""

from typing import Dict, List, Optional, Any
import logging
import json
import os
import sys
from pathlib import Path
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser

from ..base.agent import Agent

# Configure logging
logger = logging.getLogger(__name__)

# Try to import LineageAdapter from various potential paths
try:
    # First, try importing directly from the module
    from tools.sql_tools.lineage import LineageAdapter
    logger.info("Successfully imported LineageAdapter from backend.tools.sql_tools.lineage")
    USE_EXTERNAL_ADAPTER = True
except ImportError:
    try:
        # Next, try a relative import
        backend_dir = str(Path(__file__).parent.parent.parent)
        if backend_dir not in sys.path:
            sys.path.insert(0, backend_dir)
        from tools.sql_tools.lineage import LineageAdapter
        logger.info("Successfully imported LineageAdapter from tools.sql_tools.lineage")
        USE_EXTERNAL_ADAPTER = True
    except ImportError:
        # If both fail, we'll use our internal implementation
        logger.warning("LineageAdapter import failed, using internal implementation")
        USE_EXTERNAL_ADAPTER = False

class LineageAgent(Agent):
    """
    Lineage Agent that analyzes SQL code to extract table and column lineage
    
    Attributes:
        name (str): The name of the agent
        description (str): A description of what the agent does
        model: Language model to use
        sql_tools: SQL analysis tools
    """
    
    def __init__(
        self, 
        name: str = "Lineage Agent", 
        description: str = "Analyzes SQL code to extract lineage information",
        model = None,
        sql_tools = None
    ):
        """
        Initialize a new LineageAgent
        
        Args:
            name: Name of the agent
            description: Description of what the agent does
            model: Language model to use
            sql_tools: SQL analysis tools
        """
        super().__init__(name, description)
        self.model = model
        self.sql_tools = sql_tools
        
        # Use external adapter if available
        if USE_EXTERNAL_ADAPTER:
            self.adapter = LineageAdapter()
            logger.info("Using external LineageAdapter")
        else:
            self.adapter = None
            logger.info("Using internal adapter methods")
        
        # Set up the parser
        self.parser = JsonOutputParser()
        
        # Set up the prompt templates
        self.lineage_prompt = ChatPromptTemplate.from_template("""
            You are a SQL Lineage Analysis expert. Your job is to analyze SQL code and identify the lineage 
            between tables and columns.
            
            Task: {task}
            
            Context:
            {context}
            
            Please provide a detailed analysis of the lineage in JSON format with the following structure:
            
            For table lineage:
            ```
            {
                "table": "target_table_name",
                "upstream_tables": [
                    {
                        "table": "source_table_name",
                        "path": "file_path",
                        "url": "github_url"
                    }
                ],
                "downstream_tables": [
                    {
                        "table": "dependent_table_name",
                        "path": "file_path",
                        "url": "github_url"
                    }
                ]
            }
            ```
            
            For column lineage:
            ```
            {
                "table": "target_table_name",
                "column": "target_column_name",
                "upstream_columns": [
                    {
                        "table": "source_table_name",
                        "column": "source_column_name",
                        "transformation": "SQL transformation applied",
                        "path": "file_path",
                        "url": "github_url"
                    }
                ],
                "downstream_columns": [
                    {
                        "table": "dependent_table_name",
                        "column": "dependent_column_name",
                        "path": "file_path",
                        "url": "github_url"
                    }
                ]
            }
            ```
            
            Only include information that you can confidently determine from the provided SQL code.
        """)
        
    def convert_to_visualizer_format(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert dependency data to the format needed by the LineageVisualizer component
        
        Args:
            data: Dependency data from trace_complete_lineage or trace_table_dependencies
            
        Returns:
            Data in format needed by LineageVisualizer
        """
        try:
            # Check if we have the expected data structure
            if not isinstance(data, dict):
                logger.error("Invalid data format: Not a dictionary")
                return {"error": "Invalid data format"}
                
            # Extract key fields
            target_table = data.get("table") or data.get("target_table", "unknown")
            files_by_level = data.get("files_by_level", {})
            direction = data.get("direction", "upstream")
            
            # Prepare visualization data
            models = []
            edges = []
            tables_processed = set()
            
            # Add the target table as the central node
            models.append({
                "id": target_table,
                "name": target_table,
                "type": "table",
                "schema": "target"
            })
            tables_processed.add(target_table)
            
            # Process each level of dependencies
            for level_str, files in files_by_level.items():
                level = int(level_str) if isinstance(level_str, str) else level_str
                
                for file_info in files:
                    # Extract tables from this file
                    source_tables = file_info.get("source_tables", [])
                    file_target = file_info.get("target_table", "")
                    
                    # Extract file metadata
                    file_path = file_info.get("file_path", "")
                    file_url = file_info.get("url", "")
                    
                    # Process tables based on direction
                    if direction == "upstream":
                        # For upstream, create edges from sources to target
                        for source in source_tables:
                            if source not in tables_processed:
                                models.append({
                                    "id": source,
                                    "name": source,
                                    "type": "source",
                                    "schema": f"level_{level+1}"
                                })
                                tables_processed.add(source)
                            
                            # Add edge from source to file_target
                            if file_target and source != file_target:
                                edges.append({
                                    "source": source,
                                    "target": file_target,
                                    "type": "depends_on",
                                    "file_path": file_path,
                                    "url": file_url
                                })
                    else:
                        # For downstream, create edges from target to dependents
                        if file_target and file_target not in tables_processed:
                            models.append({
                                "id": file_target,
                                "name": file_target,
                                "type": "dependent",
                                "schema": f"level_{level+1}"
                            })
                            tables_processed.add(file_target)
                            
                            # Add edge from sources to target
                            for source in source_tables:
                                if source == target_table:  # Only if our target is a source
                                    edges.append({
                                        "source": source,
                                        "target": file_target,
                                        "type": "used_by",
                                        "file_path": file_path,
                                        "url": file_url
                                    })
            
            # Return formatted data
            result = {
                "models": models,
                "edges": edges,
                "metadata": {
                    "target_table": target_table,
                    "direction": direction,
                    "total_models": len(models),
                    "total_edges": len(edges),
                }
            }
            
            return result
            
        except Exception as e:
            logger.error(f"Error converting lineage data: {str(e)}")
            return {"error": f"Error converting lineage data: {str(e)}"}
    
    def convert_column_lineage(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert column lineage data to visualization format
        
        Args:
            data: Column lineage data from trace_column_lineage
            
        Returns:
            Data in format for column lineage visualization
        """
        try:
            # Check if we have the expected data structure
            if not isinstance(data, dict):
                return {"error": "Invalid data format"}
                
            # Extract key fields
            table = data.get("table", "unknown")
            column = data.get("column", "unknown")
            levels = data.get("levels", {})
            column_chain = data.get("column_chain", [])
            
            # Prepare visualization data
            models = []
            edges = []
            columns_processed = set()
            
            # Add the target column as the central node
            target_id = f"{table}.{column}"
            models.append({
                "id": target_id,
                "name": column,
                "table": table,
                "type": "column",
                "schema": "target"
            })
            columns_processed.add(target_id)
            
            # Process column chain if available
            if column_chain:
                for level_info in column_chain:
                    for col_id in level_info:
                        if col_id in columns_processed:
                            continue
                            
                        # Parse table and column from ID
                        parts = col_id.split(".")
                        if len(parts) >= 2:
                            col_table = ".".join(parts[:-1])
                            col_name = parts[-1]
                            
                            models.append({
                                "id": col_id,
                                "name": col_name,
                                "table": col_table,
                                "type": "column",
                                "schema": "source"
                            })
                            columns_processed.add(col_id)
            
            # Process each level
            for level_str, level_deps in levels.items():
                for dep in level_deps:
                    # Process upstream columns
                    for src in dep.get("source_columns", []):
                        src_table = src.get("table", "")
                        src_column = src.get("column", "")
                        
                        if src_table and src_column:
                            src_id = f"{src_table}.{src_column}"
                            
                            if src_id not in columns_processed:
                                models.append({
                                    "id": src_id,
                                    "name": src_column,
                                    "table": src_table,
                                    "type": "column",
                                    "schema": "source"
                                })
                                columns_processed.add(src_id)
                            
                            # Add edge
                            edges.append({
                                "source": src_id,
                                "target": target_id,
                                "type": "column_dependency",
                                "transformation": src.get("transformation", ""),
                                "file_path": dep.get("file_path", ""),
                                "url": dep.get("file_url", "")
                            })
            
            # Return formatted data
            result = {
                "models": models,
                "edges": edges,
                "metadata": {
                    "target_table": table,
                    "target_column": column,
                    "total_models": len(models),
                    "total_edges": len(edges),
                }
            }
            
            return result
            
        except Exception as e:
            logger.error(f"Error converting column lineage data: {str(e)}")
            return {"error": f"Error converting column lineage data: {str(e)}"}
        
    def trace_table_lineage(self, table_name: str, direction: str = "upstream",
                           dialect: Optional[str] = None, repo_url: Optional[str] = None,
                           include_visualization: bool = True):
        """
        Trace the lineage of a table
        
        Args:
            table_name: Name of the table
            direction: Direction of the lineage ('upstream' or 'downstream')
            dialect: SQL dialect to use
            repo_url: Repository URL
            include_visualization: Whether to include visualization data
            
        Returns:
            Table lineage information
        """
        try:
            # Use the sql_tools to trace table lineage
            lineage_result = self.sql_tools.get_table_lineage(
                table_name=table_name,
                direction=direction,
                max_depth=5,
                dialect=dialect,
                repo_url=repo_url
            )
            
            # Add visualization data if requested
            if include_visualization:
                if self.adapter:
                    # Use external adapter if available
                    vis_data = self.adapter.convert_to_visualizer_format(lineage_result)
                else:
                    # Use internal method as fallback
                    vis_data = self.convert_to_visualizer_format(lineage_result)
                    
                lineage_result["visualization"] = vis_data
            
            return lineage_result
        except Exception as e:
            logger.error(f"Error tracing table lineage: {str(e)}")
            return {"error": str(e)}
            
    def trace_column_lineage(self, table_name: str, column_name: str, 
                            direction: str = "upstream",
                            dialect: Optional[str] = None, 
                            repo_url: Optional[str] = None,
                            include_visualization: bool = True):
        """
        Trace the lineage of a column
        
        Args:
            table_name: Name of the table
            column_name: Name of the column
            direction: Direction of the lineage ('upstream' or 'downstream')
            dialect: SQL dialect to use
            repo_url: Repository URL
            include_visualization: Whether to include visualization data
            
        Returns:
            Column lineage information
        """
        try:
            # Use the sql_tools to trace column lineage
            lineage_result = self.sql_tools.get_column_lineage(
                table_name=table_name,
                column_name=column_name,
                direction=direction,
                max_depth=5,
                dialect=dialect,
                repo_url=repo_url
            )
            
            # Add visualization data if requested
            if include_visualization:
                if self.adapter:
                    # Use external adapter if available
                    vis_data = self.adapter.convert_column_lineage(lineage_result)
                else:
                    # Use internal method as fallback
                    vis_data = self.convert_column_lineage(lineage_result)
                    
                lineage_result["visualization"] = vis_data
            
            return lineage_result
        except Exception as e:
            logger.error(f"Error tracing column lineage: {str(e)}")
            return {"error": str(e)}
            
    def analyze_lineage(self, sql_code: str, task: str):
        """
        Analyze SQL code to extract lineage information
        
        Args:
            sql_code: SQL code to analyze
            task: Description of the analysis task
            
        Returns:
            Lineage analysis
        """
        # Build the prompt
        prompt = self.lineage_prompt.format(
            task=task,
            context=sql_code
        )
        
        # Get the model response
        response = self.model.invoke(prompt)
        
        # Parse the response
        try:
            return self.parser.parse(response.content)
        except Exception as e:
            logger.error(f"Error parsing model response: {str(e)}")
            # Return the raw response if parsing fails
            return {"raw_response": response.content}
            
    def run(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run the lineage agent on the given input data
        
        Args:
            input_data: Input data for the agent, should contain:
                - 'action': Type of lineage analysis to perform
                - 'params': Parameters for the action
                
        Returns:
            Lineage analysis results
        """
        action = input_data.get("action", "")
        params = input_data.get("params", {})
        include_vis = params.get("include_visualization", True)
        
        if action == "trace_table_lineage":
            table_name = params.get("table_name")
            direction = params.get("direction", "upstream")
            dialect = params.get("dialect")
            repo_url = params.get("repo_url")
            
            if not table_name:
                return {"error": "Table name is required"}
                
            return self.trace_table_lineage(
                table_name=table_name,
                direction=direction,
                dialect=dialect,
                repo_url=repo_url,
                include_visualization=include_vis
            )
            
        elif action == "trace_column_lineage":
            table_name = params.get("table_name")
            column_name = params.get("column_name")
            direction = params.get("direction", "upstream")
            dialect = params.get("dialect")
            repo_url = params.get("repo_url")
            
            if not table_name or not column_name:
                return {"error": "Table name and column name are required"}
                
            return self.trace_column_lineage(
                table_name=table_name,
                column_name=column_name,
                direction=direction,
                dialect=dialect,
                repo_url=repo_url,
                include_visualization=include_vis
            )
            
        elif action == "analyze_lineage":
            sql_code = params.get("sql_code")
            task = params.get("task", "Analyze the SQL code and identify the table and column lineage.")
            
            if not sql_code:
                return {"error": "SQL code is required"}
                
            return self.analyze_lineage(sql_code, task)
            
        else:
            return {"error": f"Unknown action: {action}"} 