#!/usr/bin/env python3

"""
Enhanced DBT Column Extractor

This utility provides improved column extraction for DBT SQL files.
It automatically handles common DBT patterns including:
- CTEs with 'final' blocks
- Select statements with aliases
- Both SQL and YAML files
"""

import os
import re
import logging
import sqlite3
import uuid
from typing import List, Dict, Any, Optional

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DBTColumnExtractor:
    """Enhanced column extractor for DBT SQL files"""
    
    def __init__(self, db_path: str = None):
        """Initialize the extractor with optional database path"""
        if db_path:
            self.db_path = db_path
        else:
            # Use absolute path to ensure database can be found regardless of execution context
            backend_dir = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '../../..'))
            self.db_path = os.path.join(backend_dir, 'database/lineage.db')
            
        logger.info(f"DBTColumnExtractor initialized with database path: {self.db_path}")
    
    def extract_columns_from_sql(self, sql_text: str) -> List[Dict[str, Any]]:
        """Extract column information from SQL text"""
        columns = []
        
        # Find the 'final' CTE if it exists - this is a common pattern in DBT models
        final_cte_pattern = r'final\s+as\s*\(\s*select\s+(.+?)\s+from'
        final_match = re.search(final_cte_pattern, sql_text, re.IGNORECASE | re.DOTALL)
        
        if final_match:
            # Extract columns from the final CTE
            col_text = final_match.group(1)
            col_parts = self._split_column_list(col_text)
            
            # Extract column names/aliases
            for col in col_parts:
                column_name = self._extract_column_name(col)
                if column_name:
                    columns.append({"name": column_name})
        
        # If no 'final' CTE found, look for the main SELECT statement
        if not columns:
            # Look for main SELECT pattern after all CTEs
            main_select_pattern = r'select\s+(.+?)\s+from'
            main_match = re.search(main_select_pattern, sql_text.split(')')[-1], re.IGNORECASE | re.DOTALL)
            
            if main_match:
                col_text = main_match.group(1)
                if col_text.strip() != '*':  # Skip 'SELECT *' cases
                    col_parts = self._split_column_list(col_text)
                    
                    # Extract column names/aliases
                    for col in col_parts:
                        column_name = self._extract_column_name(col)
                        if column_name:
                            columns.append({"name": column_name})
        
        return columns
    
    def _split_column_list(self, col_text: str) -> List[str]:
        """Split a column list by commas, respecting nested parentheses"""
        col_parts = []
        current_part = ""
        paren_level = 0
        
        for char in col_text:
            if char == '(':
                paren_level += 1
                current_part += char
            elif char == ')':
                paren_level -= 1
                current_part += char
            elif char == ',' and paren_level == 0:
                col_parts.append(current_part.strip())
                current_part = ""
            else:
                current_part += char
        
        # Add the last part
        if current_part.strip():
            col_parts.append(current_part.strip())
        
        return col_parts
    
    def _extract_column_name(self, col_expr: str) -> Optional[str]:
        """Extract column name from a column expression"""
        # Check for explicit alias with 'as' keyword
        alias_match = re.search(r'(?i)\s+as\s+([a-zA-Z0-9_]+)', col_expr)
        if alias_match:
            column_name = alias_match.group(1)
        else:
            # Use the last part of the column expression (after the last dot)
            parts = col_expr.split('.')
            column_name = parts[-1].strip()
        
        # Clean up the name
        column_name = column_name.strip('"`[]')
        
        return column_name if column_name and column_name != '*' else None
    
    def find_dbt_sql_files(self, repo_path: str) -> List[str]:
        """Find all DBT SQL files in a repository"""
        sql_files = []
        for root, _, files in os.walk(repo_path):
            for file in files:
                if file.endswith('.sql'):
                    # Only include DBT model files (typically in models directory)
                    if 'models' in root or 'analyses' in root:
                        sql_files.append(os.path.join(root, file))
        return sql_files
    
    def get_table_id_by_name(self, table_name: str) -> Optional[str]:
        """Get table ID from database by name"""
        if not self.db_path:
            return None
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute("SELECT table_id FROM tables WHERE table_name = ?", (table_name,))
            result = cursor.fetchone()
            return result[0] if result else None
        except Exception as e:
            logger.error(f"Database error getting table ID: {str(e)}")
            return None
        finally:
            conn.close()
    
    def _check_database_access(self):
        """Check if the database file exists and is accessible"""
        if not self.db_path:
            logger.warning("No database path specified")
            return False
            
        if not os.path.exists(self.db_path):
            logger.error(f"Database file does not exist at path: {self.db_path}")
            return False
            
        try:
            # Test connection
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='columns'")
            result = cursor.fetchone()
            conn.close()
            
            if not result:
                logger.error(f"Database exists but 'columns' table not found")
                return False
                
            return True
        except Exception as e:
            logger.error(f"Database access error: {str(e)}")
            return False
    
    def store_columns_in_database(self, table_id: str, columns: List[Dict[str, Any]]):
        """Store columns in the lineage database"""
        if not self._check_database_access():
            logger.error(f"Skipping column storage due to database access issues")
            return
        
        logger.info(f"Storing {len(columns)} columns for table ID {table_id} in database at {self.db_path}")
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Check if columns already exist for this table
            cursor.execute("SELECT COUNT(*) FROM columns WHERE table_id = ?", (table_id,))
            count = cursor.fetchone()[0]
            
            if count > 0:
                logger.info(f"Table ID {table_id} already has {count} columns, deleting existing columns before adding new ones")
                cursor.execute("DELETE FROM columns WHERE table_id = ?", (table_id,))
            
            for col in columns:
                column_id = str(uuid.uuid4())
                cursor.execute(
                    """INSERT INTO columns 
                       (column_id, table_id, column_name, data_type, is_primary_key, is_foreign_key, business_description) 
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (column_id, table_id, col["name"], None, False, False, "")
                )
                logger.info(f"Added column {col['name']} to table ID {table_id}")
            
            conn.commit()
            logger.info(f"Successfully stored {len(columns)} columns for table ID {table_id}")
        except Exception as e:
            logger.error(f"Failed to store columns in database: {str(e)}")
            if 'conn' in locals():
                conn.rollback()
        finally:
            if 'conn' in locals():
                conn.close()
    
    def process_all_dbt_files(self, repo_path: str, force_refresh: bool = False):
        """Process all DBT files in a repository and store columns in the database"""
        # Find all DBT SQL files
        sql_files = self.find_dbt_sql_files(repo_path)
        logger.info(f"Found {len(sql_files)} DBT SQL files in {repo_path}")
        
        # Process each file
        for sql_file in sql_files:
            try:
                # Extract table name from file path
                table_name = os.path.basename(sql_file)
                if table_name.endswith('.sql'):
                    table_name = table_name[:-4]
                
                # Get table ID from database
                table_id = self.get_table_id_by_name(table_name)
                if not table_id:
                    logger.warning(f"Table {table_name} not found in database, skipping column extraction")
                    continue
                
                # Check if table already has columns (skip unless force_refresh)
                if not force_refresh:
                    conn = sqlite3.connect(self.db_path)
                    cursor = conn.cursor()
                    cursor.execute("SELECT COUNT(*) FROM columns WHERE table_id = ?", (table_id,))
                    count = cursor.fetchone()[0]
                    conn.close()
                    
                    if count > 0:
                        logger.info(f"Table {table_name} already has {count} columns, skipping")
                        continue
                
                # Read SQL file
                with open(sql_file, 'r') as f:
                    sql_text = f.read()
                
                # Extract columns
                columns = self.extract_columns_from_sql(sql_text)
                logger.info(f"Extracted {len(columns)} columns from {sql_file}")
                
                # Store columns in database
                if columns:
                    self.store_columns_in_database(table_id, columns)
            except Exception as e:
                logger.error(f"Error processing {sql_file}: {str(e)}")

# Example usage
if __name__ == "__main__":
    import sys
    
    # Get repository path from command line
    if len(sys.argv) > 1:
        repo_path = sys.argv[1]
    else:
        # Default to common repo path
        repo_path = '/Users/Kranthi_1/Principal-Agent/backend/storage/repos/'
    
    force_refresh = '--force' in sys.argv
    
    # Create extractor
    extractor = DBTColumnExtractor()
    
    # Process all repositories under the given path
    if os.path.exists(repo_path):
        if os.path.isdir(repo_path):
            # Process specific repository
            extractor.process_all_dbt_files(repo_path, force_refresh)
        else:
            # Process a specific file
            with open(repo_path, 'r') as f:
                sql_text = f.read()
            
            columns = extractor.extract_columns_from_sql(sql_text)
            print(f"Extracted {len(columns)} columns from {repo_path}:")
            for col in columns:
                print(f"  - {col['name']}")
    else:
        print(f"Repository path {repo_path} does not exist")
