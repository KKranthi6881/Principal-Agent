"""
SQLGlot Lineage Extractor

This module extracts lineage information from SQL AST using SQLGlot.
"""

import os
import logging
from typing import Dict, List, Set, Tuple, Optional, Any
from sqlglot.expressions import Select, Create, Insert, Table, Column, Subquery, JoinExpression

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
            sql_ast: SQL AST from SQLGlot
            file_path: Path to the file (optional)
            
        Returns:
            Dictionary with table lineage information
        """
        result = self.get_default_output_format()
        result["file_path"] = file_path
        
        if not sql_ast:
            result["errors"].append({
                "error_type": "missing_ast",
                "message": "No SQL AST provided"
            })
            return result
        
        try:
            # Extract target table
            target_table = self._extract_target_table(sql_ast)
            result["target_table"] = target_table
            
            # Extract source tables
            source_tables = self._extract_source_tables(sql_ast)
            result["source_tables"] = list(source_tables)
            
            # Extract column-level lineage if we have a target table
            if target_table:
                column_lineage = self.extract_column_lineage(sql_ast, file_path)["column_level_lineage"]
                result["column_level_lineage"] = column_lineage
            
            return result
        except Exception as e:
            logger.error(f"Error extracting table lineage: {str(e)}")
            result["errors"].append({
                "error_type": "lineage_extraction_error",
                "message": f"Error extracting table lineage: {str(e)}"
            })
            return result
    
    def extract_column_lineage(self, sql_ast: Any, file_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Extract column-level lineage from SQL AST
        
        Args:
            sql_ast: SQL AST from SQLGlot
            file_path: Path to the file (optional)
            
        Returns:
            Dictionary with column lineage information
        """
        result = self.get_default_output_format()
        result["file_path"] = file_path
        
        if not sql_ast:
            result["errors"].append({
                "error_type": "missing_ast",
                "message": "No SQL AST provided"
            })
            return result
        
        try:
            # Extract target table
            target_table = self._extract_target_table(sql_ast)
            result["target_table"] = target_table
            
            # Extract source tables
            source_tables = self._extract_source_tables(sql_ast)
            result["source_tables"] = list(source_tables)
            
            # Extract column lineage
            column_mappings = {}
            
            # For CREATE TABLE or INSERT statements, examine the SELECT part
            select_ast = None
            if isinstance(sql_ast, Create) or isinstance(sql_ast, Insert):
                # Get the SELECT query if it's a CREATE TABLE AS or INSERT
                if hasattr(sql_ast, 'args') and 'expression' in sql_ast.args:
                    select_ast = sql_ast.args['expression']
            elif isinstance(sql_ast, Select):
                select_ast = sql_ast
            
            if select_ast and isinstance(select_ast, Select):
                column_mappings = self._extract_column_mappings(select_ast, target_table, source_tables)
            
            result["column_level_lineage"] = column_mappings
            return result
            
        except Exception as e:
            logger.error(f"Error extracting column lineage: {str(e)}")
            result["errors"].append({
                "error_type": "lineage_extraction_error",
                "message": f"Error extracting column lineage: {str(e)}"
            })
            return result
    
    def _extract_target_table(self, sql_ast: Any) -> Optional[str]:
        """
        Extract target table name from SQL AST
        
        Args:
            sql_ast: SQL AST
            
        Returns:
            Target table name or None if not found
        """
        if isinstance(sql_ast, Create):
            # For CREATE TABLE statements, the target is the table being created
            if hasattr(sql_ast, 'this') and hasattr(sql_ast.this, 'name'):
                table_name = sql_ast.this.name
                if hasattr(sql_ast.this, 'db') and sql_ast.this.db:
                    table_name = f"{sql_ast.this.db}.{table_name}"
                return table_name
        
        elif isinstance(sql_ast, Insert):
            # For INSERT statements, the target is the table being inserted into
            if hasattr(sql_ast, 'this') and hasattr(sql_ast.this, 'name'):
                table_name = sql_ast.this.name
                if hasattr(sql_ast.this, 'db') and sql_ast.this.db:
                    table_name = f"{sql_ast.this.db}.{table_name}"
                return table_name
        
        # If it's just a SELECT statement, there's no target table
        return None
    
    def _extract_source_tables(self, sql_ast: Any) -> Set[str]:
        """
        Extract source table references from SQL AST
        
        Args:
            sql_ast: SQL AST
            
        Returns:
            Set of source table references
        """
        source_tables = set()
        
        def extract_tables(expr, exclude_table=None):
            if isinstance(expr, Table):
                table_name = expr.name
                if hasattr(expr, 'db') and expr.db:
                    table_name = f"{expr.db}.{table_name}"
                # Don't include the target table as a source
                if table_name != exclude_table:
                    source_tables.add(table_name)
            
            # Handle subqueries
            if isinstance(expr, Subquery):
                if hasattr(expr, 'this'):
                    extract_tables(expr.this, exclude_table)
            
            # Process child expressions
            if hasattr(expr, 'args'):
                for arg_name, arg_value in expr.args.items():
                    if arg_value:
                        if isinstance(arg_value, list):
                            for item in arg_value:
                                extract_tables(item, exclude_table)
                        else:
                            extract_tables(arg_value, exclude_table)
        
        # Get the target table so we can exclude it
        target_table = self._extract_target_table(sql_ast)
        
        # If it's a CREATE TABLE AS or INSERT ... SELECT, extract from the SELECT part
        if isinstance(sql_ast, Create) or isinstance(sql_ast, Insert):
            if hasattr(sql_ast, 'args') and 'expression' in sql_ast.args:
                expression = sql_ast.args['expression']
                extract_tables(expression, target_table)
        else:
            # Otherwise process the whole AST
            extract_tables(sql_ast, target_table)
        
        return source_tables
    
    def _extract_column_mappings(self, select_ast: Select, target_table: Optional[str], 
                                source_tables: Set[str]) -> Dict[str, List[Dict[str, str]]]:
        """
        Extract column mappings from a SELECT statement
        
        Args:
            select_ast: SELECT AST from SQLGlot
            target_table: Target table name
            source_tables: Set of source table names
            
        Returns:
            Dictionary of {target_column: [{"table": source_table, "column": source_column}, ...]}
        """
        column_mappings = {}
        
        # Process the SELECT expressions to get target columns
        if hasattr(select_ast, 'args') and 'expressions' in select_ast.args:
            select_expressions = select_ast.args['expressions']
            
            # Build a map of table aliases
            table_aliases = self._extract_table_aliases(select_ast)
            
            # Process each SELECT expression
            for i, expr in enumerate(select_expressions):
                # Get target column name (either alias or column name)
                target_column = None
                if hasattr(expr, 'alias'):
                    target_column = expr.alias
                elif isinstance(expr, Column):
                    target_column = expr.name
                else:
                    # For expressions without clear names, use a position-based name
                    target_column = f"column_{i+1}"
                
                # Find source columns referenced in this expression
                source_refs = []
                self._find_column_references(expr, source_refs, table_aliases, source_tables)
                
                # Add to column mappings if source columns were found
                if source_refs:
                    column_mappings[target_column] = source_refs
        
        return column_mappings
    
    def _extract_table_aliases(self, select_ast: Select) -> Dict[str, str]:
        """
        Extract table aliases from a SELECT statement
        
        Args:
            select_ast: SELECT AST from SQLGlot
            
        Returns:
            Dictionary of {alias: table_name}
        """
        table_aliases = {}
        
        # Process FROM clause
        if hasattr(select_ast, 'args') and 'from' in select_ast.args:
            from_clause = select_ast.args['from']
            if from_clause:
                # Process tables and subqueries in FROM clause
                for item in from_clause:
                    if isinstance(item, Table):
                        # For tables with aliases
                        if hasattr(item, 'alias'):
                            alias = item.alias
                            table_name = item.name
                            if hasattr(item, 'db') and item.db:
                                table_name = f"{item.db}.{table_name}"
                            table_aliases[alias] = table_name
                        # For tables without aliases, use the table name as its own alias
                        else:
                            table_name = item.name
                            if hasattr(item, 'db') and item.db:
                                table_name = f"{item.db}.{table_name}"
                            table_aliases[table_name] = table_name
                    
                    # For subqueries with aliases
                    elif isinstance(item, Subquery) and hasattr(item, 'alias'):
                        table_aliases[item.alias] = item.alias  # Use alias as table name for subqueries
                    
                    # For JOINs
                    elif isinstance(item, JoinExpression):
                        # Process the main (left) table
                        if hasattr(item, 'this') and isinstance(item.this, Table):
                            left_table = item.this
                            if hasattr(left_table, 'alias'):
                                alias = left_table.alias
                                table_name = left_table.name
                                if hasattr(left_table, 'db') and left_table.db:
                                    table_name = f"{left_table.db}.{table_name}"
                                table_aliases[alias] = table_name
                            else:
                                table_name = left_table.name
                                if hasattr(left_table, 'db') and left_table.db:
                                    table_name = f"{left_table.db}.{table_name}"
                                table_aliases[table_name] = table_name
                        
                        # Process the joined (right) table
                        if hasattr(item, 'expression') and isinstance(item.expression, Table):
                            right_table = item.expression
                            if hasattr(right_table, 'alias'):
                                alias = right_table.alias
                                table_name = right_table.name
                                if hasattr(right_table, 'db') and right_table.db:
                                    table_name = f"{right_table.db}.{table_name}"
                                table_aliases[alias] = table_name
                            else:
                                table_name = right_table.name
                                if hasattr(right_table, 'db') and right_table.db:
                                    table_name = f"{right_table.db}.{table_name}"
                                table_aliases[table_name] = table_name
        
        return table_aliases
    
    def _find_column_references(self, expr, source_refs, table_aliases, source_tables, current_table=None):
        """
        Find column references in an expression
        
        Args:
            expr: SQL expression
            source_refs: List to populate with source references
            table_aliases: Dictionary of {alias: table_name}
            source_tables: Set of source table names
            current_table: Current table context
        """
        if isinstance(expr, Column):
            column_name = expr.name
            table_ref = None
            
            # If the column has a table reference
            if hasattr(expr, 'table'):
                table_ref = expr.table
                
                # Resolve the table alias if needed
                if table_ref in table_aliases:
                    actual_table = table_aliases[table_ref]
                    # Only include if it's one of our source tables
                    if actual_table in source_tables:
                        source_refs.append({"table": actual_table, "column": column_name})
                # Might already be a full table name
                elif table_ref in source_tables:
                    source_refs.append({"table": table_ref, "column": column_name})
            
            # If no table reference but we have a current table context
            elif current_table and current_table in source_tables:
                source_refs.append({"table": current_table, "column": column_name})
        
        # Set current table if we're at a table expression
        if isinstance(expr, Table):
            table_name = expr.name
            if hasattr(expr, 'db') and expr.db:
                table_name = f"{expr.db}.{table_name}"
            current_table = table_name
        
        # Process child expressions
        if hasattr(expr, 'args'):
            for arg_name, arg_value in expr.args.items():
                if arg_value:
                    if isinstance(arg_value, list):
                        for item in arg_value:
                            self._find_column_references(item, source_refs, table_aliases, source_tables, current_table)
                    else:
                        self._find_column_references(arg_value, source_refs, table_aliases, source_tables, current_table) 