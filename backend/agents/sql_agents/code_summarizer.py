"""
Code Summarizer Agent module that defines the CodeSummarizerAgent class
This agent summarizes SQL code and provides explanations
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

class CodeSummarizerAgent(Agent):
    """
    Code Summarizer Agent that summarizes SQL code and provides explanations
    
    Attributes:
        name (str): The name of the agent
        description (str): A description of what the agent does
        model: Language model to use
        sql_tools: SQL analysis tools
    """
    
    def __init__(
        self, 
        name: str = "Code Summarizer Agent", 
        description: str = "Summarizes SQL code and provides explanations",
        model = None,
        sql_tools = None
    ):
        """
        Initialize a new CodeSummarizerAgent
        
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
        self.summarize_code_prompt = ChatPromptTemplate.from_template("""
            You are a SQL Code Analysis expert. Your job is to summarize SQL code and provide explanations
            about what it does.
            
            SQL Code:
            ```sql
            {sql_code}
            ```
            
            Dialect: {dialect}
            
            Please provide a detailed summary of this SQL code in JSON format with the following structure:
            
            ```
            {
                "title": "Brief descriptive title for the SQL script",
                "summary": "High-level summary of what the script does",
                "tables": {
                    "input_tables": [
                        {
                            "name": "table_name",
                            "description": "description of how this table is used"
                        }
                    ],
                    "output_tables": [
                        {
                            "name": "table_name",
                            "description": "description of what is written to this table"
                        }
                    ]
                },
                "columns": [
                    {
                        "name": "column_name",
                        "description": "description of this column's purpose and transformations"
                    }
                ],
                "logic": [
                    {
                        "description": "description of a logical component",
                        "lines": "line numbers or relevant part of the code"
                    }
                ],
                "business_purpose": "Explanation of the business purpose of this script"
            }
            ```
            
            Focus on explaining the business logic and purpose of the code, not just the syntax.
        """)
        
        self.describe_column_prompt = ChatPromptTemplate.from_template("""
            You are a SQL Column Analysis expert. Your job is to describe the purpose and context of a column
            in a SQL table.
            
            Table: {table_name}
            Column: {column_name}
            
            SQL Code:
            ```sql
            {sql_code}
            ```
            
            Lineage Information:
            {lineage_info}
            
            Please provide a detailed description of this column in JSON format with the following structure:
            
            ```
            {
                "column": "column_name",
                "table": "table_name",
                "business_name": "Business-friendly name for this column",
                "description": "Detailed description of the column's purpose",
                "data_type": "Inferred data type",
                "business_rules": [
                    "Business rule 1",
                    "Business rule 2"
                ],
                "transformations": [
                    "Transformation or calculation 1",
                    "Transformation or calculation 2"
                ],
                "source": "Where this data originates from",
                "usage": "How this column is typically used in business context"
            }
            ```
            
            Be thorough in your analysis and focus on the business context.
        """)
        
    def summarize_code(self, sql_code: str, dialect: Optional[str] = None):
        """
        Summarize SQL code
        
        Args:
            sql_code: SQL code to summarize
            dialect: SQL dialect
            
        Returns:
            Code summary
        """
        try:
            # Build the prompt
            prompt = self.summarize_code_prompt.format(
                sql_code=sql_code,
                dialect=dialect or "unknown"
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
            logger.error(f"Error summarizing code: {str(e)}")
            return {"error": str(e)}
            
    def describe_column(self, table_name: str, column_name: str, dialect: Optional[str] = None, repo_url: Optional[str] = None):
        """
        Describe a column's purpose and context
        
        Args:
            table_name: Name of the table
            column_name: Name of the column
            dialect: SQL dialect
            repo_url: Repository URL
            
        Returns:
            Column description
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
            
            # Get column lineage
            lineage_result = self.sql_tools.get_column_lineage(
                table_name=table_name,
                column_name=column_name,
                direction="upstream",
                max_depth=2,
                dialect=dialect,
                repo_url=repo_url
            )
            
            # Format lineage info for the prompt
            lineage_info = json.dumps(lineage_result, indent=2)
            
            # Build the prompt
            prompt = self.describe_column_prompt.format(
                table_name=table_name,
                column_name=column_name,
                sql_code=sql_code,
                lineage_info=lineage_info
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
            logger.error(f"Error describing column: {str(e)}")
            return {"error": str(e)}
            
    def summarize_file(self, file_path: str, dialect: Optional[str] = None):
        """
        Summarize a SQL file
        
        Args:
            file_path: Path to the SQL file
            dialect: SQL dialect
            
        Returns:
            File summary
        """
        try:
            # Read the file content
            sql_code = ""
            if hasattr(self.sql_tools, "get_file_content"):
                sql_code = self.sql_tools.get_file_content(file_path)
            
            if not sql_code:
                return {"error": f"Could not read file content for {file_path}"}
                
            # Summarize the code
            return self.summarize_code(sql_code, dialect)
        except Exception as e:
            logger.error(f"Error summarizing file: {str(e)}")
            return {"error": str(e)}
            
    def run(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run the code summarizer agent on the given input data
        
        Args:
            input_data: Input data for the agent, should contain:
                - 'action': Type of summarization to perform
                - 'params': Parameters for the action
                
        Returns:
            Summarization results
        """
        action = input_data.get("action", "")
        params = input_data.get("params", {})
        
        if action == "summarize_code":
            sql_code = params.get("sql_code")
            dialect = params.get("dialect")
            
            if not sql_code:
                return {"error": "SQL code is required"}
                
            return self.summarize_code(sql_code, dialect)
            
        elif action == "describe_column":
            table_name = params.get("table_name")
            column_name = params.get("column_name")
            dialect = params.get("dialect")
            repo_url = params.get("repo_url")
            
            if not table_name or not column_name:
                return {"error": "Table name and column name are required"}
                
            return self.describe_column(table_name, column_name, dialect, repo_url)
            
        elif action == "summarize_file":
            file_path = params.get("file_path")
            dialect = params.get("dialect")
            
            if not file_path:
                return {"error": "File path is required"}
                
            return self.summarize_file(file_path, dialect)
            
        else:
            return {"error": f"Unknown action: {action}"} 