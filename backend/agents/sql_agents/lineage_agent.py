"""
Lineage Agent module that defines the LineageAgent class
This agent analyzes SQL code to extract table and column lineage
"""

from typing import Dict, List, Optional, Any
import logging
import json
import os
import sys
import re
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
        
    def _build_github_url(self, repo_url: str, file_path: str) -> str:
        """
        Build a properly formatted URL for a file that points to the application's repository UI
        
        Args:
            repo_url: Repository URL
            file_path: File path
            
        Returns:
            URL that points to the application's repository UI
        """
        import urllib.parse
        
        if not repo_url or not file_path:
            return ""

        # Extract repository info
        repo_name = ""
        owner = ""
        
        # Remove .git suffix if present
        if repo_url.endswith('.git'):
            repo_url = repo_url[:-4]
        
        # Ensure the repo URL doesn't have trailing slash
        if repo_url.endswith('/'):
            repo_url = repo_url[:-1]
        
        # Try to extract owner and repo
        github_url_match = re.match(r'https://github\.com/([^/]+)/([^/]+)', repo_url)
        enterprise_url_match = re.match(r'https://([^/]+)/([^/]+)/([^/]+)', repo_url)
        
        if github_url_match:
            owner = github_url_match.group(1)
            repo_name = github_url_match.group(2)
        elif enterprise_url_match:
            # Handle enterprise GitHub URLs
            domain = enterprise_url_match.group(1)
            owner = enterprise_url_match.group(2)
            repo_name = enterprise_url_match.group(3)
        else:
            # If we couldn't extract owner/repo, construct a fallback identifier
            parts = repo_url.split('/')
            if len(parts) >= 2:
                owner = parts[-2]
                repo_name = parts[-1]
            else:
                # If all else fails, use the URL as is
                owner = "unknown"
                repo_name = "repository"
        
        # Normalize file path
        # Remove leading slash from file path if present
        if file_path and file_path.startswith('/'):
            file_path = file_path[1:]
            
        # URL encode the file path for safe inclusion in URL
        encoded_path = urllib.parse.quote(file_path)
        
        # Build the application repository UI URL
        # Format: /repository/{owner}/{repo_name}/blob/main/{file_path}
        # or query parameter format if that's what the UI expects
        repo_identifier = f"{owner}/{repo_name}"
        
        # Use the repository UI URL format
        return f"http://localhost:5173/repository?repo={repo_identifier}&file={encoded_path}"
    
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
            logger.info(f"Tracing {direction} lineage for table '{table_name}' with dialect '{dialect}'")
            
            # Validate SQLTools instance exists
            if not self.sql_tools:
                return {"error": "SQL tools not available"}
                
            # Make sure sql_tools has the get_table_lineage method
            if not hasattr(self.sql_tools, 'get_table_lineage'):
                logger.error("SQL tools does not have get_table_lineage method")
                
                # Fallback to basic interface if available
                if hasattr(self.sql_tools, 'search_tables'):
                    search_result = self.sql_tools.search_tables(table_name, limit=10)
                    return {
                        "table": table_name,
                        "direction": direction,
                        "dialect_used": dialect or "unknown",
                        "levels": {"0": []},
                        "source_files": search_result.get("results", []),
                        "error_details": "Direct lineage tracing not available, returning search results only"
                    }
                    
                return {"error": "SQL tools does not have required lineage methods"}
            
            # Use the sql_tools to trace table lineage
            lineage_result = self.sql_tools.get_table_lineage(
                table_name=table_name,
                direction=direction,
                max_depth=5,
                dialect=dialect,
                repo_url=repo_url
            )
            
            logger.info(f"Received lineage result with keys: {lineage_result.keys() if isinstance(lineage_result, dict) else 'not a dict'}")
            
            # Handle errors in the result
            if isinstance(lineage_result, dict) and "error" in lineage_result:
                error_message = lineage_result["error"]
                logger.error(f"Error in lineage tracing: {error_message}")
                
                # Try to fall back to simple search if lineage fails
                logger.info(f"Trying fallback search for table '{table_name}'")
                
                if hasattr(self.sql_tools, 'search_tables'):
                    search_result = self.sql_tools.search_tables(table_name, limit=10)
                    
                    # Create a basic lineage result with search data
                    fallback_result = {
                        "table": table_name,
                        "direction": direction,
                        "dialect_used": dialect or "unknown",
                        "levels": {"0": []},
                        "total_files": search_result.get("files_found", 0),
                        "error_details": f"Lineage tracing failed: {error_message}, using search results",
                        "source_files": search_result.get("results", [])
                    }
                    
                    # Create basic level 0 entries from search results
                    level_0_files = []
                    for file_info in search_result.get("results", []):
                        # Create a file entry for level 0
                        level_0_files.append({
                            "file_path": file_info.get("file_path", ""),
                            "url": file_info.get("url", ""),
                            "github_repo": file_info.get("repo", ""),
                            "dialect": file_info.get("dialect", "unknown"),
                            "target_table": table_name,
                            "source_tables": []
                        })
                    
                    if level_0_files:
                        fallback_result["levels"]["0"] = level_0_files
                        
                    return fallback_result
                    
                # If no fallback, return the error
                return lineage_result
            
            # Ensure we have source_files in the result
            if isinstance(lineage_result, dict) and "source_files" not in lineage_result:
                # Try to get files from search
                if hasattr(self.sql_tools, 'search_tables'):
                    search_result = self.sql_tools.search_tables(table_name, limit=10)
                    lineage_result["source_files"] = search_result.get("results", [])
            
            # Add visualization data if requested
            if include_visualization:
                if self.adapter:
                    # Use external adapter if available
                    vis_data = self.adapter.convert_to_visualizer_format(lineage_result)
                else:
                    # Use internal method as fallback
                    vis_data = self.convert_to_visualizer_format(lineage_result)
                    
                lineage_result["visualization"] = vis_data
            
            # Improve the organization of lineage information
            enhanced_result = self._organize_lineage_result(lineage_result, table_name, direction)
            
            return enhanced_result
        except Exception as e:
            logger.error(f"Error tracing table lineage: {str(e)}")
            return {"error": f"Error tracing table lineage: {str(e)}"}
            
    def _organize_lineage_result(self, lineage_result: Dict[str, Any], target_table: str, direction: str) -> Dict[str, Any]:
        """
        Organize lineage result into a clearer source-to-target structure
        
        Args:
            lineage_result: Raw lineage result from SQL tools
            target_table: Target table name
            direction: Direction of lineage analysis
            
        Returns:
            Enhanced lineage result with better organization
        """
        if not isinstance(lineage_result, dict):
            return lineage_result
            
        # Get the key components
        files_by_level = lineage_result.get("files_by_level", {})
        source_files = lineage_result.get("source_files", [])
        
        # Create enhanced structure for table lineage paths
        table_lineage_paths = []
        github_file_paths = []
        processed_tables = set()
        table_to_sources = {}
        
        # Build a dependency graph
        dependency_graph = {}
        
        # First pass: Build dependency relationships from files_by_level
        for level_str, files in files_by_level.items():
            level = int(level_str) if isinstance(level_str, str) else level_str
            
            for file_info in files:
                target = file_info.get("target_table", "")
                sources = file_info.get("source_tables", [])
                file_path = file_info.get("file_path", "")
                file_url = file_info.get("url", "")
                
                if target and target not in dependency_graph:
                    dependency_graph[target] = {"sources": [], "file_info": []}
                
                for source in sources:
                    if source and source != target:  # Avoid self-dependencies
                        # Add source to target relationship
                        if target:
                            if source not in dependency_graph[target]["sources"]:
                                dependency_graph[target]["sources"].append(source)
                                
                            # Add file info for this relationship
                            dependency_graph[target]["file_info"].append({
                                "file_path": file_path,
                                "url": file_url,
                                "source": source,
                                "level": level
                            })
                        
                        # Create entry for source if doesn't exist
                        if source not in dependency_graph:
                            dependency_graph[source] = {"sources": [], "file_info": []}
        
        # Now build complete paths through the dependency graph
        def build_path(current, path=None, file_path=None):
            if path is None:
                path = [current]
            else:
                path = path + [current]
                
            if file_path is None:
                file_path = []
                
            # If no sources, this is a leaf node (source table)
            if not dependency_graph.get(current, {}).get("sources"):
                if len(path) > 1:  # Only add paths with more than one table
                    table_lineage_paths.append(path)
                    github_file_paths.append(file_path)
                return
                
            # Process each source
            for source in dependency_graph.get(current, {}).get("sources", []):
                # Get file info for this relationship
                new_file_info = []
                for info in dependency_graph[current]["file_info"]:
                    if info["source"] == source:
                        new_file_info.append(info)
                
                # Continue building the path
                build_path(source, path, file_path + new_file_info)
        
        # Start building paths from the target table
        if target_table in dependency_graph:
            build_path(target_table)
        
        # Format table lineage paths for display
        formatted_paths = []
        for i, path in enumerate(table_lineage_paths):
            # Reverse to show source → target direction
            if direction == "upstream":
                path = list(reversed(path))
                
            # Create a formatted path
            formatted_path = {
                "path": " → ".join(path),
                "tables": path,
                "files": []
            }
            
            # Add the corresponding files with proper GitHub URLs
            if i < len(github_file_paths):
                for file_info in github_file_paths[i]:
                    formatted_path["files"].append({
                        "file_path": file_info.get("file_path", ""),
                        "url": file_info.get("url", ""),
                        "level": file_info.get("level", 0)
                    })
                    
            formatted_paths.append(formatted_path)
        
        # Create final organized result
        organized_result = {
            "table": target_table,
            "direction": direction,
            "dialect_used": lineage_result.get("dialect_used", "unknown"),
            "lineage_paths": formatted_paths,  # Clear source → target paths
            "dependency_details": dependency_graph,  # Full dependency details
            "github_files": []  # List of all GitHub files in order
        }
        
        # Add a flat list of GitHub files for easy access
        for path in formatted_paths:
            for file in path.get("files", []):
                if file.get("url"):
                    file_entry = {
                        "file_path": file.get("file_path", ""),
                        "url": file.get("url", ""),
                        "tables": path.get("tables", [])
                    }
                    if file_entry not in organized_result["github_files"]:
                        organized_result["github_files"].append(file_entry)
        
        # Preserve the original data
        organized_result["original_data"] = lineage_result
        
        # Copy visualization if present
        if "visualization" in lineage_result:
            organized_result["visualization"] = lineage_result["visualization"]
            
        return organized_result
            
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
            logger.info(f"Tracing {direction} lineage for column '{table_name}.{column_name}' with dialect '{dialect}'")
            
            # Validate SQLTools instance exists
            if not self.sql_tools:
                return {"error": "SQL tools not available"}
                
            # Make sure sql_tools has the get_column_lineage method
            if not hasattr(self.sql_tools, 'get_column_lineage'):
                logger.error("SQL tools does not have get_column_lineage method")
                
                # Fallback to basic interface if available
                if hasattr(self.sql_tools, 'search_columns'):
                    search_result = self.sql_tools.search_columns(column_name, limit=10)
                    return {
                        "table": table_name,
                        "column": column_name,
                        "direction": direction,
                        "dialect_used": dialect or "unknown",
                        "levels": {"0": []},
                        "source_files": search_result.get("results", []),
                        "error_details": "Direct column lineage tracing not available, returning search results only"
                    }
                    
                return {"error": "SQL tools does not have required column lineage methods"}
            
            # Use the sql_tools to trace column lineage
            lineage_result = self.sql_tools.get_column_lineage(
                table_name=table_name,
                column_name=column_name,
                direction=direction,
                max_depth=5,
                dialect=dialect,
                repo_url=repo_url
            )
            
            logger.info(f"Received column lineage result with keys: {lineage_result.keys() if isinstance(lineage_result, dict) else 'not a dict'}")
            
            # Handle errors in the result
            if isinstance(lineage_result, dict) and "error" in lineage_result:
                error_message = lineage_result["error"]
                logger.error(f"Error in column lineage tracing: {error_message}")
                
                # Try to fall back to simple search if lineage fails
                logger.info(f"Trying fallback search for column '{column_name}'")
                
                if hasattr(self.sql_tools, 'search_columns'):
                    search_result = self.sql_tools.search_columns(column_name, limit=10)
                    
                    # Create a basic lineage result with search data
                    fallback_result = {
                        "table": table_name,
                        "column": column_name,
                        "direction": direction,
                        "dialect_used": dialect or "unknown",
                        "levels": {"0": []},
                        "error_details": f"Column lineage tracing failed: {error_message}, using search results",
                        "source_files": search_result.get("results", [])
                    }
                    
                    # Extract likely tables containing this column
                    likely_tables = search_result.get("likely_tables", [])
                    fallback_result["likely_tables"] = likely_tables
                        
                    return fallback_result
                    
                # If no fallback, return the error
                return lineage_result
            
            # Add visualization data if requested
            if include_visualization:
                if self.adapter:
                    vis_data = self.adapter.convert_column_lineage(lineage_result)
                else:
                    vis_data = self.convert_column_lineage(lineage_result)
                    
                lineage_result["visualization"] = vis_data
            
            # Organize column lineage for better presentation
            enhanced_result = self._organize_column_lineage(lineage_result, table_name, column_name, direction)
            
            return enhanced_result
            
        except Exception as e:
            logger.error(f"Error tracing column lineage: {str(e)}")
            return {"error": f"Error tracing column lineage: {str(e)}"}
            
    def _organize_column_lineage(self, lineage_result: Dict[str, Any], table_name: str, column_name: str, direction: str) -> Dict[str, Any]:
        """
        Organize column lineage result into a clearer source-to-target structure
        
        Args:
            lineage_result: Raw column lineage result from SQL tools
            table_name: Target table name
            column_name: Target column name
            direction: Direction of lineage analysis
            
        Returns:
            Enhanced column lineage result with better organization
        """
        if not isinstance(lineage_result, dict):
            return lineage_result
            
        # Get the key components
        levels = lineage_result.get("levels", {})
        column_chain = lineage_result.get("column_chain", [])
        
        # Create enhanced structure for column paths
        column_lineage_paths = []
        github_file_paths = []
        all_source_columns = set()
        
        # Build a dependency graph for columns
        column_graph = {}
        target_column_id = f"{table_name}.{column_name}"
        
        # Initialize the target column
        column_graph[target_column_id] = {
            "sources": [],
            "file_info": [],
            "table": table_name,
            "column": column_name
        }
        
        # Process levels to build column dependencies
        for level_str, columns in levels.items():
            level = int(level_str) if level_str.isdigit() else int(level_str)
            
            for col_info in columns:
                # Extract source columns
                for source_col in col_info.get("source_columns", []):
                    if not source_col:
                        continue
                        
                    src_table = source_col.get("table", "")
                    src_column = source_col.get("column", "")
                    file_path = col_info.get("file_path", "")
                    file_url = col_info.get("file_url", "")
                    transformation = source_col.get("transformation", "")
                    
                    # Skip if missing key information
                    if not src_table or not src_column:
                        continue
                        
                    # Create source column ID
                    source_id = f"{src_table}.{src_column}"
                    all_source_columns.add(source_id)
                    
                    # Get the target column ID from current level info
                    target_col_table = col_info.get("table", "")
                    target_col_name = col_info.get("column", "")
                    
                    # Skip if missing target info
                    if not target_col_table or not target_col_name:
                        continue
                        
                    target_id = f"{target_col_table}.{target_col_name}"
                    
                    # Initialize target in graph if not exists
                    if target_id not in column_graph:
                        column_graph[target_id] = {
                            "sources": [],
                            "file_info": [],
                            "table": target_col_table,
                            "column": target_col_name
                        }
                    
                    # Add source to target relationship
                    if source_id not in column_graph[target_id]["sources"]:
                        column_graph[target_id]["sources"].append(source_id)
                    
                    # Add file info
                    column_graph[target_id]["file_info"].append({
                        "file_path": file_path,
                        "url": file_url,
                        "transformation": transformation,
                        "source": source_id,
                        "level": level
                    })
                    
                    # Initialize source in graph if not exists
                    if source_id not in column_graph:
                        column_graph[source_id] = {
                            "sources": [],
                            "file_info": [],
                            "table": src_table,
                            "column": src_column
                        }
        
        # Now build complete paths through the column dependency graph
        def build_column_path(current, path=None, file_path=None):
            if path is None:
                path = [current]
            else:
                path = path + [current]
                
            if file_path is None:
                file_path = []
                
            # If no sources, this is a leaf node (source column)
            if not column_graph.get(current, {}).get("sources"):
                if len(path) > 1:  # Only add paths with more than one column
                    column_lineage_paths.append(path)
                    github_file_paths.append(file_path)
                return
                
            # Process each source
            for source in column_graph.get(current, {}).get("sources", []):
                # Get file info for this relationship
                new_file_info = []
                for info in column_graph[current]["file_info"]:
                    if info["source"] == source:
                        new_file_info.append(info)
                
                # Continue building the path
                build_column_path(source, path, file_path + new_file_info)
        
        # Start building paths from the target column
        if target_column_id in column_graph:
            build_column_path(target_column_id)
        
        # Format column lineage paths for display
        formatted_column_paths = []
        for i, path in enumerate(column_lineage_paths):
            # Reverse path for upstream direction to show source → target
            if direction == "upstream":
                path = list(reversed(path))
                
            # Format the path for display
            formatted_path = {
                "path_text": " → ".join(path),
                "columns": [],
                "files": []
            }
            
            # Add column details for each element in the path
            for col_id in path:
                if col_id in column_graph:
                    col_info = column_graph[col_id]
                    formatted_path["columns"].append({
                        "id": col_id,
                        "table": col_info.get("table", ""),
                        "column": col_info.get("column", "")
                    })
            
            # Add file information
            if i < len(github_file_paths):
                for file_info in github_file_paths[i]:
                    formatted_path["files"].append({
                        "file_path": file_info.get("file_path", ""),
                        "url": file_info.get("url", ""),
                        "transformation": file_info.get("transformation", ""),
                        "level": file_info.get("level", 0)
                    })
                    
            formatted_column_paths.append(formatted_path)
        
        # Create the organized result
        organized_result = {
            "table": table_name,
            "column": column_name,
            "direction": direction,
            "dialect_used": lineage_result.get("dialect_used", "unknown"),
            "column_lineage_paths": formatted_column_paths,
            "dependency_details": column_graph,
            "github_files": []  # Will hold all GitHub files
        }
        
        # Add a flat list of all GitHub files for easy access
        for path in formatted_column_paths:
            for file in path.get("files", []):
                if file.get("url"):
                    file_entry = {
                        "file_path": file.get("file_path", ""),
                        "url": file.get("url", ""),
                        "transformation": file.get("transformation", ""),
                        "columns": [col.get("id") for col in path.get("columns", [])]
                    }
                    if file_entry not in organized_result["github_files"]:
                        organized_result["github_files"].append(file_entry)
        
        # If no paths were found but we have source columns, create a simple entry
        if not formatted_column_paths and all_source_columns:
            simple_path = {
                "path_text": f"{target_column_id} (no complete path found)",
                "columns": [{"id": target_column_id, "table": table_name, "column": column_name}],
                "files": [],
                "source_columns": list(all_source_columns)
            }
            organized_result["column_lineage_paths"].append(simple_path)
        
        # Preserve original data
        organized_result["original_data"] = lineage_result
        
        # Copy visualization if present
        if "visualization" in lineage_result:
            organized_result["visualization"] = lineage_result["visualization"]
            
        return organized_result
            
    def analyze_lineage(self, sql_code: str, task: str = "Analyze the SQL code and identify the table and column lineage."):
        """
        Analyze SQL code to extract lineage information
        
        Args:
            sql_code: SQL code to analyze
            task: Description of the analysis task
            
        Returns:
            Lineage analysis
        """
        # Check if parameters are incorrect type (e.g., table_name was passed)
        if not sql_code or not isinstance(sql_code, str) or len(sql_code) < 10:
            # Might have received wrong parameters (e.g., table_name instead of sql_code)
            table_name = None
            if isinstance(task, dict) and "table_name" in task:
                # Task is actually params dict with table_name
                table_name = task.get("table_name")
            
            if table_name:
                logger.info(f"analyze_lineage was called with table_name. Redirecting to trace_table_lineage for {table_name}")
                # Redirect to trace_table_lineage instead
                return self.trace_table_lineage(
                    table_name=table_name,
                    direction="upstream",
                    dialect=None,
                    repo_url=None
                )
            
            return {"error": "SQL code is required and must be a valid SQL query string"}
        
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
        
        logger.info(f"Running lineage agent with action: {action}, params: {params}")
        
        # Handle case where action might be a mismatch with parameters
        if action == "analyze_lineage":
            # Check for proper sql_code parameter
            sql_code = params.get("sql_code", "")
            task = params.get("task", "Analyze the SQL code and identify the table and column lineage.")
            
            # If there's no sql_code but table_name is provided, redirect to trace_table_lineage
            if (not sql_code or len(sql_code) < 10) and "table_name" in params:
                logger.info(f"Redirecting analyze_lineage to trace_table_lineage due to missing sql_code but table_name is provided")
                action = "trace_table_lineage"
                # Continue to trace_table_lineage handler
            else:
                if not sql_code:
                    return {"error": "SQL code is required for analyze_lineage action"}
                    
                return self.analyze_lineage(sql_code, task)
        
        if action == "trace_table_lineage":
            table_name = params.get("table_name")
            direction = params.get("direction", "upstream")
            dialect = params.get("dialect")
            repo_url = params.get("repo_url")
            
            if not table_name:
                return {"error": "Table name is required"}
                
            result = self.trace_table_lineage(
                table_name=table_name,
                direction=direction,
                dialect=dialect,
                repo_url=repo_url,
                include_visualization=include_vis
            )
            
            # Add a summary for the SQL supervisor agent
            if isinstance(result, dict) and "error" not in result:
                # Count unique lineage paths
                path_count = len(result.get("lineage_paths", []))
                
                # Count unique GitHub files
                github_files = result.get("github_files", [])
                file_count = len(github_files)
                
                # Get unique source tables
                source_tables = set()
                for path in result.get("lineage_paths", []):
                    tables = path.get("tables", [])
                    # In upstream direction, first table is the source
                    if tables and len(tables) > 1 and direction == "upstream":
                        source_tables.add(tables[0])
                
                # Create a summary section
                result["summary"] = {
                    "target_table": table_name,
                    "direction": direction,
                    "lineage_path_count": path_count,
                    "github_file_count": file_count,
                    "source_table_count": len(source_tables),
                    "source_tables": list(source_tables),
                }
                
                # Create a section for LLM to better understand the results
                result["llm_guidance"] = {
                    "description": f"Table lineage analysis for {table_name} ({direction})",
                    "how_to_use": "This result contains the complete lineage paths from source to target tables with GitHub URLs.",
                    "lineage_paths_explanation": "These paths show the flow of data through tables, from source to target.",
                    "github_files_explanation": "These files contain the implementations of the dependencies between tables."
                }
            
            return result
            
        elif action == "trace_column_lineage":
            table_name = params.get("table_name")
            column_name = params.get("column_name")
            direction = params.get("direction", "upstream")
            dialect = params.get("dialect")
            repo_url = params.get("repo_url")
            
            if not table_name or not column_name:
                return {"error": "Table name and column name are required"}
                
            result = self.trace_column_lineage(
                table_name=table_name,
                column_name=column_name,
                direction=direction,
                dialect=dialect,
                repo_url=repo_url,
                include_visualization=include_vis
            )
            
            # Add a summary for the SQL supervisor agent
            if isinstance(result, dict) and "error" not in result:
                # Count unique column lineage paths
                path_count = len(result.get("column_lineage_paths", []))
                
                # Count unique GitHub files
                github_files = result.get("github_files", [])
                file_count = len(github_files)
                
                # Get unique source columns
                source_columns = set()
                for path in result.get("column_lineage_paths", []):
                    columns = path.get("columns", [])
                    # In upstream direction, first column is the source
                    if columns and len(columns) > 1 and direction == "upstream":
                        col_id = columns[0].get("id")
                        if col_id:
                            source_columns.add(col_id)
                
                # Create a summary section
                result["summary"] = {
                    "target_column": f"{table_name}.{column_name}",
                    "direction": direction,
                    "lineage_path_count": path_count,
                    "github_file_count": file_count,
                    "source_column_count": len(source_columns),
                    "source_columns": list(source_columns),
                }
                
                # Create a section for LLM to better understand the results
                result["llm_guidance"] = {
                    "description": f"Column lineage analysis for {table_name}.{column_name} ({direction})",
                    "how_to_use": "This result contains the complete lineage paths from source to target columns with GitHub URLs.",
                    "column_lineage_paths_explanation": "These paths show the flow of data through columns, from source to target.",
                    "github_files_explanation": "These files contain the implementations of the transformations between columns.",
                    "transformations_explanation": "These describe how the column values are transformed as they move through the pipeline."
                }
            
            return result
            
        elif action == "analyze_lineage":
            sql_code = params.get("sql_code")
            task = params.get("task", "Analyze the SQL code and identify the table and column lineage.")
            
            if not sql_code:
                # Last attempt - check if other parameters can help
                if "table_name" in params:
                    # Redirect to trace_table_lineage
                    logger.info(f"Redirecting analyze_lineage to trace_table_lineage due to missing sql_code")
                    return self.run({
                        "action": "trace_table_lineage",
                        "params": params
                    })
                    
                return {"error": "SQL code is required for analyze_lineage action"}
                
            return self.analyze_lineage(sql_code, task)
            
        else:
            return {"error": f"Unknown action: {action}"} 