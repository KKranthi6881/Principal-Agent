#!/usr/bin/env python
"""
Test PostgreSQL Lineage Extraction

This script tests the PostgreSQL dialect's column-level lineage extraction functionality.
"""

import os
import sys
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Import required modules
sys.path.append(str(Path(__file__).parent.parent))
from tools.sql_tools.dialects.postgres.postgres_dialect import PostgreSQLDialect

# Test SQL with clear column relationships
TEST_SQL = """
CREATE TABLE analytics.customer_summary AS
SELECT 
    c.customer_id,
    c.first_name,
    c.last_name,
    c.email,
    a.city,
    a.state,
    COUNT(o.order_id) AS total_orders,
    SUM(o.order_total) AS total_value,
    AVG(o.order_total) AS avg_order_value
FROM 
    sales.customers c
JOIN 
    sales.orders o ON c.customer_id = o.customer_id
JOIN
    sales.addresses a ON c.customer_id = a.customer_id
WHERE
    o.order_date >= '2023-01-01'
GROUP BY 
    c.customer_id, c.first_name, c.last_name, c.email, a.city, a.state
"""

def test_postgres_lineage():
    """Test PostgreSQL lineage extraction"""
    logger.info("=== Testing PostgreSQL Lineage Extraction ===")
    
    # Create PostgreSQL dialect parser
    dialect = PostgreSQLDialect()
    
    # Extract lineage
    lineage = dialect.extract_lineage(TEST_SQL)
    
    # Validate table lineage
    logger.info("\nTABLE LINEAGE:")
    logger.info(f"Target table: {lineage['table_lineage'].get('target_table')}")
    source_tables = lineage['table_lineage'].get('source_tables', [])
    logger.info(f"Source tables: {source_tables}")
    
    # Validate column lineage
    logger.info("\nCOLUMN LINEAGE:")
    target_cols = lineage['column_lineage'].get('target_columns', [])
    logger.info(f"Target columns: {len(target_cols)}")
    for i, col in enumerate(target_cols):
        logger.info(f"  {i+1}. {col.get('name')} - Table: {col.get('table')}")
    
    # Validate relationships
    relationships = lineage['column_lineage'].get('column_relationships', [])
    logger.info(f"\nColumn relationships: {len(relationships)}")
    for i, rel in enumerate(relationships):
        logger.info(f"  {i+1}. {rel.get('source_column')} ({rel.get('source_table')}) -> "
                   f"{rel.get('target_column')} ({rel.get('target_table')})")
    
    # Check if we got column lineage data
    if not target_cols:
        logger.error("❌ No target columns extracted!")
    else:
        logger.info(f"✅ Successfully extracted {len(target_cols)} target columns")
        
    if not relationships:
        logger.error("❌ No column relationships extracted!")
    else:
        logger.info(f"✅ Successfully extracted {len(relationships)} column relationships")
    
    # Return success if we have columns and relationships
    return len(target_cols) > 0 and len(relationships) > 0

if __name__ == "__main__":
    if test_postgres_lineage():
        logger.info("✅ PostgreSQL lineage extraction test PASSED")
    else:
        logger.error("❌ PostgreSQL lineage extraction test FAILED")
