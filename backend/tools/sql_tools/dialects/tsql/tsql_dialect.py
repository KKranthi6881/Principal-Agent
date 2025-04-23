"""
T-SQL Dialect Parser

This module provides T-SQL specific SQL parsing and analysis.
"""

import os
import re
import logging
from typing import Dict, List, Set, Tuple, Optional, Any
import sqlglot
from sqlglot import parse_one, ParseError
from sqlglot.expressions import Select, Table, Column, Subquery, Create

# Import base classes
from ..base_dialect import BaseSQLDialect

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class TSQLDialect(BaseSQLDialect):
    """
    T-SQL (SQL Server) dialect parser.
    """
    
    def __init__(self):
        """Initialize the T-SQL dialect parser"""
        super().__init__("tsql")
    
    def _get_sqlglot_dialect(self) -> str:
        """
        Get the SQLGlot dialect name for T-SQL
        
        Returns:
            The SQLGlot dialect name
        """
        return "tsql"
    
    def _preprocess_sql(self, sql_code: str) -> str:
        """
        Preprocess T-SQL-specific syntax
        
        Args:
            sql_code: SQL code to preprocess
            
        Returns:
            Preprocessed SQL code
        """
        # Handle T-SQL specific syntax that SQLGlot might not support
        
        # Replace square bracket identifiers with quoted identifiers for parsing
        def replace_brackets(match):
            identifier = match.group(1)
            return f'"{identifier}"'
        
        sql_code = re.sub(r'\[([^\]]+)\]', replace_brackets, sql_code)
        
        # Handle T-SQL specific date functions
        sql_code = re.sub(r'\bGETDATE\(\)', 'CURRENT_TIMESTAMP', sql_code, flags=re.IGNORECASE)
        sql_code = re.sub(r'\bGETUTCDATE\(\)', 'CURRENT_TIMESTAMP', sql_code, flags=re.IGNORECASE)
        
        # Handle T-SQL specific string functions
        sql_code = re.sub(r'\bISNULL\((.*?),(.*?)\)', r'COALESCE(\1,\2)', sql_code, flags=re.IGNORECASE)
        
        # Handle T-SQL specific syntax like TOP clause
        sql_code = re.sub(r'SELECT\s+TOP\s+(\d+)', r'SELECT', sql_code, flags=re.IGNORECASE)
        
        return sql_code
    
    def parse_sql(self, sql_code: str) -> Tuple[Any, List[str]]:
        """
        Parse T-SQL code using SQLGlot
        
        Args:
            sql_code: SQL code to parse
            
        Returns:
            Tuple of (AST, errors)
        """
        errors = []
        ast = None
        
        try:
            # Handle T-SQL-specific syntax before parsing
            cleaned_sql = self._preprocess_sql(sql_code)
            
            # Parse with SQLGlot
            ast = parse_one(cleaned_sql, dialect=self._get_sqlglot_dialect())
        except ParseError as e:
            errors.append(f"Parse error: {str(e)}")
        except Exception as e:
            errors.append(f"Error parsing SQL: {str(e)}")
        
        return ast, errors
    
    def _extract_table_references(self, node: Any, tables: Set[str]) -> None:
        """
        Recursively extract table references from an AST node
        
        Args:
            node: SQLGlot AST node
            tables: Set to populate with table names
        """
        if node is None:
            return
        
        # If it's a table reference, add it to the set
        if isinstance(node, Table):
            table_name = self._extract_table_name(node)
            if table_name:
                tables.add(table_name)
        
        # Recursively process all children
        if hasattr(node, 'args'):
            for key, value in node.args.items():
                if isinstance(value, list):
                    for item in value:
                        self._extract_table_references(item, tables)
                else:
                    self._extract_table_references(value, tables)
    
    def _extract_table_name(self, table_node: Table) -> Optional[str]:
        """
        Extract the fully qualified table name from a Table node
        
        Args:
            table_node: SQLGlot Table node
            
        Returns:
            Fully qualified table name or None
        """
        try:
            # Different versions of sqlglot might store table names differently
            if hasattr(table_node, 'name'):
                # Direct name attribute
                name = table_node.name
                
                # Get schema and database if available
                db = None
                schema = None
                
                if hasattr(table_node, 'db') and table_node.db:
                    schema = table_node.db
                if hasattr(table_node, 'catalog') and table_node.catalog:
                    db = table_node.catalog
                
                # Build the fully qualified name
                if db and schema:
                    return f"{db}.{schema}.{name}"
                elif schema:
                    return f"{schema}.{name}"
                else:
                    return name
            
            # Alternative access via args
            elif hasattr(table_node, 'args'):
                name = table_node.args.get('this')
                schema = table_node.args.get('db')
                db = table_node.args.get('catalog')
                
                # Build the fully qualified name
                if db and schema:
                    return f"{db}.{schema}.{name}"
                elif schema:
                    return f"{schema}.{name}"
                else:
                    return name
            
            # If all else fails, try to extract from string representation
            else:
                table_str = str(table_node)
                # Remove quotes and brackets
                table_str = table_str.replace('"', '').replace('[', '').replace(']', '')
                return table_str
                
        except Exception as e:
            logger.error(f"Error extracting table name: {str(e)}")
            return None
    
    def _find_source_columns(self, node: Any, columns: List[Dict[str, str]]) -> None:
        """
        Recursively find source columns in an expression
        
        Args:
            node: SQLGlot AST node
            columns: List to populate with source columns
        """
        if node is None:
            return
        
        # If it's a column reference, add it to the list
        if isinstance(node, Column):
            column_name = None
            table_name = None
            
            # Try different ways to get column name depending on SQLGlot version
            if hasattr(node, 'name'):
                column_name = node.name
                if hasattr(node, 'table'):
                    table_name = node.table
            elif hasattr(node, 'args') and 'this' in node.args:
                column_name = node.args['this']
                if 'table' in node.args:
                    table_name = node.args['table']
            
            # Add to source columns if we found a name
            if column_name:
                columns.append({
                    "table": table_name,
                    "column": column_name
                })
        
        # Recursively process all children
        if hasattr(node, 'args'):
            for key, value in node.args.items():
                if isinstance(value, list):
                    for item in value:
                        self._find_source_columns(item, columns)
                else:
                    self._find_source_columns(value, columns)