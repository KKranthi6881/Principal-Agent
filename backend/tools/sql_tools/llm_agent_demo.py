#!/usr/bin/env python3
"""
LLM Agent Demo for SQL Analysis Tools

This script demonstrates how an LLM agent would use the SQL analysis tools
to answer questions about SQL lineage and data flow.
"""

import os
import sys
import json
import logging
from pathlib import Path
from typing import Dict, List, Any

# Configure logging - keep it minimal for cleaner output
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

# Add backend directory to path
backend_dir = Path(__file__).parent.parent.parent
if str(backend_dir) not in sys.path:
    sys.path.append(str(backend_dir))

# Import the LLM interface
from tools.sql_tools.llm_interface import llm_interface

class LLMAgentDemo:
    """
    Demonstration of how an LLM agent would interact with the SQL tools
    """
    
    def __init__(self):
        """Initialize the agent demo"""
        self.interface = llm_interface
        self.memory = {}  # Simple memory to store context between calls
    
    def print_json(self, obj, compact=False):
        """Pretty print JSON object"""
        indent = None if compact else 2
        print(json.dumps(obj, indent=indent))
    
    def answer_question(self, question: str) -> str:
        """
        Answer a question about SQL lineage using the tools
        
        Args:
            question: User's question about SQL lineage
            
        Returns:
            Response from the agent
        """
        question = question.lower().strip()
        
        print(f"\n[USER QUESTION]: {question}")
        print("\n[AGENT THINKING]:")
        
        # Process question about table lineage
        if "where does" in question and "come from" in question:
            # Extract table name
            table_name = self._extract_table_name(question)
            if not table_name:
                return "I couldn't identify a specific table in your question. Please specify which table you're interested in."
            
            print(f"  - User is asking about upstream lineage for table: {table_name}")
            print(f"  - I should search for this table and trace its upstream lineage")
            
            # First search for the table
            print(f"  - Searching for table '{table_name}'...")
            search_result = self.interface.search_tables(table_name, limit=3)
            
            if search_result.get("files_found", 0) == 0:
                return f"I couldn't find any files related to table '{table_name}' in the codebase."
            
            # Get the repo URL from search results
            repo_url = None
            if search_result.get("results") and len(search_result["results"]) > 0:
                repo_url = search_result["results"][0].get("repo")
                print(f"  - Found table in repository: {repo_url}")
                
                # Store this in memory for future questions
                self.memory["current_repo"] = repo_url
                self.memory["current_table"] = table_name
            
            # Trace upstream lineage
            print(f"  - Tracing upstream lineage for table '{table_name}'...")
            lineage_result = self.interface.get_table_lineage(
                table_name=table_name,
                direction="upstream",
                max_depth=2,
                repo_url=repo_url
            )
            
            # If there's an error, return it
            if "error" in lineage_result:
                return f"I encountered an error while tracing lineage: {lineage_result['error']}"
            
            # Generate the response
            print(f"  - Generating response based on lineage results")
            return self._generate_upstream_response(lineage_result)
        
        # Process question about column lineage
        elif "column" in question and ("where" in question or "how" in question or "lineage" in question):
            # Extract table and column names
            table_name, column_name = self._extract_table_column(question)
            
            if not table_name or not column_name:
                if "current_table" in self.memory:
                    table_name = self.memory["current_table"]
                    print(f"  - Using current table from memory: {table_name}")
                else:
                    return "I couldn't identify a specific table and column in your question. Please specify which column you're interested in."
            
            print(f"  - User is asking about column lineage for: {table_name}.{column_name}")
            
            # Get repo URL from memory if available
            repo_url = self.memory.get("current_repo")
            
            # Trace column lineage
            print(f"  - Tracing column lineage for {table_name}.{column_name}...")
            column_result = self.interface.get_column_lineage(
                table_name=table_name,
                column_name=column_name,
                direction="upstream",
                max_depth=2,
                repo_url=repo_url
            )
            
            # If there's an error, return it
            if "error" in column_result:
                return f"I encountered an error while tracing column lineage: {column_result['error']}"
            
            # Generate the response
            print(f"  - Generating response based on column lineage results")
            return self._generate_column_response(column_result)
        
        # Process question about SQL implementation
        elif "show" in question and "sql" in question:
            # Extract table name
            table_name = self._extract_table_name(question)
            if not table_name and "current_table" in self.memory:
                table_name = self.memory["current_table"]
                print(f"  - Using current table from memory: {table_name}")
            
            if not table_name:
                return "I couldn't identify a specific table in your question. Please specify which table you're interested in."
            
            print(f"  - User is asking to see SQL implementation for table: {table_name}")
            
            # Search for the table
            search_result = self.interface.search_tables(table_name, limit=1)
            
            if search_result.get("files_found", 0) == 0:
                return f"I couldn't find any SQL files for table '{table_name}' in the codebase."
            
            # Generate the response
            print(f"  - Generating response with SQL implementation")
            return self._generate_sql_response(search_result, table_name)
        
        # Process general search query
        else:
            print(f"  - Treating as a general search query")
            search_terms = question.replace("?", "").split()
            query = " ".join([term for term in search_terms if len(term) > 3])
            
            # Search for SQL files
            search_result = self.interface.search_sql(query, limit=5)
            
            if search_result.get("files_found", 0) == 0:
                return f"I couldn't find any SQL files matching your query in the codebase."
            
            # Generate the response
            print(f"  - Generating response based on search results")
            return self._generate_search_response(search_result, query)
    
    def _extract_table_name(self, question: str) -> str:
        """Extract table name from question"""
        # Simple pattern matching (a real LLM would do better)
        patterns = [
            "table", "from", "for", "about", "in", "does"
        ]
        
        words = question.split()
        for i, word in enumerate(words):
            if word in patterns and i < len(words) - 1:
                # Check next word as potential table name
                candidate = words[i + 1].strip(",.'\"()")
                if len(candidate) > 2 and candidate not in ["the", "and", "come", "where", "what"]:
                    return candidate
        
        # Check for specific patterns with table names
        if "where does" in question and "come from" in question:
            parts = question.split("where does")[1].split("come from")[0].strip()
            if parts:
                return parts
        
        return None
    
    def _extract_table_column(self, question: str) -> tuple:
        """Extract table and column names from question"""
        # Simple pattern matching (a real LLM would do better)
        table_name = None
        column_name = None
        
        # Look for table.column pattern
        words = question.split()
        for word in words:
            if '.' in word:
                parts = word.strip(",.'\"()").split('.')
                if len(parts) == 2:
                    table_name = parts[0]
                    column_name = parts[1]
                    return table_name, column_name
        
        # Look for "column X in table Y" pattern
        if "column" in question and "in" in question:
            column_idx = question.find("column")
            in_idx = question.find("in", column_idx)
            
            if column_idx >= 0 and in_idx > column_idx:
                column_part = question[column_idx + 7:in_idx].strip()
                table_part = question[in_idx + 3:].strip().split()[0].strip(",.'\"()")
                
                return table_part, column_part
        
        # Look for "column X" pattern
        if "column" in question:
            column_idx = question.find("column")
            if column_idx >= 0 and column_idx + 7 < len(question):
                column_part = question[column_idx + 7:].strip().split()[0].strip(",.'\"()")
                return table_name, column_part
        
        return table_name, column_name
    
    def _generate_upstream_response(self, lineage_result: Dict[str, Any]) -> str:
        """Generate response for upstream lineage question"""
        table_name = lineage_result["table"]
        dialect = lineage_result["dialect_used"]
        summary = lineage_result.get("summary", "")
        
        response = f"The table '{table_name}' "
        
        # Check if there are dependencies
        level_0 = lineage_result.get("levels", {}).get("0", [])
        level_1 = lineage_result.get("levels", {}).get("1", [])
        
        if not level_1:
            return f"{response}doesn't seem to have any upstream dependencies. It might be a source table."
        
        # Format response
        response += f"is defined using data from the following tables:\n\n"
        
        for dep in level_1:
            src_table = dep.get("name", "")
            file_path = dep.get("file_path", "")
            
            if src_table and file_path:
                response += f"- {src_table} (defined in {file_path})\n"
            elif src_table:
                response += f"- {src_table}\n"
        
        # Add file information for the main table
        if level_0:
            main_file = level_0[0].get("file_path", "")
            if main_file:
                response += f"\nThe table '{table_name}' is defined in {main_file}."
        
        return response
    
    def _generate_column_response(self, column_result: Dict[str, Any]) -> str:
        """Generate response for column lineage question"""
        table_name = column_result["table"]
        column_name = column_result["column"]
        
        response = f"The column '{column_name}' in table '{table_name}' "
        
        # Check the column chain
        column_chain = column_result.get("column_chain", [])
        if not column_chain or len(column_chain) <= 1:
            return f"{response}doesn't have any traceable upstream sources in the codebase."
        
        # Format response based on levels
        level_1_columns = column_result.get("levels", {}).get("1", [])
        
        if level_1_columns:
            response += "is derived from the following source columns:\n\n"
            
            for col_info in level_1_columns:
                col_table = col_info.get("table", "")
                col_name = col_info.get("column", "")
                file_path = col_info.get("file_path", "")
                
                if col_table and col_name:
                    response += f"- {col_table}.{col_name}"
                    if file_path:
                        response += f" (in {file_path})"
                    response += "\n"
        
        return response
    
    def _generate_sql_response(self, search_result: Dict[str, Any], table_name: str) -> str:
        """Generate response with SQL implementation"""
        if search_result.get("files_found", 0) == 0:
            return f"I couldn't find any SQL files for table '{table_name}'."
        
        # Get the first result which should be the most relevant
        first_result = search_result["results"][0]
        file_path = first_result.get("file_path", "")
        content_summary = first_result.get("content_summary", "")
        
        response = f"Here's the SQL implementation for '{table_name}' from {file_path}:\n\n```sql\n{content_summary}\n```"
        
        # Add a link to the full file if available
        url = first_result.get("url")
        if url:
            response += f"\n\nYou can view the complete file at: {url}"
        
        return response
    
    def _generate_search_response(self, search_result: Dict[str, Any], query: str) -> str:
        """Generate response for general search query"""
        files_found = search_result.get("files_found", 0)
        
        if files_found == 0:
            return f"I couldn't find any SQL files matching '{query}'."
        
        response = f"I found {files_found} SQL files that match your query. Here are the most relevant ones:\n\n"
        
        for i, result in enumerate(search_result["results"], 1):
            file_path = result.get("file_path", "")
            dialect = result.get("dialect", "unknown")
            url = result.get("url", "")
            
            response += f"{i}. {file_path} ({dialect} dialect)"
            if url:
                response += f"\n   URL: {url}"
            response += "\n\n"
        
        return response


def main():
    """Main function to run the agent demo"""
    agent = LLMAgentDemo()
    
    # Sample questions to demonstrate
    questions = [
        "Where does the table fct_order_items come from?",
        "Can you show me the SQL for stg_tpch_orders?",
        "What is the lineage of order_key column in fct_order_items?",
        "Find SQL files with JOIN operations"
    ]
    
    # Process each question
    for question in questions:
        response = agent.answer_question(question)
        print("\n[AGENT RESPONSE]:")
        print(response)
        print("\n" + "=" * 80)


if __name__ == "__main__":
    main() 