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
            # Get upstream dependencies
            upstream = self.sql_tools.get_table_lineage(
                table_name=table_name,
                direction="upstream",
                max_depth=2,
                dialect=dialect,
                repo_url=repo_url
            )
            
            # Get downstream dependencies
            downstream = self.sql_tools.get_table_lineage(
                table_name=table_name,
                direction="downstream",
                max_depth=2,
                dialect=dialect,
                repo_url=repo_url
            )
            
            # Format the result
            result = {
                "table": table_name,
                "dependencies": {
                    "upstream": {},
                    "downstream": {}
                }
            }
            
            # Add upstream dependencies
            if "levels" in upstream:
                for level, tables in upstream["levels"].items():
                    for table in tables:
                        table_name = table.get("name", "")
                        file_path = table.get("file_path", "")
                        file_url = table.get("file_url", "")
                        
                        if table_name:
                            result["dependencies"]["upstream"][table_name] = {
                                "script": file_path,
                                "url": file_url
                            }
            
            # Add downstream dependencies
            if "levels" in downstream:
                for level, tables in downstream["levels"].items():
                    for table in tables:
                        table_name = table.get("name", "")
                        file_path = table.get("file_path", "")
                        file_url = table.get("file_url", "")
                        
                        if table_name:
                            result["dependencies"]["downstream"][table_name] = {
                                "script": file_path,
                                "url": file_url
                            }
                            
            # Add column dependencies if requested
            if include_columns:
                result["columns"] = {}
                
                # Search for columns in the table
                columns_search = self.sql_tools.search_columns("", limit=20)
                
                # Filter by table name
                table_columns = []
                for column_info in columns_search.get("results", []):
                    if column_info.get("table", "").lower() == table_name.lower():
                        column_name = column_info.get("column", "")
                        if column_name:
                            table_columns.append(column_name)
                
                # Get lineage for each column
                for column_name in table_columns:
                    column_upstream = self.sql_tools.get_column_lineage(
                        table_name=table_name,
                        column_name=column_name,
                        direction="upstream",
                        max_depth=2,
                        dialect=dialect,
                        repo_url=repo_url
                    )
                    
                    column_downstream = self.sql_tools.get_column_lineage(
                        table_name=table_name,
                        column_name=column_name,
                        direction="downstream",
                        max_depth=2,
                        dialect=dialect,
                        repo_url=repo_url
                    )
                    
                    column_deps = {
                        "upstream": {},
                        "downstream": {}
                    }
                    
                    # Add upstream column dependencies
                    if "levels" in column_upstream:
                        for level, columns in column_upstream["levels"].items():
                            for col in columns:
                                col_table = col.get("table", "")
                                col_name = col.get("column", "")
                                file_path = col.get("file_path", "")
                                file_url = col.get("file_url", "")
                                
                                if col_table and col_name:
                                    key = f"{col_table}.{col_name}"
                                    column_deps["upstream"][key] = {
                                        "table": col_table,
                                        "column": col_name,
                                        "script": file_path,
                                        "url": file_url
                                    }
                    
                    # Add downstream column dependencies
                    if "levels" in column_downstream:
                        for level, columns in column_downstream["levels"].items():
                            for col in columns:
                                col_table = col.get("table", "")
                                col_name = col.get("column", "")
                                file_path = col.get("file_path", "")
                                file_url = col.get("file_url", "")
                                
                                if col_table and col_name:
                                    key = f"{col_table}.{col_name}"
                                    column_deps["downstream"][key] = {
                                        "table": col_table,
                                        "column": col_name,
                                        "script": file_path,
                                        "url": file_url
                                    }
                    
                    result["columns"][column_name] = column_deps
            
            return result
        except Exception as e:
            logger.error(f"Error analyzing dependencies: {str(e)}")
            return {"error": str(e)}
            
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
                
            # Format the dependencies for the prompt
            upstream_deps = json.dumps(dependencies["dependencies"]["upstream"], indent=2)
            downstream_deps = json.dumps(dependencies["dependencies"]["downstream"], indent=2)
            
            if column_name and column_name in dependencies.get("columns", {}):
                upstream_deps = json.dumps(dependencies["columns"][column_name]["upstream"], indent=2)
                downstream_deps = json.dumps(dependencies["columns"][column_name]["downstream"], indent=2)
                
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
            
            if not table_name:
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
            
            if not table_name:
                return {"error": "Table name is required"}
                
            return self.analyze_impact(
                table_name=table_name,
                column_name=column_name,
                dialect=dialect,
                repo_url=repo_url
            )
            
        else:
            return {"error": f"Unknown action: {action}"} 