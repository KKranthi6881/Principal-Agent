"""
Base SQL Dialect Parser

This module defines the base class for SQL dialect-specific parsers.
"""

import os
import re
import logging
from typing import Dict, List, Set, Tuple, Optional, Any
import sqlglot
from sqlglot import parse_one, ParseError
from abc import ABC, abstractmethod

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class BaseSQLDialect(ABC):
    """
    Base class for SQL dialect parsers. All dialect-specific parsers should inherit from this.
    """
    
    def __init__(self, name: str):
        """
        Initialize the SQL dialect parser
        
        Args:
            name: The name of the dialect
        """
        self.name = name
        self.sql_dialect = self._get_sqlglot_dialect()
    
    @abstractmethod
    def _get_sqlglot_dialect(self) -> Any:
        """
        Get the sqlglot dialect class for this dialect
        
        Returns:
            sqlglot dialect class
        """
        pass
    
    def parse_sql(self, sql_code: str) -> Any:
        """
        Parse SQL code into an AST
        
        Args:
            sql_code: SQL code to parse
            
        Returns:
            Parsed SQL AST or None if parsing fails
        """
        try:
            return parse_one(sql_code, read=self.sql_dialect)
        except ParseError as e:
            logger.error(f"Error parsing SQL with {self.name} dialect: {e}")
            return None
    
    def clean_sql(self, sql_code: str) -> str:
        """
        Clean SQL code before parsing (e.g., remove comments, fix formatting)
        
        Args:
            sql_code: SQL code to clean
            
        Returns:
            Cleaned SQL code
        """
        # Default implementation just removes SQL comments and excessive whitespace
        # Dialect-specific implementations should override this if needed
        
        # Remove /* ... */ comments
        sql_code = re.sub(r'/\*.*?\*/', ' ', sql_code, flags=re.DOTALL)
        
        # Remove -- comments
        sql_code = re.sub(r'--.*?$', ' ', sql_code, flags=re.MULTILINE)
        
        # Normalize whitespace
        sql_code = re.sub(r'\s+', ' ', sql_code)
        
        return sql_code.strip()
    
    @abstractmethod
    def extract_dependencies(self, sql_code: str, file_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Extract dependencies from SQL code
        
        Args:
            sql_code: SQL code to analyze
            file_path: Path to the file (optional)
            
        Returns:
            Dictionary with extracted dependencies
        """
        pass
    
    @abstractmethod
    def extract_lineage(self, sql_code: str, file_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Extract lineage information from SQL code
        
        Args:
            sql_code: SQL code to analyze
            file_path: Path to the file (optional)
            
        Returns:
            Dictionary with extracted lineage information
        """
        pass

    def get_default_output_format(self) -> Dict[str, Any]:
        """
        Get the default output format for this dialect
        
        Returns:
            Dictionary with default output format
        """
        return {
            "dialect": self.name,
            "file_path": None,
            "target_table": None,
            "source_tables": [],
            "columns": {},
            "dependencies": [],
            "errors": []
        }
    
    def get_dialect_info(self) -> Dict[str, Any]:
        """
        Get information about this dialect
        
        Returns:
            Dictionary with dialect information
        """
        return {
            "name": self.name,
            "description": f"{self.name.title()} SQL dialect parser",
            "capabilities": [
                "dependency_extraction",
                "lineage_extraction"
            ]
        }
    
    def format_error(self, error_msg: str, error_type: str = "parsing_error") -> Dict[str, Any]:
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
            "message": error_msg,
            "dialect": self.name
        } 