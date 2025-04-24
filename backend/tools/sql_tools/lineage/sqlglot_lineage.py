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
            # Check for DBT specific reference patterns in table name
            if hasattr(node, 'name') and node.name:
                table_name = node.name
                # Handle DBT refs transformations (from {{ ref('table') }} to __dbt_ref_table)
                if table_name.startswith('__dbt_ref_'):
                    tables.append(node)
                # Handle DBT source transformations (from {{ source('schema', 'table') }} to __dbt_source_schema_table)
                elif table_name.startswith('__dbt_source_'):
                    tables.append(node)
                else:
                    tables.append(node)
            else:
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
            # Handle string table references (may happen after preprocessing)
            if isinstance(table_node, str):
                # Handle DBT specific patterns in string table references
                if table_node.startswith('__dbt_ref_'):
                    # Extract actual table name from __dbt_ref_table_name
                    table_name = table_node.replace('__dbt_ref_', '')
                    return {"name": table_name, "schema": None, "database": None, "catalog": None, "alias": None, "source_type": "dbt_ref"}
                elif table_node.startswith('__dbt_source_'):
                    # Extract schema and table name from __dbt_source_schema_table
                    parts = table_node.replace('__dbt_source_', '').split('_', 1)
                    if len(parts) == 2:
                        schema, table = parts
                        return {"name": table, "schema": schema, "database": None, "catalog": None, "alias": None, "source_type": "dbt_source"}
                    else:
                        return {"name": parts[0], "schema": None, "database": None, "catalog": None, "alias": None, "source_type": "dbt_source"}
                
                # Handle regular table references
                parts = table_node.split('.')
                if len(parts) == 1:
                    return {"name": parts[0], "schema": None, "database": None, "catalog": None, "alias": None}
                elif len(parts) == 2:
                    return {"name": parts[1], "schema": parts[0], "database": None, "catalog": None, "alias": None}
                elif len(parts) >= 3:
                    return {
                        "name": parts[-1], 
                        "schema": parts[-2], 
                        "database": parts[-3], 
                        "catalog": None, 
                        "alias": None
                    }
            
            # Handle non-Table objects that might have been passed
            if not isinstance(table_node, Table):
                # Try to convert to string and extract information
                table_str = str(table_node)
                # Handle DBT specific patterns
                if table_str.startswith('__dbt_ref_'):
                    table_name = table_str.replace('__dbt_ref_', '')
                    return {"name": table_name, "schema": None, "database": None, "catalog": None, "alias": None, "source_type": "dbt_ref"}
                elif table_str.startswith('__dbt_source_'):
                    parts = table_str.replace('__dbt_source_', '').split('_', 1)
                    if len(parts) == 2:
                        schema, table = parts
                        return {"name": table, "schema": schema, "database": None, "catalog": None, "alias": None, "source_type": "dbt_source"}
                    else:
                        return {"name": parts[0], "schema": None, "database": None, "catalog": None, "alias": None, "source_type": "dbt_source"}
                
                # Handle regular table references
                parts = table_str.split('.')
                if len(parts) == 1:
                    return {"name": parts[0], "schema": None, "database": None, "catalog": None, "alias": None}
                elif len(parts) == 2:
                    return {"name": parts[1], "schema": parts[0], "database": None, "catalog": None, "alias": None}
                elif len(parts) >= 3:
                    return {
                        "name": parts[-1], 
                        "schema": parts[-2], 
                        "database": parts[-3], 
                        "catalog": None, 
                        "alias": None
                    }
            
            # Now handle Table objects
            table_info = {
                "name": getattr(table_node, 'name', None),
                "schema": None,
                "database": None,
                "catalog": None,
                "alias": None,
                "source_type": None
            }
            
            # Handle DBT specific patterns
            if table_info["name"]:
                if table_info["name"].startswith('__dbt_ref_'):
                    table_info["name"] = table_info["name"].replace('__dbt_ref_', '')
                    table_info["source_type"] = "dbt_ref"
                elif table_info["name"].startswith('__dbt_source_'):
                    parts = table_info["name"].replace('__dbt_source_', '').split('_', 1)
                    if len(parts) == 2:
                        table_info["schema"] = parts[0]
                        table_info["name"] = parts[1]
                    else:
                        table_info["name"] = parts[0]
                    table_info["source_type"] = "dbt_source"
            
            # Handle case where name is missing but we have a string representation
            if table_info["name"] is None:
                table_str = str(table_node)
                # Check for DBT patterns in string representation
                if table_str.startswith('__dbt_ref_'):
                    table_info["name"] = table_str.replace('__dbt_ref_', '')
                    table_info["source_type"] = "dbt_ref"
                elif table_str.startswith('__dbt_source_'):
                    parts = table_str.replace('__dbt_source_', '').split('_', 1)
                    if len(parts) == 2:
                        table_info["schema"] = parts[0]
                        table_info["name"] = parts[1]
                    else:
                        table_info["name"] = parts[0]
                    table_info["source_type"] = "dbt_source"
                else:
                    parts = table_str.split('.')
                    if parts:
                        table_info["name"] = parts[-1]
            
            # Extract schema and database info from args or attributes
            if hasattr(table_node, 'args'):
                if 'this' in table_node.args and table_info["name"] is None:
                    table_info["name"] = table_node.args.get('this')
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
            if table_info["name"] and '.' in table_info["name"] and not table_info["source_type"]:
                parts = table_info["name"].split('.')
                if len(parts) == 2:
                    table_info["schema"] = parts[0]
                    table_info["name"] = parts[1]
                elif len(parts) == 3:
                    table_info["database"] = parts[0]
                    table_info["schema"] = parts[1]
                    table_info["name"] = parts[2]
            
            # Ensure we have at least a name
            if not table_info["name"]:
                table_info["name"] = str(table_node)
            
            return table_info
        except Exception as e:
            logger.error(f"Error extracting table info: {str(e)}")
            # As a fallback, try to return something useful
            try:
                return {"name": str(table_node), "schema": None, "database": None, "catalog": None, "alias": None}
            except:
                return {"name": "unknown_table", "schema": None, "database": None, "catalog": None, "alias": None}
    
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
        try:
            # Handle string column references (may happen after preprocessing)
            if isinstance(column_node, str):
                parts = column_node.split('.')
                if len(parts) == 1:
                    return {"name": parts[0], "table": None, "alias": None, "data_type": None}
                elif len(parts) >= 2:
                    return {"name": parts[-1], "table": parts[-2], "alias": None, "data_type": None}
            
            # Handle non-Column objects
            if not isinstance(column_node, Column):
                # Try to extract information from string representation
                column_str = str(column_node)
                parts = column_str.split('.')
                if len(parts) == 1:
                    return {"name": parts[0], "table": None, "alias": None, "data_type": None}
                elif len(parts) >= 2:
                    return {"name": parts[-1], "table": parts[-2], "alias": None, "data_type": None}
            
            # Now handle Column objects
            column_info = {
                "name": None,
                "table": None,
                "alias": None,
                "data_type": None
            }
            
            # Extract from attributes or args
            if hasattr(column_node, 'name'):
                column_info["name"] = column_node.name
            elif hasattr(column_node, 'args') and 'this' in column_node.args:
                column_info["name"] = column_node.args['this']
            
            if hasattr(column_node, 'table'):
                column_info["table"] = column_node.table
            elif hasattr(column_node, 'args') and 'table' in column_node.args:
                column_info["table"] = column_node.args['table']
            
            if hasattr(column_node, 'alias'):
                column_info["alias"] = column_node.alias
            elif hasattr(column_node, 'args') and 'alias' in column_node.args:
                column_info["alias"] = column_node.args['alias']
            
            if hasattr(column_node, 'type'):
                column_info["data_type"] = str(column_node.type)
            elif hasattr(column_node, 'args') and 'type' in column_node.args:
                column_info["data_type"] = str(column_node.args['type'])
            
            # Ensure we have a name
            if not column_info["name"]:
                column_info["name"] = str(column_node)
            
            return column_info
        except Exception as e:
            logger.error(f"Error extracting column info: {str(e)}")
            # Fallback to string representation
            try:
                return {"name": str(column_node), "table": None, "alias": None, "data_type": None}
            except:
                return {"name": "unknown_column", "table": None, "alias": None, "data_type": None}
    
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
        
        try:
            # Handle string values that might be column names
            if isinstance(node, str) and not node.startswith('__') and not node.isnumeric():
                columns.append({"column": node, "table": None})
                return
            
            # If it's a column reference, add it
            if isinstance(node, Column):
                col_info = self._extract_column_info(node)
                if col_info:
                    columns.append({"column": col_info["name"], "table": col_info["table"]})
            
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
        except Exception as e:
            logger.error(f"Error finding column references: {str(e)}")
    
    def _extract_column_name(self, col_expr: Any) -> Optional[str]:
        """Extract column name from a column expression"""
        try:
            # Handle string values
            if isinstance(col_expr, str):
                # If it contains a dot, extract the column part
                if '.' in col_expr:
                    return col_expr.split('.')[-1]
                return col_expr
            
            # Handle Column objects
            if isinstance(col_expr, Column):
                if hasattr(col_expr, 'name'):
                    return col_expr.name
                elif hasattr(col_expr, 'args') and 'this' in col_expr.args:
                    return col_expr.args['this']
                
            # Try to get alias if available
            if hasattr(col_expr, 'alias') and col_expr.alias:
                return col_expr.alias
            elif hasattr(col_expr, 'args') and 'alias' in col_expr.args and col_expr.args['alias']:
                return col_expr.args['alias']
            
            # Fallback to string representation
            return str(col_expr)
        except Exception as e:
            logger.error(f"Error extracting column name: {str(e)}")
            return None 