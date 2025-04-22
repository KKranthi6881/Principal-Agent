"""
Description Summarizer Agent module that defines the DescriptionSummarizerAgent class
This agent provides business and technical descriptions for SQL tables and columns
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

class DescriptionSummarizerAgent(Agent):
    """
    Description Summarizer Agent that provides business and technical descriptions for SQL tables and columns
    
    Attributes:
        name (str): The name of the agent
        description (str): A description of what the agent does
        model: Language model to use
        sql_tools: SQL analysis tools
    """
    
    def __init__(
        self, 
        name: str = "Description Summarizer Agent", 
        description: str = "Provides business and technical descriptions for SQL tables and columns",
        model = None,
        sql_tools = None
    ):
        """
        Initialize a new DescriptionSummarizerAgent
        
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
        self.table_description_prompt = ChatPromptTemplate.from_template("""
            You are a Data Dictionary Expert. Your job is to create comprehensive descriptions for SQL tables
            based on their structure, code, and context.
            
            Table: {table_name}
            
            SQL Code:
            ```sql
            {sql_code}
            ```
            
            Additional Context:
            {context}
            
            Please provide a detailed description of this table in JSON format with the following structure:
            
            ```
            {
                "table_name": "The table name",
                "business_name": "Business-friendly name for this table",
                "technical_description": "Technical description of the table structure and purpose",
                "business_description": "Business-focused description of what this table represents",
                "domain": "Business domain this table belongs to",
                "primary_key": ["column1", "column2"],
                "update_frequency": "How often this table is updated",
                "main_columns": [
                    {
                        "column": "column_name",
                        "business_name": "Business-friendly name",
                        "description": "Description of the column's purpose",
                        "data_type": "Inferred data type"
                    }
                ],
                "relationships": [
                    {
                        "related_table": "table_name",
                        "relationship_type": "parent/child/reference",
                        "description": "Description of the relationship"
                    }
                ]
            }
            ```
            
            Infer as much information as possible from the provided code and context.
        """)
        
        self.column_description_prompt = ChatPromptTemplate.from_template("""
            You are a Data Dictionary Expert. Your job is to create comprehensive descriptions for SQL columns
            based on their structure, code, and context.
            
            Table: {table_name}
            Column: {column_name}
            
            SQL Code:
            ```sql
            {sql_code}
            ```
            
            Column Lineage:
            {lineage}
            
            Please provide a detailed description of this column in JSON format with the following structure:
            
            ```
            {
                "column_name": "The column name",
                "table_name": "The table name",
                "business_name": "Business-friendly name for this column",
                "technical_description": "Technical description including data type, constraints, etc.",
                "business_description": "Business-focused description of what this column represents",
                "data_type": "Inferred data type",
                "nullable": true/false,
                "constraints": ["constraint1", "constraint2"],
                "sample_values": ["example1", "example2"],
                "source": "Where this data originates from",
                "transformations": [
                    "Description of transformation 1",
                    "Description of transformation 2"
                ],
                "business_rules": [
                    "Business rule 1",
                    "Business rule 2"
                ]
            }
            ```
            
            Infer as much information as possible from the provided code and lineage.
            If you cannot determine a value with confidence, use "Unknown" or skip the field.
        """)
        
    def describe_table(self, table_name: str, dialect: Optional[str] = None, repo_url: Optional[str] = None):
        """
        Generate a comprehensive description for a table
        
        Args:
            table_name: Name of the table
            dialect: SQL dialect
            repo_url: Repository URL
            
        Returns:
            Table description
        """
        try:
            # Search for the SQL code defining the table
            search_result = self.sql_tools.search_tables(table_name, limit=1)
            sql_code = ""
            
            if search_result.get("files_found", 0) > 0 and len(search_result.get("results", [])) > 0:
                result = search_result["results"][0]
                sql_code = result.get("content_summary", "")
                
                # If we have a full file path, try to get the complete content
                if hasattr(self.sql_tools, "get_file_content") and result.get("file_path"):
                    full_content = self.sql_tools.get_file_content(result.get("file_path"))
                    if full_content:
                        sql_code = full_content
            
            # Get table lineage for additional context
            lineage_result = self.sql_tools.get_table_lineage(
                table_name=table_name,
                direction="upstream",
                max_depth=2,
                dialect=dialect,
                repo_url=repo_url
            )
            
            # Format lineage info as context
            context = json.dumps(lineage_result, indent=2)
            
            # Build the prompt
            prompt = self.table_description_prompt.format(
                table_name=table_name,
                sql_code=sql_code,
                context=context
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
            logger.error(f"Error describing table: {str(e)}")
            return {"error": str(e)}
            
    def describe_column(self, table_name: str, column_name: str, dialect: Optional[str] = None, repo_url: Optional[str] = None):
        """
        Generate a comprehensive description for a column
        
        Args:
            table_name: Name of the table
            column_name: Name of the column
            dialect: SQL dialect
            repo_url: Repository URL
            
        Returns:
            Column description
        """
        try:
            # Validate input parameters
            if not column_name:
                logger.error("Column name is required")
                return {
                    "error": "Column name is required",
                    "column_name": "None",
                    "table_name": table_name or "unknown"
                }
                
            # Search for the SQL code defining the table
            search_result = self.sql_tools.search_tables(table_name, limit=1)
            sql_code = ""
            
            if search_result.get("files_found", 0) > 0 and len(search_result.get("results", [])) > 0:
                result = search_result["results"][0]
                sql_code = result.get("content_summary", "")
                
                # If we have a full file path, try to get the complete content
                if hasattr(self.sql_tools, "get_file_content") and result.get("file_path"):
                    full_content = self.sql_tools.get_file_content(result.get("file_path"))
                    if full_content:
                        sql_code = full_content
            
            # Get column lineage with try-except to handle potential errors
            try:
                lineage_result = self.sql_tools.get_column_lineage(
                    table_name=table_name,
                    column_name=column_name,
                    direction="upstream",
                    max_depth=2
                )
            except Exception as lineage_error:
                logger.error(f"Error getting column lineage: {str(lineage_error)}")
                # Create a default structure for lineage result
                lineage_result = {
                    "table": table_name or "unknown",
                    "column": column_name,
                    "error": str(lineage_error),
                    "levels": {}
                }
            
            # Format lineage info for the prompt - handle case where lineage_result is None or not a dict
            if not lineage_result or not isinstance(lineage_result, dict):
                lineage = json.dumps({"error": "No lineage information available"}, indent=2)
            else:
                lineage = json.dumps(lineage_result, indent=2)
            
            # Build the prompt
            prompt = self.column_description_prompt.format(
                table_name=table_name or "unknown",
                column_name=column_name,
                sql_code=sql_code or "-- No SQL code available",
                lineage=lineage
            )
            
            # Get the model response
            response = self.model.invoke(prompt)
            
            # Parse the response
            try:
                result = self.parser.parse(response.content)
                # Ensure required fields are present
                if "column_name" not in result:
                    result["column_name"] = column_name
                if "table_name" not in result:
                    result["table_name"] = table_name or "unknown"
                return result
            except Exception as e:
                logger.error(f"Error parsing model response: {str(e)}")
                # Return a structured response even if parsing fails
                return {
                    "raw_response": response.content,
                    "column_name": column_name,
                    "table_name": table_name or "unknown"
                }
        except Exception as e:
            logger.error(f"Error describing column: {str(e)}")
            return {
                "error": str(e),
                "column_name": column_name,
                "table_name": table_name or "unknown"
            }
            
    def run(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run the description summarizer agent on the given input data
        
        Args:
            input_data: Input data for the agent, should contain:
                - 'action': Type of description to generate
                - 'params': Parameters for the action
                
        Returns:
            Description results
        """
        action = input_data.get("action", "")
        params = input_data.get("params", {})
        
        if action == "describe_table":
            table_name = params.get("table_name")
            dialect = params.get("dialect")
            repo_url = params.get("repo_url")
            
            if not table_name:
                return {"error": "Table name is required"}
                
            return self.describe_table(table_name, dialect, repo_url)
            
        elif action == "describe_column":
            table_name = params.get("table_name")
            column_name = params.get("column_name")
            dialect = params.get("dialect")
            repo_url = params.get("repo_url")
            
            if not table_name or not column_name:
                return {"error": "Table name and column name are required"}
                
            return self.describe_column(table_name, column_name, dialect, repo_url)
            
        else:
            return {"error": f"Unknown action: {action}"} 