"""
SQLite database connector for storing SQL lineage information
"""

import sqlite3
import logging
import json
import uuid
import time
from typing import Dict, List, Any, Optional, Tuple

# Import the database path from db_setup
from .db_setup import LINEAGE_DB, setup_lineage_db

# Import column lineage enhancement utilities
from .enhance_lineage import enhance_lineage_with_columns

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
            
    def create_or_get_table(self, table_name: str, tech_stack: str, github_path: str = None, 
                          schema_name: str = None, database_name: str = None, 
                          connector_id: str = None, github_repo: str = None,
                          business_description: str = None) -> str:
        """
        Create a table if it doesn't exist, or get the existing table ID
        
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
        # First check if table already exists
        existing_table = self.get_table_by_name(table_name, tech_stack)
        if existing_table:
            logger.info(f"Table {table_name} already exists, returning existing ID")
            return existing_table['table_id']
        
        # Otherwise create a new table
        return self.add_table(
            table_name=table_name,
            tech_stack=tech_stack,
            github_path=github_path,
            schema_name=schema_name,
            database_name=database_name,
            connector_id=connector_id,
            github_repo=github_repo,
            business_description=business_description
        )
    
    def add_column(self, table_id: str, column_name: str, data_type: str = None,
                   is_primary_key: bool = False, is_foreign_key: bool = False,
                   business_description: str = None, github_path: str = None) -> str:
        """
        Add a column to a table
        
        Args:
            table_id: ID of the table
            column_name: Name of the column
            data_type: Data type of the column
            is_primary_key: Whether the column is a primary key
            is_foreign_key: Whether the column is a foreign key
            business_description: Business description of the column
            github_path: GitHub file path where the column is defined
            
        Returns:
            Column ID
        """
        column_id = str(uuid.uuid4())
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                """INSERT INTO columns 
                   (column_id, table_id, column_name, data_type, is_primary_key, 
                    is_foreign_key, business_description, github_path) 
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (column_id, table_id, column_name, data_type, 
                 1 if is_primary_key else 0, 1 if is_foreign_key else 0, 
                 business_description, github_path)
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
            
    def create_or_get_column(self, table_id: str, column_name: str, data_type: str = None,
                           is_primary_key: bool = False, is_foreign_key: bool = False,
                           description: str = None, github_path: str = None) -> str:
        """
        Create a column if it doesn't exist, or get the existing column ID
        
        Args:
            table_id: ID of the table
            column_name: Name of the column
            data_type: Data type of the column
            is_primary_key: Whether the column is a primary key
            is_foreign_key: Whether the column is a foreign key
            description: Description of the column
            github_path: GitHub file path where column is defined
            
        Returns:
            Column ID
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # Check if column already exists for this table
            cursor.execute(
                """SELECT * FROM columns 
                   WHERE table_id = ? AND column_name = ?""",
                (table_id, column_name)
            )
            
            existing_column = cursor.fetchone()
            if existing_column:
                # If it exists, return its ID but potentially update it with new info
                column_id = existing_column['column_id']
                
                # Update column metadata if new info is provided
                if data_type or is_primary_key or is_foreign_key or description or github_path:
                    update_params = []
                    update_values = []
                    
                    if data_type and data_type != "unknown" and (not existing_column['data_type'] or existing_column['data_type'] == "unknown"):
                        update_params.append("data_type = ?")
                        update_values.append(data_type)
                    
                    if description and (not existing_column['business_description']):
                        update_params.append("business_description = ?")
                        update_values.append(description)
                    
                    if github_path and (not existing_column['github_path']):
                        update_params.append("github_path = ?")
                        update_values.append(github_path)
                    
                    # Handle boolean flags - set to true if new value is true
                    if is_primary_key and not existing_column['is_primary_key']:
                        update_params.append("is_primary_key = ?")
                        update_values.append(1)
                    
                    if is_foreign_key and not existing_column['is_foreign_key']:
                        update_params.append("is_foreign_key = ?")
                        update_values.append(1)
                    
                    # Only update if we have changes
                    if update_params:
                        cursor.execute(
                            f"""UPDATE columns 
                               SET {', '.join(update_params)}
                               WHERE column_id = ?""",
                            update_values + [column_id]
                        )
                        conn.commit()
                        logger.info(f"Updated column {column_name} for table {table_id} with new metadata")
                
                return column_id
            
            # Otherwise create a new column
            return self.add_column(
                table_id=table_id,
                column_name=column_name,
                data_type=data_type,
                is_primary_key=is_primary_key,
                is_foreign_key=is_foreign_key,
                business_description=description,
                github_path=github_path
            )
        except Exception as e:
            logger.error(f"Error in create_or_get_column: {str(e)}")
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
                """SELECT * FROM columns WHERE table_id = ?""",
                (table_id,)
            )
            
            columns = [dict(row) for row in cursor.fetchall()]
            return columns
        except Exception as e:
            logger.error(f"Error getting columns: {str(e)}")
            raise
        finally:
            conn.close()
    
    def add_relationship(self, source_table_id: str, target_table_id: str, 
                        relationship_type: str, source_column_id: str = None,
                        target_column_id: str = None, github_path: str = None) -> str:
        """
        Add a relationship between tables or columns
        
        Args:
            source_table_id: ID of the source table
            target_table_id: ID of the target table
            relationship_type: Type of relationship (e.g., join, foreign_key)
            source_column_id: ID of the source column (optional)
            target_column_id: ID of the target column (optional)
            github_path: Path to the file in GitHub that defines this relationship
            
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
                    source_column_id, target_column_id, github_path) 
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (relationship_id, source_table_id, target_table_id, relationship_type, 
                 source_column_id, target_column_id, github_path)
            )
            
            conn.commit()
            return relationship_id
        except Exception as e:
            logger.error(f"Error adding relationship: {str(e)}")
            conn.rollback()
            raise
        finally:
            conn.close()
            
    def create_or_get_relationship(self, source_table_id: str, target_table_id: str, 
                                 relationship_type: str, source_column_id: str = None,
                                 target_column_id: str = None, github_path: str = None) -> str:
        """
        Create a relationship if it doesn't exist, or get the existing relationship ID
        
        Args:
            source_table_id: ID of the source table
            target_table_id: ID of the target table
            relationship_type: Type of relationship (e.g., join, foreign_key, dependency)
            source_column_id: ID of the source column (optional)
            target_column_id: ID of the target column (optional)
            github_path: Path to the file in GitHub that defines this relationship
            
        Returns:
            Relationship ID
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # Check if relationship already exists
            query = """
                SELECT * FROM relationships 
                WHERE source_table_id = ? AND target_table_id = ?
            """
            params = [source_table_id, target_table_id]
            
            # Add additional filters if provided
            if relationship_type:
                query += " AND relationship_type = ?"
                params.append(relationship_type)
            
            if source_column_id:
                query += " AND source_column_id = ?"
                params.append(source_column_id)
                
            if target_column_id:
                query += " AND target_column_id = ?"
                params.append(target_column_id)
            
            cursor.execute(query, params)
            existing_relationship = cursor.fetchone()
            
            if existing_relationship:
                # If it exists, return its ID
                return existing_relationship['relationship_id']
            
            # Otherwise create a new relationship
            return self.add_relationship(
                source_table_id=source_table_id,
                target_table_id=target_table_id,
                relationship_type=relationship_type,
                source_column_id=source_column_id,
                target_column_id=target_column_id,
                github_path=github_path
            )
        except Exception as e:
            logger.error(f"Error in create_or_get_relationship: {str(e)}")
            raise
        finally:
            conn.close()
    
    def generate_comprehensive_lineage(self, root_table_id: str, tech_stack: str, github_path: str = None) -> Dict:
        """
        Generate a comprehensive lineage definition for a root table
        
        This builds a complete lineage graph for the specified table, including
        all upstream and downstream dependencies, and column-level relationships
        
        Args:
            root_table_id: ID of the root table
            tech_stack: Technology stack for the lineage
            github_path: Path to the file in GitHub (optional)
            
        Returns:
            Dictionary with comprehensive lineage information
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # Get the root table details
            cursor.execute(
                """SELECT * FROM tables WHERE table_id = ?""",
                (root_table_id,)
            )
            root_table = dict(cursor.fetchone() or {})
            if not root_table:
                logger.error(f"Root table {root_table_id} not found for lineage")
                return None
            
            # Initialize the lineage structure
            lineage = {
                "tables": [],
                "columns": [],
                "relationships": [],
                "root_table": None,
                "metadata": {
                    "tech_stack": tech_stack,
                    "generated_at": time.time(),
                }
            }
            
            # Add the root table
            formatted_root = {
                "id": root_table["table_id"],
                "name": root_table["table_name"],
                "schema": root_table["schema_name"],
                "database": root_table["database_name"],
                "type": "table", # Default type
                "github_path": root_table["github_path"],
                "description": root_table["business_description"]
            }
            lineage["tables"].append(formatted_root)
            lineage["root_table"] = formatted_root
            
            # Get all tables related to the root table (directly or indirectly)
            processed_ids = set([root_table_id])
            table_ids = set([root_table_id])
            to_process = set([root_table_id])
            
            # BFS to find all related tables
            while to_process:
                current_id = to_process.pop()
                
                # Get related tables through relationships
                cursor.execute(
                    """SELECT source_table_id, target_table_id
                       FROM relationships
                       WHERE source_table_id = ? OR target_table_id = ?""",
                    (current_id, current_id)
                )
                
                for relation in cursor.fetchall():
                    source_id = relation["source_table_id"]
                    target_id = relation["target_table_id"]
                    
                    if source_id not in processed_ids:
                        processed_ids.add(source_id)
                        table_ids.add(source_id)
                        to_process.add(source_id)
                    
                    if target_id not in processed_ids:
                        processed_ids.add(target_id)
                        table_ids.add(target_id)
                        to_process.add(target_id)
            
            # Get details for all tables
            for table_id in table_ids:
                if table_id == root_table_id:
                    continue  # Already added the root table
                
                cursor.execute(
                    """SELECT * FROM tables WHERE table_id = ?""",
                    (table_id,)
                )
                table = dict(cursor.fetchone() or {})
                
                if table:
                    formatted_table = {
                        "id": table["table_id"],
                        "name": table["table_name"],
                        "schema": table["schema_name"],
                        "database": table["database_name"],
                        "type": "table",  # Default type
                        "github_path": table["github_path"],
                        "description": table["business_description"]
                    }
                    lineage["tables"].append(formatted_table)
                    
                    # Get columns for this table
                    cursor.execute(
                        """SELECT * FROM columns WHERE table_id = ?""",
                        (table_id,)
                    )
                    
                    for col in cursor.fetchall():
                        lineage["columns"].append({
                            "id": col["column_id"],
                            "name": col["column_name"],
                            "table_id": table_id,
                            "data_type": col["data_type"] or "unknown",
                            "is_primary_key": bool(col["is_primary_key"]),
                            "is_foreign_key": bool(col["is_foreign_key"]),
                            "description": col["business_description"]
                        })
            
            # Get all relationships between these tables
            table_ids_list = list(table_ids)
            placeholders = ", ".join(["?"] * len(table_ids_list))
            
            cursor.execute(
                f"""SELECT r.*, 
                      st.table_name as source_table_name,
                      tt.table_name as target_table_name,
                      sc.column_name as source_column_name,
                      tc.column_name as target_column_name
                   FROM relationships r
                   JOIN tables st ON r.source_table_id = st.table_id
                   JOIN tables tt ON r.target_table_id = tt.table_id
                   LEFT JOIN columns sc ON r.source_column_id = sc.column_id
                   LEFT JOIN columns tc ON r.target_column_id = tc.column_id
                   WHERE r.source_table_id IN ({placeholders}) 
                     AND r.target_table_id IN ({placeholders})""",
                table_ids_list + table_ids_list
            )
            
            # Process each relationship
            for rel in cursor.fetchall():
                formatted_rel = {
                    "id": rel["relationship_id"],
                    "type": rel["relationship_type"],
                    "source": {
                        "table_id": rel["source_table_id"],
                        "table_name": rel["source_table_name"],
                        "column_id": rel["source_column_id"],
                        "column_name": rel["source_column_name"]
                    },
                    "target": {
                        "table_id": rel["target_table_id"],
                        "table_name": rel["target_table_name"],
                        "column_id": rel["target_column_id"],
                        "column_name": rel["target_column_name"]
                    },
                    "github_path": rel["github_path"]
                }
                lineage["relationships"].append(formatted_rel)
                
                # Add column-level lineage connections if available
                if rel["source_column_id"] and rel["target_column_id"]:
                    lineage.setdefault("column_lineage", []).append({
                        "source": rel["source_column_id"],
                        "target": rel["target_column_id"],
                        "type": rel["relationship_type"]
                    })
            
            # Ensure consistent naming for frontend compatibility
            # LineageGraph.jsx expects models and edges, but our backend uses tables and relationships
            if "tables" in lineage and "models" not in lineage:
                lineage["models"] = lineage["tables"]
            
            if "relationships" in lineage and "edges" not in lineage:
                lineage["edges"] = lineage["relationships"]
            
            # Store this comprehensive lineage in the database
            lineage_id = self.add_lineage_definition(root_table_id, lineage, tech_stack)
            
            # Add column lineage enhancement
            if "column_lineage" not in lineage and "columns" in lineage:
                enhanced_lineage = enhance_lineage_with_columns(lineage, self.db_path)
                lineage["column_lineage"] = enhanced_lineage.get("column_lineage", [])
            
            # Ensure the root_table_id is included for the frontend
            if "root_table_id" not in lineage:
                lineage["root_table_id"] = root_table_id
                
            return lineage
        except Exception as e:
            logger.error(f"Error generating comprehensive lineage: {str(e)}")
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
            # Convert JSON to string for storage
            lineage_json_str = json.dumps(lineage_json)
            
            cursor.execute(
                """INSERT INTO lineage_definitions 
                   (lineage_id, root_table_id, lineage_json, tech_stack, created_at) 
                   VALUES (?, ?, ?, ?, ?)""",
                (lineage_id, root_table_id, lineage_json_str, tech_stack, time.time())
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
    
    def get_lineage_by_github_path(self, github_path: str) -> Dict:
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
            import os
            import re
            
            # First check if github_path is in owner/repo/path format
            relative_path = github_path
            # Match owner/repo/path or owner/repo.git/path pattern
            match = re.match(r'^[^/]+/[^/]+(?:\.git)?/(.+)$', github_path)
            if match:
                relative_path = match.group(1)
            
            filename = os.path.basename(github_path)
            logger.info(f"Looking up lineage for path: {github_path}, extracted relative path: {relative_path}")
            
            # Check if github_path column exists in lineage_definitions table
            cursor.execute("PRAGMA table_info(lineage_definitions)")
            columns = [column[1] for column in cursor.fetchall()]
            
            result = None
            
            # If the github_path column exists, use it for querying
            if 'github_path' in columns:
                # Try to find by the extracted relative path
                cursor.execute(
                    """SELECT ld.*, t.table_name, t.tech_stack 
                       FROM lineage_definitions ld
                       JOIN tables t ON ld.root_table_id = t.table_id
                       WHERE ld.github_path = ?
                       ORDER BY ld.created_at DESC
                       LIMIT 1""",
                    (relative_path,)
                )
                result = cursor.fetchone()
                
                # If not found by exact match, try with the original path
                if not result:
                    cursor.execute(
                        """SELECT ld.*, t.table_name, t.tech_stack 
                           FROM lineage_definitions ld
                           JOIN tables t ON ld.root_table_id = t.table_id
                           WHERE ld.github_path = ?
                           ORDER BY ld.created_at DESC
                           LIMIT 1""",
                        (github_path,)
                    )
                    result = cursor.fetchone()
                
                # If still not found, try by filename
                if not result:
                    cursor.execute(
                        """SELECT ld.*, t.table_name, t.tech_stack 
                           FROM lineage_definitions ld
                           JOIN tables t ON ld.root_table_id = t.table_id
                           WHERE ld.github_path LIKE ? 
                           ORDER BY ld.created_at DESC
                           LIMIT 1""",
                        (f'%{filename}%',)
                    )
                    result = cursor.fetchone()
            
            # Fall back to searching in the tables.github_path
            if not 'github_path' in columns or not result:
                cursor.execute(
                    """SELECT ld.*, t.table_name, t.tech_stack 
                       FROM lineage_definitions ld
                       JOIN tables t ON ld.root_table_id = t.table_id
                       WHERE t.github_path = ?
                       ORDER BY ld.created_at DESC
                       LIMIT 1""",
                    (github_path,)
                )
                result = cursor.fetchone()
                
                # If not found, try by partial match
                if not result:
                    import os
                    filename = os.path.basename(github_path)
                    
                    cursor.execute(
                        """SELECT ld.*, t.table_name, t.tech_stack 
                           FROM lineage_definitions ld
                           JOIN tables t ON ld.root_table_id = t.table_id
                           WHERE t.github_path LIKE ? 
                           ORDER BY ld.created_at DESC
                           LIMIT 1""",
                        (f'%{filename}%',)
                    )
                    result = cursor.fetchone()
            
            if result:
                lineage_def = dict(result)
                
                # Parse the JSON
                if lineage_def.get("lineage_json") and isinstance(lineage_def["lineage_json"], str):
                    lineage_def["lineage_json"] = json.loads(lineage_def["lineage_json"])
                
                # If a specific file is requested, filter the lineage to focus on that file
                if github_path:
                    try:
                        root_table = None
                        all_tables = lineage_def["lineage_json"].get('tables', [])
                        
                        # First try to find by exact github_path match
                        for table in all_tables:
                            if table.get('github_path') == relative_path:
                                root_table = table
                                break
                        
                        # If not found, try by filename
                        if not root_table:
                            import os
                            filename = os.path.basename(relative_path)
                            for table in all_tables:
                                if table.get('github_path') and os.path.basename(table['github_path']) == filename:
                                    root_table = table
                                    break
                        
                        if root_table:
                            # Set this as the root table in the lineage definition
                            lineage_def["lineage_json"]["root_table"] = root_table
                            
                            # Find directly related tables (one level up and down)
                            related_table_ids = set([root_table['id']])
                            
                            # Get related tables from relationships
                            relationships = lineage_def["lineage_json"].get('relationships', [])
                            for rel in relationships:
                                # If root table is source, add target
                                if rel.get('source', {}).get('table_id') == root_table['id']:
                                    related_table_ids.add(rel.get('target', {}).get('table_id'))
                                
                                # If root table is target, add source
                                if rel.get('target', {}).get('table_id') == root_table['id']:
                                    related_table_ids.add(rel.get('source', {}).get('table_id'))
                            
                            # Filter tables to only include related ones
                            filtered_tables = [t for t in all_tables if t['id'] in related_table_ids]
                            lineage_def["lineage_json"]["tables"] = filtered_tables
                            
                            # Filter relationships to only include those between related tables
                            filtered_relationships = [r for r in relationships 
                                                   if r.get('source', {}).get('table_id') in related_table_ids 
                                                   and r.get('target', {}).get('table_id') in related_table_ids]
                            lineage_def["lineage_json"]["relationships"] = filtered_relationships
                            
                            # Filter columns to only include those from related tables
                            if 'columns' in lineage_def["lineage_json"]:
                                filtered_columns = [c for c in lineage_def["lineage_json"]["columns"] 
                                                 if c.get('table_id') in related_table_ids]
                                lineage_def["lineage_json"]["columns"] = filtered_columns
                            
                            logger.info(f"Filtered lineage data for {github_path} from {len(all_tables)} tables to {len(filtered_tables)} related tables")
                    except Exception as e:
                        logger.error(f"Error filtering lineage data: {str(e)}")
                        # Return the full lineage data if filtering fails
                        pass
            
                return lineage_def
            return None
        except Exception as e:
            logger.error(f"Error getting lineage by GitHub path: {str(e)}")
            raise
        finally:
            conn.close()
