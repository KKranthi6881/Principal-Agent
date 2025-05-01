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
            You are a Data Dictionary Expert tasked with creating consistent, concise descriptions for SQL tables.
            
            Table Name: {table_name}
            
            SQL Code:
            ```sql
            {sql_code}
            ```
            
            Additional Context:
            {context}

            # INSTRUCTIONS
            1. Analyze the table structure, code patterns, and naming conventions
            2. Generate a clear, concise description focusing on BUSINESS VALUE first
            3. Include technical details that would help developers and analysts
            4. ALWAYS provide GitHub URLs when available
            5. Be CONSISTENT in formatting and level of detail
            6. Keep descriptions CRISP and to the point - avoid unnecessary words
            
            # OUTPUT FORMAT
            Provide your description in this exact JSON format:
            
            ```json
            {
                "table_name": "The exact table name",
                "business_name": "Business-friendly table name (1-3 words)",
                "technical_description": "Clear technical description (1-2 sentences)",
                "business_description": "Business-focused description (2-3 sentences)",
                "domain": "Business domain this table belongs to (1-2 words)",
                "primary_key": ["column1", "column2"],
                "update_frequency": "How often this table is updated",
                "main_columns": [
                    {
                        "column": "column_name",
                        "business_name": "Clear business name",
                        "description": "Concise purpose description",
                        "data_type": "Inferred data type"
                    }
                ],
                "relationships": [
                    {
                        "related_table": "table_name",
                        "relationship_type": "parent/child/reference",
                        "description": "Short relationship description"
                    }
                ],
                "github_urls": [
                    {
                        "file": "Filename",
                        "url": "Complete GitHub URL"
                    }
                ]
            }
            ```
            
            If you cannot determine a value with high confidence, use "Unknown" as the value.
            ALWAYS include the "github_urls" section even if it's empty.
        """)
        
        self.column_description_prompt = ChatPromptTemplate.from_template("""
            You are a Data Dictionary Expert tasked with creating consistent, concise descriptions for SQL columns.
            
            Table: {table_name}
            Column: {column_name}
            
            SQL Code:
            ```sql
            {sql_code}
            ```
            
            Column Lineage:
            {lineage}
            
            # INSTRUCTIONS
            1. Analyze how this column is created, used, and transformed
            2. Generate a CONCISE description focusing on BUSINESS VALUE first
            3. Include technical details that would help developers and analysts
            4. ALWAYS provide GitHub URLs when available
            5. Be CONSISTENT in formatting and level of detail
            6. Keep descriptions CRISP and to the point - avoid unnecessary words
            
            # OUTPUT FORMAT
            Provide your description in this exact JSON format:
            
            ```json
            {
                "column_name": "The exact column name",
                "table_name": "The exact table name",
                "business_name": "Business-friendly name (1-3 words)",
                "technical_description": "Technical description (1-2 sentences)",
                "business_description": "Business-focused description (1-2 sentences)",
                "data_type": "Inferred data type",
                "nullable": true/false,
                "primary_key": true/false,
                "constraints": ["constraint1", "constraint2"],
                "source": "Origin of this data",
                "transformations": [
                    "Transformation 1 - be specific and concise",
                    "Transformation 2 - be specific and concise"
                ],
                "business_rules": [
                    "Business rule 1 - be specific",
                    "Business rule 2 - be specific"
                ],
                "github_urls": [
                    {
                        "file": "Filename",
                        "url": "Complete GitHub URL"
                    }
                ]
            }
            ```
            
            If you cannot determine a value with high confidence, use "Unknown" as the value.
            ALWAYS include the "github_urls" section even if it's empty.
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