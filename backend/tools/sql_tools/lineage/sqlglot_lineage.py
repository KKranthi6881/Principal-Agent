"""
SQLGlot Lineage Extractor

This module extracts lineage information from SQL AST using SQLGlot.
"""

import os
import logging
from typing import Dict, List, Set, Tuple, Optional, Any
from sqlglot.expressions import Select, Create, Insert, Table, Column, Subquery

from .base_lineage import BaseLineageExtractor

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class SQLGlotLineageExtractor(BaseLineageExtractor):
    """
    SQL lineage extractor using SQLGlot AST
    """
    
    def __init__(self):
        """Initialize the SQLGlot lineage extractor"""
        super().__init__()
    
    def extract_table_lineage(self, sql_ast: Any, file_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Extract table-level lineage from SQL AST
        
        Args:
            sql_ast: SQLGlot AST
            file_path: Original file path
            
        Returns:
            Dictionary with table lineage information
        """
        try:
            # Initialize result
            result = {
                "source_tables": [],
                "target_table": None,
                "file_path": file_path,
                "relationships": []
            }
            
            # Check for CREATE or INSERT statements to determine target table
            if isinstance(sql_ast, Create):
                target_obj = sql_ast.find(Table)
                if target_obj:
                    result["target_table"] = self._extract_table_name(target_obj)
            elif isinstance(sql_ast, Insert):
                target_obj = sql_ast.find(Table)
                if target_obj:
                    result["target_table"] = self._extract_table_name(target_obj)
            
            # Extract source tables from SELECT statements
            self._extract_source_tables(sql_ast, result["source_tables"])
            
            # Remove duplicates while preserving order
            seen = set()
            result["source_tables"] = [x for x in result["source_tables"] 
                                      if not (x in seen or seen.add(x))]
            
            # Build relationships
            if result["target_table"] and result["source_tables"]:
                for source_table in result["source_tables"]:
                    result["relationships"].append({
                        "source": source_table,
                        "target": result["target_table"],
                        "type": "depends_on"
                    })
            
            return result
        except Exception as e:
            logger.error(f"Error extracting table lineage: {str(e)}")
            return {
                "source_tables": [],
                "target_table": None,
                "file_path": file_path,
                "error": str(e)
            }
    
    def _extract_source_tables(self, node: Any, tables: List[str]) -> None:
        """
        Recursively extract source tables from an AST node
        
        Args:
            node: SQLGlot AST node
            tables: List to populate with source table names
        """
        if node is None:
            return
        
        # If it's a table reference, add it to the list
        if isinstance(node, Table):
            table_name = self._extract_table_name(node)
            if table_name and table_name not in tables:
                tables.append(table_name)
        
        # Handle join expressions which might have different structure in this sqlglot version
        # Instead of checking for JoinExpression, look for join-related attributes
        if hasattr(node, 'args') and isinstance(node.args, dict):
            # Check for join-related attributes that might exist in different sqlglot versions
            if 'join' in node.args or 'joins' in node.args:
                # Handle joins by processing their table references
                joins = node.args.get('join', []) or node.args.get('joins', [])
                if isinstance(joins, list):
                    for join_item in joins:
                        self._extract_source_tables(join_item, tables)
                else:
                    self._extract_source_tables(joins, tables)
        
        # Process all child nodes
        if hasattr(node, 'args'):
            if isinstance(node.args, dict):
                for child in node.args.values():
                    if isinstance(child, list):
                        for item in child:
                            self._extract_source_tables(item, tables)
                    else:
                        self._extract_source_tables(child, tables)
            elif isinstance(node.args, list):
                for child in node.args:
                    self._extract_source_tables(child, tables)
    
    def _extract_table_name(self, table_node: Any) -> Optional[str]:
        """
        Extract table name from a Table node
        
        Args:
            table_node: SQLGlot Table node
            
        Returns:
            Table name as string
        """
        try:
            # Different versions of sqlglot might store table names differently
            if hasattr(table_node, 'name'):
                # Direct name attribute
                name = table_node.name
                if hasattr(table_node, 'db') and table_node.db:
                    return f"{table_node.db}.{name}"
                return name
            elif hasattr(table_node, 'args') and 'this' in table_node.args:
                # Name stored in args.this
                name = table_node.args.get('this')
                db = table_node.args.get('db')
                if db:
                    return f"{db}.{name}"
                return name
            elif hasattr(table_node, 'args') and 'name' in table_node.args:
                # Name stored in args.name
                name = table_node.args.get('name')
                db = table_node.args.get('db')
                if db:
                    return f"{db}.{name}"
                return name
            else:
                # Try to extract from string representation
                return str(table_node).split('.')[-1].strip('`"[]')
        except Exception as e:
            logger.error(f"Error extracting table name: {str(e)}")
            return None
    
    def extract_column_lineage(self, sql_ast: Any, file_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Extract column-level lineage from SQL AST
        
        Args:
            sql_ast: SQLGlot AST
            file_path: Original file path
            
        Returns:
            Dictionary with column lineage information
        """
        try:
            # Initialize result
            result = {
                "target_table": None,
                "column_mappings": {},
                "file_path": file_path
            }
            
            # Extract target table
            if isinstance(sql_ast, Create):
                target_obj = sql_ast.find(Table)
                if target_obj:
                    result["target_table"] = self._extract_table_name(target_obj)
            elif isinstance(sql_ast, Insert):
                target_obj = sql_ast.find(Table)
                if target_obj:
                    result["target_table"] = self._extract_table_name(target_obj)
            
            # Extract column mappings from SELECT statements
            if isinstance(sql_ast, Select) or (hasattr(sql_ast, 'args') and 'expression' in sql_ast.args):
                select_node = sql_ast if isinstance(sql_ast, Select) else sql_ast.args.get('expression')
                if select_node:
                    self._extract_column_mappings(select_node, result["column_mappings"])
            
            return result
        except Exception as e:
            logger.error(f"Error extracting column lineage: {str(e)}")
            return {
                "target_table": None,
                "column_mappings": {},
                "file_path": file_path,
                "error": str(e)
            }
    
    def _extract_column_mappings(self, select_node: Any, mappings: Dict[str, List[Dict[str, str]]]) -> None:
        """
        Extract column mappings from a SELECT statement
        
        Args:
            select_node: SQLGlot SELECT node
            mappings: Dictionary to populate with column mappings
        """
        try:
            # Extract column expressions from the SELECT clause
            columns = []
            if hasattr(select_node, 'args') and 'expressions' in select_node.args:
                columns = select_node.args.get('expressions', [])
            
            # Process each column expression
            for col_expr in columns:
                target_col = self._extract_column_name(col_expr)
                if not target_col:
                    continue
                
                source_cols = []
                # Find all column references in the expression
                self._find_column_references(col_expr, source_cols)
                
                # Add mapping
                if target_col and source_cols:
                    mappings[target_col] = source_cols
        except Exception as e:
            logger.error(f"Error extracting column mappings: {str(e)}")
    
    def _extract_column_name(self, col_expr: Any) -> Optional[str]:
        """
        Extract column name from a column expression
        
        Args:
            col_expr: SQLGlot column expression
            
        Returns:
            Column name as string
        """
        try:
            # Check for an alias first
            if hasattr(col_expr, 'args') and 'alias' in col_expr.args:
                return col_expr.args.get('alias')
            
            # If it's a direct column reference, use its name
            if isinstance(col_expr, Column):
                return col_expr.name if hasattr(col_expr, 'name') else col_expr.args.get('this')
            
            # Try to extract from string representation
            return str(col_expr).split('.')[-1].strip('`"[]')
        except Exception as e:
            logger.error(f"Error extracting column name: {str(e)}")
            return None
    
    def _find_column_references(self, node: Any, columns: List[Dict[str, str]]) -> None:
        """
        Recursively find column references in an expression
        
        Args:
            node: SQLGlot AST node
            columns: List to populate with column references
        """
        if node is None:
            return
        
        # If it's a column reference, add it to the list
        if isinstance(node, Column):
            col_name = self._extract_column_name(node)
            if col_name:
                # Try to extract table name
                table_name = None
                if hasattr(node, 'table'):
                    table_name = node.table
                elif hasattr(node, 'args') and 'table' in node.args:
                    table_name = node.args.get('table')
                
                if col_name and col_name not in [c.get('column') for c in columns]:
                    columns.append({
                        "table": table_name,
                        "column": col_name
                    })
        
        # Process all child nodes
        if hasattr(node, 'args'):
            if isinstance(node.args, dict):
                for child in node.args.values():
                    if isinstance(child, list):
                        for item in child:
                            self._find_column_references(item, columns)
                    else:
                        self._find_column_references(child, columns)
            elif isinstance(node.args, list):
                for child in node.args:
                    self._find_column_references(child, columns) 