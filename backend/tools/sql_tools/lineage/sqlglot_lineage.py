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
    
    def extract_column_lineage(self, sql_ast: Any, target_table_name: str = None, file_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Extract column-level lineage from SQL AST
        
        Args:
            sql_ast: SQLGlot AST
            target_table_name: Name of the target table (optional)
            file_path: Original file path (optional)
            
        Returns:
            Dictionary with column lineage information
        """
        try:
            # Initialize result
            result = {
                "source_columns": [],
                "target_columns": [],
                "column_relationships": [], 
                "file_path": file_path,
                "metadata": {}
            }
            
            # Log the type of AST we're processing
            logger.debug(f"Extracting column lineage from {type(sql_ast).__name__} AST")
            logger.info(f"Processing SQL AST for column lineage with target table: {target_table_name}")
            
            # Check for CREATE or INSERT statements to determine target columns
            target_table_name = None
            target_table_schema = None
            
            # For CREATE statements, identify the target table
            if isinstance(sql_ast, Create):
                logger.debug("Processing CREATE statement for column lineage")
                
                # Extract target table name
                if not target_table_name:  # Only extract if not already provided
                    target_schema_name = None
                    
                    if hasattr(sql_ast, "this") and sql_ast.this:
                        target_table_name = sql_ast.this
                    elif hasattr(sql_ast, "args") and "this" in sql_ast.args:
                        target_table_name = sql_ast.args["this"]
                    
                    logger.info(f"Raw target table name: {target_table_name}")
                    
                    # Remove schema if present
                    if target_table_name and "." in target_table_name:
                        parts = target_table_name.split(".")
                        target_schema_name = parts[0]
                        target_table_name = parts[-1]  # Use last part to handle multi-part names
                        logger.info(f"Extracted table name {target_table_name} from {parts}")
            
            # Extract columns from CREATE TABLE statements
            if isinstance(sql_ast, Create):
                logger.debug("Processing CREATE TABLE statement for column lineage")
                
                # Look for column definitions in CREATE TABLE statements
                columns_def = []
                if hasattr(sql_ast, 'args') and 'columns' in sql_ast.args:
                    columns_def = sql_ast.args.get("columns", [])
                    logger.info(f"Found {len(columns_def)} columns in CREATE TABLE args")
                
                # Direct debug of structure
                if not columns_def and hasattr(sql_ast, 'args'):
                    logger.debug(f"CREATE TABLE args keys: {list(sql_ast.args.keys())}")
                    if 'expression' in sql_ast.args:
                        logger.debug(f"CREATE TABLE has an expression: {type(sql_ast.args['expression'])}")
                        
                        # If it's a CREATE TABLE AS SELECT, extract columns from the SELECT clause
                        select_expr = sql_ast.args.get('expression')
                        if isinstance(select_expr, Select):
                            logger.info(f"Extracting columns from SELECT in CREATE TABLE AS")
                            expressions = select_expr.args.get('expressions', [])
                            for expr in expressions:
                                col_name = None
                                if hasattr(expr, 'alias') and expr.alias:
                                    col_name = expr.alias
                                elif hasattr(expr, 'args') and 'alias' in expr.args and expr.args['alias']:
                                    col_name = expr.args['alias']
                                elif hasattr(expr, 'name'):
                                    col_name = expr.name
                                elif hasattr(expr, 'args') and 'this' in expr.args:
                                    col_name = expr.args['this']
                                
                                if col_name:
                                    result["target_columns"].append({
                                        "name": col_name,
                                        "table": target_table_name,
                                        "data_type": "unknown"
                                    })
            
            # Fallback: Extract columns directly from SQL text if available
            # For tsql and postgres dialects, always try regex extraction for completeness
            # This ensures we catch all columns, especially for dialects where AST extraction is inconsistent
            if file_path and (len(columns_def) == 0 or 'tsql' in file_path.lower() or 'postgres' in file_path.lower()):
                logger.info("Extracting columns from SQL directly using regex")
                import re
                try:
                    with open(file_path, 'r') as f:
                        sql_text = f.read()
                        
                        # If target table name isn't set, try to extract it from the CREATE TABLE statement
                        if not target_table_name:
                            table_pattern = re.compile(r'CREATE\s+TABLE\s+([^\s\(]+)', re.IGNORECASE)
                            table_match = table_pattern.search(sql_text)
                            if table_match:
                                extracted_name = table_match.group(1).strip('"[]`')
                                logger.info(f"Extracted raw table name: {extracted_name}")
                                # Remove schema if present
                                if '.' in extracted_name:
                                    parts = extracted_name.split('.')
                                    target_table_name = parts[-1]  # Last part is the table name
                                    logger.info(f"Extracted table name {target_table_name} from {parts}")
                                else:
                                    target_table_name = extracted_name
                                logger.info(f"Extracted table name from SQL: {target_table_name}")
                        
                        # Simple regex to extract column definitions
                        create_pattern = re.compile(r'CREATE\s+TABLE\s+[^\(]+(\(([^\)]+)\))', re.IGNORECASE | re.DOTALL)
                        match = create_pattern.search(sql_text)
                        if match:
                            col_defs = match.group(2).strip().split(',')
                            for col_def in col_defs:
                                # Skip if it starts with things like PRIMARY KEY, CONSTRAINT, etc.
                                if re.match(r'\s*(PRIMARY|FOREIGN|UNIQUE|CHECK|CONSTRAINT)', col_def, re.IGNORECASE):
                                    continue
                                # Extract column name and type
                                parts = re.split(r'\s+', col_def.strip(), 1)
                                if parts:
                                    col_name = parts[0].strip('"[]`')
                                    data_type = parts[1].strip() if len(parts) > 1 else "unknown"
                                    is_primary = 'PRIMARY KEY' in col_def.upper()
                                    is_foreign = 'FOREIGN KEY' in col_def.upper() or 'REFERENCES' in col_def.upper()
                                    logger.debug(f"Extracted column {col_name} of type {data_type} from SQL")
                                    result["target_columns"].append({
                                        "name": col_name,
                                        "table": target_table_name,
                                        "data_type": data_type,
                                        "is_primary_key": is_primary,
                                        "is_foreign_key": is_foreign
                                    })
                            
                        # Also check for CREATE TABLE AS SELECT pattern
                        as_pattern = re.compile(r'CREATE\s+TABLE\s+([^\s]+)\s+AS\s+SELECT\s+(.+?)\s+FROM', re.IGNORECASE | re.DOTALL)
                        as_match = as_pattern.search(sql_text)
                        if as_match and not result.get("target_columns"):
                            table_name = as_match.group(1).strip('"[]`')
                            if '.' in table_name:
                                target_table_name = table_name.split('.')[-1]
                            else:
                                target_table_name = table_name
                                
                            logger.info(f"Found CREATE TABLE AS SELECT for table {target_table_name}")
                            
                            # Extract columns from the SELECT clause
                            select_cols = as_match.group(2).strip()
                            col_list = select_cols.split(',')
                            for col_item in col_list:
                                col_item = col_item.strip()
                                # Handle aliased columns
                                if ' AS ' in col_item.upper():
                                    parts = col_item.split(' AS ', 1)
                                    col_name = parts[1].strip('"[]`')
                                else:
                                    # For columns without AS, use the last part after a dot or the full name
                                    if '.' in col_item:
                                        col_name = col_item.split('.')[-1].strip('"[]`')
                                    else:
                                        col_name = col_item.strip('"[]`')
                                
                                logger.debug(f"Extracted column {col_name} from CREATE TABLE AS SELECT")
                                result["target_columns"].append({
                                    "name": col_name,
                                    "table": target_table_name,
                                    "data_type": "unknown"
                                })
                except Exception as e:
                    logger.warning(f"Error extracting columns from SQL text: {str(e)}")
            
            # Process column definitions from AST
            for col_def in columns_def:
                try:
                    col_name = None
                    # Extract column name using different possible structures based on SQLGlot version and dialect
                    if hasattr(col_def, "this"):
                        col_name = col_def.this
                    elif hasattr(col_def, "args") and "this" in col_def.args:
                        col_name = col_def.args.get("this")
                    elif hasattr(col_def, "name"):
                        col_name = col_def.name
                    elif isinstance(col_def, str):
                        col_name = col_def
                    elif hasattr(col_def, "expressions") and len(col_def.expressions) > 0:
                        # Handle T-SQL specific column structure
                        col_name = col_def.expressions[0].name
                    elif hasattr(col_def, "alias"):
                        # Try alias for some dialects
                        col_name = col_def.alias
                    
                    # Strip brackets for T-SQL identifiers
                    if col_name and col_name.startswith('[') and col_name.endswith(']'):
                        col_name = col_name[1:-1]
                        
                    if not col_name:
                        # Debug the column definition structure
                        if hasattr(col_def, 'args'):
                            logger.debug(f"Column def args keys: {list(col_def.args.keys())}")
                        logger.debug(f"Could not extract column name from: {col_def}")
                        continue
                        
                    logger.debug(f"Processing column: {col_name} for table {target_table_name}")
                    
                    # Extract data type
                    data_type = None
                    if hasattr(col_def, "args") and "kind" in col_def.args:
                        data_type = str(col_def.args.get("kind"))
                    elif hasattr(col_def, "args") and "type" in col_def.args:
                        data_type = str(col_def.args.get("type"))
                    elif hasattr(col_def, "type"):
                        data_type = str(col_def.type)
                    elif hasattr(col_def, "expressions") and len(col_def.expressions) > 0 and hasattr(col_def.expressions[0], "args") and "type" in col_def.expressions[0].args:
                        # Handle T-SQL specific data type structure
                        data_type = str(col_def.expressions[0].args.get("type"))
                    
                    # Extract description from comments if available
                    description = None
                    if hasattr(col_def, "args") and "comment" in col_def.args:
                        description = str(col_def.args.get("comment"))
                    
                    # Check for constraints
                    is_primary = False
                    is_foreign = False
                    constraints = None
                    
                    if hasattr(col_def, "args") and "constraints" in col_def.args:
                        constraints = col_def.args.get("constraints", [])
                    
                    if constraints:
                        for constraint in constraints:
                            constraint_type = None
                            if hasattr(constraint, "this"):
                                constraint_type = constraint.this
                            elif hasattr(constraint, "args") and "this" in constraint.args:
                                constraint_type = constraint.args.get("this")
                            elif hasattr(constraint, "kind"):
                                constraint_type = constraint.kind
                            
                            if constraint_type:
                                constraint_type = str(constraint_type).lower()
                                if "primary" in constraint_type or "pk" in constraint_type:
                                    is_primary = True
                                    logger.debug(f"Column {col_name} is a primary key")
                                elif "foreign" in constraint_type or "references" in constraint_type or "fk" in constraint_type:
                                    is_foreign = True
                                    logger.debug(f"Column {col_name} is a foreign key")
                    
                    result["target_columns"].append({
                        "name": col_name,
                        "table": target_table_name,
                        "data_type": data_type,
                        "description": description,
                        "is_primary_key": is_primary,
                        "is_foreign_key": is_foreign
                    })
                except Exception as col_err:
                    logger.warning(f"Error processing column definition: {str(col_err)}")
            
            # Extract business metadata from comments
            if sql_ast and hasattr(sql_ast, 'comments'):
                for comment in sql_ast.comments:
                    # Look for column descriptions in comments
                    # Common formats: -- column_name: description or /* column_name: description */
                    col_desc_match = re.search(r'(\w+)\s*:\s*([^\n,]+)', comment)
                    if col_desc_match:
                        col_name = col_desc_match.group(1)
                        col_desc = col_desc_match.group(2).strip()
                        
                        # Add to existing column or create new one
                        found = False
                        for col in result['target_columns']:
                            if col['name'] == col_name:
                                col['description'] = col_desc
                                found = True
                                break
                        
                        if not found:
                            result['target_columns'].append({
                                'name': col_name,
                                'table': target_table_name,
                                'description': col_desc,
                                'data_type': 'unknown'
                            })
                            
                    # Look for table descriptions in comments
                    table_desc_match = re.search(r'table\s*:\s*([^\n,]+)', comment, re.IGNORECASE)
                    if table_desc_match and target_table_name:
                        table_desc = table_desc_match.group(1).strip()
                        result['metadata']['table_description'] = table_desc
            
            # For SELECT statements, extract column mappings
            if isinstance(sql_ast, Select):
                logger.debug("Processing SELECT statement for column lineage")
                
                # Extract target table from context or infer from file name if possible
                if not target_table_name and file_path:
                    import os
                    file_basename = os.path.basename(file_path)
                    # Remove extension
                    if '.' in file_basename:
                        table_from_file = file_basename.split('.')[0]
                        logger.info(f"Inferred target table {table_from_file} from file name {file_basename}")
                        target_table_name = table_from_file
                        
                # For views and CTEs, also check for alias in FROM clause (common in DBT models)
                if not target_table_name and hasattr(sql_ast, 'args') and 'from' in sql_ast.args:
                    from_clause = sql_ast.args['from']
                    if hasattr(from_clause, 'alias') and from_clause.alias:
                        target_table_name = from_clause.alias
                        logger.info(f"Extracted target table {target_table_name} from FROM clause alias")
                
                # Extract columns from SELECT expressions
                if hasattr(sql_ast, 'args') and 'expressions' in sql_ast.args:
                    expressions = sql_ast.args['expressions']
                    for expr in expressions:
                        col_name = None
                        col_table = None
                        
                        # Try to extract column name from various AST structures
                        if hasattr(expr, 'alias') and expr.alias:
                            col_name = expr.alias
                        elif hasattr(expr, 'args') and 'alias' in expr.args and expr.args['alias']:
                            col_name = expr.args['alias']
                        elif hasattr(expr, 'name'):
                            col_name = expr.name
                        elif hasattr(expr, 'this'):
                            col_name = expr.this
                        elif hasattr(expr, 'args') and 'this' in expr.args:
                            col_name = expr.args['this']
                        
                        # Try to extract table name
                        if hasattr(expr, 'table'):
                            col_table = expr.table
                        elif hasattr(expr, 'args') and 'table' in expr.args:
                            col_table = expr.args['table']
                        
                        if col_name:
                            if target_table_name and not col_table:
                                col_table = target_table_name
                            
                            result["target_columns"].append({
                                "name": col_name,
                                "table": col_table or target_table_name,
                                "data_type": "unknown"
                            })
            
            # For INSERT statements, map source to target columns
            elif isinstance(sql_ast, Insert):
                logger.info("Processing INSERT statement for column mappings")
                target_obj = sql_ast.find(Table)
                if target_obj:
                    target_table_info = self._extract_table_info(target_obj)
                    target_table_name = target_table_info.get("name")
                    
                    # Get columns being inserted into
                    target_column_names = []
                    if hasattr(sql_ast, "args") and "expressions" in sql_ast.args:
                        for col in sql_ast.args["expressions"]:
                            if hasattr(col, "this"):
                                target_column_names.append(col.this)
                            elif hasattr(col, "args") and "this" in col.args:
                                target_column_names.append(col.args["this"])
                    
                    if target_column_names:
                        logger.info(f"Found target columns in INSERT: {target_column_names}")
                    
                    # Find source query
                    source_query = None
                    if hasattr(sql_ast, "args") and "expression" in sql_ast.args:
                        source_query = sql_ast.args["expression"]
                    
                    if isinstance(source_query, Select):
                        logger.info("Processing INSERT...SELECT for column mappings")
                        select_result = self.extract_column_lineage(source_query, target_table_name, file_path)
                        if "source_columns" in select_result:
                            result["source_columns"] = select_result["source_columns"]
                        if "column_relationships" in select_result:
                            result["column_relationships"] = select_result["column_relationships"]
            
            # For CREATE TABLE AS SELECT, extract column mapping
            if isinstance(sql_ast, Create) and target_table_name:
                # If the CREATE has a SELECT, extract column information from it
                select_expr = None
                if hasattr(sql_ast, "args") and "expression" in sql_ast.args:
                    select_expr = sql_ast.args["expression"]
                
                if isinstance(select_expr, Select):
                    # Process the SELECT for source columns
                    select_result = self.extract_column_lineage(select_expr, target_table_name, file_path)
                    if "source_columns" in select_result:
                        result["source_columns"] = select_result["source_columns"]
                    if "column_relationships" in select_result:
                        result["column_relationships"] = select_result["column_relationships"]
                    if "target_columns" in select_result and not result.get("target_columns"):
                        result["target_columns"] = select_result["target_columns"]
                        # Update target table name for all columns
                        for col in result["target_columns"]:
                            col["table"] = target_table_name
            
            # Log results
            logger.info(f"Extracted {len(result.get('target_columns', []))} target columns, {len(result.get('source_columns', []))} source columns, {len(result.get('column_relationships', []))} column relationships")
            
            return result
            
        except Exception as e:
            import traceback
            logger.error(f"Error extracting column lineage: {str(e)}")
            logger.debug(f"Stack trace: {traceback.format_exc()}")
            return {
                "source_columns": [],
                "target_columns": [],
                "column_relationships": [],
                "file_path": file_path,
                "error": str(e)
            }
    
    def _extract_source_tables(self, node: Any, tables: List[Any]) -> None:
        """
        Extract source tables from a SQL AST
        
        Args:
            node: SQLGlot AST node
            tables: List to populate with source tables
        """
        if node is None:
            return
            
        # Special handling for DBT source() macros in SQL comments or string literals
        if hasattr(node, 'comments') and node.comments:
            for comment in node.comments:
                if 'source(' in comment:
                    # Try to extract source reference from comment
                    try:
                        # Pattern: source('schema_name', 'table_name')
                        import re
                        source_match = re.search(r"source\(['\"]([^'\"]+)['\"],\s*['\"]([^'\"]+)['\"]\)", comment)
                        if source_match:
                            schema_name, table_name = source_match.groups()
                            source_table = sqlglot.exp.Table(this=table_name, db=schema_name)
                            source_table.set_source_type('dbt_source')
                            tables.append(source_table)
                    except Exception as e:
                        pass
        
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
    
    def _extract_select_column_mappings(self, select_stmt: Select, result: Dict[str, Any], 
                                  target_table_name: str, target_schema: str = None,
                                  target_column_names: List[str] = None) -> None:
        """
        Extract column mappings from a SELECT statement, establishing relationships between
        source and target columns.
        
        Args:
            select_stmt: The SELECT statement to analyze
            result: Dictionary to populate with column mappings
            target_table_name: Name of the target table
            target_schema: Schema of the target table (optional)
            target_column_names: List of target column names if specified (optional)
        """
        try:
            # Get SELECT expressions (columns)
            columns = []
            if hasattr(select_stmt, 'expressions'):
                columns = select_stmt.expressions
            
            # If we don't have specific target column names, we'll infer them
            # from the SELECT column aliases or expressions
            if not target_column_names:
                target_column_names = []
                for col in columns:
                    # Try to get alias first
                    if hasattr(col, 'alias') and col.alias:
                        target_column_names.append(col.alias)
                    # Fallback to column name
                    else:
                        target_column_names.append(self._extract_column_name(col))
            
            # Process each column expression in the SELECT statement
            for i, col in enumerate(columns):
                # Only process if we have a corresponding target column name
                if i < len(target_column_names):
                    target_column_name = target_column_names[i]
                    
                    # Create target column info
                    target_col_info = {
                        "name": target_column_name,
                        "table": target_table_name,
                        "schema": target_schema,
                        "alias": None,
                        "data_type": None  # We might not know the data type here
                    }
                    
                    # Add to target columns if not already there
                    if target_col_info not in result["target_columns"]:
                        result["target_columns"].append(target_col_info)
                    
                    # Find source column references for this expression
                    source_references = []
                    self._find_column_references(col, source_references)
                    
                    # Add source references to the overall source columns list
                    for src_ref in source_references:
                        if src_ref not in result["source_columns"]:
                            result["source_columns"].append(src_ref)
                        
                        # Create a column relationship
                        relationship = {
                            "source_column": src_ref["column"],
                            "source_table": src_ref["table"],
                            "target_column": target_column_name,
                            "target_table": target_table_name,
                            "relationship_type": "derived_from"
                        }
                        
                        # Add relationship if not already present
                        if relationship not in result["column_relationships"]:
                            result["column_relationships"].append(relationship)
        
        except Exception as e:
            logger.error(f"Error extracting column mappings: {str(e)}")

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