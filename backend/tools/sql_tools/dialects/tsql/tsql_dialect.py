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
    
    def parse_sql(self, sql_code: str, file_path: str = None) -> Tuple[Any, List[str]]:
        """
        Parse T-SQL code using SQLGlot
        
        Args:
            sql_code: SQL code to parse
            file_path: Optional path to the file being parsed (for better error reporting)
            
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
            
            # If parsing succeeded but we have a file path, log it for debugging
            if file_path:
                logger.debug(f"Successfully parsed {file_path} with T-SQL dialect")
                
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
    
    def _parse_tsql(self, sql_code: str) -> Any:
        """
        Parse T-SQL code using basic pattern matching
        
        Args:
            sql_code: T-SQL code to parse
            
        Returns:
            Simplified AST-like structure
        """
        # This is a placeholder for future implementation
        # For now, it just extracts tables - this could be enhanced
        # to extract more information in the future
        tables = self._extract_tables_from_sql(sql_code)
        
        return {
            "type": "parsed_tsql",
            "tables": tables
        }
    
    def extract_lineage(self, sql_code: str, file_path: str = None) -> Dict[str, Any]:
        """
        Extract column-level lineage from T-SQL code
        
        Args:
            sql_code: SQL code to analyze
            file_path: Path to the file (optional)
            
        Returns:
            Dictionary with lineage information
        """
        # Initialize return data structure
        result = {
            "table_lineage": {
                "target_table": None,
                "source_tables": []
            },
            "column_lineage": {
                "target_columns": [],
                "column_relationships": []
            },
            "errors": []
        }
        
        # Try to infer target table from file path if not explicitly set
        target_table_name = None
        if file_path:
            # Extract file name without extension
            file_name = os.path.basename(file_path)
            target_table_name = os.path.splitext(file_name)[0]
            logger.info(f"Inferred target table {target_table_name} from file path {file_path}")
            
            # Set the target table in the result
            result["table_lineage"]["target_table"] = target_table_name
        
        try:
            # Parse SQL using SQLGlot
            ast, errors = self.parse_sql(sql_code, file_path)
            
            # Handle parsing errors
            if errors:
                for error in errors:
                    result["errors"].append(error)
            
            # Extract source tables and columns regardless of parsing success
            source_tables = set()
            
            # If we successfully parsed with SQLGlot, use AST for extraction
            if ast:
                # Extract tables from the AST
                self._extract_table_references(ast, source_tables)
                
                # If it's a SELECT query, try to extract column lineage
                if isinstance(ast, Select):
                    # Build a dictionary to store source columns for each target column
                    column_lineage = {}
                    
                    # Extract column-level lineage
                    self._extract_column_lineage(ast, column_lineage)
                    
                    # Convert the column lineage to the expected format
                    for target_col, source_cols in column_lineage.items():
                        for source_col in source_cols:
                            # Only add relationships where we have both source table and column
                            if source_col.get("table") and source_col.get("column"):
                                result["column_lineage"]["column_relationships"].append({
                                    "source_table": source_col["table"],
                                    "source_column": source_col["column"],
                                    "target_table": target_table_name,
                                    "target_column": target_col,
                                    "relationship_type": "projection"
                                })
            else:
                # Fallback to regex-based extraction if parsing failed
                tables = self._extract_tables_from_sql(sql_code)
                for table in tables:
                    # Skip target table
                    if table == target_table_name:
                        continue
                    source_tables.add(table)
            
            # Update source tables in the result
            result["table_lineage"]["source_tables"] = list(source_tables)
            
            # Extract target columns
            target_columns = self._extract_columns_from_sql(sql_code, target_table_name)
            if target_columns:
                result["column_lineage"]["target_columns"] = target_columns
            
            # If we have source tables but no column relationships, create simple relationships
            # This is a fallback for when we couldn't extract detailed column lineage
            if source_tables and target_columns and not result["column_lineage"]["column_relationships"]:
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
            error_msg = f"Error extracting lineage: {str(e)}"
            result["errors"].append(error_msg)
            logger.error(error_msg)
        
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
    
    def _extract_tables_from_sql(self, sql_code: str) -> List[str]:
        """
        Extract tables from SQL code using regex-based parsing
        
        Args:
            sql_code: SQL code to extract tables from
            
        Returns:
            List of tables with their schema information
        """
        tables = []
        
        # Common patterns for T-SQL table references
        import re
        
        # Pattern 1: FROM/JOIN table_name (or schema.table_name)
        # This captures table names in FROM clauses and JOIN statements
        pattern1 = r'\b(FROM|JOIN)\s+(\[?([\w\-\_]+)\]?\.)?\[?([\w\-\_]+)\]?'
        
        # Find all matches for pattern 1
        for match in re.finditer(pattern1, sql_code, re.IGNORECASE):
            schema_name = match.group(3)
            table_name = match.group(4)
            if table_name:
                # Create a table entry
                table_entry = {
                    "name": table_name,
                    "schema": schema_name
                }
                # Check if we already have this table
                if table_entry not in tables:
                    # Create fully qualified table name
                    if schema_name:
                        qualified_name = f"{schema_name}.{table_name}"
                    else:
                        qualified_name = table_name
                    
                    if qualified_name not in tables:
                        tables.append(qualified_name)
        
        # Pattern 2: CREATE TABLE table_name
        pattern2 = r'\bCREATE\s+TABLE\s+(\[?([\w\-\_]+)\]?\.)?\[?([\w\-\_]+)\]?'
        
        # Find all matches for pattern 2
        for match in re.finditer(pattern2, sql_code, re.IGNORECASE):
            schema_name = match.group(2)
            table_name = match.group(3)
            if table_name:
                # Create a table entry
                table_entry = {
                    "name": table_name,
                    "schema": schema_name
                }
                # Check if we already have this table
                if table_entry not in tables:
                    # Create fully qualified table name
                    if schema_name:
                        qualified_name = f"{schema_name}.{table_name}"
                    else:
                        qualified_name = table_name
                    
                    if qualified_name not in tables:
                        tables.append(qualified_name)
        
        # Pattern 3: INSERT INTO table_name
        pattern3 = r'\bINSERT\s+INTO\s+(\[?([\w\-\_]+)\]?\.)?\[?([\w\-\_]+)\]?'
        
        # Find all matches for pattern 3
        for match in re.finditer(pattern3, sql_code, re.IGNORECASE):
            schema_name = match.group(2)
            table_name = match.group(3)
            if table_name:
                # Create a table entry
                table_entry = {
                    "name": table_name,
                    "schema": schema_name
                }
                # Check if we already have this table
                if table_entry not in tables:
                    # Create fully qualified table name
                    if schema_name:
                        qualified_name = f"{schema_name}.{table_name}"
                    else:
                        qualified_name = table_name
                    
                    if qualified_name not in tables:
                        tables.append(qualified_name)
        
        return tables
        
    def _extract_columns_from_sql(self, sql_code: str, target_table_name: str = None) -> List[Dict[str, Any]]:
        """
        Extract columns from SQL code using regex-based parsing for T-SQL specific syntax
        
        Args:
            sql_code: SQL code to extract columns from
            target_table_name: Target table name if known
            
        Returns:
            List of column dictionaries with name, data type, etc.
        """
        # Print out what we're trying to extract (debugging)
        if target_table_name:
            logger.debug(f"Extracting columns for table: {target_table_name}")
        columns = []
        import re
        
        # Handle column definitions in CREATE TABLE statements
        try:
            # Match CREATE TABLE statements
            create_table_match = re.search(r'CREATE\s+TABLE\s+(\[?[\w\.]+\]?)\s*\(([^\)]*)\)', sql_code, re.IGNORECASE | re.DOTALL)
            if create_table_match:
                # Extract table name if not provided
                if not target_table_name:
                    raw_table_name = create_table_match.group(1).strip('[]')
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
                    col_match = re.match(r'\s*\[?([\w_]+)\]?\s+([\w\(\),]+)', col_def, re.IGNORECASE)
                    if col_match:
                        col_name = col_match.group(1)
                        data_type = col_match.group(2)
                        
                        # Check for constraints in the column definition
                        is_primary = 'PRIMARY KEY' in col_def.upper()
                        is_foreign = 'FOREIGN KEY' in col_def.upper() or 'REFERENCES' in col_def.upper()
                        
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
                
            # Also look for ALTER TABLE ADD COLUMN statements
            alter_table_matches = re.finditer(r'ALTER\s+TABLE\s+(\[?[\w\.]+\]?)\s+ADD\s+(\[?[\w_]+\]?\s+[\w\(\),]+)', sql_code, re.IGNORECASE)
            for match in alter_table_matches:
                table_name = match.group(1).strip('[]')
                # Handle schema.table format
                if '.' in table_name:
                    table_name = table_name.split('.')[-1]
                    
                # Only process if this is for our target table
                if not target_table_name or table_name == target_table_name:
                    col_def = match.group(2)
                    col_match = re.match(r'\s*\[?([\w_]+)\]?\s+([\w\(\),]+)', col_def, re.IGNORECASE)
                    if col_match:
                        col_name = col_match.group(1)
                        data_type = col_match.group(2)
                        
                        columns.append({
                            "name": col_name,
                            "table": table_name,
                            "data_type": data_type,
                            "description": ""
                        })
            
            # First look for SELECT statements, which are common in lineage extraction
            # This handles both SELECT INTO and CREATE TABLE AS SELECT
            select_match = re.search(r'(?:SELECT|AS\s+SELECT)\s+([\s\S]+?)(?:INTO|FROM|;)', sql_code, re.IGNORECASE)
            if select_match and (not columns or len(columns) == 0):
                # Extract column list
                column_list = select_match.group(1)
                # Split by commas but be careful with function calls that might have commas
                # This is a simplified approach and might not work for all cases
                in_function = 0
                col_parts = []
                current_part = ""
                
                for char in column_list:
                    if char == '(' and not in_function:
                        in_function += 1
                        current_part += char
                    elif char == ')' and in_function:
                        in_function -= 1
                        current_part += char
                    elif char == ',' and not in_function:
                        col_parts.append(current_part.strip())
                        current_part = ""
                    else:
                        current_part += char
                        
                if current_part.strip():
                    col_parts.append(current_part.strip())
                
                # Process each column expression
                for col_expr in col_parts:
                    # Handle aliased columns
                    if ' AS ' in col_expr.upper():
                        parts = col_expr.split(' AS ', 1)
                        col_name = parts[1].strip('[]').strip('"').strip()
                    else:
                        # Try to extract a column name - look for table.column pattern
                        col_match = re.search(r'(?:[\w_]+\.)?([\w_]+)$', col_expr.strip())
                        if col_match:
                            col_name = col_match.group(1).strip('[]').strip('"').strip()
                        else:
                            # Just use the whole expression as a fallback
                            col_name = col_expr.strip()
                    
                    # Create a column entry
                    columns.append({
                        "name": col_name,
                        "table": target_table_name,
                        "data_type": None,  # We don't have type info from SELECT statements
                        "description": ""
                    })
                    
        except Exception as e:
            logger.warning(f"Error extracting columns from T-SQL: {str(e)}")
            
        return columns
            
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
    
    def extract_dependencies(self, sql_code: str, file_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Extract dependencies from SQL code
        
        Args:
            sql_code: SQL code to analyze
            file_path: Path to the file (optional)
            
        Returns:
            Dictionary with extracted dependencies
        """
        result = {
            "dependencies": [],
            "errors": []
        }
        
        try:
            # Parse the SQL code
            ast, errors = self.parse_sql(sql_code, file_path)
            if errors:
                result["errors"].extend(errors)
                return result
                
            if not ast:
                result["errors"].append("Failed to parse SQL code")
                return result
            
            # Extract table references from the AST
            source_tables = set()
            self._extract_table_references(ast, source_tables)
            
            # Format dependencies as table references
            for table in source_tables:
                result["dependencies"].append({
                    "type": "table",
                    "name": table
                })
                
        except Exception as e:
            result["errors"].append(str(e))
            
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