"""
SQLGlot Lineage Extractor

This module extracts lineage information from SQL AST using SQLGlot.
"""

import os
import logging
from typing import Dict, List, Set, Tuple, Optional, Any
from sqlglot.expressions import Select, Create, Insert, Table, Column, Subquery, Join, Comment

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
                "relationships": [],
                "business_metadata": {
                    "description": None,
                    "owner": None,
                    "tags": [],
                    "notes": []
                }
            }
            
            # Extract business metadata from comments
            self._extract_business_metadata(sql_ast, result["business_metadata"])
            
            # Check for CREATE or INSERT statements to determine target table
            if isinstance(sql_ast, Create):
                target_obj = sql_ast.find(Table)
                if target_obj:
                    result["target_table"] = self._extract_table_info(target_obj)
            elif isinstance(sql_ast, Insert):
                target_obj = sql_ast.find(Table)
                if target_obj:
                    result["target_table"] = self._extract_table_info(target_obj)
            
            # Extract source tables and relationships
            source_tables = []
            self._extract_source_tables(sql_ast, source_tables)
            
            # Process each source table
            for source in source_tables:
                source_info = self._extract_table_info(source)
                if source_info not in result["source_tables"]:
                    result["source_tables"].append(source_info)
                
                # Add relationship if we have a target
                if result["target_table"]:
                    relationship = self._extract_relationship(source, sql_ast)
                    if relationship:
                        result["relationships"].append(relationship)
            
            return result
            
        except Exception as e:
            logger.error(f"Error extracting table lineage: {str(e)}")
            return {
                "source_tables": [],
                "target_table": None,
                "file_path": file_path,
                "error": str(e)
            }
    
    def _extract_source_tables(self, node: Any, tables: List[Any]) -> None:
        """
        Recursively extract source tables from an AST node
        
        Args:
            node: SQLGlot AST node
            tables: List to populate with source table nodes
        """
        if node is None:
            return
        
        # If it's a table reference, add it to the list
        if isinstance(node, Table):
            tables.append(node)
        
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
    
    def _extract_table_info(self, table_node: Table) -> Dict[str, Any]:
        """Extract detailed information about a table"""
        try:
            table_info = {
                "name": table_node.name,
                "schema": None,
                "database": None,
                "catalog": None,
                "alias": None
            }
            
            # Extract schema and database info from args or attributes
            if hasattr(table_node, 'args'):
                if 'db' in table_node.args:
                    table_info["database"] = table_node.args.get('db')
                if 'schema' in table_node.args:
                    table_info["schema"] = table_node.args.get('schema')
                if 'catalog' in table_node.args:
                    table_info["catalog"] = table_node.args.get('catalog')
                if 'alias' in table_node.args:
                    table_info["alias"] = table_node.args.get('alias')
                
            # Extract from direct attributes if available
            if hasattr(table_node, 'db') and table_node.db is not None:
                table_info["database"] = table_node.db
            if hasattr(table_node, 'alias') and table_node.alias is not None:
                table_info["alias"] = table_node.alias
            
            # Extract schema from full name if it contains a dot
            if '.' in table_node.name:
                parts = table_node.name.split('.')
                if len(parts) == 2:
                    table_info["schema"] = parts[0]
                    table_info["name"] = parts[1]
                elif len(parts) == 3:
                    table_info["database"] = parts[0]
                    table_info["schema"] = parts[1]
                    table_info["name"] = parts[2]
            
            return table_info
        except Exception as e:
            logger.error(f"Error extracting table info: {str(e)}")
            return {"name": str(table_node), "schema": None, "database": None}
    
    def _extract_relationship(self, source_table: Table, ast: Any) -> Optional[Dict[str, Any]]:
        """Extract relationship information between tables"""
        relationship = {
            "type": "depends_on",  # Default relationship type
            "source": self._extract_table_info(source_table),
            "join_type": None,
            "join_conditions": []
        }
        
        # Look for JOIN information
        joins = ast.find_all(Join)
        for join in joins:
            if join.left and self._is_same_table(join.left, source_table):
                relationship["join_type"] = join.kind  # INNER, LEFT, RIGHT, etc.
                if join.on:
                    relationship["join_conditions"] = self._extract_join_conditions(join.on)
                break
        
        return relationship
    
    def _extract_join_conditions(self, join_condition: Any) -> List[Dict[str, str]]:
        """Extract conditions from a JOIN clause"""
        conditions = []
        
        def visit_condition(node):
            if hasattr(node, "left") and hasattr(node, "right"):
                if isinstance(node.left, Column) and isinstance(node.right, Column):
                    conditions.append({
                        "left_column": node.left.name,
                        "left_table": node.left.table.name if node.left.table else None,
                        "operator": node.key if hasattr(node, "key") else "=",
                        "right_column": node.right.name,
                        "right_table": node.right.table.name if node.right.table else None
                    })
            
            # Recursively process children
            if hasattr(node, "args"):
                for arg in node.args.values():
                    if isinstance(arg, list):
                        for item in arg:
                            visit_condition(item)
                    else:
                        visit_condition(arg)
        
        visit_condition(join_condition)
        return conditions
    
    def _is_same_table(self, table1: Table, table2: Table) -> bool:
        """Check if two table nodes refer to the same table"""
        return (table1.name == table2.name and 
                getattr(table1, 'db', None) == getattr(table2, 'db', None))
    
    def _extract_business_metadata(self, node: Any, metadata: Dict[str, Any]):
        """Extract business metadata from comments"""
        comments = node.find_all(Comment)
        
        for comment in comments:
            text = comment.text.strip()
            
            # Look for structured comments
            if text.startswith('@'):
                parts = text[1:].split(':', 1)
                if len(parts) == 2:
                    key, value = parts[0].strip(), parts[1].strip()
                    if key == 'description':
                        metadata["description"] = value
                    elif key == 'owner':
                        metadata["owner"] = value
                    elif key == 'tags':
                        metadata["tags"].extend([t.strip() for t in value.split(',')])
                    elif key == 'note':
                        metadata["notes"].append(value)
            else:
                # Treat as general description if no structured format
                if not metadata["description"]:
                    metadata["description"] = text
    
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
            result = {
                "target_columns": [],
                "source_columns": [],
                "column_relationships": [],
                "file_path": file_path
            }
            
            # Handle CREATE TABLE
            if isinstance(sql_ast, Create):
                # Extract target columns from CREATE TABLE definition
                columns = sql_ast.find_all(Column)
                for col in columns:
                    col_info = self._extract_column_info(col)
                    if col_info:
                        result["target_columns"].append(col_info)
            
            # Handle SELECT statements
            select_stmt = sql_ast.find(Select)
            if select_stmt:
                # Extract target columns from SELECT list
                for col in select_stmt.expressions:
                    if isinstance(col, Column):
                        col_info = self._extract_column_info(col)
                        if col_info:
                            result["target_columns"].append(col_info)
                    
                # Extract source columns and relationships
                self._extract_source_columns(select_stmt, result)
            
            return result
            
        except Exception as e:
            logger.error(f"Error extracting column lineage: {str(e)}")
            return {
                "target_columns": [],
                "source_columns": [],
                "column_relationships": [],
                "file_path": file_path,
                "error": str(e)
            }
    
    def _extract_column_info(self, column_node: Column) -> Dict[str, Any]:
        """Extract detailed information about a column"""
        info = {
            "name": column_node.name,
            "table": None,
            "data_type": None,
            "is_nullable": True,
            "default_value": None,
            "business_metadata": {
                "description": None,
                "tags": [],
                "notes": []
            },
            "constraints": []
        }
        
        # Get table reference
        if column_node.table:
            info["table"] = self._extract_table_info(column_node.table)
        
        # Extract business metadata from comments
        self._extract_business_metadata(column_node, info["business_metadata"])
        
        # Look for constraints and data type
        parent = column_node.parent
        while parent:
            if hasattr(parent, "type"):
                info["data_type"] = str(parent.type)
            elif isinstance(parent, Comment):
                if not info["business_metadata"]["description"]:
                    info["business_metadata"]["description"] = parent.text
            
            # Check for constraints
            constraint = self._extract_constraint(parent)
            if constraint:
                info["constraints"].append(constraint)
            
            parent = parent.parent
        
        return info
    
    def _extract_constraint(self, node: Any) -> Optional[Dict[str, str]]:
        """Extract constraint information from a node"""
        if hasattr(node, "type") and node.type == "Constraint":
            return {
                "type": node.type,
                "name": node.name,
                "columns": [col.name for col in node.find_all(Column)]
            }
        return None
    
    def _extract_source_columns(self, select_stmt: Select, result: Dict[str, Any]) -> None:
        """Extract source columns and relationships from a SELECT statement"""
        columns = []
        if hasattr(select_stmt, 'expressions'):
            columns = select_stmt.expressions
        
        for col in columns:
            if isinstance(col, Column):
                col_info = self._extract_column_info(col)
                if col_info:
                    result["target_columns"].append(col_info)
                    self._find_column_references(col, result["source_columns"])
    
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
            column_info = {
                "name": node.name,
                "table": None
            }
            
            # Add table reference if present
            if node.table:
                column_info["table"] = node.table.name
            
            columns.append(column_info)
        
        # Process child nodes
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