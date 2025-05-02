#!/usr/bin/env python
"""
Test Column Lineage Extraction

This script tests column lineage extraction directly using the SQLGlotLineageExtractor.
"""

import os
import sys
import logging
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Import required modules
from sqlglot import parse_one, ParseError
from tools.sql_tools.lineage.sqlglot_lineage import SQLGlotLineageExtractor

# Set up test SQL files 
TEST_SQL_DIR = Path(__file__).parent / "test_sql"
TEST_SQL_DIR.mkdir(exist_ok=True)

# Sample SQL files
TSQL_SAMPLE = """
CREATE TABLE dbo.CustomerOrders (
    CustomerID INT PRIMARY KEY,
    OrderID INT NOT NULL,
    OrderDate DATETIME,
    TotalAmount DECIMAL(10,2),
    Region VARCHAR(50),
    CONSTRAINT FK_CustomerOrders_Customers FOREIGN KEY (CustomerID) REFERENCES dbo.Customers(CustomerID)
);

INSERT INTO dbo.CustomerOrders (CustomerID, OrderID, OrderDate, TotalAmount, Region)
SELECT 
    c.CustomerID,
    o.OrderID,
    o.OrderDate,
    SUM(od.Quantity * od.UnitPrice) as TotalAmount,
    c.Region
FROM 
    dbo.Customers c
JOIN 
    dbo.Orders o ON c.CustomerID = o.CustomerID
JOIN 
    dbo.OrderDetails od ON o.OrderID = od.OrderID
WHERE 
    c.Active = 1
GROUP BY 
    c.CustomerID, o.OrderID, o.OrderDate, c.Region;
"""

POSTGRES_SAMPLE = """
CREATE TABLE public.sales_summary (
    product_id INTEGER NOT NULL,
    category_id INTEGER,
    product_name VARCHAR(100),
    total_sales DECIMAL(12,2),
    units_sold INTEGER,
    avg_unit_price DECIMAL(10,2),
    year INTEGER,
    month INTEGER,
    PRIMARY KEY (product_id, year, month),
    FOREIGN KEY (category_id) REFERENCES public.categories(category_id)
);

INSERT INTO public.sales_summary (
    product_id, category_id, product_name, total_sales, 
    units_sold, avg_unit_price, year, month
)
SELECT 
    p.product_id,
    p.category_id,
    p.product_name,
    SUM(s.quantity * s.unit_price) as total_sales,
    SUM(s.quantity) as units_sold,
    AVG(s.unit_price) as avg_unit_price,
    EXTRACT(YEAR FROM s.sale_date) as year,
    EXTRACT(MONTH FROM s.sale_date) as month
FROM 
    public.products p
JOIN 
    public.sales s ON p.product_id = s.product_id
GROUP BY 
    p.product_id, p.category_id, p.product_name, 
    EXTRACT(YEAR FROM s.sale_date), EXTRACT(MONTH FROM s.sale_date);
"""

DBT_SAMPLE = """
{{ config(
    materialized='table',
    tags=['daily', 'sales']
) }}

WITH customer_orders AS (
    SELECT
        c.customer_id,
        c.first_name,
        c.last_name,
        c.email,
        o.order_id,
        o.order_date,
        o.status
    FROM 
        {{ ref('customers') }} c
    JOIN 
        {{ ref('orders') }} o ON c.customer_id = o.customer_id
    WHERE 
        o.status != 'canceled'
),

order_items AS (
    SELECT
        order_id,
        SUM(quantity) as total_items,
        SUM(quantity * price) as order_value
    FROM 
        {{ ref('order_items') }}
    GROUP BY 
        order_id
)

SELECT
    co.customer_id,
    co.first_name,
    co.last_name,
    co.email,
    co.order_id,
    co.order_date,
    co.status,
    oi.total_items,
    oi.order_value
FROM 
    customer_orders co
JOIN 
    order_items oi ON co.order_id = oi.order_id
"""

def write_test_files():
    """Write test SQL files"""
    (TEST_SQL_DIR / "tsql_sample.sql").write_text(TSQL_SAMPLE)
    (TEST_SQL_DIR / "postgres_sample.sql").write_text(POSTGRES_SAMPLE)
    (TEST_SQL_DIR / "dbt_sample.sql").write_text(DBT_SAMPLE)
    
    logger.info(f"Test SQL files created in {TEST_SQL_DIR}")
    return {
        "tsql": str(TEST_SQL_DIR / "tsql_sample.sql"),
        "postgres": str(TEST_SQL_DIR / "postgres_sample.sql"),
        "dbt": str(TEST_SQL_DIR / "dbt_sample.sql")
    }

def test_parse_and_extract(sql_content, dialect_name, file_path=None):
    """Parse SQL and extract column lineage"""
    logger.info(f"Testing column lineage extraction for {dialect_name}")
    
    try:
        # Parse SQL with appropriate dialect
        ast = parse_one(sql_content, dialect=dialect_name)
        
        # Create lineage extractor
        lineage_extractor = SQLGlotLineageExtractor()
        
        # Extract column lineage
        column_lineage = lineage_extractor.extract_column_lineage(ast, file_path=file_path)
        
        # Log results
        logger.info(f"Column lineage results:")
        logger.info(f"Source columns: {len(column_lineage.get('source_columns', []))}")
        logger.info(f"Target columns: {len(column_lineage.get('target_columns', []))}")
        logger.info(f"Column relationships: {len(column_lineage.get('column_relationships', []))}")
        
        # Log detailed info
        if column_lineage.get('target_columns'):
            logger.info("Target columns:")
            for i, col in enumerate(column_lineage.get('target_columns', [])):
                logger.info(f"  {i+1}. {col.get('name')} - Table: {col.get('table')}, Type: {col.get('data_type')}")
        
        if column_lineage.get('source_columns'):
            logger.info("Source columns:")
            for i, col in enumerate(column_lineage.get('source_columns', [])[:5]):  # Show first 5 only
                logger.info(f"  {i+1}. {col.get('column')} - Table: {col.get('table')}")
        
        if column_lineage.get('column_relationships'):
            logger.info("Column relationships:")
            for i, rel in enumerate(column_lineage.get('column_relationships', [])[:5]):  # Show first 5 only
                logger.info(f"  {i+1}. {rel.get('source_column')} ({rel.get('source_table')}) -> {rel.get('target_column')} ({rel.get('target_table')})")
        
        return column_lineage
        
    except Exception as e:
        logger.error(f"Error in test_parse_and_extract: {str(e)}")
        return None

def main():
    """Main function"""
    logger.info("Starting column lineage test script")
    
    # Create test files
    test_files = write_test_files()
    
    # Test with different SQL dialects
    results = {}
    
    # Test T-SQL
    logger.info("\n=== Testing T-SQL Column Lineage ===")
    with open(test_files["tsql"], 'r') as f:
        tsql_content = f.read()
    results["tsql"] = test_parse_and_extract(tsql_content, "tsql", test_files["tsql"])
    
    # Test PostgreSQL
    logger.info("\n=== Testing PostgreSQL Column Lineage ===")
    with open(test_files["postgres"], 'r') as f:
        postgres_content = f.read()
    results["postgres"] = test_parse_and_extract(postgres_content, "postgres", test_files["postgres"])
    
    # Test basic SQL for DBT
    logger.info("\n=== Testing DBT Column Lineage (as postgres) ===")
    with open(test_files["dbt"], 'r') as f:
        dbt_content = f.read()
    results["dbt"] = test_parse_and_extract(dbt_content, "postgres", test_files["dbt"])
    
    # Log summary
    logger.info("\n=== Column Lineage Testing Summary ===")
    for dialect, result in results.items():
        if result:
            target_cols = len(result.get('target_columns', []))
            relationships = len(result.get('column_relationships', []))
            logger.info(f"{dialect.upper()}: {target_cols} target columns, {relationships} relationships")
        else:
            logger.info(f"{dialect.upper()}: Failed to extract column lineage")
    
    logger.info("Column lineage testing complete")

if __name__ == "__main__":
    main()
