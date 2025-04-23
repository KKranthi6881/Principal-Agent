"""
Base Lineage Extractor

This module provides the base class for SQL lineage extractors.
"""

import os
import logging
from typing import Dict, List, Set, Tuple, Optional, Any
from abc import ABC, abstractmethod

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class BaseLineageExtractor(ABC):
    """Base class for SQL lineage extractors"""
    
    def __init__(self):
        """Initialize the base lineage extractor"""
        pass
    
    def extract_table_lineage(self, sql_ast: Any, file_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Extract table-level lineage from SQL AST
        
        Args:
            sql_ast: SQL AST (implementation-specific)
            file_path: Path to the original SQL file
            
        Returns:
            Dictionary with table lineage information
        """
        raise NotImplementedError("Subclasses must implement extract_table_lineage")
    
    def extract_column_lineage(self, sql_ast: Any, file_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Extract column-level lineage from SQL AST
        
        Args:
            sql_ast: SQL AST (implementation-specific)
            file_path: Path to the original SQL file
            
        Returns:
            Dictionary with column lineage information
        """
        raise NotImplementedError("Subclasses must implement extract_column_lineage")
    
    def format_lineage(self, 
                       target_table: str, 
                       source_tables: List[str], 
                       column_mappings: Dict[str, List[Tuple[str, str]]], 
                       file_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Format lineage information in a standard way
        
        Args:
            target_table: Target table name
            source_tables: List of source table names
            column_mappings: Dictionary of {target_column: [(source_table, source_column), ...]}
            file_path: Path to the file (optional)
            
        Returns:
            Dictionary with formatted lineage information
        """
        file_name = os.path.basename(file_path) if file_path else None
        
        # Build the lineage object
        lineage = {
            "file_path": file_path,
            "file_name": file_name,
            "target_table": target_table,
            "source_tables": source_tables,
            "column_level_lineage": {}
        }
        
        # Add column-level lineage if available
        for target_column, sources in column_mappings.items():
            formatted_sources = []
            for source_table, source_column in sources:
                formatted_sources.append({
                    "table": source_table,
                    "column": source_column
                })
            
            lineage["column_level_lineage"][target_column] = formatted_sources
        
        return lineage
    
    def get_default_output_format(self) -> Dict[str, Any]:
        """
        Get the default output format for lineage information
        
        Returns:
            Dictionary with default lineage output format
        """
        return {
            "file_path": None,
            "file_name": None,
            "target_table": None,
            "source_tables": [],
            "column_level_lineage": {},
            "errors": []
        }
    
    def extract_table_references(self, sql_ast: Any) -> Set[str]:
        """
        Extract table references from SQL AST
        
        Args:
            sql_ast: SQL AST
            
        Returns:
            Set of table references
        """
        # Base implementation returns empty set
        # Dialect-specific implementations should override this
        return set()
    
    def format_error(self, error_msg: str, error_type: str = "lineage_error") -> Dict[str, Any]:
        """
        Format an error message
        
        Args:
            error_msg: Error message
            error_type: Type of error
            
        Returns:
            Dictionary with formatted error
        """
        return {
            "error_type": error_type,
            "message": error_msg
        } 