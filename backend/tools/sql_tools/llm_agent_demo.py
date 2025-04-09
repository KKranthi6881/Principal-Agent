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
        
        # Process questions about column location or lineage
        elif ("column" in question or "field" in question or "where" in question or "find" in question) and any(keyword in question for keyword in ["where is", "location", "find", "search", "help me"]):
            # Try to extract column name directly
            column_name = self._extract_column_name_only(question)
            
            if not column_name:
                return "I couldn't identify a specific column in your question. Please specify which column you're looking for."
            
            print(f"  - User is asking about the location of column: {column_name}")
            
            # Search for the column across all tables
            print(f"  - Searching for column '{column_name}' across all tables...")
            
            # Use the more specialized column search functionality
            search_result = self.interface.search_columns(column_name, limit=5)
            
            if search_result.get("files_found", 0) == 0:
                return f"I couldn't find any files referencing the column '{column_name}' in the codebase."
            
            # Generate a response about the column location
            print(f"  - Found {search_result.get('files_found', 0)} files referencing the column")
            print(f"  - Likely tables: {search_result.get('likely_tables', [])}")
            
            return self._generate_column_location_response_from_search(column_name, search_result)
        
        # Process question about column lineage
        elif "column" in question and ("lineage" in question or "trace" in question or "dependency" in question):
            # Extract table and column names
            table_name, column_name = self._extract_table_column(question)
            
            # If only column name is found, try to determine table from previous context or search
            if column_name and not table_name:
                # Check memory first
                if "current_table" in self.memory:
                    table_name = self.memory["current_table"]
                    print(f"  - Using current table from memory: {table_name}")
                else:
                    # Search for the column to find its table
                    print(f"  - Searching for column '{column_name}' to determine its table...")
                    search_result = self.interface.search_sql(f"{column_name}", limit=5)
                    
                    if search_result.get("files_found", 0) > 0:
                        tables = self._find_tables_with_column(search_result, column_name)
                        if tables:
                            table_name = tables[0]["table"]
                            print(f"  - Found potential table for column: {table_name}")
            
            if not table_name or not column_name:
                return "I couldn't identify a specific table and column in your question. Please specify both the table and column you're interested in."
            
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
    
    def _extract_column_name_only(self, question: str) -> str:
        """Extract just a column name from the question"""
        # Look for column patterns with keywords
        for pattern in ["column", "field"]:
            if pattern in question:
                idx = question.find(pattern)
                if idx >= 0:
                    # Extract text after the pattern
                    text_after = question[idx + len(pattern):].strip()
                    
                    # Common separators that might appear after "column" or "field"
                    for separator in ["is", "called", "named", ":"]:
                        if separator in text_after:
                            text_after = text_after.split(separator, 1)[1].strip()
                    
                    # If too many words, take just the first meaningful one
                    words = text_after.split()
                    if words:
                        column = words[0].strip(",.'\"()")
                        if len(column) > 2 and column not in ["the", "are", "is", "a", "an"]:
                            return column
        
        # Look for specific columns mentioned without context
        words = question.split()
        for word in words:
            # Check if the word has common column name patterns like snake_case or camelCase
            if "_" in word or (any(c.isupper() for c in word) and not word.isupper()):
                clean_word = word.strip(",.'\"():")
                if len(clean_word) > 3:
                    return clean_word
                    
        # Extract the most likely column name from the question
        # This logic looks for longer words that sound like field names
        candidates = []
        for word in question.split():
            # Clean the word
            clean_word = word.strip(",.'\"():")
            # Skip short words and common terms
            if len(clean_word) <= 3 or clean_word in ["the", "and", "are", "is", "for", "from", "where", "what", "how", "help", "find", "can", "you", "this", "that"]:
                continue
            candidates.append(clean_word)
        
        # Choose the longest candidate or the one that looks most like a field name
        if candidates:
            # Prefer snake_case or camelCase patterns
            for candidate in candidates:
                if "_" in candidate or (any(c.isupper() for c in candidate) and not candidate.isupper()):
                    return candidate
            # Otherwise return the longest
            return max(candidates, key=len)
        
        return None
        
    def _find_tables_with_column(self, search_result, column_name):
        """Extract tables that seem to contain the specified column"""
        tables_with_column = []
        
        for result in search_result.get("results", []):
            content = result.get("content_summary", "")
            file_path = result.get("file_path", "")
            url = result.get("url", "")
            repo = result.get("repo", "")
            
            # Attempt to identify the table name from content and file path
            table_name = self._extract_table_from_file(file_path, content)
            
            if table_name:
                tables_with_column.append({
                    "table": table_name,
                    "file_path": file_path,
                    "url": url,
                    "repo": repo
                })
        
        return tables_with_column
    
    def _extract_table_from_file(self, file_path, content):
        """Extract potential table name from file path or content"""
        # Try to extract from file path first (DBT naming convention)
        if file_path:
            # Extract the file name without extension
            file_name = file_path.split("/")[-1].split(".")[0]
            
            # Check for common naming patterns
            if any(prefix in file_name for prefix in ["stg_", "dim_", "fct_", "int_", "tbl_"]):
                return file_name
        
        # Try to extract from file content
        if content:
            # Look for table name in CREATE TABLE or similar statements
            content_lower = content.lower()
            
            for pattern in ["create table", "create or replace table", "create view", "select * from"]:
                if pattern in content_lower:
                    idx = content_lower.find(pattern) + len(pattern)
                    end_idx = content_lower.find("\n", idx)
                    if end_idx == -1:
                        end_idx = len(content_lower)
                    
                    table_part = content_lower[idx:end_idx].strip()
                    # Remove any schema prefixes or parentheses
                    table_name = table_part.split(".")[-1].split("(")[0].strip().strip('"\'')
                    if table_name:
                        return table_name
        
        # Fallback to file name without extension
        if file_path:
            return file_path.split("/")[-1].split(".")[0]
        
        return None
    
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
    
    def _generate_column_location_response_from_search(self, column_name, search_result):
        """Generate response for column location questions using search_columns result"""
        response = f"The column '{column_name}' appears to be present in the following table(s):\n\n"
        
        # Group results by likely table
        tables_info = {}
        for result in search_result.get("results", []):
            table_name = result.get("likely_table", "Unknown table")
            if table_name not in tables_info:
                tables_info[table_name] = []
            
            tables_info[table_name].append({
                "file_path": result.get("file_path", ""),
                "url": result.get("url", ""),
                "content_summary": result.get("content_summary", "")
            })
        
        # Generate response for each table
        for table_name, files in tables_info.items():
            response += f"- Table: {table_name}\n"
            
            # Show the first file for each table
            if files:
                file = files[0]
                response += f"  File: {file['file_path']}\n"
                if file.get("url"):
                    response += f"  URL: {file['url']}\n"
            
            response += "\n"
        
        # Store the first table for context in future questions
        likely_tables = search_result.get("likely_tables", [])
        if likely_tables:
            self.memory["current_table"] = likely_tables[0]
        
        # Include a relevant code snippet if available
        if search_result.get("results") and search_result["results"][0].get("content_summary"):
            first_file = search_result["results"][0]
            snippet = first_file.get("content_summary", "")
            
            # Try to extract a more focused snippet around the column
            column_snippet = self._extract_column_snippet(snippet, column_name)
            if column_snippet:
                response += f"Here's a relevant code snippet showing how this column is used:\n\n```sql\n{column_snippet}\n```"
        
        return response
    
    def _extract_column_snippet(self, content, column_name):
        """Extract a relevant code snippet focusing on the column"""
        if not content:
            return None
            
        # Split into lines
        lines = content.split("\n")
        
        # Find lines containing the column name
        matching_lines = []
        for i, line in enumerate(lines):
            if column_name.lower() in line.lower():
                # Get some context lines
                start = max(0, i-2)
                end = min(len(lines), i+3)
                context = "\n".join(lines[start:end])
                matching_lines.append(context)
                break  # Just get the first match for now
        
        if matching_lines:
            return matching_lines[0]
        
        return content[:200] + "..." if len(content) > 200 else content


def main():
    """Main function to run the agent demo"""
    agent = LLMAgentDemo()
    
    # Sample questions to demonstrate
    questions = [
        #"Where does the table fct_order_items come from?",
        #"Can you show me the SQL for stg_tpch_orders?",
        "can you help me where is the orders.clerk_name ?"
       # "Find SQL files with JOIN operations"
    ]
    
    # Process each question
    for question in questions:
        response = agent.answer_question(question)
        print("\n[AGENT RESPONSE]:")
        print(response)
        print("\n" + "=" * 80)


if __name__ == "__main__":
    main() 