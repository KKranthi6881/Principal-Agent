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
                
                # Process each file to extract dependencies
                for file_info in result["source_files"]:
                    # Get file content and path
                    sql_code = file_info.get("content", "")
                    file_path = file_info.get("file_path", "")
                    file_url = file_info.get("url", "")
                    
                    if sql_code and file_path:
                        # Try to extract lineage from the SQL code
                        try:
                            lineage = self.sql_tools.extract_lineage(sql_code, dialect=dialect, file_path=file_path)
                            
                            # Process extracted lineage to identify upstream and downstream dependencies
                            if isinstance(lineage, dict) and "table_lineage" in lineage:
                                table_lineage = lineage["table_lineage"]
                                
                                # Check for upstream and downstream relationships
                                for relation in table_lineage:
                                    source = relation.get("source")
                                    target = relation.get("target")
                                    
                                    # If this table is the target, the source is upstream
                                    if target and target.lower() == table_name.lower() and source:
                                        # Add to upstream dependencies if not already there
                                        if not any(dep["table"] == source for dep in result["dependencies"]["upstream"]):
                                            result["dependencies"]["upstream"].append({
                                                "table": source,
                                                "script": file_path,
                                                "url": file_url
                                            })
                                    
                                    # If this table is the source, the target is downstream
                                    if source and source.lower() == table_name.lower() and target:
                                        # Add to downstream dependencies if not already there
                                        if not any(dep["table"] == target for dep in result["dependencies"]["downstream"]):
                                            result["dependencies"]["downstream"].append({
                                                "table": target,
                                                "script": file_path,
                                                "url": file_url
                                            })
                            
                            # Process column lineage if requested
                            if include_columns and isinstance(lineage, dict) and "column_lineage" in lineage:
                                column_lineage = lineage["column_lineage"]
                                
                                for relation in column_lineage:
                                    source_table = relation.get("source_table")
                                    source_column = relation.get("source_column")
                                    target_table = relation.get("target_table")
                                    target_column = relation.get("target_column")
                                    
                                    # If this table is involved in the column relationship
                                    if (source_table and source_table.lower() == table_name.lower()) or \
                                       (target_table and target_table.lower() == table_name.lower()):
                                        # Add the column to the list if it belongs to the target table
                                        column_name = None
                                        if source_table and source_table.lower() == table_name.lower():
                                            column_name = source_column
                                        elif target_table and target_table.lower() == table_name.lower():
                                            column_name = target_column
                                            
                                        if column_name and not any(col["name"] == column_name for col in result["columns"]):
                                            result["columns"].append({
                                                "name": column_name,
                                                "table": table_name,
                                                "referenced_in": file_path,
                                                "url": file_url
                                            })
                        except Exception as lineage_error:
                            logger.warning(f"Error extracting lineage from file {file_path}: {str(lineage_error)}")
            
            # If no dependencies found, try fallback approach with direct SQL search
            if not result["dependencies"]["upstream"] and not result["dependencies"]["downstream"]:
                logger.info(f"No dependencies found using lineage extraction, trying SQL search approach")
                
                # Search for SQL with queries involving this table
                if hasattr(self.sql_tools, 'search_sql'):
                    # Search for upstream dependencies (tables that feed into this table)
                    query = f"INSERT INTO {table_name} SELECT FROM OR CREATE TABLE {table_name} AS SELECT FROM OR WITH.*SELECT.*FROM OR UPDATE {table_name} SET"
                    upstream_search = self.sql_tools.search_sql(query, limit=10)
                    
                    # Process matches to find tables that feed into this one
                    for match in upstream_search.get("results", []):
                        sql_code = match.get("content", "")
                        file_path = match.get("file_path", "")
                        file_url = match.get("url", "")
                        
                        # Extract table names from SQL
                        tables = self._extract_table_dependencies(sql_code, table_name)
                        for source_table in tables.get("upstream", []):
                            if not any(dep["table"] == source_table for dep in result["dependencies"]["upstream"]):
                                result["dependencies"]["upstream"].append({
                                    "table": source_table,
                                    "script": file_path,
                                    "url": file_url
                                })
                    
                    # Search for downstream dependencies (tables that use this table)
                    query = f"FROM {table_name} OR JOIN {table_name} OR WITH.*{table_name}"
                    downstream_search = self.sql_tools.search_sql(query, limit=10)
                    
                    # Process matches to find tables that use this one
                    for match in downstream_search.get("results", []):
                        sql_code = match.get("content", "")
                        file_path = match.get("file_path", "")
                        file_url = match.get("url", "")
                        
                        # Extract table names from SQL
                        tables = self._extract_table_dependencies(sql_code, table_name)
                        for target_table in tables.get("downstream", []):
                            if not any(dep["table"] == target_table for dep in result["dependencies"]["downstream"]):
                                result["dependencies"]["downstream"].append({
                                    "table": target_table,
                                    "script": file_path,
                                    "url": file_url
                                })
            
            # Update summary counts
            result["summary"]["upstream_count"] = len(result["dependencies"]["upstream"])
            result["summary"]["downstream_count"] = len(result["dependencies"]["downstream"])
            result["summary"]["column_count"] = len(result["columns"])
            result["summary"]["file_count"] = len(result["source_files"])
            
            # Add natural language summary for LLM
            result["natural_language_summary"] = self._generate_dependency_summary(result)
            
            logger.info(f"Completed dependency analysis for table {table_name}: "
                       f"{result['summary']['upstream_count']} upstream, "
                       f"{result['summary']['downstream_count']} downstream, "
                       f"{result['summary']['column_count']} columns")
            
            return result
        except Exception as e:
            logger.error(f"Error analyzing dependencies: {str(e)}")
            return {
                "error": str(e),
                "table": table_name,
                "dependencies": {"upstream": [], "downstream": []},
                "columns": [],
                "natural_language_summary": f"Error analyzing dependencies for table {table_name}: {str(e)}"
            }
            
    def _extract_table_dependencies(self, sql_code: str, table_name: str) -> Dict[str, List[str]]:
        """
        Extract table dependencies from SQL code
        
        Args:
            sql_code: SQL code to analyze
            table_name: Name of the table being analyzed
            
        Returns:
            Dictionary with upstream and downstream table dependencies
        """
        result = {
            "upstream": [],
            "downstream": []
        }
        
        try:
            # Normalize SQL code and table name for easier processing
            sql_code = sql_code.lower()
            normalized_table = table_name.lower()
            
            # Simple regex patterns to extract potential table references
            # These are basic and would ideally be replaced with a proper SQL parser
            table_pattern = r'\b(from|join)\s+([a-z0-9_\.]+)'  # FROM or JOIN clause
            target_pattern = r'\b(into|update)\s+([a-z0-9_\.]+)'  # INTO or UPDATE clause
            cte_pattern = r'\bwith\s+([a-z0-9_]+)\s+as\s*\('  # CTE definitions
            create_pattern = r'\bcreate\s+(or\s+replace\s+)?(?:table|view)\s+([a-z0-9_\.]+)'  # CREATE statements
            insert_pattern = r'\binsert\s+into\s+([a-z0-9_\.]+)'  # INSERT statements
            select_pattern = r'\bselect\s+.*?\bfrom\s+([a-z0-9_\.]+)'  # SELECT statements
            
            # Extract tables referenced in FROM or JOIN clauses
            import re
            source_tables = set()
            for match in re.finditer(table_pattern, sql_code):
                source_name = match.group(2).strip()
                if source_name != normalized_table and source_name not in source_tables:
                    source_tables.add(source_name)
                    
            # Extract target tables in INTO or UPDATE clauses
            target_tables = set()
            for match in re.finditer(target_pattern, sql_code):
                target_name = match.group(2).strip()
                if target_name != normalized_table and target_name not in target_tables:
                    target_tables.add(target_name)
            
            # Check for CREATE statements
            create_matches = re.finditer(create_pattern, sql_code)
            for match in create_matches:
                created_table = match.group(2).strip()
                if created_table.lower() == normalized_table:
                    # This SQL creates our target table, so source tables are upstream
                    result["upstream"] = list(source_tables)
                elif normalized_table in source_tables:
                    # Our target table is used to create another table, so that table is downstream
                    target_tables.add(created_table)
            
            # Check for INSERT statements
            insert_matches = re.finditer(insert_pattern, sql_code)
            for match in insert_matches:
                inserted_table = match.group(1).strip()
                if inserted_table.lower() == normalized_table:
                    # Data is being inserted into our target table, sources are upstream
                    result["upstream"] = list(source_tables)
                elif normalized_table in source_tables:
                    # Our target table is used in an insert, so the target is downstream
                    target_tables.add(inserted_table)
            
            # If we have specific references, assign them to appropriate categories
            if normalized_table in sql_code:
                # If this SQL mentions our table but doesn't create it, it's likely using the table
                if normalized_table in source_tables:
                    # Tables created or updated using our table as a source are downstream
                    result["downstream"] = list(target_tables)
                else:
                    # If our table is a target, then the sources are upstream
                    result["upstream"] = list(source_tables)
            
            # Clean up results
            result["upstream"] = [table for table in result["upstream"] if table != normalized_table]
            result["downstream"] = [table for table in result["downstream"] if table != normalized_table]
            
            return result
            
        except Exception as e:
            logger.error(f"Error extracting table dependencies: {str(e)}")
            return result
    
    def _generate_dependency_summary(self, result: Dict[str, Any]) -> str:
        """
        Generate a natural language summary of dependencies
        
        Args:
            result: Dependency analysis result
            
        Returns:
            Natural language summary
        """
        summary_parts = []
        table_name = result.get("table", "unknown")
        
        # Upstream dependencies
        upstream = result.get("dependencies", {}).get("upstream", [])
        if upstream:
            # Format upstream tables with their files
            upstream_tables = []
            for dep in upstream:
                table = dep.get("table", "")
                script = dep.get("script", "").split("/")[-1] if dep.get("script") else ""  # Just filename not full path
                if table:
                    if script:
                        upstream_tables.append(f"{table} (defined in {script})")
                    else:
                        upstream_tables.append(table)
            
            if len(upstream_tables) == 1:
                summary_parts.append(f"The table {table_name} depends on {upstream_tables[0]}.")
            elif len(upstream_tables) > 1:
                tables_list = ", ".join(upstream_tables[:-1]) + " and " + upstream_tables[-1]
                summary_parts.append(f"The table {table_name} depends on {tables_list}.")
        else:
            summary_parts.append(f"The table {table_name} does not have any identified upstream dependencies.")
        
        # Downstream dependencies
        downstream = result.get("dependencies", {}).get("downstream", [])
        if downstream:
            # Format downstream tables with their files
            downstream_tables = []
            for dep in downstream:
                table = dep.get("table", "")
                script = dep.get("script", "").split("/")[-1] if dep.get("script") else ""  # Just filename not full path
                if table:
                    if script:
                        downstream_tables.append(f"{table} (defined in {script})")
                    else:
                        downstream_tables.append(table)
            
            if len(downstream_tables) == 1:
                summary_parts.append(f"The table {downstream_tables[0]} depends on {table_name}.")
            elif len(downstream_tables) > 1:
                tables_list = ", ".join(downstream_tables[:-1]) + " and " + downstream_tables[-1]
                summary_parts.append(f"The tables {tables_list} depend on {table_name}.")
        else:
            summary_parts.append(f"No downstream dependencies were identified for the table {table_name}.")
        
        # Column information
        columns = result.get("columns", [])
        if columns:
            column_names = [col.get("name", "") for col in columns if col.get("name", "")]
            if column_names:
                if len(column_names) <= 5:
                    columns_list = ", ".join(column_names)
                    summary_parts.append(f"The table includes these columns: {columns_list}.")
                else:
                    columns_sample = ", ".join(column_names[:5])
                    summary_parts.append(f"The table includes these columns (showing 5 of {len(column_names)}): {columns_sample}.")
        
        # Files information
        files = result.get("source_files", [])
        if files:
            file_paths = [file.get("file_path", "").split("/")[-1] for file in files if file.get("file_path", "")]  # Just filename not full path
            if len(file_paths) == 1:
                summary_parts.append(f"The table is referenced in the file {file_paths[0]}.")
            elif len(file_paths) > 1:
                if len(file_paths) <= 3:
                    files_list = ", ".join(file_paths)
                    summary_parts.append(f"The table is referenced in these files: {files_list}.")
                else:
                    files_sample = ", ".join(file_paths[:3])
                    summary_parts.append(f"The table is referenced in {len(file_paths)} files, including: {files_sample}.")
        
        # Join all parts
        result_summary = " ".join(summary_parts)
        
        # Add a business implications section
        if upstream or downstream:
            result_summary += "\n\nBusiness implications: "
            if upstream and downstream:
                result_summary += f"The table {table_name} serves as an intermediary in a data pipeline, processing data from upstream sources and providing it to downstream consumers."
            elif upstream:
                result_summary += f"The table {table_name} is a consumer of data from other tables, likely used for analytics, reporting, or as a refined data product."
            elif downstream:
                result_summary += f"The table {table_name} is a source of data for other tables, indicating it serves as foundational data in the system."
        else:
            result_summary += f"\n\nBusiness implications: The table {table_name} appears to be isolated in the current codebase, without clear data lineage connections."
        
        return result_summary
    
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
            # Get the dependencies
            dependencies = self.analyze_dependencies(
                table_name=table_name,
                include_columns=True,
                dialect=dialect,
                repo_url=repo_url
            )
            
            # Get the entity type (table or column)
            entity_type = "table"
            if column_name:
                entity_type = "column"
                
            # Initialize with empty defaults to prevent errors
            upstream_deps = "[]"
            downstream_deps = "[]"
            
            # Handle potential error cases with appropriate checks
            if isinstance(dependencies, dict) and "dependencies" in dependencies:
                # Format the dependencies for the prompt - handle table level
                if "upstream" in dependencies.get("dependencies", {}):
                    upstream_deps = json.dumps(dependencies["dependencies"]["upstream"], indent=2)
                if "downstream" in dependencies.get("dependencies", {}):
                    downstream_deps = json.dumps(dependencies["dependencies"]["downstream"], indent=2)
                
                # Handle column level if it exists
                if column_name and "columns" in dependencies and isinstance(dependencies["columns"], dict):
                    if column_name in dependencies["columns"]:
                        col_info = dependencies["columns"][column_name]
                        if "upstream" in col_info:
                            upstream_deps = json.dumps(col_info["upstream"], indent=2)
                        if "downstream" in col_info:
                            downstream_deps = json.dumps(col_info["downstream"], indent=2)
            else:
                # If dependencies is not in expected format, use empty lists
                logger.warning(f"Dependencies not in expected format: {dependencies}")
                
            # Build the prompt
            prompt = self.impact_analysis_prompt.format(
                table=table_name,
                column=column_name or "N/A",
                entity_type=entity_type,
                upstream_dependencies=upstream_deps,
                downstream_dependencies=downstream_deps
            )
            
            # Get the model response
            response = self.model.invoke(prompt)
            
            # Parse the response
            try:
                return self.parser.parse(response.content)
            except Exception as e:
                logger.error(f"Error parsing model response: {str(e)}")
                # Return the raw response if parsing fails
                return {"raw_response": response.content}
        except Exception as e:
            logger.error(f"Error analyzing impact: {str(e)}")
            return {"error": str(e)}
            
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