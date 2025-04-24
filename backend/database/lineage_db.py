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
    
    def export_lineage_to_json(self, root_table_id: str = None, lineage_id: str = None) -> Dict:
        """
        Export a complete lineage structure with GitHub file links for UI visualization
        
        This method builds a comprehensive JSON representation of the lineage graph,
        including all tables, columns, relationships, and GitHub file paths.
        
        Args:
            root_table_id: ID of the root table (if looking up by table)
            lineage_id: ID of the lineage definition (if looking up directly)
            
        Returns:
            Complete lineage structure with GitHub file integration
        """
        # First, get the base lineage definition
        lineage_def = self.get_lineage_definition(root_table_id, lineage_id)
        if not lineage_def:
            logger.error(f"No lineage definition found for root_table_id={root_table_id}, lineage_id={lineage_id}")
            return None
            
        # Start building our enhanced lineage structure
        result = {
            "lineage_id": lineage_def["lineage_id"],
            "root_table_id": lineage_def["root_table_id"],
            "root_table_name": lineage_def["table_name"],
            "tech_stack": lineage_def["tech_stack"],
            "created_at": lineage_def["created_at"],
            "base_lineage": lineage_def["lineage_json"],
            "tables": [],
            "relationships": [],
            "column_relationships": []  # Add specific section for column relationships
        }
        
        # Get all tables referenced in the lineage
        table_ids = set()
        
        # Add the root table
        table_ids.add(lineage_def["root_table_id"])
        
        # Extract all table IDs from the relationships
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # Get all relationships connected to the root table (directly or indirectly through other tables)
            processed_ids = set()
            to_process = {lineage_def["root_table_id"]}
            
            while to_process:
                current_id = to_process.pop()
                processed_ids.add(current_id)
                
                cursor.execute(
                    """SELECT source_table_id, target_table_id
                       FROM relationships
                       WHERE source_table_id = ? OR target_table_id = ?""",
                    (current_id, current_id)
                )
                
                for relation in cursor.fetchall():
                    source_id = relation["source_table_id"]
                    target_id = relation["target_table_id"]
                    table_ids.add(source_id)
                    table_ids.add(target_id)
                    
                    # Add unprocessed tables to process queue
                    if source_id not in processed_ids:
                        to_process.add(source_id)
                    if target_id not in processed_ids:
                        to_process.add(target_id)
            
            # Get details for all tables
            for table_id in table_ids:
                cursor.execute(
                    """SELECT * FROM tables WHERE table_id = ?""",
                    (table_id,)
                )
                table = dict(cursor.fetchone())
                
                # Get columns for this table
                cursor.execute(
                    """SELECT * FROM columns WHERE table_id = ?""",
                    (table_id,)
                )
                columns = [dict(col) for col in cursor.fetchall()]
                
                # Add columns to table
                table["columns"] = columns
                
                # Add GitHub link if available
                if table.get("github_repo") and table.get("github_path"):
                    file_path = table["github_path"].lstrip("/")
                    # Format: https://github.com/username/repo/blob/main/path/to/file.sql
                    repo_url = table["github_repo"].rstrip("/")
                    if repo_url.endswith(".git"):
                        repo_url = repo_url[:-4]
                    # Assuming main branch, can be parameterized if needed
                    table["github_url"] = f"{repo_url}/blob/main/{file_path}"
                
                result["tables"].append(table)
            
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
            
            relationships = []
            column_relationships = []
            for row in cursor.fetchall():
                rel = dict(row)
                
                # Add GitHub link if available
                if rel.get("github_path"):
                    # Find the associated GitHub repo
                    # First try to get it from the source table
                    cursor.execute(
                        """SELECT github_repo FROM tables WHERE table_id = ?""",
                        (rel["source_table_id"],)
                    )
                    source_repo = cursor.fetchone()
                    
                    if source_repo and source_repo["github_repo"]:
                        repo_url = source_repo["github_repo"].rstrip("/")
                        if repo_url.endswith(".git"):
                            repo_url = repo_url[:-4]
                        file_path = rel["github_path"].lstrip("/")
                        rel["github_url"] = f"{repo_url}/blob/main/{file_path}"
                
                # Add to table-level relationships
                relationships.append(rel)
                
                # If this is a column-level relationship, also add to column_relationships
                if rel.get("source_column_id") and rel.get("target_column_id"):
                    column_rel = {
                        "relationship_id": rel["relationship_id"],
                        "source_table_id": rel["source_table_id"],
                        "target_table_id": rel["target_table_id"],
                        "source_table_name": rel["source_table_name"],
                        "target_table_name": rel["target_table_name"],
                        "source_column_id": rel["source_column_id"],
                        "target_column_id": rel["target_column_id"],
                        "source_column_name": rel["source_column_name"],
                        "target_column_name": rel["target_column_name"],
                        "relationship_type": rel["relationship_type"],
                        "github_path": rel.get("github_path"),
                        "github_url": rel.get("github_url")
                    }
                    column_relationships.append(column_rel)
            
            result["relationships"] = relationships
            result["column_relationships"] = column_relationships
            
            # If there are no explicit column relationships but we have column lineage in the base lineage,
            # extract column relationships from there
            if not column_relationships and result["base_lineage"] and isinstance(result["base_lineage"], dict):
                column_lineage = result["base_lineage"].get("column_lineage", {})
                
                if column_lineage and "target_columns" in column_lineage:
                    # Build column lookup dictionaries
                    column_name_to_id = {}
                    
                    # Collect all column information by name
                    for table in result["tables"]:
                        table_name = table["table_name"]
                        for column in table.get("columns", []):
                            key = f"{table_name}.{column['column_name']}"
                            column_name_to_id[key] = {
                                "column_id": column["column_id"],
                                "table_id": table["table_id"],
                                "table_name": table_name
                            }
                    
                    # Process column lineage to create relationships
                    for target_column in column_lineage.get("target_columns", []):
                        target_col_name = target_column.get("name")
                        target_table_name = result["root_table_name"]
                        target_key = f"{target_table_name}.{target_col_name}"
                        
                        if target_col_name and target_key in column_name_to_id:
                            target_info = column_name_to_id[target_key]
                            
                            # Process source columns for this target
                            for source_column in target_column.get("source_columns", []):
                                source_col_name = source_column.get("name")
                                source_table_name = source_column.get("table")
                                
                                # If we have a source table name, use it
                                if source_table_name:
                                    source_key = f"{source_table_name}.{source_col_name}"
                                else:
                                    # Try to find the source column in any table
                                    source_key = None
                                    for key in column_name_to_id:
                                        if key.endswith(f".{source_col_name}"):
                                            source_key = key
                                            break
                                
                                if source_key and source_key in column_name_to_id:
                                    source_info = column_name_to_id[source_key]
                                    
                                    # Create a synthetic column relationship
                                    syn_rel = {
                                        "relationship_id": str(uuid.uuid4()),
                                        "source_table_id": source_info["table_id"],
                                        "target_table_id": target_info["table_id"],
                                        "source_table_name": source_info["table_name"],
                                        "target_table_name": target_info["table_name"],
                                        "source_column_id": source_info["column_id"],
                                        "target_column_id": target_info["column_id"],
                                        "source_column_name": source_col_name,
                                        "target_column_name": target_col_name,
                                        "relationship_type": "column_lineage",
                                        "derived": True  # Flag this as a derived relationship
                                    }
                                    column_relationships.append(syn_rel)
            
            # Add field-level metadata from the lineage_json if available
            if result["base_lineage"] and "column_lineage" in result["base_lineage"]:
                result["column_metadata"] = result["base_lineage"]["column_lineage"]
            
            return result
        except Exception as e:
            logger.error(f"Error exporting lineage to JSON: {str(e)}")
            raise
        finally:
            conn.close()

    def save_lineage_to_json_file(self, root_table_id: str = None, tech_stack: str = None, 
                              output_dir: str = "exports", filename: str = None) -> str:
        """
        Export lineage data to a JSON file for visualization tools
        
        This method exports lineage data to a JSON file that can be used by external
        visualization tools. If a specific table is provided, only that table's lineage
        is exported. Otherwise, all tables for the specified tech stack are exported.
        
        Args:
            root_table_id: ID of the root table (optional)
            tech_stack: Technology stack to filter by (optional)
            output_dir: Directory to save the JSON file to
            filename: Name of the JSON file (optional, will be generated if not provided)
            
        Returns:
            Path to the exported JSON file
        """
        import os
        import json
        
        # Create output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)
        
        # Generate filename if not provided
        if not filename:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            if root_table_id:
                table = self.get_table_by_id(root_table_id)
                if table:
                    table_name = table.get("table_name", "unknown")
                    filename = f"lineage_{table_name}_{timestamp}.json"
                else:
                    filename = f"lineage_table_{root_table_id}_{timestamp}.json"
            elif tech_stack:
                filename = f"lineage_{tech_stack}_{timestamp}.json"
            else:
                filename = f"lineage_full_{timestamp}.json"
        
        # Full path to output file
        output_path = os.path.join(output_dir, filename)
        
        # Export data
        if root_table_id:
            # Export single table
            lineage_data = self.export_lineage_to_json(root_table_id=root_table_id)
            if not lineage_data:
                logger.error(f"No lineage data found for table ID {root_table_id}")
                return None
                
            # Write to file
            with open(output_path, 'w') as f:
                json.dump(lineage_data, f, indent=2)
                
            logger.info(f"Exported lineage data for table ID {root_table_id} to {output_path}")
            return output_path
            
        elif tech_stack:
            # Export all tables for tech stack
            lineage_defs = self.get_lineage_by_tech_stack(tech_stack)
            if not lineage_defs:
                logger.error(f"No lineage definitions found for tech stack {tech_stack}")
                return None
                
            # Combine all lineage data
            all_lineage_data = {
                "tech_stack": tech_stack,
                "tables": [],
                "relationships": [],
                "column_relationships": [],
                "lineage_definitions": []
            }
            
            # Export each lineage definition
            for lineage_def in lineage_defs:
                root_table_id = lineage_def["root_table_id"]
                lineage_data = self.export_lineage_to_json(root_table_id=root_table_id)
                
                if lineage_data:
                    # Add tables
                    all_lineage_data["tables"].extend(lineage_data["tables"])
                    
                    # Add relationships
                    all_lineage_data["relationships"].extend(lineage_data["relationships"])
                    
                    # Add column relationships
                    all_lineage_data["column_relationships"].extend(lineage_data["column_relationships"])
                    
                    # Add lineage definition
                    all_lineage_data["lineage_definitions"].append({
                        "lineage_id": lineage_data["lineage_id"],
                        "root_table_id": lineage_data["root_table_id"],
                        "root_table_name": lineage_data["root_table_name"],
                        "created_at": lineage_data["created_at"]
                    })
            
            # Deduplicate tables and relationships by ID
            unique_tables = {}
            for table in all_lineage_data["tables"]:
                unique_tables[table["table_id"]] = table
            all_lineage_data["tables"] = list(unique_tables.values())
            
            unique_relationships = {}
            for rel in all_lineage_data["relationships"]:
                unique_relationships[rel["relationship_id"]] = rel
            all_lineage_data["relationships"] = list(unique_relationships.values())
            
            unique_col_relationships = {}
            for rel in all_lineage_data["column_relationships"]:
                unique_col_relationships[rel["relationship_id"]] = rel
            all_lineage_data["column_relationships"] = list(unique_col_relationships.values())
            
            # Write to file
            with open(output_path, 'w') as f:
                json.dump(all_lineage_data, f, indent=2)
                
            logger.info(f"Exported lineage data for tech stack {tech_stack} to {output_path}")
            return output_path
            
        else:
            # Export all tables
            conn = self._get_connection()
            cursor = conn.cursor()
            
            try:
                cursor.execute("SELECT DISTINCT tech_stack FROM tables")
                tech_stacks = [row["tech_stack"] for row in cursor.fetchall()]
                
                # Combine all lineage data
                all_lineage_data = {
                    "tech_stacks": tech_stacks,
                    "tables": [],
                    "relationships": [],
                    "column_relationships": [],
                    "lineage_definitions": []
                }
                
                # Process each tech stack
                for tech_stack in tech_stacks:
                    lineage_defs = self.get_lineage_by_tech_stack(tech_stack)
                    
                    # Process each lineage definition
                    for lineage_def in lineage_defs:
                        root_table_id = lineage_def["root_table_id"]
                        lineage_data = self.export_lineage_to_json(root_table_id=root_table_id)
                        
                        if lineage_data:
                            # Add tables
                            all_lineage_data["tables"].extend(lineage_data["tables"])
                            
                            # Add relationships
                            all_lineage_data["relationships"].extend(lineage_data["relationships"])
                            
                            # Add column relationships
                            all_lineage_data["column_relationships"].extend(lineage_data["column_relationships"])
                            
                            # Add lineage definition
                            all_lineage_data["lineage_definitions"].append({
                                "lineage_id": lineage_data["lineage_id"],
                                "root_table_id": lineage_data["root_table_id"],
                                "root_table_name": lineage_data["root_table_name"],
                                "tech_stack": lineage_data["tech_stack"],
                                "created_at": lineage_data["created_at"]
                            })
                
                # Deduplicate tables and relationships by ID
                unique_tables = {}
                for table in all_lineage_data["tables"]:
                    unique_tables[table["table_id"]] = table
                all_lineage_data["tables"] = list(unique_tables.values())
                
                unique_relationships = {}
                for rel in all_lineage_data["relationships"]:
                    unique_relationships[rel["relationship_id"]] = rel
                all_lineage_data["relationships"] = list(unique_relationships.values())
                
                unique_col_relationships = {}
                for rel in all_lineage_data["column_relationships"]:
                    unique_col_relationships[rel["relationship_id"]] = rel
                all_lineage_data["column_relationships"] = list(unique_col_relationships.values())
                
                # Write to file
                with open(output_path, 'w') as f:
                    json.dump(all_lineage_data, f, indent=2)
                    
                logger.info(f"Exported all lineage data to {output_path}")
                return output_path
                
            except Exception as e:
                logger.error(f"Error exporting lineage data: {str(e)}")
                raise
            finally:
                conn.close()

    def get_table_by_id(self, table_id: str) -> Dict:
        """
        Get a table by ID
        
        Args:
            table_id: ID of the table
            
        Returns:
            Table details or None if not found
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                """SELECT * FROM tables 
                   WHERE table_id = ?""",
                (table_id,)
            )
            
            result = cursor.fetchone()
            if result:
                return dict(result)
            return None
        except Exception as e:
            logger.error(f"Error getting table by ID: {str(e)}")
            raise
        finally:
            conn.close()