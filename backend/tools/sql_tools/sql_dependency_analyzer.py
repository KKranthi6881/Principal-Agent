"""
SQL Dependency Analyzer

This module analyzes SQL code to extract table dependencies.
It supports multiple SQL dialects including Snowflake, Redshift, 
PostgreSQL, MySQL, Azure SQL and dbt syntax.
"""

import os
import logging
from typing import Dict, List, Set, Tuple, Optional, Any
import sqlglot
from sqlglot import parse_one, ParseError
from sqlglot.expressions import Select, Insert, Update, Delete, Table, Column, Subquery
import networkx as nx

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter('%(levelname)s - %(name)s - %(message)s'))
logger.addHandler(handler)

# SQL dialects mapping
DIALECT_MAP = {
    "snowflake": sqlglot.dialects.Snowflake,
    "redshift": sqlglot.dialects.Redshift,
    "postgresql": sqlglot.dialects.Postgres,
    "postgres": sqlglot.dialects.Postgres,
    "mysql": sqlglot.dialects.MySQL,
    "azuresql": sqlglot.dialects.TSQL,
    "tsql": sqlglot.dialects.TSQL,
    "mssql": sqlglot.dialects.TSQL,
    "dbt": sqlglot.dialects.Snowflake,  # Default to snowflake for dbt but can be overridden
}


class SQLDependencyAnalyzer:
    """
    Analyzes SQL code to extract table and column-level dependencies
    """
    
    def __init__(self, dialect: str = "snowflake"):
        """
        Initialize the analyzer
        
        Args:
            dialect: SQL dialect to use for parsing (snowflake, redshift, postgres, etc.)
        """
        self.dialect = dialect.lower()
        self.dialect_class = DIALECT_MAP.get(self.dialect, sqlglot.dialects.Snowflake)
        self.dependency_graph = nx.DiGraph()
        
    def parse_sql(self, sql_code: str) -> Any:
        """
        Parse SQL code into an AST
        
        Args:
            sql_code: SQL code to parse
            
        Returns:
            Parsed SQL AST
        """
        try:
            return parse_one(sql_code, read=self.dialect_class)
        except ParseError as e:
            logger.error(f"Error parsing SQL: {e}")
            # Try with a more forgiving parser for dbt files
            if self.dialect == "dbt":
                try:
                    # Remove Jinja templating for basic parsing
                    clean_sql = self._clean_dbt_sql(sql_code)
                    return parse_one(clean_sql, read=self.dialect_class)
                except ParseError as inner_e:
                    logger.error(f"Error parsing cleaned dbt SQL: {inner_e}")
            return None
    
    def _clean_dbt_sql(self, sql_code: str) -> str:
        """
        Clean dbt SQL by removing Jinja templates for basic parsing
        
        Args:
            sql_code: dbt SQL code
            
        Returns:
            Cleaned SQL code
        """
        # Simple Jinja removal (not comprehensive)
        import re
        # Remove Jinja comments
        sql_code = re.sub(r'{#.*?#}', '', sql_code, flags=re.DOTALL)
        # Replace Jinja blocks with empty strings
        sql_code = re.sub(r'{%.*?%}', '', sql_code, flags=re.DOTALL)
        # Replace Jinja variables with placeholder
        sql_code = re.sub(r'{{.*?}}', 'NULL', sql_code, flags=re.DOTALL)
        return sql_code
    
    def extract_tables_and_columns(self, sql_ast) -> Tuple[Set[str], Dict[str, List[str]]]:
        """
        Extract tables and columns from SQL AST
        
        Args:
            sql_ast: Parsed SQL AST
            
        Returns:
            Tuple of (set of table names, dict of {table_name: [column_names]})
        """
        if not sql_ast:
            return set(), {}
        
        tables = set()
        columns = {}
        
        def extract_from_expression(expr, current_table=None):
            nonlocal tables, columns
            
            if isinstance(expr, Table):
                table_name = expr.name
                if hasattr(expr, 'db') and expr.db:
                    table_name = f"{expr.db}.{table_name}"
                
                tables.add(table_name)
                if table_name not in columns:
                    columns[table_name] = []
                
                return table_name
            
            elif isinstance(expr, Column):
                col_name = expr.name
                if current_table and col_name not in columns.get(current_table, []):
                    if current_table in columns:
                        columns[current_table].append(col_name)
            
            # Handle all child expressions
            current_table_context = current_table
            if hasattr(expr, 'args'):
                for arg_name, arg_value in expr.args.items():
                    if arg_value:
                        # If this is a FROM clause or table reference,
                        # the returned value becomes the current table context
                        if isinstance(arg_value, Table):
                            current_table_context = extract_from_expression(arg_value)
                        elif isinstance(arg_value, list):
                            for item in arg_value:
                                extract_from_expression(item, current_table_context)
                        else:
                            extract_from_expression(arg_value, current_table_context)
            
            return current_table_context
        
        # Start extraction from root
        extract_from_expression(sql_ast)
        
        return tables, columns
    
    def analyze_sql(self, sql_code: str, target_table: Optional[str] = None) -> Dict[str, Any]:
        """
        Analyze SQL code to extract dependencies
        
        Args:
            sql_code: SQL code to analyze
            target_table: Target table name (if known)
            
        Returns:
            Dict with analysis results
        """
        logger.info(f"Analyzing SQL code for dependencies (dialect: {self.dialect})")
        
        try:
            sql_ast = self.parse_sql(sql_code)
            if not sql_ast:
                logger.warning("Failed to parse SQL")
                # For debugging: Print first 100 chars of SQL
                logger.debug(f"SQL snippet: {sql_code[:100]}...")
                return {"error": "Failed to parse SQL", "tables": [], "columns": {}, "dependencies": []}
            
            logger.info(f"SQL parsed successfully, AST type: {type(sql_ast).__name__}")
            
            # Extract tables and columns
            source_tables, columns_dict = self.extract_tables_and_columns(sql_ast)
            logger.info(f"Extracted tables: {source_tables}")
            
            # Try to extract target table from the SQL if not provided
            if not target_table:
                # For our sample data, extract from CREATE TABLE AS or CREATE OR REPLACE TABLE AS
                # This handles our sample data format which has statements like "CREATE OR REPLACE TABLE analytics.fct_order_items AS"
                if "CREATE OR REPLACE TABLE " in sql_code:
                    parts = sql_code.split("CREATE OR REPLACE TABLE ", 1)[1].split(" AS", 1)[0].strip()
                    target_table = parts
                    logger.info(f"Extracted target table from SQL string: {target_table}")
                elif "CREATE TABLE " in sql_code:
                    parts = sql_code.split("CREATE TABLE ", 1)[1].split(" AS", 1)[0].strip()
                    target_table = parts
                    logger.info(f"Extracted target table from SQL string: {target_table}")
                
                # If still not found, use the AST approach
                if not target_table:
                    expr_type = type(sql_ast).__name__
                    if expr_type == 'Create' and hasattr(sql_ast, 'name'):
                        # Handle CREATE TABLE statements
                        target_table = sql_ast.name
                        if hasattr(sql_ast, 'db') and sql_ast.db:
                            target_table = f"{sql_ast.db}.{target_table}"
                    elif isinstance(sql_ast, Select) and hasattr(sql_ast, 'args') and sql_ast.args.get('with'):
                        cte_relations = sql_ast.args.get('with')
                        if cte_relations:
                            target_table = cte_relations[0].alias_or_name
                    elif isinstance(sql_ast, Insert):
                        if sql_ast.args.get('table'):
                            target_table = sql_ast.args.get('table').name
                            if hasattr(sql_ast.args.get('table'), 'db') and sql_ast.args.get('table').db:
                                target_table = f"{sql_ast.args.get('table').db}.{target_table}"
                    elif isinstance(sql_ast, Update):
                        if sql_ast.args.get('table'):
                            target_table = sql_ast.args.get('table').name
                            if hasattr(sql_ast.args.get('table'), 'db') and sql_ast.args.get('table').db:
                                target_table = f"{sql_ast.args.get('table').db}.{target_table}"
                    elif isinstance(sql_ast, Select):
                        # For SELECT statements creating a view
                        target_table = "query_result"
            
            logger.info(f"Identified target table: {target_table}")
            
            # Build dependencies
            dependencies = []
            if target_table:
                for source in source_tables:
                    if source != target_table:  # Avoid self-dependency
                        dependencies.append({
                            "source": source,
                            "target": target_table,
                            "columns": columns_dict.get(source, [])
                        })
            
            return {
                "tables": list(source_tables),
                "target_table": target_table,
                "columns": columns_dict,
                "dependencies": dependencies
            }
        except Exception as e:
            logger.error(f"Error analyzing SQL: {str(e)}")
            return {"error": f"Error analyzing SQL: {str(e)}", "tables": [], "columns": {}, "dependencies": []}
    
    def build_dependency_graph(self, sql_files: List[Dict[str, str]]) -> nx.DiGraph:
        """
        Build a dependency graph from multiple SQL files
        
        Args:
            sql_files: List of dicts with keys 'content', 'path', and optionally 'dialect'
            
        Returns:
            NetworkX DiGraph of dependencies
        """
        graph = nx.DiGraph()
        
        for file_info in sql_files:
            sql_content = file_info['content']
            file_path = file_info['path']
            
            # Override dialect if specified for this file
            current_dialect = file_info.get('dialect', self.dialect)
            if current_dialect != self.dialect:
                original_dialect = self.dialect
                self.dialect = current_dialect
                self.dialect_class = DIALECT_MAP.get(self.dialect, sqlglot.dialects.Snowflake)
            
            # Analyze the SQL
            try:
                analysis = self.analyze_sql(sql_content)
                target_table = analysis.get('target_table')
                
                if target_table:
                    # Add nodes for all tables
                    for table in analysis.get('tables', []):
                        if table not in graph:
                            graph.add_node(table, files=[])
                        
                        # Add the file reference to the table
                        table_node = graph.nodes[table]
                        if file_path not in table_node['files']:
                            table_node['files'].append(file_path)
                    
                    # Add edges for dependencies
                    for dep in analysis.get('dependencies', []):
                        source = dep['source']
                        target = dep['target']
                        columns = dep['columns']
                        
                        if not graph.has_edge(source, target):
                            graph.add_edge(source, target, columns=columns, files=[file_path])
                        else:
                            # Update existing edge with additional columns and files
                            edge_data = graph.get_edge_data(source, target)
                            edge_cols = set(edge_data.get('columns', []))
                            edge_cols.update(columns)
                            
                            edge_files = edge_data.get('files', [])
                            if file_path not in edge_files:
                                edge_files.append(file_path)
                            
                            graph[source][target]['columns'] = list(edge_cols)
                            graph[source][target]['files'] = edge_files
                
            except Exception as e:
                logger.error(f"Error analyzing {file_path}: {str(e)}")
            
            # Restore original dialect if it was changed
            if current_dialect != self.dialect:
                self.dialect = original_dialect
                self.dialect_class = DIALECT_MAP.get(self.dialect, sqlglot.dialects.Snowflake)
        
        self.dependency_graph = graph
        return graph
    
    def find_upstream_dependencies(self, target_table: str, max_depth: int = 10) -> Dict[str, Any]:
        """
        Find all upstream dependencies for a target table
        
        Args:
            target_table: Target table name
            max_depth: Maximum depth of dependencies to traverse
            
        Returns:
            Dict with upstream dependency information
        """
        if not self.dependency_graph:
            return {"error": "Dependency graph not built"}
        
        if target_table not in self.dependency_graph:
            return {"error": f"Table {target_table} not found in dependency graph"}
        
        # Use NetworkX to find all predecessors (upstream dependencies)
        upstream_tables = []
        current_level = [target_table]
        visited = set()
        
        for depth in range(max_depth):
            if not current_level:
                break
                
            next_level = []
            for table in current_level:
                if table in visited:
                    continue
                    
                visited.add(table)
                predecessors = list(self.dependency_graph.predecessors(table))
                
                for pred in predecessors:
                    edge_data = self.dependency_graph.get_edge_data(pred, table) or {}
                    
                    upstream_tables.append({
                        "source": pred,
                        "target": table,
                        "depth": depth,
                        "columns": edge_data.get("columns", []),
                        "files": edge_data.get("files", [])
                    })
                    
                    if pred not in visited:
                        next_level.append(pred)
            
            current_level = next_level
        
        # Get unique files for all dependencies
        all_files = set()
        for dep in upstream_tables:
            for file in dep.get("files", []):
                all_files.add(file)
                
        return {
            "target_table": target_table,
            "upstream_dependencies": upstream_tables,
            "all_files": list(all_files),
            "total_dependencies": len(upstream_tables),
            "total_files": len(all_files)
        }
    
    def find_downstream_dependencies(self, source_table: str, max_depth: int = 10) -> Dict[str, Any]:
        """
        Find all downstream dependencies for a source table
        
        Args:
            source_table: Source table name
            max_depth: Maximum depth of dependencies to traverse
            
        Returns:
            Dict with downstream dependency information
        """
        if not self.dependency_graph:
            return {"error": "Dependency graph not built"}
        
        if source_table not in self.dependency_graph:
            return {"error": f"Table {source_table} not found in dependency graph"}
        
        # Use NetworkX to find all successors (downstream dependencies)
        downstream_tables = []
        current_level = [source_table]
        visited = set()
        
        for depth in range(max_depth):
            if not current_level:
                break
                
            next_level = []
            for table in current_level:
                if table in visited:
                    continue
                    
                visited.add(table)
                successors = list(self.dependency_graph.successors(table))
                
                for succ in successors:
                    edge_data = self.dependency_graph.get_edge_data(table, succ) or {}
                    
                    downstream_tables.append({
                        "source": table,
                        "target": succ,
                        "depth": depth,
                        "columns": edge_data.get("columns", []),
                        "files": edge_data.get("files", [])
                    })
                    
                    if succ not in visited:
                        next_level.append(succ)
            
            current_level = next_level
        
        # Get unique files for all dependencies
        all_files = set()
        for dep in downstream_tables:
            for file in dep.get("files", []):
                all_files.add(file)
                
        return {
            "source_table": source_table,
            "downstream_dependencies": downstream_tables,
            "all_files": list(all_files),
            "total_dependencies": len(downstream_tables),
            "total_files": len(all_files)
        } 