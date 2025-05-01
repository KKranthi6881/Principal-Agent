"""
Dependency Analysis Agent module that defines the DependencyAgent class
This agent analyzes SQL dependencies between tables, columns, and scripts
"""

from typing import Dict, List, Optional, Any
import logging
import json
import os
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser

from ..base.agent import Agent

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DependencyAgent(Agent):
    """
    Dependency Analysis Agent that analyzes SQL dependencies
    
    Attributes:
        name (str): The name of the agent
        description (str): A description of what the agent does
        model: Language model to use
        sql_tools: SQL analysis tools
        github_tools: GitHub tools
    """
    
    def __init__(
        self, 
        name: str = "Dependency Agent", 
        description: str = "Analyzes SQL dependencies between tables, columns, and scripts",
        model = None,
        sql_tools = None,
        github_tools = None
    ):
        """
        Initialize a new DependencyAgent
        
        Args:
            name: Name of the agent
            description: Description of what the agent does
            model: Language model to use
            sql_tools: SQL analysis tools
            github_tools: GitHub tools
        """
        super().__init__(name, description)
        self.model = model
        self.sql_tools = sql_tools
        self.github_tools = github_tools
        
        # Set up the parser
        self.parser = JsonOutputParser()
        
        # Set up the prompt templates
        self.dependency_prompt = ChatPromptTemplate.from_template("""
            You are a SQL Dependencies Analysis expert. Your job is to analyze SQL code and identify the dependencies 
            between tables, columns, and scripts.
            
            Task: {task}
            
            Context:
            {context}
            
            Please provide a detailed analysis of the dependencies in JSON format with the following structure:
            
            ```
            {
                "table": "table_name",
                "dependencies": {
                    "upstream": [
                        {
                            "table": "source_table_name",
                            "script": "script_path",
                            "url": "github_url"
                        }
                    ],
                    "downstream": [
                        {
                            "table": "dependent_table_name",
                            "script": "script_path",
                            "url": "github_url"
                        }
                    ]
                },
                "columns": [
                    {
                        "column": "column_name",
                        "dependencies": {
                            "upstream": [
                                {
                                    "table": "source_table_name",
                                    "column": "source_column_name",
                                    "script": "script_path",
                                    "url": "github_url"
                                }
                            ],
                            "downstream": [
                                {
                                    "table": "dependent_table_name",
                                    "column": "dependent_column_name",
                                    "script": "script_path",
                                    "url": "github_url"
                                }
                            ]
                        }
                    }
                ]
            }
            ```
            
            Only include information that you can confidently determine from the provided SQL code.
        """)
        
        self.impact_analysis_prompt = ChatPromptTemplate.from_template("""
            You are a SQL Impact Analysis expert. Your job is to analyze what would happen if changes were made
            to a particular table or column.
            
            Table: {table}
            Column: {column}
            
            Upstream Dependencies:
            {upstream_dependencies}
            
            Downstream Dependencies:
            {downstream_dependencies}
            
            Please analyze the impact of modifying the {entity_type} and provide a detailed assessment in JSON format:
            
            ```
            {
                "entity_type": "table or column",
                "name": "entity_name",
                "impact_summary": "High-level summary of the impact",
                "upstream_impact": [
                    {
                        "entity": "affected_entity",
                        "impact": "description of impact",
                        "severity": "high/medium/low"
                    }
                ],
                "downstream_impact": [
                    {
                        "entity": "affected_entity",
                        "impact": "description of impact",
                        "severity": "high/medium/low"
                    }
                ],
                "recommendations": [
                    "recommendation 1",
                    "recommendation 2"
                ]
            }
            ```
            
            Be thorough in your analysis and consider all potential effects.
        """)
        
    def _build_github_url(self, repo_url: str, file_path: str) -> str:
        """
        Build a properly formatted URL for a file that points to the application's repository UI
        
        Args:
            repo_url: Repository URL
            file_path: File path
            
        Returns:
            URL that points to the application's repository UI
        """
        if not repo_url:
            return ""

        # Extract repository info
        repo_name = ""
        owner = ""
        
        # Remove .git suffix if present
        if repo_url.endswith('.git'):
            repo_url = repo_url[:-4]
        
        # Ensure the repo URL doesn't have trailing slash
        if repo_url.endswith('/'):
            repo_url = repo_url[:-1]
        
        # Try to extract owner and repo
        import re
        github_url_match = re.match(r'https://github.com/([^/]+)/([^/]+)', repo_url)
        if github_url_match:
            owner = github_url_match.group(1)
            repo_name = github_url_match.group(2)
        else:
            # If we couldn't extract owner/repo, use GitHub URL as fallback
            if file_path and file_path.startswith('/'):
                file_path = file_path[1:]
            return f"{repo_url}/blob/main/{file_path}"
        
        # Remove leading slash from file path if present
        if file_path and file_path.startswith('/'):
            file_path = file_path[1:]
            
        # Build the application repository UI URL with file parameter for direct file opening
        return f"http://localhost:5173/repository?repo={owner}/{repo_name}&path={file_path}&file={file_path}"
        
    def analyze_dependencies(self, table_name: str, include_columns: bool = True,
                            dialect: Optional[str] = None, repo_url: Optional[str] = None):
        """
        Analyze dependencies for a table
        
        Args:
            table_name: Name of the table
            include_columns: Whether to include column dependencies
            dialect: SQL dialect to use
            repo_url: Repository URL
            
        Returns:
            Dependency analysis
        """
        try:
            logger.info(f"Analyzing dependencies for table '{table_name}' with dialect '{dialect}'")
            
            # Validate SQLTools instance exists
            if not self.sql_tools:
                return {"error": "SQL tools not available"}
            
            # Initialize result structure
            result = {
                "table": table_name,
                "dependencies": {
                    "upstream": [],
                    "downstream": []
                },
                "columns": [],
                "source_files": [],
                "dependency_paths": [],
                "summary": {
                    "table": table_name,
                    "dialect": dialect or "default",
                    "upstream_count": 0,
                    "downstream_count": 0,
                    "column_count": 0
                }
            }
            
            # Search for the target table to get information about its usage
            logger.info(f"Searching for table: {table_name}")
            table_search = self.sql_tools.search_for_table(table_name, limit=10)
            
            # Extract files containing the table definition and usage
            if "results" in table_search and table_search["results"]:
                result["source_files"] = table_search["results"]
                
                # Log files found
                logger.info(f"Found {len(result['source_files'])} files mentioning table {table_name}")
                
                # Build dependency graphs for upstream and downstream relationships
                upstream_graph = {}
                downstream_graph = {}
                
                # Process each file to extract dependencies
                for file_info in result["source_files"]:
                    # Get file content and path
                    sql_code = file_info.get("content", "")
                    file_path = file_info.get("file_path", "")
                    
                    if sql_code and file_path:
                        # Try to extract lineage from the SQL code
                        try:
                            # Check which method is available in the SQL tools interface
                            if hasattr(self.sql_tools, 'extract_lineage'):
                                lineage = self.sql_tools.extract_lineage(sql_code, dialect=dialect, file_path=file_path)
                            elif hasattr(self.sql_tools, 'analyze_lineage'):
                                lineage = self.sql_tools.analyze_lineage(sql_code, dialect=dialect, file_path=file_path)
                            else:
                                logger.warning(f"No lineage extraction method available for file {file_path}")
                                continue
                            
                            # Process extracted lineage to identify upstream and downstream dependencies
                            if isinstance(lineage, dict) and "table_lineage" in lineage:
                                table_lineage = lineage["table_lineage"]
                                
                                # Check for upstream and downstream relationships
                                for relation in table_lineage:
                                    source = relation.get("source")
                                    target = relation.get("target")
                                    
                                    # If this table is the target, the source is upstream
                                    if target and target.lower() == table_name.lower() and source:
                                        # Build the upstream graph
                                        if source not in upstream_graph:
                                            upstream_graph[source] = {
                                                "table": source,
                                                "files": [],
                                                "references": 0
                                            }
                                        
                                        # Add file info to the graph
                                        file_entry = {
                                            "file_path": file_path,
                                            "url": self._build_github_url(repo_url, file_path) if repo_url else file_info.get("url", "")
                                        }
                                        
                                        if file_entry not in upstream_graph[source]["files"]:
                                            upstream_graph[source]["files"].append(file_entry)
                                            upstream_graph[source]["references"] += 1
                                    
                                    # If this table is the source, the target is downstream
                                    if source and source.lower() == table_name.lower() and target:
                                        # Build the downstream graph
                                        if target not in downstream_graph:
                                            downstream_graph[target] = {
                                                "table": target,
                                                "files": [],
                                                "references": 0
                                            }
                                        
                                        # Add file info to the graph
                                        file_entry = {
                                            "file_path": file_path,
                                            "url": self._build_github_url(repo_url, file_path) if repo_url else file_info.get("url", "")
                                        }
                                        
                                        if file_entry not in downstream_graph[target]["files"]:
                                            downstream_graph[target]["files"].append(file_entry)
                                            downstream_graph[target]["references"] += 1
                        
                                # Process column lineage if requested
                                if include_columns and "column_lineage" in lineage:
                                    column_lineage = lineage["column_lineage"]
                                    
                                    for relation in column_lineage:
                                        source_table = relation.get("source_table")
                                        source_column = relation.get("source_column")
                                        target_table = relation.get("target_table")
                                        target_column = relation.get("target_column")
                                        transformation = relation.get("transformation")
                                        
                                        # Add column lineage information
                                        if source_table and source_column and target_table and target_column:
                                            # For upstream dependencies (target table is our table)
                                            if target_table.lower() == table_name.lower():
                                                column_entry = {
                                                    "source_table": source_table,
                                                    "source_column": source_column,
                                                    "target_table": target_table,
                                                    "target_column": target_column,
                                                    "transformation": transformation,
                                                    "file": file_path,
                                                    "url": self._build_github_url(repo_url, file_path) if repo_url else file_info.get("url", "")
                                                }
                                                result["columns"].append(column_entry)
                                            
                                            # For downstream dependencies (source table is our table)
                                            elif source_table.lower() == table_name.lower():
                                                column_entry = {
                                                    "source_table": source_table,
                                                    "source_column": source_column,
                                                    "target_table": target_table,
                                                    "target_column": target_column,
                                                    "transformation": transformation,
                                                    "file": file_path,
                                                    "url": self._build_github_url(repo_url, file_path) if repo_url else file_info.get("url", "")
                                                }
                                                result["columns"].append(column_entry)
                        except Exception as e:
                            logger.error(f"Error processing lineage for file {file_path}: {str(e)}")
                
                # Convert the dependency graphs to lists for result
                result["dependencies"]["upstream"] = list(upstream_graph.values())
                result["dependencies"]["downstream"] = list(downstream_graph.values())
                
                # Build dependency paths
                result["dependency_paths"] = self._build_dependency_paths(
                    table_name, 
                    upstream_graph, 
                    downstream_graph,
                    repo_url
                )
                
                # Update summary counts
                result["summary"]["upstream_count"] = len(result["dependencies"]["upstream"])
                result["summary"]["downstream_count"] = len(result["dependencies"]["downstream"])
                result["summary"]["column_count"] = len(result["columns"])
                
                # Generate a natural language summary
                result["summary_text"] = self._generate_dependency_summary(result)
            
            return result
            
        except Exception as e:
            logger.error(f"Error analyzing dependencies: {str(e)}")
            return {"error": f"Error analyzing dependencies: {str(e)}"}
    
    def _build_dependency_paths(self, table_name, upstream_graph, downstream_graph, repo_url=None):
        """
        Build dependency paths for better visualization
        
        Args:
            table_name: The central table name
            upstream_graph: Graph of upstream dependencies
            downstream_graph: Graph of downstream dependencies
            repo_url: Repository URL for building GitHub links
            
        Returns:
            List of dependency paths
        """
        paths = []
        
        # Build upstream paths (source -> table)
        for source_table, source_info in upstream_graph.items():
            path = {
                "direction": "upstream",
                "path": f"{source_table} → {table_name}",
                "tables": [source_table, table_name],
                "files": source_info["files"]
            }
            paths.append(path)
        
        # Build downstream paths (table -> target)
        for target_table, target_info in downstream_graph.items():
            path = {
                "direction": "downstream",
                "path": f"{table_name} → {target_table}",
                "tables": [table_name, target_table],
                "files": target_info["files"]
            }
            paths.append(path)
        
        return paths
    
    def _generate_dependency_summary(self, result):
        """
        Generate a natural language summary of the dependencies
        
        Args:
            result: The dependency analysis result
            
        Returns:
            Natural language summary
        """
        table_name = result.get("table", "unknown")
        upstream = result.get("dependencies", {}).get("upstream", [])
        downstream = result.get("dependencies", {}).get("downstream", [])
        columns = result.get("columns", [])
        
        summary_parts = []
        
        # Upstream dependencies
        if upstream:
            if len(upstream) == 1:
                summary_parts.append(f"The table {table_name} depends on 1 upstream table: {upstream[0]['table']}.")
            else:
                upstream_names = [u["table"] for u in upstream[:5]]
                if len(upstream) <= 5:
                    tables_list = ", ".join(upstream_names)
                    summary_parts.append(f"The table {table_name} depends on {len(upstream)} upstream tables: {tables_list}.")
                else:
                    tables_sample = ", ".join(upstream_names)
                    summary_parts.append(f"The table {table_name} depends on {len(upstream)} upstream tables, including: {tables_sample}...")
        else:
            summary_parts.append(f"The table {table_name} has no identifiable upstream dependencies.")
        
        # Downstream dependencies
        if downstream:
            if len(downstream) == 1:
                summary_parts.append(f"1 downstream table depends on {table_name}: {downstream[0]['table']}.")
            else:
                downstream_names = [d["table"] for d in downstream[:5]]
                if len(downstream) <= 5:
                    tables_list = ", ".join(downstream_names)
                    summary_parts.append(f"{len(downstream)} downstream tables depend on {table_name}: {tables_list}.")
                else:
                    tables_sample = ", ".join(downstream_names)
                    summary_parts.append(f"{len(downstream)} downstream tables depend on {table_name}, including: {tables_sample}...")
        else:
            summary_parts.append(f"No identifiable downstream tables depend on {table_name}.")
        
        # Column dependencies
        if columns:
            column_counts = {}
            for col in columns:
                source_table = col.get("source_table")
                target_table = col.get("target_table")
                
                if source_table == table_name:
                    # This is a downstream column relation
                    key = f"{source_table} → {target_table}"
                    column_counts[key] = column_counts.get(key, 0) + 1
                else:
                    # This is an upstream column relation
                    key = f"{source_table} → {target_table}"
                    column_counts[key] = column_counts.get(key, 0) + 1
            
            # Format column dependency information
            col_summaries = []
            for relation, count in column_counts.items():
                col_summaries.append(f"{count} column dependencies between {relation}")
            
            if col_summaries:
                summary_parts.append("Column-level dependencies:")
                for summary in col_summaries[:3]:
                    summary_parts.append(f"- {summary}")
                
                if len(col_summaries) > 3:
                    summary_parts.append(f"- ...and {len(col_summaries) - 3} more column dependencies")
        
        # Join all parts
        full_summary = "\n".join(summary_parts)
        return full_summary
    
    def analyze_impact(self, table_name: str, column_name: Optional[str] = None,
                      dialect: Optional[str] = None, repo_url: Optional[str] = None):
        """
        Analyze the impact of modifying a table or column
        
        Args:
            table_name: Name of the table
            column_name: Name of the column (if applicable)
            dialect: SQL dialect to use
            repo_url: Repository URL
            
        Returns:
            Impact analysis
        """
        try:
            logger.info(f"Analyzing impact for table '{table_name}', column '{column_name}' with dialect '{dialect}'")
            
            # Validate SQLTools instance exists
            if not self.sql_tools:
                return {"error": "SQL tools not available"}
            
            # Initialize result structure
            result = {
                "entity_type": "table" if not column_name else "column",
                "entity_name": column_name if column_name else table_name,
                "table_name": table_name,
                "column_name": column_name,
                "affected_tables": [],
                "affected_columns": [],
                "affected_queries": [],
                "summary": {
                    "affected_tables_count": 0,
                    "affected_columns_count": 0,
                    "affected_queries_count": 0
                }
            }
            
            # First, get dependencies for the table to find affected entities
            deps = self.analyze_dependencies(
                table_name=table_name,
                include_columns=True,
                dialect=dialect,
                repo_url=repo_url
            )
            
            # Handle the case where dependencies couldn't be found
            if "error" in deps:
                return {
                    "entity_type": "table" if not column_name else "column",
                    "entity_name": column_name if column_name else table_name,
                    "table_name": table_name,
                    "column_name": column_name,
                    "error": deps["error"],
                    "summary": "Could not analyze impact due to error in dependency analysis"
                }
            
            # Extract downstream dependencies (tables affected by this table)
            downstream = deps.get("dependencies", {}).get("downstream", [])
            result["affected_tables"] = downstream
            result["summary"]["affected_tables_count"] = len(downstream)
            
            # Extract column-level dependencies if we're analyzing a column
            if column_name:
                columns = deps.get("columns", [])
                affected_columns = []
                
                for col_dep in columns:
                    if col_dep.get("source_table") == table_name and col_dep.get("source_column") == column_name:
                        affected_columns.append({
                            "table": col_dep.get("target_table"),
                            "column": col_dep.get("target_column"),
                            "transformation": col_dep.get("transformation")
                        })
                
                result["affected_columns"] = affected_columns
                result["summary"]["affected_columns_count"] = len(affected_columns)
            
            # Look for queries that use this table/column
            if self.sql_tools:
                # Search for the table in SQL files
                search_terms = [table_name]
                if column_name:
                    search_terms.append(column_name)
                
                for term in search_terms:
                    search_results = self.sql_tools.search_for_table(term, limit=10)
                    if "results" in search_results:
                        for item in search_results["results"]:
                            # Add file info to affected queries
                            result["affected_queries"].append({
                                "file": item.get("file_path", ""),
                                "url": self._build_github_url(repo_url, item.get("file_path", "")) if repo_url else item.get("url", ""),
                                "matched_term": term
                            })
            
            # Remove duplicates from affected queries
            unique_queries = []
            unique_paths = set()
            for query in result["affected_queries"]:
                if query["file"] not in unique_paths:
                    unique_paths.add(query["file"])
                    unique_queries.append(query)
            
            result["affected_queries"] = unique_queries
            result["summary"]["affected_queries_count"] = len(unique_queries)
            
            # Generate a natural language summary
            result["summary_text"] = self._generate_impact_summary(result)
            
            return result
        except Exception as e:
            logger.error(f"Error analyzing impact: {str(e)}")
            return {
                "entity_type": "table" if not column_name else "column",
                "entity_name": column_name if column_name else table_name,
                "table_name": table_name,
                "column_name": column_name,
                "error": str(e),
                "summary": f"Error analyzing impact: {str(e)}"
            }
    
    def _generate_impact_summary(self, result: Dict[str, Any]) -> str:
        """
        Generate a natural language summary of the impact analysis
        
        Args:
            result: Impact analysis result
            
        Returns:
            Natural language summary
        """
        summary_parts = []
        entity_type = result.get("entity_type", "table")
        entity_name = result.get("entity_name", "unknown")
        table_name = result.get("table_name", "unknown")
        
        # Affected tables
        affected_tables = result.get("affected_tables", [])
        if affected_tables:
            if len(affected_tables) == 1:
                summary_parts.append(f"Modifying the {entity_type} {entity_name} will affect the table {affected_tables[0]['table']}.")
            else:
                tables_list = ", ".join([t["table"] for t in affected_tables])
                summary_parts.append(f"Modifying the {entity_type} {entity_name} will affect the tables {tables_list}.")
        else:
            summary_parts.append(f"Modifying the {entity_type} {entity_name} does not appear to affect any other tables.")
        
        # Affected columns
        affected_columns = result.get("affected_columns", [])
        if affected_columns:
            if len(affected_columns) == 1:
                summary_parts.append(f"Modifying the {entity_type} {entity_name} will affect the column {affected_columns[0]['column']} in the table {affected_columns[0]['table']}.")
            else:
                columns_list = ", ".join([f"{col['column']} in {col['table']}" for col in affected_columns])
                summary_parts.append(f"Modifying the {entity_type} {entity_name} will affect the columns {columns_list}.")
        else:
            summary_parts.append(f"Modifying the {entity_type} {entity_name} does not appear to affect any other columns.")
        
        # Affected queries
        affected_queries = result.get("affected_queries", [])
        if affected_queries:
            if len(affected_queries) == 1:
                summary_parts.append(f"Modifying the {entity_type} {entity_name} will affect the query in the file {affected_queries[0]['file']}.")
            else:
                files_list = ", ".join([q["file"] for q in affected_queries])
                summary_parts.append(f"Modifying the {entity_type} {entity_name} will affect the queries in the files {files_list}.")
        else:
            summary_parts.append(f"Modifying the {entity_type} {entity_name} does not appear to affect any queries.")
        
        # Join all parts
        result_summary = " ".join(summary_parts)
        
        # Add a business implications section
        if affected_tables or affected_columns or affected_queries:
            result_summary += "\n\nBusiness implications: "
            if affected_tables and affected_columns and affected_queries:
                result_summary += f"Modifying the {entity_type} {entity_name} will have a significant impact on the data pipeline, affecting multiple tables, columns, and queries."
            elif affected_tables and affected_columns:
                result_summary += f"Modifying the {entity_type} {entity_name} will have a moderate impact on the data pipeline, affecting multiple tables and columns."
            elif affected_tables and affected_queries:
                result_summary += f"Modifying the {entity_type} {entity_name} will have a moderate impact on the data pipeline, affecting multiple tables and queries."
            elif affected_columns and affected_queries:
                result_summary += f"Modifying the {entity_type} {entity_name} will have a moderate impact on the data pipeline, affecting multiple columns and queries."
            elif affected_tables:
                result_summary += f"Modifying the {entity_type} {entity_name} will have a minor impact on the data pipeline, affecting one or more tables."
            elif affected_columns:
                result_summary += f"Modifying the {entity_type} {entity_name} will have a minor impact on the data pipeline, affecting one or more columns."
            elif affected_queries:
                result_summary += f"Modifying the {entity_type} {entity_name} will have a minor impact on the data pipeline, affecting one or more queries."
        else:
            result_summary += f"\n\nBusiness implications: Modifying the {entity_type} {entity_name} does not appear to have any significant impact on the data pipeline."
        
        return result_summary
    
    def search_and_analyze(self, keyword: str, dialect: Optional[str] = None, repo_url: Optional[str] = None) -> Dict[str, Any]:
        """
        Search for a keyword (column name or business logic) and analyze related tables
        
        Args:
            keyword: Keyword to search for (column name or business logic)
            dialect: SQL dialect to use
            repo_url: Repository URL
            
        Returns:
            Analysis with tables containing the keyword and their dependencies
        """
        try:
            logger.info(f"Searching for keyword/column: '{keyword}'")
            
            # Initialize result
            result = {
                "keyword": keyword,
                "related_tables": [],
                "matched_files": [],
                "column_matches": [],
                "code_matches": [],
                "dependencies": {}
            }
            
            # First try to search for it as a column name
            if hasattr(self.sql_tools, 'search_for_column'):
                # Search for column without specifying a table
                logger.info(f"Searching for column: {keyword}")
                column_search = self.sql_tools.search_for_column("", keyword, limit=10)
                
                if "results" in column_search and column_search["results"]:
                    for item in column_search["results"]:
                        table_name = item.get("table", "")
                        file_path = item.get("file_path", "")
                        file_url = item.get("url", "")
                        snippet = item.get("snippet", "")
                        
                        if table_name and table_name not in [t["name"] for t in result["related_tables"]]:
                            result["related_tables"].append({
                                "name": table_name,
                                "reason": f"Contains column '{keyword}'",
                                "file": file_path
                            })
                            
                        if snippet and {"column": keyword, "snippet": snippet} not in result["column_matches"]:
                            result["column_matches"].append({
                                "column": keyword,
                                "table": table_name,
                                "file": file_path,
                                "url": file_url,
                                "snippet": snippet
                            })
                            
                        if file_path and file_path not in [f["path"] for f in result["matched_files"]]:
                            result["matched_files"].append({
                                "path": file_path,
                                "url": file_url,
                                "match_type": "column"
                            })
            
            # Then search for general keyword in SQL code
            if hasattr(self.sql_tools, 'search_sql'):
                logger.info(f"Searching for SQL keyword: {keyword}")
                sql_search = self.sql_tools.search_sql(keyword, limit=10)
                
                if "results" in sql_search and sql_search["results"]:
                    for item in sql_search["results"]:
                        content = item.get("content", "")
                        file_path = item.get("file_path", "")
                        file_url = item.get("url", "")
                        
                        # Try to extract tables mentioned in this SQL
                        try:
                            import re
                            # Extract CREATE TABLE, INSERT INTO, or UPDATE statements
                            table_pattern = r'\b(?:create\s+table|insert\s+into|update|from|join)\s+([a-z0-9_\.]+)'
                            for match in re.finditer(table_pattern, content.lower()):
                                table_name = match.group(1).strip()
                                if table_name and table_name not in [t["name"] for t in result["related_tables"]]:
                                    result["related_tables"].append({
                                        "name": table_name,
                                        "reason": f"SQL file contains keyword '{keyword}'",
                                        "file": file_path
                                    })
                        except Exception as e:
                            logger.warning(f"Error extracting tables from SQL: {e}")
                        
                        # Get a snippet around the keyword
                        try:
                            import re
                            pattern = re.compile(r'(.{0,100}' + re.escape(keyword) + r'.{0,100})', re.IGNORECASE | re.DOTALL)
                            matches = pattern.findall(content)
                            if matches:
                                snippet = "..." + matches[0] + "..."
                                result["code_matches"].append({
                                    "file": file_path,
                                    "url": file_url,
                                    "snippet": snippet
                                })
                        except Exception as e:
                            logger.warning(f"Error extracting snippet: {e}")
                            
                        if file_path and file_path not in [f["path"] for f in result["matched_files"]]:
                            result["matched_files"].append({
                                "path": file_path,
                                "url": file_url,
                                "match_type": "code"
                            })
            
            # If we found related tables, analyze their dependencies
            if result["related_tables"]:
                for table_info in result["related_tables"][:5]:  # Limit to first 5 tables to avoid excessive processing
                    table_name = table_info["name"]
                    logger.info(f"Analyzing dependencies for related table: {table_name}")
                    
                    # Get dependencies for this table
                    deps = self.analyze_dependencies(
                        table_name=table_name,
                        include_columns=True,
                        dialect=dialect,
                        repo_url=repo_url
                    )
                    
                    if "error" not in deps:
                        result["dependencies"][table_name] = deps
            
            # Generate a natural language summary
            summary = self._generate_keyword_search_summary(result, keyword)
            result["natural_language_summary"] = summary
            
            logger.info(f"Completed search and analysis for keyword '{keyword}': "
                      f"Found {len(result['related_tables'])} related tables, "
                      f"{len(result['matched_files'])} matching files")
            
            return result
            
        except Exception as e:
            logger.error(f"Error in search_and_analyze for '{keyword}': {str(e)}")
            return {
                "error": str(e),
                "keyword": keyword,
                "natural_language_summary": f"Error searching for '{keyword}': {str(e)}"
            }
    
    def _generate_keyword_search_summary(self, result: Dict[str, Any], keyword: str) -> str:
        """
        Generate a natural language summary for keyword search results
        
        Args:
            result: Search results
            keyword: The keyword that was searched
            
        Returns:
            Natural language summary
        """
        summary_parts = []
        
        # Related tables
        tables = result.get("related_tables", [])
        if tables:
            if len(tables) == 1:
                table_info = tables[0]
                summary_parts.append(f"The keyword '{keyword}' is found in the table {table_info['name']} ({table_info['reason']}).")
            else:
                table_names = [t["name"] for t in tables[:5]]
                if len(tables) <= 5:
                    tables_list = ", ".join(table_names)
                    summary_parts.append(f"The keyword '{keyword}' is found in these tables: {tables_list}.")
                else:
                    tables_sample = ", ".join(table_names)
                    summary_parts.append(f"The keyword '{keyword}' is found in {len(tables)} tables, including: {tables_sample}.")
        else:
            summary_parts.append(f"The keyword '{keyword}' was not found in any table names or column definitions.")
        
        # Code matches
        code_matches = result.get("code_matches", [])
        if code_matches:
            if len(code_matches) == 1:
                file_path = code_matches[0]["file"].split("/")[-1] if code_matches[0]["file"] else "unknown file"
                summary_parts.append(f"Found a code reference in {file_path}.")
            else:
                file_paths = [match["file"].split("/")[-1] for match in code_matches[:3] if match["file"]]
                if len(code_matches) <= 3:
                    files_list = ", ".join(file_paths)
                    summary_parts.append(f"Found code references in these files: {files_list}.")
                else:
                    files_sample = ", ".join(file_paths)
                    summary_parts.append(f"Found {len(code_matches)} code references in files including: {files_sample}.")
        
        # Join all parts
        result_summary = " ".join(summary_parts)
        
        # Add examples of the business logic if we have them
        if code_matches:
            # Get a representative code snippet
            snippet = code_matches[0].get("snippet", "").strip()
            if snippet:
                result_summary += f"\n\nExample of the business logic containing '{keyword}':\n```sql\n{snippet}\n```"
        
        # Add information about dependencies if available
        deps = result.get("dependencies", {})
        if deps:
            result_summary += "\n\nDependency Information:"
            for table_name, table_deps in deps.items():
                # Extract upstream and downstream counts
                upstream = table_deps.get("dependencies", {}).get("upstream", [])
                downstream = table_deps.get("dependencies", {}).get("downstream", [])
                
                upstream_text = ", ".join([dep.get("table", "") for dep in upstream[:3]]) if upstream else "none"
                downstream_text = ", ".join([dep.get("table", "") for dep in downstream[:3]]) if downstream else "none"
                
                result_summary += f"\n- {table_name}:\n  - Upstream dependencies: {upstream_text}{' (and more)' if len(upstream) > 3 else ''}\n  - Downstream dependencies: {downstream_text}{' (and more)' if len(downstream) > 3 else ''}"
        
        return result_summary
            
    def run(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run the dependency agent on the given input data
        
        Args:
            input_data: Input data for the agent, should contain:
                - 'action': Type of dependency analysis to perform
                - 'params': Parameters for the action
                
        Returns:
            Dependency analysis results
        """
        action = input_data.get("action", "")
        params = input_data.get("params", {})
        
        # Handle common misspelling of analyze_dependencies
        if action == "analyze_dependenies":
            logger.info("Correcting misspelled action 'analyze_dependenies' to 'analyze_dependencies'")
            action = "analyze_dependencies"
        
        if action == "analyze_dependencies":
            table_name = params.get("table_name")
            include_columns = params.get("include_columns", True)
            dialect = params.get("dialect")
            repo_url = params.get("repo_url")
            keyword = params.get("keyword")
            
            # If we have a keyword but no table, search for the keyword first
            if not table_name and keyword:
                logger.info(f"No table specified but keyword '{keyword}' provided, performing keyword search")
                return self.search_and_analyze(
                    keyword=keyword,
                    dialect=dialect,
                    repo_url=repo_url
                )
            elif not table_name:
                # Check if the table_name parameter might actually be a column or keyword
                # This handles cases where the planning node didn't properly identify the query type
                for param_name, param_value in params.items():
                    if param_value and isinstance(param_value, str) and param_name != "dialect" and param_name != "repo_url":
                        logger.info(f"No table specified, treating '{param_value}' as a keyword")
                        return self.search_and_analyze(
                            keyword=param_value,
                            dialect=dialect,
                            repo_url=repo_url
                        )
                        
                return {"error": "Table name is required"}
                
            return self.analyze_dependencies(
                table_name=table_name,
                include_columns=include_columns,
                dialect=dialect,
                repo_url=repo_url
            )
            
        elif action == "analyze_impact":
            table_name = params.get("table_name")
            column_name = params.get("column_name")
            dialect = params.get("dialect")
            repo_url = params.get("repo_url")
            
            # If we have a column but no table, search for the column first
            if not table_name and column_name:
                logger.info(f"No table specified but column '{column_name}' provided, performing column search")
                return self.search_and_analyze(
                    keyword=column_name,
                    dialect=dialect,
                    repo_url=repo_url
                )
            elif not table_name:
                return {"error": "Table name is required"}
                
            return self.analyze_impact(
                table_name=table_name,
                column_name=column_name,
                dialect=dialect,
                repo_url=repo_url
            )
            
        else:
            return {"error": f"Unknown action: {action}"} 