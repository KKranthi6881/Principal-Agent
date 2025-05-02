"""
PostgreSQL SQL Dialect Parser

This module provides PostgreSQL-specific SQL parsing and analysis.
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

class PostgreSQLDialect(BaseSQLDialect):
    """
    PostgreSQL-specific SQL dialect parser.
    """
    
    def __init__(self):
        """Initialize the PostgreSQL dialect parser"""
        super().__init__("postgresql")
    
    def _get_sqlglot_dialect(self) -> str:
        """
        Get the SQLGlot dialect name for PostgreSQL
        
        Returns:
            The SQLGlot dialect name
        """
        return "postgres"
    
    def parse_sql(self, sql_code: str, file_path: str = None) -> Tuple[Any, List[str]]:
        """
        Parse PostgreSQL code using SQLGlot
        
        Args:
            sql_code: SQL code to parse
            file_path: Optional path to the file being parsed (for better error reporting)
            
        Returns:
            Tuple of (AST, errors)
        """
        errors = []
        ast = None
        
        try:
            # Handle PostgreSQL-specific syntax before parsing
            cleaned_sql = self._preprocess_sql(sql_code)
            
            # Parse with SQLGlot
            ast = parse_one(cleaned_sql, dialect=self._get_sqlglot_dialect())
            
            # If parsing succeeded but we have a file path, log it for debugging
            if file_path:
                logger.debug(f"Successfully parsed {file_path} with PostgreSQL dialect")
                
        except ParseError as e:
            error_msg = f"Parse error: {str(e)}"
            if file_path:
                error_msg = f"Parse error in {file_path}: {str(e)}"
            errors.append(error_msg)
        except Exception as e:
            error_msg = f"Error parsing SQL: {str(e)}"
            if file_path:
                error_msg = f"Error parsing {file_path}: {str(e)}"
            errors.append(error_msg)
        
        return ast, errors
    
    def _preprocess_sql(self, sql_code: str) -> str:
        """
        Preprocess PostgreSQL-specific syntax
        
        Args:
            sql_code: SQL code to preprocess
            
        Returns:
            Preprocessed SQL code
        """
        # Handle PostgreSQL-specific syntax that SQLGlot might not support
        
        # Replace SIMILAR TO with LIKE for parsing purposes
        sql_code = re.sub(r'\bSIMILAR\s+TO\b', 'LIKE', sql_code, flags=re.IGNORECASE)
        
        # Replace interval syntax
        sql_code = re.sub(r"interval\s+'([^']+)'", r"interval '\1'", sql_code, flags=re.IGNORECASE)
        
        # Handle $ quoted strings by converting to single quotes
        def replace_dollar_quotes(match):
            content = match.group(2)
            return f"'{content}'"
        
        sql_code = re.sub(r'(\$\w*\$)(.*?)(\$\w*\$)', replace_dollar_quotes, sql_code, flags=re.DOTALL)
        
        return sql_code
    
    def extract_dependencies(self, sql_code: str, file_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Extract table dependencies from PostgreSQL code
        
        Args:
            sql_code: SQL code to analyze
            file_path: Path to the file (optional)
            
        Returns:
            Dictionary with dependency information
        """
        # Parse the SQL code
        ast, errors = self.parse_sql(sql_code)
        
        # Initialize dependency result
        result = {
            "source_tables": [],
            "target_table": None,
            "errors": errors,
            "file_path": file_path
        }
        
        if not ast:
            return result
        
        try:
            # Extract target table for CREATE and INSERT statements
            if isinstance(ast, Create):
                table_ref = ast.find(Table)
                if table_ref:
                    table_name = self._extract_table_name(table_ref)
                    result["target_table"] = table_name
            
            # Extract source tables from all statements
            source_tables = set()
            self._extract_table_references(ast, source_tables)
            
            # Convert to list and remove target table from sources if it exists
            source_tables = list(source_tables)
            if result["target_table"] in source_tables:
                source_tables.remove(result["target_table"])
            
            result["source_tables"] = source_tables
            
        except Exception as e:
            result["errors"].append(f"Error extracting dependencies: {str(e)}")
        
        return result
    
    def _extract_table_references(self, node: Any, tables: Set[str]) -> None:
        """
        Recursively extract table references from an AST node
        
        Args:
            node: SQLGlot AST node
            tables: Set to populate with table names
        """
        if node is None:
            return
        
        # If it's a Table node, extract its name
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
            Table name, possibly schema-qualified
        """
        try:
            # The table node might store the name in different places depending on SQLGlot version
            table_name = None
            schema_name = None
            
            # Try to extract from direct attributes
            if hasattr(table_node, 'name'):
                table_name = table_node.name
                if hasattr(table_node, 'db'):
                    schema_name = table_node.db
            
            # Try to extract from args
            elif hasattr(table_node, 'args'):
                if 'this' in table_node.args:
                    table_name = table_node.args['this']
                elif 'name' in table_node.args:
                    table_name = table_node.args['name']
                
                if 'db' in table_node.args:
                    schema_name = table_node.args['db']
            
            # Fallback to string representation
            if not table_name:
                table_str = str(table_node)
                if '.' in table_str:
                    parts = table_str.split('.')
                    schema_name = parts[-2]
                    table_name = parts[-1]
                else:
                    table_name = table_str
            
            # Remove quotes and brackets if present
            if table_name:
                table_name = table_name.strip('"[]`')
            if schema_name:
                schema_name = schema_name.strip('"[]`')
            
            # Return schema-qualified name if schema is available
            if schema_name:
                return f"{schema_name}.{table_name}"
            return table_name
            
        except Exception as e:
            logger.error(f"Error extracting table name: {str(e)}")
            return None
    
    def extract_lineage(self, sql_code: str, file_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Extract column-level lineage from PostgreSQL code
        
        Args:
            sql_code: SQL code to analyze
            file_path: Path to the file (optional)
            
        Returns:
            Dictionary with lineage information
        """
        # Parse the SQL code
        ast, errors = self.parse_sql(sql_code)
        
        # Initialize lineage result
        result = {
            "target_table": None,
            "source_tables": [],
            "column_level_lineage": {},
            "errors": errors,
            "file_path": file_path
        }
        
        if not ast:
            return result
        
        try:
            # Get table-level dependencies
            deps = self.extract_dependencies(sql_code, file_path)
            result["target_table"] = deps["target_table"]
            result["source_tables"] = deps["source_tables"]
            
            # Extract column mappings for CREATE TABLE AS or SELECT statements
            if isinstance(ast, Create) and ast.find(Select):
                select_node = ast.find(Select)
                self._extract_column_lineage(select_node, result["column_level_lineage"])
            elif isinstance(ast, Select):
                self._extract_column_lineage(ast, result["column_level_lineage"])
            
        except Exception as e:
            result["errors"].append(f"Error extracting lineage: {str(e)}")
        
        return result
    
    def _extract_column_lineage(self, select_node: Select, lineage: Dict[str, List[Dict[str, str]]]) -> None:
        """
        Extract column lineage from a SELECT statement
        
        Args:
            select_node: SQLGlot SELECT node
            lineage: Dictionary to populate with column lineage
        """
        if not select_node or not hasattr(select_node, 'args'):
            return
        
        # Get the column expressions from the SELECT
        select_expressions = select_node.args.get('expressions', [])
        
        # Process each column expression
        for expr in select_expressions:
            # Get the target column name (alias or derived)
            target_column = None
            
            # Check for alias
            if hasattr(expr, 'alias'):
                target_column = expr.alias
            elif hasattr(expr, 'args') and 'alias' in expr.args:
                target_column = expr.args['alias']
            # If it's a direct column reference with no alias, use its name
            elif isinstance(expr, Column):
                if hasattr(expr, 'name'):
                    target_column = expr.name
                elif hasattr(expr, 'args') and 'this' in expr.args:
                    target_column = expr.args['this']
            
            # Skip if we couldn't determine the target column
            if not target_column:
                continue
            
            # Find all source columns in this expression
            source_columns = []
            self._find_source_columns(expr, source_columns)
            
            # Only add to lineage if we found source columns
            if source_columns:
                lineage[target_column] = source_columns
    
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
            elif hasattr(node, 'args') and 'this' in node.args:
                column_name = node.args['this']
            
            # Try different ways to get table name
            if hasattr(node, 'table'):
                table_name = node.table
            elif hasattr(node, 'args') and 'table' in node.args:
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