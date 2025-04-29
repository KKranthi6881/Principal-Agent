"""
Column lineage enhancement function to add to export_lineage_to_json method
"""

def enhance_with_column_lineage(self, lineage_data):
    """
    Enhance existing lineage data with column-level connections
    
    Args:
        lineage_data: The lineage data to enhance
        
    Returns:
        Enhanced lineage data with column-level relationships
    """
    # Initialize column_lineage if it doesn't exist
    if "column_lineage" not in lineage_data:
        lineage_data["column_lineage"] = []
        
    try:
        # Connect to the database
        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Get all table IDs from the models
        table_ids = [model["id"] for model in lineage_data.get("models", [])]
        if not table_ids:
            logger.warning("No models found in lineage data")
            return lineage_data
            
        # Create placeholders for SQL query
        placeholders = ", ".join(["?" for _ in table_ids])
        
        # Get all column relationships for these tables
        query = f"""
            SELECT r.source_column_id, r.target_column_id, r.relationship_type 
            FROM relationships r 
            WHERE r.source_table_id IN ({placeholders}) 
              AND r.target_table_id IN ({placeholders}) 
              AND r.source_column_id IS NOT NULL 
              AND r.target_column_id IS NOT NULL
        """
        cursor.execute(query, table_ids + table_ids)
        
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
        
        logger.info(f"Enhanced lineage data with {len(column_rels)} column relationships")
        return lineage_data
        
    except Exception as e:
        logger.error(f"Error enhancing lineage with columns: {str(e)}")
        return lineage_data
    finally:
        if conn:
            conn.close()
