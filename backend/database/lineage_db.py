"""
SQLite database connector for storing SQL lineage information
"""

import sqlite3
import logging
import json
import uuid
from typing import Dict, List, Any, Optional, Tuple

# Import the database path from db_setup
from .db_setup import LINEAGE_DB, setup_lineage_db

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class LineageDB:
    """
    SQLite database connector for storing SQL lineage information
    """
    
    def __init__(self, db_path: str = LINEAGE_DB):
        """
        Initialize a new LineageDB
        
        Args:
            db_path: Path to the SQLite database
        """
        self.db_path = db_path
        self._ensure_tables_exist()
        
    def _get_connection(self) -> sqlite3.Connection:
        """Get a connection to the SQLite database"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Return rows as dictionaries
        return conn
        
    def _ensure_tables_exist(self):
        """Ensure the necessary tables exist in the database"""
        # Use the existing setup function from db_setup.py
        setup_lineage_db()
    
    def add_table(self, table_name: str, tech_stack: str, github_path: str = None, 
                  schema_name: str = None, database_name: str = None, 
                  connector_id: str = None, github_repo: str = None,
                  business_description: str = None) -> str:
        """
        Add a table to the lineage database
        
        Args:
            table_name: Name of the table
            tech_stack: Technology stack (tsql, dbt, mysql, postgresql, snowflake)
            github_path: Path to the file in GitHub
            schema_name: Schema name (optional)
            database_name: Database name (optional)
            connector_id: GitHub connector ID
            github_repo: GitHub repository URL
            business_description: Business description of the table
            
        Returns:
            Table ID
        """
        table_id = str(uuid.uuid4())
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                """INSERT INTO tables 
                   (table_id, table_name, schema_name, database_name, github_path, 
                    github_repo, connector_id, tech_stack, business_description) 
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (table_id, table_name, schema_name, database_name, github_path, 
                 github_repo, connector_id, tech_stack, business_description)
            )
            
            conn.commit()
            logger.info(f"Added table {table_name} with tech stack {tech_stack}")
            return table_id
        except Exception as e:
            logger.error(f"Error adding table: {str(e)}")
            conn.rollback()
            raise
        finally:
            conn.close()
    
    def get_table_by_name(self, table_name: str, tech_stack: str = None) -> Dict:
        """
        Get a table by name and optionally tech stack
        
        Args:
            table_name: Name of the table
            tech_stack: Technology stack filter (optional)
            
        Returns:
            Table details or None if not found
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            if tech_stack:
                cursor.execute(
                    """SELECT * FROM tables 
                       WHERE table_name = ? AND tech_stack = ?""",
                    (table_name, tech_stack)
                )
            else:
                cursor.execute(
                    """SELECT * FROM tables 
                       WHERE table_name = ?""",
                    (table_name,)
                )
            
            result = cursor.fetchone()
            if result:
                return dict(result)
            return None
        except Exception as e:
            logger.error(f"Error getting table: {str(e)}")
            raise
        finally:
            conn.close()
    
    def add_column(self, table_id: str, column_name: str, data_type: str = None,
                   is_primary_key: bool = False, is_foreign_key: bool = False,
                   business_description: str = None) -> str:
        """
        Add a column to a table
        
        Args:
            table_id: ID of the table
            column_name: Name of the column
            data_type: Data type of the column
            is_primary_key: Whether the column is a primary key
            is_foreign_key: Whether the column is a foreign key
            business_description: Business description of the column
            
        Returns:
            Column ID
        """
        column_id = str(uuid.uuid4())
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                """INSERT INTO columns 
                   (column_id, table_id, column_name, data_type, 
                    is_primary_key, is_foreign_key, business_description) 
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (column_id, table_id, column_name, data_type, 
                 is_primary_key, is_foreign_key, business_description)
            )
            
            conn.commit()
            logger.info(f"Added column {column_name} to table {table_id}")
            return column_id
        except Exception as e:
            logger.error(f"Error adding column: {str(e)}")
            conn.rollback()
            raise
        finally:
            conn.close()
    
    def get_columns_for_table(self, table_id: str) -> List[Dict]:
        """
        Get all columns for a table
        
        Args:
            table_id: ID of the table
            
        Returns:
            List of column details
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                """SELECT * FROM columns 
                   WHERE table_id = ? 
                   ORDER BY column_name""",
                (table_id,)
            )
            
            result = []
            for row in cursor.fetchall():
                result.append(dict(row))
                
            return result
        except Exception as e:
            logger.error(f"Error getting columns: {str(e)}")
            raise
        finally:
            conn.close()
    
    def add_relationship(self, source_table_id: str, target_table_id: str, 
                         relationship_type: str, source_column_id: str = None,
                         target_column_id: str = None, sql_snippet: str = None,
                         github_path: str = None) -> str:
        """
        Add a relationship between tables or columns
        
        Args:
            source_table_id: ID of the source table
            target_table_id: ID of the target table
            relationship_type: Type of relationship (join, projection, reference, etc.)
            source_column_id: ID of the source column (optional for column-level relationships)
            target_column_id: ID of the target column (optional for column-level relationships)
            sql_snippet: SQL snippet that defines the relationship
            github_path: Path to the GitHub file where the relationship is defined
            
        Returns:
            Relationship ID
        """
        relationship_id = str(uuid.uuid4())
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                """INSERT INTO relationships 
                   (relationship_id, source_table_id, target_table_id, relationship_type,
                    source_column_id, target_column_id, sql_snippet, github_path) 
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (relationship_id, source_table_id, target_table_id, relationship_type,
                 source_column_id, target_column_id, sql_snippet, github_path)
            )
            
            conn.commit()
            logger.info(f"Added {relationship_type} relationship between tables {source_table_id} and {target_table_id}")
            return relationship_id
        except Exception as e:
            logger.error(f"Error adding relationship: {str(e)}")
            conn.rollback()
            raise
        finally:
            conn.close()
    
    def get_relationships_for_table(self, table_id: str, relationship_type: str = None) -> List[Dict]:
        """
        Get relationships for a table
        
        Args:
            table_id: ID of the table
            relationship_type: Type of relationship to filter by (optional)
            
        Returns:
            List of relationship details
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            if relationship_type:
                cursor.execute(
                    """SELECT r.*, 
                          st.table_name as source_table_name,
                          tt.table_name as target_table_name,
                          sc.column_name as source_column_name,
                          tc.column_name as target_column_name
                       FROM relationships r
                       JOIN tables st ON r.source_table_id = st.table_id
                       JOIN tables tt ON r.target_table_id = tt.table_id
                       LEFT JOIN columns sc ON r.source_column_id = sc.column_id
                       LEFT JOIN columns tc ON r.target_column_id = tc.column_id
                       WHERE (r.source_table_id = ? OR r.target_table_id = ?)
                       AND r.relationship_type = ?""",
                    (table_id, table_id, relationship_type)
                )
            else:
                cursor.execute(
                    """SELECT r.*, 
                          st.table_name as source_table_name,
                          tt.table_name as target_table_name,
                          sc.column_name as source_column_name,
                          tc.column_name as target_column_name
                       FROM relationships r
                       JOIN tables st ON r.source_table_id = st.table_id
                       JOIN tables tt ON r.target_table_id = tt.table_id
                       LEFT JOIN columns sc ON r.source_column_id = sc.column_id
                       LEFT JOIN columns tc ON r.target_column_id = tc.column_id
                       WHERE r.source_table_id = ? OR r.target_table_id = ?""",
                    (table_id, table_id)
                )
            
            result = []
            for row in cursor.fetchall():
                result.append(dict(row))
                
            return result
        except Exception as e:
            logger.error(f"Error getting relationships: {str(e)}")
            raise
        finally:
            conn.close()
    
    def add_lineage_definition(self, root_table_id: str, lineage_json: Dict, tech_stack: str) -> str:
        """
        Add a lineage definition for visualization
        
        Args:
            root_table_id: ID of the root table
            lineage_json: JSON object with lineage information
            tech_stack: Technology stack
            
        Returns:
            Lineage ID
        """
        lineage_id = str(uuid.uuid4())
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            lineage_json_str = json.dumps(lineage_json)
                
            cursor.execute(
                """INSERT INTO lineage_definitions 
                   (lineage_id, root_table_id, lineage_json, tech_stack) 
                   VALUES (?, ?, ?, ?)""",
                (lineage_id, root_table_id, lineage_json_str, tech_stack)
            )
            
            conn.commit()
            logger.info(f"Added lineage definition for root table {root_table_id}")
            return lineage_id
        except Exception as e:
            logger.error(f"Error adding lineage definition: {str(e)}")
            conn.rollback()
            raise
        finally:
            conn.close()
    
    def get_lineage_definition(self, root_table_id: str = None, lineage_id: str = None) -> Dict:
        """
        Get a lineage definition
        
        Args:
            root_table_id: ID of the root table (if looking up by table)
            lineage_id: ID of the lineage definition (if looking up directly)
            
        Returns:
            Lineage definition including JSON
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            if lineage_id:
                cursor.execute(
                    """SELECT ld.*, t.table_name 
                       FROM lineage_definitions ld
                       JOIN tables t ON ld.root_table_id = t.table_id
                       WHERE ld.lineage_id = ?""",
                    (lineage_id,)
                )
            else:
                cursor.execute(
                    """SELECT ld.*, t.table_name 
                       FROM lineage_definitions ld
                       JOIN tables t ON ld.root_table_id = t.table_id
                       WHERE ld.root_table_id = ?
                       ORDER BY ld.updated_at DESC
                       LIMIT 1""",
                    (root_table_id,)
                )
            
            result = cursor.fetchone()
            if result:
                row_dict = dict(result)
                
                # Parse JSON field
                if row_dict.get('lineage_json'):
                    try:
                        row_dict['lineage_json'] = json.loads(row_dict['lineage_json'])
                    except (json.JSONDecodeError, TypeError):
                        pass  # Keep as string if not valid JSON
                
                return row_dict
            return None
        except Exception as e:
            logger.error(f"Error getting lineage definition: {str(e)}")
            raise
        finally:
            conn.close()
    
    def get_lineage_by_tech_stack(self, tech_stack: str) -> List[Dict]:
        """
        Get all lineage definitions for a specific tech stack
        
        Args:
            tech_stack: Technology stack
            
        Returns:
            List of lineage definitions
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                """SELECT ld.*, t.table_name 
                   FROM lineage_definitions ld
                   JOIN tables t ON ld.root_table_id = t.table_id
                   WHERE ld.tech_stack = ?
                   ORDER BY t.table_name, ld.updated_at DESC""",
                (tech_stack,)
            )
            
            result = []
            for row in cursor.fetchall():
                row_dict = dict(row)
                
                # Parse JSON field
                if row_dict.get('lineage_json'):
                    try:
                        row_dict['lineage_json'] = json.loads(row_dict['lineage_json'])
                    except (json.JSONDecodeError, TypeError):
                        pass  # Keep as string if not valid JSON
                
                result.append(row_dict)
                
            return result
        except Exception as e:
            logger.error(f"Error getting lineage by tech stack: {str(e)}")
            raise
        finally:
            conn.close()