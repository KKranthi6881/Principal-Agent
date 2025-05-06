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
        # Preprocess SQL code to help with parsing
        cleaned_sql = self._preprocess_sql(sql_code)
        
        # Parse the SQL code
        ast, errors = self.parse_sql(cleaned_sql)
        
        # Initialize lineage results
        result = {
            "table_lineage": {
                "source_tables": [],
                "target_table": None,
                "errors": errors,
                "file_path": file_path
            },
            "column_lineage": {
                "source_columns": [],
                "target_columns": [],
                "column_relationships": [],
                "column_level_lineage": {}
            },
            "errors": errors
        }
        
        # Infer target table name from file path if possible
        target_table_name = None
        if file_path:
            import os
            base_name = os.path.basename(file_path)
            if base_name.endswith('.sql'):
                target_table_name = base_name[:-4]  # Remove .sql extension
                logger.info(f"Inferred target table {target_table_name} from file path {file_path}")
        
        if not ast:
            # Even if parsing failed, try to extract columns using regex
            target_columns = self._extract_columns_from_sql(sql_code, target_table_name)
            if target_columns:
                result["column_lineage"]["target_columns"] = target_columns
                if target_table_name and not result["table_lineage"]["target_table"]:
                    result["table_lineage"]["target_table"] = target_table_name
            return result
        
        try:
            # Extract table-level dependencies
            deps = self.extract_dependencies(sql_code, file_path)
            result["table_lineage"]["target_table"] = deps["target_table"]
            result["table_lineage"]["source_tables"] = deps["source_tables"]
            
            # If we found a target table, use it
            if deps["target_table"]:
                target_table_name = deps["target_table"]
            
            # Extract column mappings for CREATE TABLE AS or SELECT statements
            column_mappings = {}
            if isinstance(ast, Create) and ast.find(Select):
                select_node = ast.find(Select)
                self._extract_column_lineage(select_node, column_mappings)
            elif isinstance(ast, Select):
                self._extract_column_lineage(ast, column_mappings)
                
            # Process column mappings into standard format
            if column_mappings:
                # Extract source columns from mappings
                source_columns = []
                target_columns = []
                column_relationships = []
                
                for target_col, source_cols in column_mappings.items():
                    # Add target column
                    target_columns.append({
                        "name": target_col,
                        "table": target_table_name,
                        "data_type": "unknown"
                    })
                    
                    # Process source columns and relationships
                    for source_col in source_cols:
                        # Add source column if not already there
                        if source_col not in source_columns:
                            source_columns.append(source_col)
                        
                        # Create relationship
                        column_relationships.append({
                            "source_table": source_col.get("table"),
                            "source_column": source_col.get("column"),
                            "target_table": target_table_name,
                            "target_column": target_col,
                            "relationship_type": "dependency"
                        })
                
                result["column_lineage"]["source_columns"] = source_columns
                result["column_lineage"]["target_columns"] = target_columns
                result["column_lineage"]["column_relationships"] = column_relationships
                result["column_lineage"]["column_level_lineage"] = column_mappings
            
            # If no columns were found, try direct SQL parsing
            if not result["column_lineage"]["target_columns"]:
                target_columns = self._extract_columns_from_sql(sql_code, target_table_name)
                if target_columns:
                    result["column_lineage"]["target_columns"] = target_columns
                    
                    # Try to build relationships with source tables if available
                    source_tables = deps.get("source_tables", [])
                    if source_tables:
                        # For each source table, try to match column names
                        for source_table in source_tables:
                            for target_col in target_columns:
                                # Add a relationship assuming column names match in source and target
                                result["column_lineage"]["column_relationships"].append({
                                    "source_table": source_table,
                                    "source_column": target_col["name"],
                                    "target_table": target_table_name,
                                    "target_column": target_col["name"],
                                    "relationship_type": "dependency"
                                })
                        
        except Exception as e:
            import traceback
            error_msg = f"Error extracting lineage: {str(e)}"
            logger.error(f"{error_msg}\n{traceback.format_exc()}")
            result["errors"].append(error_msg)
        
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
            
            # If we still don't have a target column name, try to derive it from the expression
            if not target_column and hasattr(expr, 'args'):
                # Try to extract from a field name or function name
                if 'this' in expr.args:
                    target_column = expr.args['this']
                elif 'name' in expr.args:
                    target_column = expr.args['name']
                elif str(expr):
                    # Use the string representation as a last resort
                    target_str = str(expr)
                    # Clean it up if it's too long
                    if len(target_str) > 30:
                        target_str = target_str[:27] + '...'
                    target_column = target_str
            
            # Skip if we couldn't determine the target column
            if not target_column:
                continue
            
            # Find all source columns in this expression
            source_columns = []
            self._find_source_columns(expr, source_columns)
            
            # For direct column references with no source columns found
            # (often happens with simple column selections), create a source 
            # column that matches the target column
            if not source_columns and isinstance(expr, Column):
                table_name = None
                if hasattr(expr, 'table'):
                    table_name = expr.table
                elif hasattr(expr, 'args') and 'table' in expr.args:
                    table_name = expr.args['table']
                
                # Only add if we have a table reference
                if table_name:
                    source_columns.append({
                        "table": table_name,
                        "column": target_column
                    })
            
            # Add to lineage whether we found source columns or not
            # This ensures we capture all columns, even those without clear lineage
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
                    
    def _extract_columns_from_sql(self, sql_code: str, target_table_name: str = None) -> List[Dict[str, Any]]:
        """
        Extract columns from SQL code using regex-based parsing for PostgreSQL specific syntax
        
        Args:
            sql_code: SQL code to extract columns from
            target_table_name: Target table name if known
            
        Returns:
            List of column dictionaries with name, data type, etc.
        """
        columns = []
        import re
        
        # Handle column definitions in CREATE TABLE statements
        try:
            # Match CREATE TABLE statements
            create_table_match = re.search(r'CREATE\s+TABLE\s+([\w\."]+)\s*\(([^\)]*)\)', sql_code, re.IGNORECASE | re.DOTALL)
            if create_table_match:
                # Extract table name if not provided
                if not target_table_name:
                    raw_table_name = create_table_match.group(1).strip('"')
                    # Handle schema.table format
                    if '.' in raw_table_name:
                        target_table_name = raw_table_name.split('.')[-1]
                    else:
                        target_table_name = raw_table_name
                    
                # Extract column definitions
                column_defs = create_table_match.group(2).split(',')
                for col_def in column_defs:
                    col_def = col_def.strip()
                    # Skip constraint definitions
                    if re.match(r'\s*(CONSTRAINT|PRIMARY|FOREIGN|CHECK|UNIQUE)', col_def, re.IGNORECASE):
                        continue
                    
                    # Parse column name and type
                    col_match = re.match(r'\s*"?([\w_]+)"?\s+([\w\(\),\s]+)', col_def, re.IGNORECASE)
                    if col_match:
                        col_name = col_match.group(1)
                        data_type = col_match.group(2).strip()
                        
                        # Check for constraints in the column definition
                        is_primary = 'PRIMARY KEY' in col_def.upper()
                        is_foreign = 'REFERENCES' in col_def.upper()
                        
                        # Extract description from column definition if present
                        description = ""
                        desc_match = re.search(r'--\s*(.+?)$', col_def, re.MULTILINE)
                        if desc_match:
                            description = desc_match.group(1).strip()
                        
                        columns.append({
                            "name": col_name,
                            "table": target_table_name,
                            "data_type": data_type,
                            "description": description,
                            "is_primary_key": is_primary,
                            "is_foreign_key": is_foreign
                        })
            
            # Look for columns in CREATE VIEW statements
            view_match = re.search(r'CREATE\s+(?:OR\s+REPLACE\s+)?VIEW\s+([\w\."]+)\s+AS\s+SELECT\s+(.+?)\s+FROM', 
                                  sql_code, re.IGNORECASE | re.DOTALL)
            if view_match and not columns:
                # Extract view name if not provided
                if not target_table_name:
                    raw_view_name = view_match.group(1).strip('"')
                    # Handle schema.view format
                    if '.' in raw_view_name:
                        target_table_name = raw_view_name.split('.')[-1]
                    else:
                        target_table_name = raw_view_name
                
                # Extract column list from SELECT clause
                select_cols = view_match.group(2).strip()
                
                # Split by commas but be careful with functions that might have commas
                in_function = 0
                in_quotes = False
                col_parts = []
                current_part = ""
                
                for char in select_cols:
                    if char == '(' and not in_quotes:
                        in_function += 1
                        current_part += char
                    elif char == ')' and not in_quotes and in_function > 0:
                        in_function -= 1
                        current_part += char
                    elif char == '"' and (len(current_part) == 0 or current_part[-1] != '\\'):
                        in_quotes = not in_quotes
                        current_part += char
                    elif char == ',' and not in_quotes and in_function == 0:
                        col_parts.append(current_part.strip())
                        current_part = ""
                    else:
                        current_part += char
                
                if current_part.strip():
                    col_parts.append(current_part.strip())
                
                # Process each column expression
                for col_expr in col_parts:
                    col_name = None
                    # Handle aliased columns
                    if ' AS ' in col_expr.upper():
                        parts = col_expr.split(' AS ', 1)
                        col_name = parts[1].strip('"')
                    elif re.search(r'"([^"]+)"$', col_expr):
                        # Extract last quoted identifier as column name
                        match = re.search(r'"([^"]+)"$', col_expr)
                        if match:
                            col_name = match.group(1)
                    else:
                        # Try to extract a simple column name
                        col_match = re.search(r'(?:\.|^)([\w_]+)$', col_expr)  # Get last word as column name
                        if col_match:
                            col_name = col_match.group(1)
                        else:
                            # Just use a simplified expression as fallback
                            col_name = col_expr[:20] + "..." if len(col_expr) > 20 else col_expr
                    
                    columns.append({
                        "name": col_name,
                        "table": target_table_name,
                        "data_type": "unknown"  # Type is not specified in CREATE VIEW
                    })
            
            # Look for ALTER TABLE ADD COLUMN statements
            alter_matches = re.finditer(
                r'ALTER\s+TABLE\s+([\w\."]+)\s+ADD\s+(?:COLUMN\s+)?"?([\w_]+)"?\s+([\w\(\),\s]+)', 
                sql_code, re.IGNORECASE)
            
            for match in alter_matches:
                table_name = match.group(1).strip('"')
                # Handle schema.table format
                if '.' in table_name:
                    table_name = table_name.split('.')[-1]
                
                # Only process if this is for our target table or if we don't have columns yet
                if not target_table_name or table_name == target_table_name or not columns:
                    col_name = match.group(2)
                    data_type = match.group(3).strip()
                    
                    columns.append({
                        "name": col_name,
                        "table": table_name if table_name else target_table_name,
                        "data_type": data_type
                    })
        except Exception as e:
            logger.warning(f"Error extracting columns from PostgreSQL: {str(e)}")
        
        return columns