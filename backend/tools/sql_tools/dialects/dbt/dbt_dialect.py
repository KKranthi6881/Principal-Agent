"""
DBT SQL Dialect Parser

This module provides DBT-specific SQL parsing and analysis.
"""

import os
import re
import json
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

class DBTDialect(BaseSQLDialect):
    """
    DBT-specific SQL dialect parser.
    Handles DBT-specific syntax including macros and ref/source functions.
    """
    
    def __init__(self):
        """Initialize the DBT dialect parser"""
        super().__init__("dbt")
    
    def _get_sqlglot_dialect(self) -> str:
        """
        Get the SQLGlot dialect name for DBT (uses postgres as base)
        
        Returns:
            The SQLGlot dialect name
        """
        return "postgres"  # DBT is typically based on the target warehouse dialect, default to Postgres
    
    def parse_sql(self, sql_code: str) -> Tuple[Any, List[str]]:
        """
        Parse DBT SQL code using SQLGlot
        
        Args:
            sql_code: SQL code to parse
            
        Returns:
            Tuple of (AST, errors)
        """
        errors = []
        ast = None
        
        try:
            # Handle DBT-specific syntax before parsing
            cleaned_sql = self._preprocess_sql(sql_code)
            
            # Parse with SQLGlot
            ast = parse_one(cleaned_sql, dialect=self._get_sqlglot_dialect())
        except ParseError as e:
            errors.append(f"Parse error: {str(e)}")
        except Exception as e:
            errors.append(f"Error parsing SQL: {str(e)}")
        
        return ast, errors
    
    def _preprocess_sql(self, sql_code: str) -> str:
        """
        Preprocess DBT-specific syntax like Jinja templates
        
        Args:
            sql_code: SQL code to preprocess
            
        Returns:
            Preprocessed SQL code
        """
        # Skip if not SQL content
        if not self._looks_like_sql(sql_code):
            return ""
            
        # Remove Jinja comments
        sql_code = re.sub(r'{#.*?#}', '', sql_code, flags=re.DOTALL)
        
        # Handle DBT jinja blocks (config, docs, etc.)
        sql_code = re.sub(r'{{\s*config\s*\(.*?\)\s*}}', '', sql_code, flags=re.DOTALL)
        sql_code = re.sub(r'{{\s*doc\s*\(.*?\)\s*}}', '', sql_code, flags=re.DOTALL)
        
        # Replace DBT refs with table names
        def replace_ref(match):
            ref_name = match.group(1).strip("' \"")
            return f"table_{ref_name}"
        
        sql_code = re.sub(r'{{\s*ref\s*\(\s*([^)]+)\s*\)\s*}}', replace_ref, sql_code)
        
        # Replace DBT sources with table names
        def replace_source(match):
            source_parts = match.group(1).split(',')
            if len(source_parts) >= 2:
                source_name = source_parts[0].strip("' \"")
                table_name = source_parts[1].strip("' \"")
                return f"src_{source_name}_{table_name}"
            return "source_table"
        
        sql_code = re.sub(r'{{\s*source\s*\(\s*([^)]+)\s*\)\s*}}', replace_source, sql_code)
        
        # Replace other Jinja expressions with placeholders
        sql_code = re.sub(r'{{\s*([^}]+)\s*}}', 'NULL', sql_code)
        
        # Replace Jinja control structures with SQL comments
        sql_code = re.sub(r'{%\s*if\s*.*?%}', '/* if condition */', sql_code, flags=re.DOTALL)
        sql_code = re.sub(r'{%\s*else\s*.*?%}', '/* else condition */', sql_code, flags=re.DOTALL)
        sql_code = re.sub(r'{%\s*endif\s*.*?%}', '/* endif */', sql_code, flags=re.DOTALL)
        sql_code = re.sub(r'{%\s*for\s*.*?%}', '/* for loop */', sql_code, flags=re.DOTALL)
        sql_code = re.sub(r'{%\s*endfor\s*.*?%}', '/* endfor */', sql_code, flags=re.DOTALL)
        
        # Replace macros with SQL comments
        sql_code = re.sub(r'{{\s*([a-zA-Z0-9_]+)\((.*?)\)\s*}}', r'/* macro \1 */', sql_code, flags=re.DOTALL)
        
        return sql_code
    
    def _looks_like_sql(self, text: str) -> bool:
        """
        Check if the text looks like SQL code and not a YML file or markdown
        
        Args:
            text: Text to check
            
        Returns:
            True if it looks like SQL, False otherwise
        """
        # Skip empty text
        if not text or not text.strip():
            return False
            
        # Check if it starts with YAML markers
        if text.lstrip().startswith('version:') or text.lstrip().startswith('---'):
            return False
            
        # Check if it's markdown
        if text.lstrip().startswith('#') or text.lstrip().startswith('##'):
            return False
        
        # Look for common SQL keywords
        sql_keywords = ['select', 'from', 'where', 'with', 'insert', 'update', 'delete', 'create', 'drop']
        text_lower = text.lower()
        for keyword in sql_keywords:
            if re.search(rf'\b{keyword}\b', text_lower):
                return True
        
        return False
    
    def extract_dependencies(self, sql_code: str, file_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Extract table dependencies from DBT SQL code
        
        Args:
            sql_code: SQL code to analyze
            file_path: Path to the file (optional)
            
        Returns:
            Dictionary with dependency information
        """
        # Initialize dependency result
        result = {
            "source_tables": [],
            "target_table": None,
            "errors": [],
            "file_path": file_path
        }
        
        # Skip non-SQL files like YML or MD
        if not self._looks_like_sql(sql_code):
            return result
            
        # Extract DBT refs and sources directly from the Jinja syntax
        refs = self._extract_refs(sql_code)
        sources = self._extract_sources(sql_code)
        
        # Combine refs and sources as source tables
        source_tables = refs + sources
        
        # Try to extract target table from model name or file path
        target_table = self._extract_model_name(sql_code, file_path)
        if target_table:
            logger.info(f"Extracted target table from DBT model: {target_table}")
        
        # Add extracted dependencies to result
        result["source_tables"] = source_tables
        result["target_table"] = target_table
        
        # Try to parse the SQL code with SQLGlot for additional dependencies
        cleaned_sql = self._preprocess_sql(sql_code)
        if cleaned_sql:
            ast, errors = self.parse_sql(cleaned_sql)
            if errors:
                result["errors"].extend(errors)
            
            if ast:
                # Extract tables from parsed SQL
                parsed_target, parsed_sources = self._extract_tables_from_ast(ast)
                
                # If we couldn't extract the target table earlier, use the parsed one
                if not result["target_table"] and parsed_target:
                    result["target_table"] = parsed_target
                    logger.info(f"Using parsed target table: {parsed_target}")
                
                # Add any additional source tables found in the SQL
                for src in parsed_sources:
                    if src not in result["source_tables"]:
                        result["source_tables"].append(src)
        
        return result
    
    def _extract_refs(self, sql_code: str) -> List[str]:
        """
        Extract DBT ref() dependencies
        
        Args:
            sql_code: SQL code containing DBT refs
            
        Returns:
            List of table names referenced with ref()
        """
        refs = []
        
        # Match ref('table_name') or ref("table_name") patterns
        ref_pattern = r'{{\s*ref\s*\(\s*[\'"]([^\'"]+)[\'"]\s*\)\s*}}'
        matches = re.findall(ref_pattern, sql_code)
        
        # Match ref(table_name) pattern (without quotes)
        ref_pattern_no_quotes = r'{{\s*ref\s*\(\s*([a-zA-Z0-9_]+)\s*\)\s*}}'
        matches_no_quotes = re.findall(ref_pattern_no_quotes, sql_code)
        
        # Combine both results
        refs.extend(matches)
        refs.extend(matches_no_quotes)
        
        # Log what we found to help with debugging
        if refs:
            logger.info(f"Found DBT refs: {refs}")
        
        return refs
    
    def _extract_sources(self, sql_code: str) -> List[str]:
        """
        Extract DBT source() dependencies
        
        Args:
            sql_code: SQL code containing DBT sources
            
        Returns:
            List of table names referenced with source()
        """
        sources = []
        
        # Match source('schema_name', 'table_name') patterns
        source_pattern = r'{{\s*source\s*\(\s*[\'"]([^\'"]+)[\'"]\s*,\s*[\'"]([^\'"]+)[\'"]\s*\)\s*}}'
        matches = re.findall(source_pattern, sql_code)
        
        # Format as schema.table
        for schema, table in matches:
            sources.append(f"{schema}.{table}")
        
        # Log what we found to help with debugging
        if sources:
            logger.info(f"Found DBT sources: {sources}")
        
        return sources
    
    def _extract_model_name(self, sql_code: str, file_path: Optional[str] = None) -> Optional[str]:
        """
        Extract the DBT model name from file path or code
        
        Args:
            sql_code: SQL code of the DBT model
            file_path: Path to the SQL file
            
        Returns:
            Model name if found, otherwise None
        """
        # Try to extract from file path first
        if file_path:
            # Get the file name without extension
            file_name = os.path.basename(file_path)
            if file_name.endswith('.sql'):
                return file_name[:-4]  # Remove .sql extension
        
        # Try to extract from model configuration
        config_pattern = r'{{\s*config\s*\(\s*.*?[\'"](alias|materialized)[\'"]\s*:\s*[\'"]([^\'"]+)[\'"].*?\)\s*}}'
        matches = re.findall(config_pattern, sql_code)
        for config_type, value in matches:
            if config_type == 'alias':
                return value
        
        # Final fallback: try to get it from the first SELECT statement
        if file_path:
            return os.path.basename(file_path).split('.')[0]
        
        return None
    
    def _extract_tables_from_ast(self, ast: Any) -> Tuple[Optional[str], List[str]]:
        """
        Extract target and source tables from a parsed SQL AST
        
        Args:
            ast: SQLGlot AST
            
        Returns:
            Tuple of (target_table, source_tables)
        """
        target_table = None
        source_tables = set()
        
        # Extract target table from CREATE or INSERT statements
        if isinstance(ast, Create):
            table_ref = ast.find(Table)
            if table_ref:
                target_table = self._extract_table_name(table_ref)
        
        # Extract source tables by traversing the AST
        def extract_tables(node):
            if node is None:
                return
            
            # If it's a table reference, add it to source tables
            if isinstance(node, Table):
                table_name = self._extract_table_name(node)
                if table_name and table_name != target_table:
                    source_tables.add(table_name)
            
            # Process child nodes
            if hasattr(node, 'args'):
                for key, value in node.args.items():
                    if isinstance(value, list):
                        for item in value:
                            extract_tables(item)
                    else:
                        extract_tables(value)
        
        # Start extraction
        extract_tables(ast)
        
        return target_table, list(source_tables)
    
    def _extract_table_name(self, table_node: Table) -> Optional[str]:
        """
        Extract table name from a SQLGlot Table node
        
        Args:
            table_node: SQLGlot Table node
            
        Returns:
            Table name as string
        """
        try:
            # Extract from direct attributes
            if hasattr(table_node, 'name'):
                table_name = table_node.name
                if hasattr(table_node, 'db') and table_node.db:
                    return f"{table_node.db}.{table_name}"
                return table_name
            
            # Extract from args
            if hasattr(table_node, 'args'):
                if 'this' in table_node.args:
                    table_name = table_node.args['this']
                    db = table_node.args.get('db')
                    if db:
                        return f"{db}.{table_name}"
                    return table_name
            
            # Extract from string representation
            table_str = str(table_node)
            if '.' in table_str:
                parts = table_str.split('.')
                return f"{parts[-2]}.{parts[-1]}"
            return table_str
            
        except Exception as e:
            logger.error(f"Error extracting table name: {str(e)}")
            return None
    
    def extract_lineage(self, sql_code: str, file_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Extract column-level lineage from DBT SQL code
        
        Args:
            sql_code: SQL code to analyze
            file_path: Path to the file (optional)
            
        Returns:
            Dictionary with lineage information
        """
        # Initialize lineage result
        result = {
            "target_table": None,
            "source_tables": [],
            "column_level_lineage": {},
            "errors": [],
            "file_path": file_path
        }
        
        # Skip non-SQL files like YML or MD
        if not self._looks_like_sql(sql_code):
            return result
        
        # Extract table-level dependencies
        deps = self.extract_dependencies(sql_code, file_path)
        result["target_table"] = deps["target_table"]
        result["source_tables"] = deps["source_tables"]
        result["errors"] = deps["errors"]
        
        # Try to preprocess and parse the SQL
        cleaned_sql = self._preprocess_sql(sql_code)
        if not cleaned_sql:
            return result
            
        ast, errors = self.parse_sql(cleaned_sql)
        if errors:
            result["errors"].extend(errors)
        
        if not ast:
            return result
        
        # Extract column mappings
        try:
            # Find the main SELECT statement
            select_node = None
            if isinstance(ast, Create) and hasattr(ast, 'args') and 'expression' in ast.args:
                select_node = ast.args['expression']
            elif isinstance(ast, Select):
                select_node = ast
            
            if select_node and hasattr(select_node, 'args') and 'expressions' in select_node.args:
                column_mappings = {}
                
                # Process each column expression
                for expr in select_node.args['expressions']:
                    # Get target column name
                    target_column = None
                    if hasattr(expr, 'alias'):
                        target_column = expr.alias
                    elif hasattr(expr, 'args') and 'alias' in expr.args:
                        target_column = expr.args['alias']
                    elif isinstance(expr, Column):
                        if hasattr(expr, 'name'):
                            target_column = expr.name
                        elif hasattr(expr, 'args') and 'this' in expr.args:
                            target_column = expr.args['this']
                    
                    if not target_column:
                        continue
                    
                    # Find source columns
                    source_columns = []
                    self._find_source_columns(expr, source_columns)
                    
                    if source_columns:
                        column_mappings[target_column] = source_columns
                
                result["column_level_lineage"] = column_mappings
        except Exception as e:
            result["errors"].append(f"Error extracting column lineage: {str(e)}")
        
        return result
    
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
            
            # Extract column name
            if hasattr(node, 'name'):
                column_name = node.name
            elif hasattr(node, 'args') and 'this' in node.args:
                column_name = node.args['this']
            
            # Extract table name
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
        
        # Process child nodes
        if hasattr(node, 'args'):
            for key, value in node.args.items():
                if isinstance(value, list):
                    for item in value:
                        self._find_source_columns(item, columns)
                else:
                    self._find_source_columns(value, columns) 