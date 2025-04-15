"""
SQL Lineage Adapters

This module contains adapters to convert dependency results to visualization formats.
"""

import logging
from typing import Dict, List, Any, Optional

# Configure logging
logger = logging.getLogger(__name__)

class LineageAdapter:
    """
    Adapter to convert dependency data to visualization formats
    """
    
    @staticmethod
    def convert_to_visualizer_format(data: Dict[str, Any]) -> Dict[str, Any]:
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
    
    @staticmethod
    def convert_column_lineage(data: Dict[str, Any]) -> Dict[str, Any]:
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

# Direct reference to the class for easy importing
adapter = LineageAdapter() 