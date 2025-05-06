#!/usr/bin/env python
"""
Test All SQL Dialect Lineage Extraction

This script tests column-level lineage extraction for all SQL dialects:
- PostgreSQL
- T-SQL
- DBT
"""

import os
import sys
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

# Import required modules
from tools.sql_tools.dialects import get_dialect_parser

# Test SQL for each dialect

# PostgreSQL SQL with column relationships
POSTGRES_SQL = """
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

# T-SQL SQL with column relationships
TSQL_SQL = """
CREATE TABLE analytics.customer_summary
WITH (DISTRIBUTION = HASH(customer_id), CLUSTERED COLUMNSTORE INDEX)
AS 
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

# DBT SQL with column relationships (using ref syntax)
DBT_SQL = """
{{
  config(
    materialized = 'table',
    schema = 'analytics'
  )
}}

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
    {{ ref('customers') }} c
JOIN 
    {{ ref('orders') }} o ON c.customer_id = o.customer_id
JOIN
    {{ ref('addresses') }} a ON c.customer_id = a.customer_id
WHERE
    o.order_date >= '2023-01-01'
GROUP BY 
    c.customer_id, c.first_name, c.last_name, c.email, a.city, a.state
"""

def test_dialect_lineage(dialect_name, sql_content, file_path=None):
    """Test lineage extraction for a specific dialect"""
    logger.info(f"\n=== Testing {dialect_name.upper()} Dialect Lineage Extraction ===")
    
    # Get dialect handler
    dialect_handler = get_dialect_parser(dialect_name)
    if not dialect_handler:
        logger.error(f"❌ Failed to get dialect handler for {dialect_name}")
        return False
    
    logger.info(f"✅ Successfully loaded {dialect_name} dialect handler")
    
    # Check if the dialect has extract_lineage method
    if not hasattr(dialect_handler, 'extract_lineage'):
        logger.error(f"❌ {dialect_name} dialect does not have extract_lineage method")
        return False
    
    logger.info(f"✅ {dialect_name} dialect has extract_lineage method")
    
    # Extract lineage
    try:
        lineage = dialect_handler.extract_lineage(sql_content, file_path)
        logger.info(f"✅ Successfully called extract_lineage for {dialect_name}")
    except Exception as e:
        logger.error(f"❌ Failed to extract lineage for {dialect_name}: {str(e)}", exc_info=True)
        return False
    
    # Validate table lineage
    table_lineage_ok = False
    if "table_lineage" in lineage:
        target_table = lineage["table_lineage"].get("target_table")
        source_tables = lineage["table_lineage"].get("source_tables", [])
        
        logger.info("\nTABLE LINEAGE:")
        logger.info(f"Target table: {target_table}")
        logger.info(f"Source tables: {source_tables}")
        
        if target_table and source_tables:
            table_lineage_ok = True
            logger.info(f"✅ {dialect_name} extracted both target and source tables")
        else:
            logger.error(f"❌ {dialect_name} failed to extract complete table lineage")
    else:
        logger.error(f"❌ {dialect_name} does not provide table_lineage")
    
    # Validate column lineage
    column_lineage_ok = False
    if "column_lineage" in lineage:
        target_cols = lineage["column_lineage"].get("target_columns", [])
        relationships = lineage["column_lineage"].get("column_relationships", [])
        
        logger.info("\nCOLUMN LINEAGE:")
        logger.info(f"Target columns: {len(target_cols)}")
        for i, col in enumerate(target_cols):
            col_name = col.get("name") if isinstance(col, dict) else col
            table_name = col.get("table") if isinstance(col, dict) else None
            logger.info(f"  {i+1}. {col_name}" + (f" - Table: {table_name}" if table_name else ""))
        
        logger.info(f"\nColumn relationships: {len(relationships)}")
        for i, rel in enumerate(relationships):
            if isinstance(rel, dict):
                source_col = rel.get("source_column", "Unknown")
                source_tbl = rel.get("source_table", "Unknown")
                target_col = rel.get("target_column", "Unknown")
                target_tbl = rel.get("target_table", "Unknown")
                logger.info(f"  {i+1}. {source_col} ({source_tbl}) -> {target_col} ({target_tbl})")
            else:
                logger.info(f"  {i+1}. {rel}")
        
        if target_cols:
            logger.info(f"✅ Successfully extracted {len(target_cols)} target columns")
            column_lineage_ok = True
        else:
            logger.error("❌ No target columns extracted!")
            
        if relationships:
            logger.info(f"✅ Successfully extracted {len(relationships)} column relationships")
            column_lineage_ok = column_lineage_ok and True
        else:
            logger.error("❌ No column relationships extracted!")
            column_lineage_ok = False
    else:
        # For backward compatibility with older dialect implementations
        if "columns" in lineage:
            columns = lineage.get("columns", [])
            logger.info(f"\nColumns (legacy format): {len(columns)}")
            for i, col in enumerate(columns[:5]):  # Show first 5 columns
                logger.info(f"  {i+1}. {col}")
            
            if columns:
                logger.info(f"✅ Successfully extracted {len(columns)} columns (legacy format)")
                column_lineage_ok = True
            else:
                logger.error("❌ No columns extracted (legacy format)!")
        else:
            logger.error(f"❌ {dialect_name} does not provide column_lineage or columns")
    
    # Overall success
    if table_lineage_ok and column_lineage_ok:
        logger.info(f"✅ {dialect_name.upper()} lineage extraction test PASSED\n")
        return True
    else:
        logger.error(f"❌ {dialect_name.upper()} lineage extraction test FAILED\n")
        return False

def main():
    """Main function to test all dialects"""
    # Set up test file paths
    file_paths = {
        "postgres": "customer_summary.sql",
        "tsql": "customer_summary.sql",
        "dbt": "models/analytics/customer_summary.sql"
    }
    
    # Test each dialect
    results = {}
    
    logger.info("Starting comprehensive dialect lineage testing...")
    
    # Test PostgreSQL
    results["postgres"] = test_dialect_lineage("postgres", POSTGRES_SQL, file_paths["postgres"])
    
    # Test T-SQL
    results["tsql"] = test_dialect_lineage("tsql", TSQL_SQL, file_paths["tsql"])
    
    # Test DBT
    results["dbt"] = test_dialect_lineage("dbt", DBT_SQL, file_paths["dbt"])
    
    # Print summary
    logger.info("\n=== DIALECT TESTING SUMMARY ===")
    for dialect, passed in results.items():
        status = "✅ PASSED" if passed else "❌ FAILED"
        logger.info(f"{dialect.upper()}: {status}")
    
    # Overall success
    if all(results.values()):
        logger.info("\n✅ ALL DIALECTS PASSED")
        return 0
    else:
        logger.error("\n❌ SOME DIALECTS FAILED")
        return 1

if __name__ == "__main__":
    sys.exit(main())
