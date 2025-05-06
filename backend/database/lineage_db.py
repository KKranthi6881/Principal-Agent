"""
SQLite database connector for storing SQL lineage information
"""

import os
import sqlite3
import logging
import json
import uuid
from typing import Dict, List, Tuple, Any, Optional

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
    
    def create_or_get_table(self, table_name: str, tech_stack: str, github_path: str = None, 
                          schema_name: str = None, database_name: str = None, 
                          connector_id: str = None, github_repo: str = None,
                          business_description: str = None) -> str:
        """
        Create a table if it doesn't exist, or get the existing table ID
        
        Args:
            table_name: Name of the table
            tech_stack: Technology stack
            github_path: Path to the file in GitHub
            schema_name: Name of the schema
            database_name: Name of the database
            connector_id: ID of the connector
            github_repo: GitHub repository URL
            business_description: Business description
            
        Returns:
            Table ID
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # Check if table already exists
            cursor.execute(
                "SELECT table_id FROM tables WHERE table_name = ? AND (schema_name = ? OR (schema_name IS NULL AND ? IS NULL))",
                (table_name, schema_name, schema_name)
            )
            
            result = cursor.fetchone()
            if result:
                # Table already exists, return the ID
                return result["table_id"]
            
            # Table doesn't exist, create it
            table_id = str(uuid.uuid4())
            
            cursor.execute(
                """INSERT INTO tables 
                   (table_id, table_name, schema_name, database_name, github_path, github_repo, connector_id, tech_stack, business_description, created_at, updated_at) 
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))""",
                (table_id, table_name, schema_name, database_name, github_path, github_repo, connector_id, tech_stack, business_description)
            )
            
            conn.commit()
            logger.info(f"Created table: {table_name} with ID {table_id}")
            return table_id
        except Exception as e:
            logger.error(f"Error creating table: {str(e)}")
            conn.rollback()
            raise
        finally:
            conn.close()
    
    def create_or_get_column(self, table_id: str, column_name: str, data_type: str = None,
                           description: str = None, is_primary_key: bool = False,
                           is_foreign_key: bool = False, github_path: str = None) -> str:
        """
        Create a column if it doesn't exist, or get the existing column ID
        
        Args:
            table_id: ID of the table
            column_name: Name of the column
            data_type: Data type of the column
            description: Description of the column
            is_primary_key: Whether the column is a primary key
            is_foreign_key: Whether the column is a foreign key
            github_path: Path to the file in GitHub
            
        Returns:
            Column ID
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # Check if column already exists
            cursor.execute(
                "SELECT column_id FROM columns WHERE table_id = ? AND column_name = ?",
                (table_id, column_name)
            )
            
            result = cursor.fetchone()
            if result:
                # Column already exists, return the ID
                return result["column_id"]
            
            # Column doesn't exist, create it
            column_id = str(uuid.uuid4())
            
            cursor.execute(
                """INSERT INTO columns 
                   (column_id, table_id, column_name, data_type, is_primary_key, is_foreign_key, business_description, created_at, updated_at) 
                   VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))""",
                (column_id, table_id, column_name, data_type, is_primary_key, is_foreign_key, description)
            )
            
            conn.commit()
            logger.info(f"Created column: {column_name} with ID {column_id}")
            return column_id
        except Exception as e:
            logger.error(f"Error creating column: {str(e)}")
            conn.rollback()
            raise
        finally:
            conn.close()
    
    def create_or_get_relationship(self, source_table_id: str, target_table_id: str, 
                                 relationship_type: str = "dependency", source_column_id: str = None,
                                 target_column_id: str = None, github_path: str = None) -> str:
        """
        Create a relationship if it doesn't exist, or get the existing relationship ID
        
        Args:
            source_table_id: ID of the source table
            target_table_id: ID of the target table
            relationship_type: Type of relationship
            source_column_id: ID of the source column (for column-level relationships)
            target_column_id: ID of the target column (for column-level relationships)
            github_path: Path to the file in GitHub
            
        Returns:
            Relationship ID
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # Check if relationship already exists
            cursor.execute(
                """SELECT relationship_id FROM relationships 
                   WHERE source_table_id = ? AND target_table_id = ? AND 
                   (source_column_id = ? OR (source_column_id IS NULL AND ? IS NULL)) AND
                   (target_column_id = ? OR (target_column_id IS NULL AND ? IS NULL))""",
                (source_table_id, target_table_id, source_column_id, source_column_id, target_column_id, target_column_id)
            )
            
            result = cursor.fetchone()
            if result:
                # Relationship already exists, return the ID
                return result["relationship_id"]
            
            # Relationship doesn't exist, create it
            relationship_id = str(uuid.uuid4())
            
            cursor.execute(
                """INSERT INTO relationships 
                   (relationship_id, source_table_id, target_table_id, relationship_type, source_column_id, target_column_id, github_path, created_at) 
                   VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
                (relationship_id, source_table_id, target_table_id, relationship_type, source_column_id, target_column_id, github_path)
            )
            
            conn.commit()
            logger.info(f"Created relationship with ID {relationship_id}")
            return relationship_id
        except Exception as e:
            logger.error(f"Error creating relationship: {str(e)}")
            conn.rollback()
            raise
        finally:
            conn.close()
    
    def add_lineage_definition(self, root_table_id: str, lineage_json: Dict, tech_stack: str, github_path: str = None) -> str:
        """
        Add a lineage definition for visualization
        
        Args:
            root_table_id: ID of the root table
            lineage_json: JSON object with lineage information
            tech_stack: Technology stack
            github_path: Path to the file in GitHub
            
        Returns:
            Lineage ID
        """
        lineage_id = str(uuid.uuid4())
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # First, check if the updated_at column exists
            cursor.execute("PRAGMA table_info(lineage_definitions)")
            columns = [col['name'] for col in cursor.fetchall()]
            has_updated_at = 'updated_at' in columns
            
            if has_updated_at:
                # Use the updated_at column if it exists
                cursor.execute(
                    """INSERT INTO lineage_definitions 
                       (lineage_id, root_table_id, lineage_json, tech_stack, github_path, created_at, updated_at) 
                       VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))""",
                    (lineage_id, root_table_id, json.dumps(lineage_json), tech_stack, github_path)
                )
            else:
                # Fall back to not using updated_at
                cursor.execute(
                    """INSERT INTO lineage_definitions 
                       (lineage_id, root_table_id, lineage_json, tech_stack, github_path, created_at) 
                       VALUES (?, ?, ?, ?, ?, datetime('now'))""",
                    (lineage_id, root_table_id, json.dumps(lineage_json), tech_stack, github_path)
                )
            
            conn.commit()
            logger.info(f"Added lineage definition for table {root_table_id}")
            return lineage_id
        except Exception as e:
            logger.error(f"Error adding lineage definition: {str(e)}")
            conn.rollback()
            raise
        finally:
            conn.close()
    
    def get_all_tables(self) -> List[Dict]:
        """
        Get all tables from the database
        
        Returns:
            List of tables
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("SELECT * FROM tables")
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error getting tables: {str(e)}")
            raise
        finally:
            conn.close()
            
    def get_table_by_id(self, table_id: str) -> Optional[Dict]:
        """
        Get a table by ID
        
        Args:
            table_id: ID of the table
            
        Returns:
            Table or None if not found
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("SELECT * FROM tables WHERE table_id = ?", (table_id,))
            result = cursor.fetchone()
            if result:
                return dict(result)
            return None
        except Exception as e:
            logger.error(f"Error getting table by ID: {str(e)}")
            raise
        finally:
            conn.close()
    
    def get_table_by_name(self, table_name: str, schema_name: str = None) -> Optional[Dict]:
        """
        Get a table by name and schema
        
        Args:
            table_name: Name of the table
            schema_name: Name of the schema
            
        Returns:
            Table or None if not found
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            if schema_name:
                cursor.execute("SELECT * FROM tables WHERE table_name = ? AND schema_name = ?", (table_name, schema_name))
            else:
                cursor.execute("SELECT * FROM tables WHERE table_name = ?", (table_name,))
            
            result = cursor.fetchone()
            if result:
                return dict(result)
            return None
        except Exception as e:
            logger.error(f"Error getting table by name: {str(e)}")
            raise
        finally:
            conn.close()
            
    def get_columns_for_table(self, table_id: str) -> List[Dict]:
        """
        Get all columns for a table
        
        Args:
            table_id: ID of the table
            
        Returns:
            List of columns
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("SELECT * FROM columns WHERE table_id = ?", (table_id,))
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error getting columns for table: {str(e)}")
            raise
        finally:
            conn.close()
            
    def get_relationships_for_table(self, table_id: str, as_source: bool = True, as_target: bool = True) -> List[Dict]:
        """
        Get all relationships for a table
        
        Args:
            table_id: ID of the table
            as_source: Whether to include relationships where this table is the source
            as_target: Whether to include relationships where this table is the target
            
        Returns:
            List of relationships
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            query = "SELECT * FROM relationships WHERE "
            conditions = []
            params = []
            
            if as_source:
                conditions.append("source_table_id = ?")
                params.append(table_id)
            
            if as_target:
                conditions.append("target_table_id = ?")
                params.append(table_id)
            
            query += " OR ".join(conditions)
            
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error getting relationships for table: {str(e)}")
            raise
        finally:
            conn.close()
            
    def get_lineage_definitions_for_table(self, table_id: str) -> List[Dict]:
        """
        Get all lineage definitions for a table
        
        Args:
            table_id: ID of the table
            
        Returns:
            List of lineage definitions
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("SELECT * FROM lineage_definitions WHERE root_table_id = ?", (table_id,))
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error getting lineage definitions for table: {str(e)}")
            raise
        finally:
            conn.close()

    def get_lineage_by_github_path(self, github_path: str) -> Optional[Dict]:
        """
        Get lineage definition for a GitHub file path
        
        Args:
            github_path: GitHub file path
            
        Returns:
            Lineage definition or None if not found
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # Get the table ID first
            cursor.execute("SELECT * FROM tables WHERE github_path = ?", (github_path,))
            table_result = cursor.fetchone()
            
            if not table_result:
                return None
                
            table_id = table_result["table_id"]
            
            # Get the lineage definition
            cursor.execute("SELECT * FROM lineage_definitions WHERE root_table_id = ?", (table_id,))
            lineage_result = cursor.fetchone()
            
            if lineage_result:
                lineage_def = dict(lineage_result)
                lineage_def["lineage_json"] = json.loads(lineage_def["lineage_json"])
                
                # Include table information
                lineage_def["table_name"] = table_result["table_name"]
                lineage_def["schema_name"] = table_result["schema_name"]
                lineage_def["tech_stack"] = table_result["tech_stack"]
                
                return lineage_def
            
            return None
        except Exception as e:
            logger.error(f"Error getting lineage by GitHub path: {str(e)}")
            raise
        finally:
            conn.close()
            
    def generate_comprehensive_lineage(self, root_table_id: str, tech_stack: str, github_path: str = None) -> Dict:
        """
        Generate comprehensive lineage for a table, including tables, columns, and relationships
        
        Args:
            root_table_id: ID of the root table
            tech_stack: Technology stack
            github_path: Path to the file in GitHub
            
        Returns:
            Comprehensive lineage dictionary
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # Get the root table
            cursor.execute("SELECT * FROM tables WHERE table_id = ?", (root_table_id,))
            root_table = cursor.fetchone()
            
            if not root_table:
                logger.warning(f"Root table {root_table_id} not found")
                return {}
            
            root_table_dict = dict(root_table)
            
            # Get columns for the root table
            cursor.execute("SELECT * FROM columns WHERE table_id = ?", (root_table_id,))
            columns = [dict(row) for row in cursor.fetchall()]
            
            # Get immediate relationships
            cursor.execute("""
                SELECT r.*, 
                       st.table_name as source_table_name,
                       st.schema_name as source_schema_name,
                       tt.table_name as target_table_name,
                       tt.schema_name as target_schema_name,
                       sc.column_name as source_column_name,
                       tc.column_name as target_column_name
                FROM relationships r
                JOIN tables st ON r.source_table_id = st.table_id
                JOIN tables tt ON r.target_table_id = tt.table_id
                LEFT JOIN columns sc ON r.source_column_id = sc.column_id
                LEFT JOIN columns tc ON r.target_column_id = tc.column_id
                WHERE r.source_table_id = ? OR r.target_table_id = ?
            """, (root_table_id, root_table_id))
            
            relationships = [dict(row) for row in cursor.fetchall()]
            
            # Generate response
            lineage = {
                "table": root_table_dict,
                "columns": columns,
                "relationships": []
            }
            
            # Process relationships
            source_tables = set()
            target_tables = set()
            
            for rel in relationships:
                rel_dict = {
                    "relationship_id": rel["relationship_id"],
                    "relationship_type": rel["relationship_type"],
                    "source": {
                        "table_id": rel["source_table_id"],
                        "table_name": rel["source_table_name"],
                        "schema_name": rel["source_schema_name"],
                    },
                    "target": {
                        "table_id": rel["target_table_id"],
                        "table_name": rel["target_table_name"],
                        "schema_name": rel["target_schema_name"],
                    }
                }
                
                # Add column info if available
                if rel["source_column_id"]:
                    rel_dict["source"]["column_id"] = rel["source_column_id"]
                    rel_dict["source"]["column_name"] = rel["source_column_name"]
                
                if rel["target_column_id"]:
                    rel_dict["target"]["column_id"] = rel["target_column_id"]
                    rel_dict["target"]["column_name"] = rel["target_column_name"]
                
                lineage["relationships"].append(rel_dict)
                
                # Track related tables
                if rel["source_table_id"] != root_table_id:
                    source_tables.add(rel["source_table_id"])
                
                if rel["target_table_id"] != root_table_id:
                    target_tables.add(rel["target_table_id"])
            
            # Get related tables
            related_table_ids = list(source_tables.union(target_tables))
            related_tables = {}
            
            if related_table_ids:
                # Use OR with parameters to build the query
                placeholders = ",".join(["?" for _ in related_table_ids])
                query = f"SELECT * FROM tables WHERE table_id IN ({placeholders})"
                
                cursor.execute(query, related_table_ids)
                for row in cursor.fetchall():
                    related_tables[row["table_id"]] = dict(row)
            
            lineage["related_tables"] = related_tables
            
            # Save this lineage definition for future use
            try:
                lineage_id = self.add_lineage_definition(
                    root_table_id=root_table_id,
                    lineage_json=lineage,
                    tech_stack=tech_stack,
                    github_path=github_path
                )
            except Exception as e:
                logger.warning(f"Failed to save lineage definition: {str(e)}")
                lineage_id = str(uuid.uuid4())
            
            lineage["lineage_id"] = lineage_id
            
            return lineage
        except Exception as e:
            logger.error(f"Error generating comprehensive lineage: {str(e)}")
            return {}
        finally:
            conn.close()
