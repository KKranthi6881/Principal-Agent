#!/usr/bin/env python
"""
Test SQL Lineage Extraction from Files

This script tests the full lineage extraction process using real SQL files
to verify that column data is correctly extracted and stored in the database.
"""

import os
import sys
import logging
from pathlib import Path
import tempfile

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

# Configure logging
logging.basicConfig(level=logging.DEBUG, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Import required modules
from sqlglot import parse_one
from tools.sql_tools.lineage.sqlglot_lineage import SQLGlotLineageExtractor
from database.lineage_db import LineageDB

# Test SQL - Complex query with joins and column relationships
TEST_SQL = """
CREATE TABLE analytics.customer_order_summary (
    customer_id INT PRIMARY KEY,
    first_name VARCHAR(50),
    last_name VARCHAR(50),
    email VARCHAR(100),
    total_orders INT,
    total_value DECIMAL(12,2),
    avg_order_value DECIMAL(10,2),
    first_order_date DATE,
    last_order_date DATE,
    account_manager VARCHAR(100)
);

INSERT INTO analytics.customer_order_summary (
    customer_id, first_name, last_name, email, 
    total_orders, total_value, avg_order_value, 
    first_order_date, last_order_date, account_manager
)
SELECT
    c.customer_id,
    c.first_name,
    c.last_name,
    c.email,
    COUNT(o.order_id) AS total_orders,
    SUM(o.order_total) AS total_value,
    SUM(o.order_total) / COUNT(o.order_id) AS avg_order_value,
    MIN(o.order_date) AS first_order_date,
    MAX(o.order_date) AS last_order_date,
    am.full_name AS account_manager
FROM
    sales.customers c
JOIN
    sales.orders o ON c.customer_id = o.customer_id
LEFT JOIN
    sales.account_managers am ON c.account_manager_id = am.manager_id
WHERE
    o.order_status = 'completed'
    AND o.order_date >= '2023-01-01'
GROUP BY
    c.customer_id, c.first_name, c.last_name, c.email, am.full_name;
"""

# Test SQL for column propagation
TEST_SQL_PROJECTION = """
CREATE TABLE analytics.customer_profile AS
SELECT
    c.customer_id,
    c.first_name,
    c.last_name,
    c.email,
    c.phone,
    a.street_address,
    a.city,
    a.state,
    a.postal_code,
    a.country,
    s.total_spend,
    s.loyalty_tier
FROM
    sales.customers c
JOIN
    sales.addresses a ON c.customer_id = a.customer_id
JOIN
    sales.customer_stats s ON c.customer_id = s.customer_id
WHERE
    c.is_active = true;
"""

def write_test_files():
    """Write test SQL files to temporary directory"""
    # Create a temp directory
    temp_dir = Path(tempfile.mkdtemp(prefix="lineage_test_"))
    
    # Write test files
    sql_file = temp_dir / "customer_order_summary.sql"
    sql_file.write_text(TEST_SQL)
    
    projection_file = temp_dir / "customer_profile.sql"
    projection_file.write_text(TEST_SQL_PROJECTION)
    
    logger.info(f"Created test files in {temp_dir}")
    return temp_dir, {"main": sql_file, "projection": projection_file}

def test_file_extraction(file_path, dialect="postgres"):
    """Test lineage extraction from a file"""
    logger.info(f"Testing lineage extraction for file: {file_path}")
    
    # Read SQL content
    with open(file_path, 'r') as f:
        sql_content = f.read()
    
    try:
        # Parse SQL
        ast = parse_one(sql_content, dialect=dialect)
        
        # Create lineage extractor
        lineage_extractor = SQLGlotLineageExtractor()
        
        # Extract table and column lineage
        table_lineage = lineage_extractor.extract_table_lineage(ast, file_path=str(file_path))
        column_lineage = lineage_extractor.extract_column_lineage(ast, file_path=str(file_path))
        
        # Log results
        logger.info(f"Table lineage results:")
        if table_lineage.get("target_table"):
            logger.info(f"Target table: {table_lineage['target_table'].get('name')}")
        
        logger.info(f"Source tables: {len(table_lineage.get('source_tables', []))}")
        for i, table in enumerate(table_lineage.get("source_tables", [])):
            logger.info(f"  {i+1}. {table.get('name')}")
        
        logger.info(f"Column lineage results:")
        logger.info(f"Target columns: {len(column_lineage.get('target_columns', []))}")
        for i, col in enumerate(column_lineage.get("target_columns", [])):
            logger.info(f"  {i+1}. {col.get('name')} - Table: {col.get('table')}, Type: {col.get('data_type')}")
        
        logger.info(f"Column relationships: {len(column_lineage.get('column_relationships', []))}")
        for i, rel in enumerate(column_lineage.get("column_relationships", [])[:5]):  # Show first 5 only
            logger.info(f"  {i+1}. {rel.get('source_column')} ({rel.get('source_table')}) -> {rel.get('target_column')} ({rel.get('target_table')})")
        
        return file_path, table_lineage, column_lineage
        
    except Exception as e:
        logger.error(f"Error in test_file_extraction: {str(e)}")
        return file_path, None, None

def store_in_database(file_path, table_lineage, column_lineage, tech_stack="postgres"):
    """Store lineage data in the database"""
    try:
        logger.info(f"Storing lineage data for {file_path} in database")
        
        # Initialize database
        lineage_db = LineageDB()
        
        # Get target table
        target_table_name = None
        if table_lineage and table_lineage.get("target_table"):
            target_table_name = table_lineage["target_table"].get("name")
        
        if not target_table_name:
            logger.error("No target table found")
            return False
        
        # Create table record
        table_id = lineage_db.create_or_get_table(
            table_name=target_table_name,
            tech_stack=tech_stack,
            github_path=str(file_path),
            github_repo="test_repository"
        )
        
        logger.info(f"Created/got table '{target_table_name}' with ID: {table_id}")
        
        # Process columns
        column_ids = {}
        columns_created = 0
        
        # Process target columns
        if column_lineage and column_lineage.get("target_columns"):
            for column in column_lineage.get("target_columns", []):
                column_name = column.get("name")
                if column_name:
                    data_type = column.get("data_type", "unknown")
                    description = column.get("description", "")
                    is_primary = column.get("is_primary_key", False)
                    is_foreign = column.get("is_foreign_key", False)
                    
                    column_id = lineage_db.create_or_get_column(
                        table_id=table_id,
                        column_name=column_name,
                        data_type=data_type,
                        description=description,
                        is_primary_key=is_primary,
                        is_foreign_key=is_foreign,
                        github_path=str(file_path)
                    )
                    
                    column_ids[column_name] = column_id
                    columns_created += 1
        
        logger.info(f"Created/updated {columns_created} columns for table {target_table_name}")
        
        # Process relationships
        relationships_created = 0
        
        if column_lineage and column_lineage.get("column_relationships"):
            for rel in column_lineage.get("column_relationships", []):
                source_table = rel.get("source_table")
                source_column = rel.get("source_column")
                target_column = rel.get("target_column")
                
                if source_table and source_column and target_column:
                    # Create source table
                    source_table_id = lineage_db.create_or_get_table(
                        table_name=source_table,
                        tech_stack=tech_stack,
                        github_repo="test_repository"
                    )
                    
                    # Create source column
                    source_column_id = lineage_db.create_or_get_column(
                        table_id=source_table_id,
                        column_name=source_column
                    )
                    
                    # Get or create target column
                    target_column_id = column_ids.get(target_column)
                    if not target_column_id:
                        target_column_id = lineage_db.create_or_get_column(
                            table_id=table_id,
                            column_name=target_column
                        )
                    
                    # Create relationship
                    lineage_db.create_or_get_relationship(
                        source_table_id=source_table_id,
                        target_table_id=table_id,
                        relationship_type="derived_from",
                        source_column_id=source_column_id,
                        target_column_id=target_column_id,
                        github_path=str(file_path)
                    )
                    
                    relationships_created += 1
        
        logger.info(f"Created {relationships_created} column relationships")
        
        # Store overall lineage
        lineage_id = lineage_db.add_lineage_definition(
            root_table_id=table_id,
            lineage_json={
                "table_lineage": table_lineage,
                "column_lineage": column_lineage
            },
            tech_stack=tech_stack
        )
        
        logger.info(f"Stored full lineage data with ID: {lineage_id}")
        return table_id
        
    except Exception as e:
        logger.error(f"Error storing lineage in database: {str(e)}")
        return None

def verify_table_content(table_id):
    """Verify that lineage data is correctly stored in the database"""
    try:
        if not table_id:
            logger.error("No table ID provided")
            return False
            
        logger.info(f"Verifying database content for table ID '{table_id}'")
        
        # Initialize database
        lineage_db = LineageDB()
        
        # Get database connection
        conn = lineage_db._get_connection()
        cursor = conn.cursor()
        
        # Get table
        cursor.execute(
            "SELECT * FROM tables WHERE table_id = ?",
            (table_id,)
        )
        table = cursor.fetchone()
        
        if not table:
            logger.error(f"Table with ID '{table_id}' not found in database")
            conn.close()
            return False
        
        logger.info(f"Found table: {table['table_name']} (ID: {table['table_id']})")
        
        # Check columns
        cursor.execute(
            "SELECT * FROM columns WHERE table_id = ?",
            (table_id,)
        )
        columns = cursor.fetchall()
        
        logger.info(f"Found {len(columns)} columns for table '{table['table_name']}':")
        for i, col in enumerate(columns):
            logger.info(f"  {i+1}. {col['column_name']} - Type: {col['data_type']}")
        
        # Check relationships
        cursor.execute("""
            SELECT r.relationship_id, 
                   s_t.table_name as source_table,
                   s_c.column_name as source_column,
                   t_t.table_name as target_table,
                   t_c.column_name as target_column,
                   r.relationship_type
            FROM relationships r
            JOIN tables s_t ON r.source_table_id = s_t.table_id
            JOIN tables t_t ON r.target_table_id = t_t.table_id
            LEFT JOIN columns s_c ON r.source_column_id = s_c.column_id
            LEFT JOIN columns t_c ON r.target_column_id = t_c.column_id
            WHERE r.target_table_id = ?
        """, (table_id,))
        
        relationships = cursor.fetchall()
        
        logger.info(f"Found {len(relationships)} relationships for table '{table['table_name']}':")
        for i, rel in enumerate(relationships):
            source_col = rel['source_column'] if rel['source_column'] else 'None'
            target_col = rel['target_column'] if rel['target_column'] else 'None'
            logger.info(f"  {i+1}. {source_col} ({rel['source_table']}) -> {target_col} ({rel['target_table']})")
        
        conn.close()
        return len(columns) > 0
        
    except Exception as e:
        logger.error(f"Error verifying database content: {str(e)}")
        return False

def main():
    """Main function"""
    logger.info("=== Starting file-based lineage extraction test ===")
    
    # Create test files
    temp_dir, test_files = write_test_files()
    
    try:
        # Test file extraction - main SQL file
        file_path, table_lineage, column_lineage = test_file_extraction(test_files["main"])
        
        if not table_lineage or not column_lineage:
            logger.error("Lineage extraction failed for main SQL file")
        else:
            # Store in database
            table_id = store_in_database(file_path, table_lineage, column_lineage)
            
            # Verify database content
            if table_id and verify_table_content(table_id):
                logger.info("Successfully extracted and stored lineage for main SQL file")
            else:
                logger.error("Failed to store or verify lineage for main SQL file")
        
        # Test file extraction - projection SQL file
        file_path, table_lineage, column_lineage = test_file_extraction(test_files["projection"])
        
        if not table_lineage or not column_lineage:
            logger.error("Lineage extraction failed for projection SQL file")
        else:
            # Store in database
            table_id = store_in_database(file_path, table_lineage, column_lineage)
            
            # Verify database content
            if table_id and verify_table_content(table_id):
                logger.info("Successfully extracted and stored lineage for projection SQL file")
            else:
                logger.error("Failed to store or verify lineage for projection SQL file")
        
    finally:
        # Clean up
        import shutil
        try:
            shutil.rmtree(temp_dir)
            logger.info(f"Cleaned up temporary directory: {temp_dir}")
        except Exception as e:
            logger.error(f"Error during cleanup: {str(e)}")
    
    logger.info("=== File-based lineage extraction test completed ===")

if __name__ == "__main__":
    main()
