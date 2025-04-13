"""
Lineage Agent module that defines the LineageAgent class
This agent analyzes SQL code to extract table and column lineage
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

class LineageAgent(Agent):
    """
    Lineage Agent that analyzes SQL code to extract table and column lineage
    
    Attributes:
        name (str): The name of the agent
        description (str): A description of what the agent does
        model: Language model to use
        sql_tools: SQL analysis tools
    """
    
    def __init__(
        self, 
        name: str = "Lineage Agent", 
        description: str = "Analyzes SQL code to extract lineage information",
        model = None,
        sql_tools = None
    ):
        """
        Initialize a new LineageAgent
        
        Args:
            name: Name of the agent
            description: Description of what the agent does
            model: Language model to use
            sql_tools: SQL analysis tools
        """
        super().__init__(name, description)
        self.model = model
        self.sql_tools = sql_tools
        
        # Set up the parser
        self.parser = JsonOutputParser()
        
        # Set up the prompt templates
        self.lineage_prompt = ChatPromptTemplate.from_template("""
            You are a SQL Lineage Analysis expert. Your job is to analyze SQL code and identify the lineage 
            between tables and columns.
            
            Task: {task}
            
            Context:
            {context}
            
            Please provide a detailed analysis of the lineage in JSON format with the following structure:
            
            For table lineage:
            ```
            {
                "table": "target_table_name",
                "upstream_tables": [
                    {
                        "table": "source_table_name",
                        "path": "file_path",
                        "url": "github_url"
                    }
                ],
                "downstream_tables": [
                    {
                        "table": "dependent_table_name",
                        "path": "file_path",
                        "url": "github_url"
                    }
                ]
            }
            ```
            
            For column lineage:
            ```
            {
                "table": "target_table_name",
                "column": "target_column_name",
                "upstream_columns": [
                    {
                        "table": "source_table_name",
                        "column": "source_column_name",
                        "transformation": "SQL transformation applied",
                        "path": "file_path",
                        "url": "github_url"
                    }
                ],
                "downstream_columns": [
                    {
                        "table": "dependent_table_name",
                        "column": "dependent_column_name",
                        "path": "file_path",
                        "url": "github_url"
                    }
                ]
            }
            ```
            
            Only include information that you can confidently determine from the provided SQL code.
        """)
        
    def trace_table_lineage(self, table_name: str, direction: str = "upstream",
                           dialect: Optional[str] = None, repo_url: Optional[str] = None):
        """
        Trace the lineage of a table
        
        Args:
            table_name: Name of the table
            direction: Direction of the lineage ('upstream' or 'downstream')
            dialect: SQL dialect to use
            repo_url: Repository URL
            
        Returns:
            Table lineage information
        """
        try:
            # Use the sql_tools to trace table lineage
            lineage_result = self.sql_tools.get_table_lineage(
                table_name=table_name,
                direction=direction,
                max_depth=3,
                dialect=dialect,
                repo_url=repo_url
            )
            
            return lineage_result
        except Exception as e:
            logger.error(f"Error tracing table lineage: {str(e)}")
            return {"error": str(e)}
            
    def trace_column_lineage(self, table_name: str, column_name: str, 
                            direction: str = "upstream",
                            dialect: Optional[str] = None, 
                            repo_url: Optional[str] = None):
        """
        Trace the lineage of a column
        
        Args:
            table_name: Name of the table
            column_name: Name of the column
            direction: Direction of the lineage ('upstream' or 'downstream')
            dialect: SQL dialect to use
            repo_url: Repository URL
            
        Returns:
            Column lineage information
        """
        try:
            # Use the sql_tools to trace column lineage
            lineage_result = self.sql_tools.get_column_lineage(
                table_name=table_name,
                column_name=column_name,
                direction=direction,
                max_depth=3,
                dialect=dialect,
                repo_url=repo_url
            )
            
            return lineage_result
        except Exception as e:
            logger.error(f"Error tracing column lineage: {str(e)}")
            return {"error": str(e)}
            
    def analyze_lineage(self, sql_code: str, task: str):
        """
        Analyze SQL code to extract lineage information
        
        Args:
            sql_code: SQL code to analyze
            task: Description of the analysis task
            
        Returns:
            Lineage analysis
        """
        # Build the prompt
        prompt = self.lineage_prompt.format(
            task=task,
            context=sql_code
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
            
    def run(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run the lineage agent on the given input data
        
        Args:
            input_data: Input data for the agent, should contain:
                - 'action': Type of lineage analysis to perform
                - 'params': Parameters for the action
                
        Returns:
            Lineage analysis results
        """
        action = input_data.get("action", "")
        params = input_data.get("params", {})
        
        if action == "trace_table_lineage":
            table_name = params.get("table_name")
            direction = params.get("direction", "upstream")
            dialect = params.get("dialect")
            repo_url = params.get("repo_url")
            
            if not table_name:
                return {"error": "Table name is required"}
                
            return self.trace_table_lineage(
                table_name=table_name,
                direction=direction,
                dialect=dialect,
                repo_url=repo_url
            )
            
        elif action == "trace_column_lineage":
            table_name = params.get("table_name")
            column_name = params.get("column_name")
            direction = params.get("direction", "upstream")
            dialect = params.get("dialect")
            repo_url = params.get("repo_url")
            
            if not table_name or not column_name:
                return {"error": "Table name and column name are required"}
                
            return self.trace_column_lineage(
                table_name=table_name,
                column_name=column_name,
                direction=direction,
                dialect=dialect,
                repo_url=repo_url
            )
            
        elif action == "analyze_lineage":
            sql_code = params.get("sql_code")
            task = params.get("task", "Analyze the SQL code and identify the table and column lineage.")
            
            if not sql_code:
                return {"error": "SQL code is required"}
                
            return self.analyze_lineage(sql_code, task)
            
        else:
            return {"error": f"Unknown action: {action}"} 