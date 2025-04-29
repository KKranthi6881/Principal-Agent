"""
Column-level lineage enhancement utilities

This module provides functions to enhance lineage data with column-level relationships
"""

import logging
import sqlite3
from typing import Dict, List, Any, Optional

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def enhance_lineage_with_columns(lineage_data: Dict[str, Any], db_path: str) -> Dict[str, Any]:
    """
    Enhance lineage data with column-level relationships
    
    Args:
        lineage_data: Lineage data structure to enhance
        db_path: Path to the SQLite database
        
    Returns:
        Enhanced lineage data with column-level relationships
    """
    if not lineage_data or not isinstance(lineage_data, dict):
        logger.warning("Invalid lineage data provided")
        return lineage_data
    
    # Ensure tables/models, relationships/edges and columns exist in the lineage data
    # Handle both naming conventions since the frontend expects models/edges but our backend uses tables/relationships
    if "tables" in lineage_data and "models" not in lineage_data:
        lineage_data["models"] = lineage_data["tables"]
    elif "models" in lineage_data and "tables" not in lineage_data:
        lineage_data["tables"] = lineage_data["models"]
    elif "models" not in lineage_data and "tables" not in lineage_data:
        lineage_data["models"] = []
        lineage_data["tables"] = []
    
    if "relationships" in lineage_data and "edges" not in lineage_data:
        lineage_data["edges"] = lineage_data["relationships"]
    elif "edges" in lineage_data and "relationships" not in lineage_data:
        lineage_data["relationships"] = lineage_data["edges"]
    elif "relationships" not in lineage_data and "edges" not in lineage_data:
        lineage_data["relationships"] = []
        lineage_data["edges"] = []
    
    if "columns" not in lineage_data:
        lineage_data["columns"] = []
    
    # Initialize column_lineage if it doesn't exist
    if "column_lineage" not in lineage_data:
        lineage_data["column_lineage"] = []
        
    try:
        # Connect to the database
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row  # Return rows as dictionaries
        cursor = conn.cursor()
        
        # Get all table IDs from the models
        table_ids = [model["id"] for model in lineage_data["models"]]
        if not table_ids:
            logger.warning("No models found in lineage data")
            return lineage_data
            
        # Create placeholders for SQL query
        placeholders = ", ".join(["?" for _ in table_ids])
        
        # Get all column relationships for these tables
        cursor.execute(
            f"""SELECT r.source_column_id, r.target_column_id, r.relationship_type 
               FROM relationships r 
               WHERE r.source_table_id IN ({placeholders}) 
                 AND r.target_table_id IN ({placeholders}) 
                 AND r.source_column_id IS NOT NULL 
                 AND r.target_column_id IS NOT NULL""",
            table_ids + table_ids
        )
        
        # Process column relationships
        column_rels = []
        for row in cursor.fetchall():
            column_rels.append({
                "source": row["source_column_id"],
                "target": row["target_column_id"],
                "type": row["relationship_type"] 
            })
            
        # Add column relationships to lineage data
        lineage_data["column_lineage"] = column_rels
        
        # Additional handling for DBT source tables
        try:
            # Find source tables (DBT sources or tables with no columns)
            source_tables = []
            for table in lineage_data.get("tables", lineage_data.get("models", [])):
                # Check if this is a source table (either DBT source or has no columns)
                is_source = False
                
                # Check if table name contains keywords suggesting it's a source
                table_name = table.get("name", "").lower()
                if "source" in table_name or table_name.startswith("stg_") or "raw" in table_name:
                    is_source = True
                
                # Check if this table has no columns
                table_id = table.get("id")
                table_columns = [c for c in lineage_data["columns"] if c["table_id"] == table_id]
                if not table_columns:
                    is_source = True
                    
                if is_source:
                    source_tables.append(table)
            
            # For each source table, try to find its downstream tables and propagate column info
            for source_table in source_tables:
                source_id = source_table.get("id")
                # Find relationships where this table is the source
                downstream_edges = []
                for edge in lineage_data.get("edges", lineage_data.get("relationships", [])):
                    edge_source = edge.get("source", edge.get("source_table_id"))
                    if edge_source == source_id:
                        downstream_edges.append(edge)
                
                # For each downstream table, infer source columns from target columns
                for edge in downstream_edges:
                    target_id = edge.get("target", edge.get("target_table_id"))
                    target_columns = [c for c in lineage_data["columns"] if c["table_id"] == target_id]
                    
                    # Only proceed if target has columns but source doesn't
                    if target_columns and not any(c["table_id"] == source_id for c in lineage_data["columns"]):
                        # Get SQL query for target if available
                        target_table = next((t for t in lineage_data.get("tables", lineage_data.get("models", [])) if t["id"] == target_id), None)
                        github_path = target_table.get("github_path") if target_table else None
                        
                        if github_path:
                            # This target table has a github_path - try to fetch the SQL to extract source references
                            try:
                                # Connect to get the SQL content
                                cursor.execute(
                                    """SELECT table_id, table_name FROM tables WHERE github_path = ?""",
                                    (github_path,)
                                )
                                # Infer source columns from target columns
                                for target_col in target_columns:
                                    # Create a matching source column
                                    original_col_name = target_col["name"]
                                    
                                    # Look for aliases in column name (e.g. "s_suppkey as supplier_key")
                                    source_col_name = original_col_name
                                    if target_table and "renamed" in target_table.get("name", "").lower():
                                        # This might be a renamed column - try to derive original name
                                        # Check common patterns like "x_field as field_name" or "field AS renamed_field"
                                        if original_col_name.startswith("supplier_"):
                                            source_col_name = "s_" + original_col_name[9:]
                                        elif original_col_name.startswith("customer_"):
                                            source_col_name = "c_" + original_col_name[9:]
                                        elif original_col_name.startswith("order_"):
                                            source_col_name = "o_" + original_col_name[6:]
                                        elif original_col_name.startswith("part_"):
                                            source_col_name = "p_" + original_col_name[5:]
                                    
                                    # Add inferred source column
                                    source_column = {
                                        "id": f"{source_id}_{source_col_name}",  # Generate a predictable ID
                                        "name": source_col_name,
                                        "table_id": source_id,
                                        "data_type": target_col.get("data_type", "unknown"),
                                        "inferred": True
                                    }
                                    
                                    # Only add if not already present
                                    if not any(c["table_id"] == source_id and c["name"] == source_col_name 
                                              for c in lineage_data["columns"]):
                                        lineage_data["columns"].append(source_column)
                                    
                                    # Add relationship between source and target columns
                                    lineage_data["column_lineage"].append({
                                        "source": source_column["id"],
                                        "target": target_col["id"],
                                        "type": "inferred_from_alias"
                                    })
                            except Exception as e:
                                logger.warning(f"Error inferring source columns from github_path: {str(e)}")
        except Exception as e:
            logger.warning(f"Error during DBT source column enhancement: {str(e)}")
        
        # If we don't have any column relationships but we do have columns,
        # make an additional attempt to infer relationships based on column names
        if not lineage_data["column_lineage"] and lineage_data["columns"]:
            inferred_rels = infer_column_relationships(lineage_data, cursor)
            lineage_data["column_lineage"] = inferred_rels
            
        logger.info(f"Enhanced lineage data with {len(lineage_data['column_lineage'])} column relationships")
        return lineage_data
        
    except Exception as e:
        logger.error(f"Error enhancing lineage with columns: {str(e)}")
        return lineage_data
    finally:
        conn.close()

def infer_column_relationships(lineage_data: Dict[str, Any], cursor) -> List[Dict[str, Any]]:
    """
    Infer column relationships based on column names and table relationships
    
    Args:
        lineage_data: Lineage data structure
        cursor: Database cursor
        
    Returns:
        List of inferred column relationships
    """
    inferred_rels = []
    
    # Create a map of column name to column ID
    column_map = {}
    column_table_map = {}  # Track which table each column belongs to
    
    # Create lookup tables for efficient column matching
    for col in lineage_data["columns"]:
        # Use table_id and column_name as key for exact matches
        key = f"{col['table_id']}_{col['name'].lower()}"
        column_map[key] = col["id"]
        
        # Also track columns by name for fuzzy matching
        if col["name"].lower() not in column_table_map:
            column_table_map[col["name"].lower()] = []
        column_table_map[col["name"].lower()].append({
            "id": col["id"],
            "table_id": col["table_id"]
        })
    
    # 1. Match based on existing relationships in the database
    try:
        # Get all table IDs
        table_ids = []
        if "tables" in lineage_data:
            table_ids = [table["id"] for table in lineage_data["tables"]]
        elif "models" in lineage_data:
            table_ids = [model["id"] for model in lineage_data["models"]]
        
        if table_ids:
            # Create placeholders for SQL query
            placeholders = ", ".join(["?" for _ in table_ids])
            
            # Get column relationships from the database
            cursor.execute(
                f"""SELECT r.source_column_id, r.target_column_id, r.relationship_type, 
                       sc.column_name as source_column_name, tc.column_name as target_column_name
                   FROM relationships r 
                   JOIN columns sc ON r.source_column_id = sc.column_id
                   JOIN columns tc ON r.target_column_id = tc.column_id
                   WHERE r.source_table_id IN ({placeholders}) 
                     AND r.target_table_id IN ({placeholders}) 
                     AND r.source_column_id IS NOT NULL 
                     AND r.target_column_id IS NOT NULL""",
                table_ids + table_ids
            )
            
            for row in cursor.fetchall():
                inferred_rels.append({
                    "source": row["source_column_id"],
                    "target": row["target_column_id"],
                    "type": row["relationship_type"] or "inferred",
                    "source_column_name": row["source_column_name"],
                    "target_column_name": row["target_column_name"]
                })
            
            logger.info(f"Found {len(inferred_rels)} explicit column relationships in the database")
    except Exception as e:
        logger.warning(f"Error retrieving column relationships from database: {str(e)}")
    
    # 2. For each table edge, try to find columns with the same name
    edges_list = lineage_data.get("edges", lineage_data.get("relationships", []))
    
    for edge in edges_list:
        source_table_id = edge.get("source", edge.get("source_table_id"))
        target_table_id = edge.get("target", edge.get("target_table_id"))
        
        if not source_table_id or not target_table_id:
            continue
        
        # Get columns for source and target tables
        source_columns = [c for c in lineage_data["columns"] if c["table_id"] == source_table_id]
        target_columns = [c for c in lineage_data["columns"] if c["table_id"] == target_table_id]
        
        # Try to match columns by name - exact match
        for src_col in source_columns:
            for tgt_col in target_columns:
                # Check if this relationship already exists
                relationship_exists = any(
                    rel["source"] == src_col["id"] and rel["target"] == tgt_col["id"]
                    for rel in inferred_rels
                )
                
                if relationship_exists:
                    continue
                
                # 2a. Exact name match
                if src_col["name"].lower() == tgt_col["name"].lower():
                    inferred_rels.append({
                        "source": src_col["id"],
                        "target": tgt_col["id"],
                        "type": "direct",  # Exact matches are likely direct copies
                        "source_column_name": src_col["name"],
                        "target_column_name": tgt_col["name"]
                    })
                # 2b. Partial name match (target contains source or vice versa)
                elif src_col["name"].lower() in tgt_col["name"].lower() or \
                     tgt_col["name"].lower() in src_col["name"].lower():
                    inferred_rels.append({
                        "source": src_col["id"],
                        "target": tgt_col["id"],
                        "type": "derived",  # Partial matches suggest transformation
                        "source_column_name": src_col["name"],
                        "target_column_name": tgt_col["name"]
                    })
    
    # 3. Add derived id/key relationships when clear connections exist
    table_connections = {}
    for edge in edges_list:
        source_id = edge.get("source", edge.get("source_table_id"))
        target_id = edge.get("target", edge.get("target_table_id"))
        if source_id and target_id:
            if source_id not in table_connections:
                table_connections[source_id] = []
            table_connections[source_id].append(target_id)
    
    # For each source table, find key or ID columns and connect to dependent tables
    for table_id, connections in table_connections.items():
        source_key_columns = [c for c in lineage_data["columns"] 
                            if c["table_id"] == table_id and 
                            ("id" in c["name"].lower() or "key" in c["name"].lower())]
        
        for connected_table in connections:
            target_key_columns = [c for c in lineage_data["columns"] 
                                if c["table_id"] == connected_table and 
                                ("id" in c["name"].lower() or "key" in c["name"].lower())]
            
            for src_key in source_key_columns:
                for tgt_key in target_key_columns:
                    # Check if this relationship already exists
                    relationship_exists = any(
                        rel["source"] == src_key["id"] and rel["target"] == tgt_key["id"]
                        for rel in inferred_rels
                    )
                    
                    if not relationship_exists:
                        inferred_rels.append({
                            "source": src_key["id"],
                            "target": tgt_key["id"],
                            "type": "key_relationship",
                            "source_column_name": src_key["name"],
                            "target_column_name": tgt_key["name"]
                        })
    
    logger.info(f"Inferred {len(inferred_rels)} total column relationships")
    return inferred_rels
