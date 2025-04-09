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
        # DBT config patterns
        self.dbt_config_pattern = re.compile(r'{{\s*config\s*\((.*?)\)\s*}}', re.DOTALL)
        self.dbt_ref_pattern = re.compile(r'{{\s*ref\s*\(\s*[\'"]([^\'"]+)[\'"]\s*\)\s*}}')
        self.dbt_source_pattern = re.compile(r'{{\s*source\s*\(\s*[\'"]([^\'"]+)[\'"]\s*,\s*[\'"]([^\'"]+)[\'"]\s*\)\s*}}')
        self.dbt_macro_pattern = re.compile(r'{{\s*([a-zA-Z0-9_]+)\s*\((.*?)\)\s*}}', re.DOTALL)
        
    def _get_sqlglot_dialect(self) -> Any:
        """Get the SQLGlot dialect for DBT (uses Snowflake as base)"""
        return sqlglot.dialects.Snowflake
    
    def clean_sql(self, sql_code: str) -> str:
        """
        Clean DBT SQL code before parsing, handling Jinja templating
        
        Args:
            sql_code: DBT SQL code to clean
            
        Returns:
            Cleaned SQL code
        """
        # Remove Jinja comments
        sql_code = re.sub(r'{#.*?#}', '', sql_code, flags=re.DOTALL)
        
        # Replace ref() with table names
        # {{ ref('model_name') }} becomes model_name
        sql_code = re.sub(r'{{\s*ref\s*\(\s*[\'"]([^\'"]+)[\'"]\s*\)\s*}}', r'\1', sql_code)
        
        # Replace source() with table names
        # {{ source('source_name', 'table_name') }} becomes source_name__table_name
        sql_code = re.sub(r'{{\s*source\s*\(\s*[\'"]([^\'"]+)[\'"]\s*,\s*[\'"]([^\'"]+)[\'"]\s*\)\s*}}', r'\1__\2', sql_code)
        
        # Replace other Jinja blocks with empty strings
        sql_code = re.sub(r'{%.*?%}', '', sql_code, flags=re.DOTALL)
        
        # Replace remaining Jinja variables with NULL
        sql_code = re.sub(r'{{.*?}}', 'NULL', sql_code, flags=re.DOTALL)
        
        # Remove SQL comments and excessive whitespace
        return super().clean_sql(sql_code)
    
    def extract_dbt_configs(self, sql_code: str) -> Dict[str, Any]:
        """
        Extract DBT configurations from SQL code
        
        Args:
            sql_code: DBT SQL code
            
        Returns:
            Dictionary with extracted configurations
        """
        configs = {}
        
        # Extract config block
        config_match = self.dbt_config_pattern.search(sql_code)
        if config_match:
            config_str = config_match.group(1)
            
            # Try to parse configs
            try:
                # Extract key-value pairs like key="value" or key=value
                key_value_pattern = re.compile(r'([a-zA-Z0-9_]+)\s*=\s*(?:[\'"]([^\'"]*)[\'"]|([a-zA-Z0-9_]+))')
                for match in key_value_pattern.finditer(config_str):
                    key = match.group(1)
                    # Group 2 is quoted value, group 3 is unquoted value
                    value = match.group(2) if match.group(2) is not None else match.group(3)
                    configs[key] = value
            except Exception as e:
                logger.error(f"Error parsing DBT config: {e}")
        
        return configs
    
    def extract_dbt_refs(self, sql_code: str) -> List[str]:
        """
        Extract DBT ref() calls from SQL code
        
        Args:
            sql_code: DBT SQL code
            
        Returns:
            List of referenced model names
        """
        refs = []
        for match in self.dbt_ref_pattern.finditer(sql_code):
            refs.append(match.group(1))
        return refs
    
    def extract_dbt_sources(self, sql_code: str) -> List[Tuple[str, str]]:
        """
        Extract DBT source() calls from SQL code
        
        Args:
            sql_code: DBT SQL code
            
        Returns:
            List of (source_name, table_name) tuples
        """
        sources = []
        for match in self.dbt_source_pattern.finditer(sql_code):
            sources.append((match.group(1), match.group(2)))
        return sources
    
    def extract_target_table(self, sql_code: str, file_path: Optional[str] = None) -> Optional[str]:
        """
        Extract target table name from DBT SQL model
        
        Args:
            sql_code: DBT SQL code
            file_path: Path to the file (optional)
            
        Returns:
            Target table name or None if not found
        """
        # For DBT models, the target table is usually derived from the filename
        if file_path:
            file_name = os.path.basename(file_path)
            # Remove extension
            target_table = os.path.splitext(file_name)[0]
            return target_table
        
        # If no file path, try to extract from SQL AST
        sql_ast = self.parse_sql(self.clean_sql(sql_code))
        if sql_ast and isinstance(sql_ast, Create):
            if hasattr(sql_ast, 'name'):
                target_table = sql_ast.name
                if hasattr(sql_ast, 'db') and sql_ast.db:
                    target_table = f"{sql_ast.db}.{target_table}"
                return target_table
        
        return None
    
    def extract_dependencies(self, sql_code: str, file_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Extract dependencies from DBT SQL code
        
        Args:
            sql_code: DBT SQL code
            file_path: Path to the file (optional)
            
        Returns:
            Dictionary with extracted dependencies
        """
        result = self.get_default_output_format()
        result["file_path"] = file_path
        
        try:
            # Extract DBT-specific references
            refs = self.extract_dbt_refs(sql_code)
            sources = self.extract_dbt_sources(sql_code)
            
            # Extract target table
            target_table = self.extract_target_table(sql_code, file_path)
            result["target_table"] = target_table
            
            # Add ref dependencies
            source_tables = []
            for ref in refs:
                source_tables.append(ref)
            
            # Add source dependencies
            for source_name, table_name in sources:
                source_tables.append(f"{source_name}.{table_name}")
            
            result["source_tables"] = source_tables
            
            # Now try to extract more detailed info using sqlglot
            cleaned_sql = self.clean_sql(sql_code)
            sql_ast = self.parse_sql(cleaned_sql)
            
            if sql_ast:
                # Extract additional table references from the AST
                tables_from_ast = self._extract_tables_from_ast(sql_ast)
                for table in tables_from_ast:
                    if table not in source_tables and table != target_table:
                        source_tables.append(table)
                
                # Extract columns and build dependencies
                columns_dict = self._extract_columns_from_ast(sql_ast)
                result["columns"] = columns_dict
                
                dependencies = []
                for source_table in source_tables:
                    dep = {
                        "source": source_table,
                        "target": target_table,
                        "columns": columns_dict.get(source_table, [])
                    }
                    dependencies.append(dep)
                
                result["dependencies"] = dependencies
            
            return result
            
        except Exception as e:
            error = self.format_error(f"Error extracting dependencies: {str(e)}")
            result["errors"].append(error)
            logger.error(f"Error extracting dependencies from DBT SQL: {e}")
            return result
    
    def extract_lineage(self, sql_code: str, file_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Extract lineage information from DBT SQL code
        
        Args:
            sql_code: DBT SQL code
            file_path: Path to the file (optional)
            
        Returns:
            Dictionary with extracted lineage information
        """
        # Start with the default output format for lineage
        result = {
            "dialect": self.name,
            "file_path": file_path,
            "file_name": os.path.basename(file_path) if file_path else None,
            "target_table": None,
            "source_tables": [],
            "column_level_lineage": {},
            "errors": []
        }
        
        try:
            # Extract dependencies first
            deps = self.extract_dependencies(sql_code, file_path)
            
            # Set target and source tables
            result["target_table"] = deps["target_table"]
            result["source_tables"] = deps["source_tables"]
            
            # Try to extract column-level lineage
            cleaned_sql = self.clean_sql(sql_code)
            sql_ast = self.parse_sql(cleaned_sql)
            
            if sql_ast:
                column_lineage = self._extract_column_lineage_from_ast(sql_ast, result["target_table"], result["source_tables"])
                result["column_level_lineage"] = column_lineage
            
            return result
            
        except Exception as e:
            error = self.format_error(f"Error extracting lineage: {str(e)}")
            result["errors"].append(error)
            logger.error(f"Error extracting lineage from DBT SQL: {e}")
            return result
    
    def _extract_tables_from_ast(self, sql_ast) -> List[str]:
        """
        Extract table references from SQL AST
        
        Args:
            sql_ast: SQL AST
            
        Returns:
            List of table references
        """
        tables = []
        
        def extract_tables_recursive(expr):
            if isinstance(expr, Table):
                table_name = expr.name
                if hasattr(expr, 'db') and expr.db:
                    table_name = f"{expr.db}.{table_name}"
                tables.append(table_name)
            
            # Recursively process child expressions
            if hasattr(expr, 'args'):
                for arg_name, arg_value in expr.args.items():
                    if arg_value:
                        if isinstance(arg_value, list):
                            for item in arg_value:
                                extract_tables_recursive(item)
                        else:
                            extract_tables_recursive(arg_value)
        
        extract_tables_recursive(sql_ast)
        return list(set(tables))
    
    def _extract_columns_from_ast(self, sql_ast) -> Dict[str, List[str]]:
        """
        Extract columns by table from SQL AST
        
        Args:
            sql_ast: SQL AST
            
        Returns:
            Dictionary of {table_name: [column_names]}
        """
        columns = {}
        
        def extract_columns_recursive(expr, current_table=None):
            if isinstance(expr, Table):
                table_name = expr.name
                if hasattr(expr, 'db') and expr.db:
                    table_name = f"{expr.db}.{table_name}"
                
                if table_name not in columns:
                    columns[table_name] = []
                
                return table_name
            
            elif isinstance(expr, Column):
                col_name = expr.name
                if current_table and col_name not in columns.get(current_table, []):
                    if current_table in columns:
                        columns[current_table].append(col_name)
            
            # Recursively process child expressions
            current_table_context = current_table
            if hasattr(expr, 'args'):
                for arg_name, arg_value in expr.args.items():
                    if arg_value:
                        if isinstance(arg_value, Table):
                            current_table_context = extract_columns_recursive(arg_value)
                        elif isinstance(arg_value, list):
                            for item in arg_value:
                                extract_columns_recursive(item, current_table_context)
                        else:
                            extract_columns_recursive(arg_value, current_table_context)
            
            return current_table_context
        
        extract_columns_recursive(sql_ast)
        return columns
    
    def _extract_column_lineage_from_ast(self, sql_ast, target_table: str, source_tables: List[str]) -> Dict[str, List[Dict[str, str]]]:
        """
        Extract column-level lineage from SQL AST
        
        Args:
            sql_ast: SQL AST
            target_table: Target table name
            source_tables: List of source table names
            
        Returns:
            Dictionary of {target_column: [{"table": source_table, "column": source_column}, ...]}
        """
        column_lineage = {}
        
        # Simple implementation - extract target columns from SELECT clause
        if isinstance(sql_ast, Select):
            if hasattr(sql_ast, 'args') and 'expressions' in sql_ast.args:
                select_expressions = sql_ast.args['expressions']
                for expr in select_expressions:
                    # Get target column name (either alias or column name)
                    target_column = None
                    if hasattr(expr, 'alias'):
                        target_column = expr.alias
                    elif isinstance(expr, Column):
                        target_column = expr.name
                    
                    if target_column:
                        # Find source columns referenced in this expression
                        source_columns = []
                        
                        def find_columns(expr, current_table=None):
                            if isinstance(expr, Table):
                                table_name = expr.name
                                if hasattr(expr, 'db') and expr.db:
                                    table_name = f"{expr.db}.{table_name}"
                                return table_name
                            
                            elif isinstance(expr, Column):
                                col_name = expr.name
                                table = current_table
                                
                                # If table matches one of our source tables, add to lineage
                                if table and table in source_tables:
                                    source_columns.append({"table": table, "column": col_name})
                            
                            # Recursively process child expressions
                            current_table_context = current_table
                            if hasattr(expr, 'args'):
                                for arg_name, arg_value in expr.args.items():
                                    if arg_value:
                                        if isinstance(arg_value, Table):
                                            current_table_context = find_columns(arg_value)
                                        elif isinstance(arg_value, list):
                                            for item in arg_value:
                                                find_columns(item, current_table_context)
                                        else:
                                            find_columns(arg_value, current_table_context)
                            
                            return current_table_context
                        
                        # Process the expression to find source columns
                        find_columns(expr)
                        
                        # Add to column lineage if source columns were found
                        if source_columns:
                            column_lineage[target_column] = source_columns
        
        return column_lineage 