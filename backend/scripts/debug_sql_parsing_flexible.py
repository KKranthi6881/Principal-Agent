#!/usr/bin/env python3
"""
Debug script to test SQL parsing and column extraction with flexible approach

This script directly tests the SQL parsing and column extraction logic,
handling different method signatures by inspecting them first.
"""

import os
import sys
import logging
import json
import inspect
from typing import Dict, List, Any, Optional

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Add the backend directory to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import the SQL dialect handlers
from tools.sql_tools.dialects import get_dialect_parser, get_available_dialects
from tools.sql_tools.lineage.sqlglot_lineage import SQLGlotLineageExtractor

def print_dict(d, indent=0):
    """Helper function to print a dictionary with indentation"""
    for key, value in d.items():
        if isinstance(value, dict):
            print(" " * indent + f"{key}:")
            print_dict(value, indent + 4)
        elif isinstance(value, list):
            print(" " * indent + f"{key}: [{len(value)} items]")
            for i, item in enumerate(value[:5]):  # Only show first 5 items
                if isinstance(item, dict):
                    print(" " * (indent + 4) + f"[{i}]:")
                    print_dict(item, indent + 8)
                else:
                    print(" " * (indent + 4) + f"[{i}]: {item}")
            if len(value) > 5:
                print(" " * (indent + 4) + f"... {len(value) - 5} more items")
        else:
            print(" " * indent + f"{key}: {value}")

def call_parse_sql_flexible(dialect, sql_code, file_path=None):
    """Call parse_sql with flexible arguments based on method inspection"""
    # Get the signature of the parse_sql method
    sig = inspect.signature(dialect.parse_sql)
    logger.info(f"Method signature for parse_sql: {sig}")
    
    # Check if the method accepts file_path parameter
    if 'file_path' in sig.parameters:
        logger.info("Method accepts file_path parameter")
        return dialect.parse_sql(sql_code, file_path)
    else:
        logger.info("Method does not accept file_path parameter, calling without it")
        return dialect.parse_sql(sql_code)

def test_parse_sql(tech_stack: str, sql_code: str, file_path: Optional[str] = None) -> None:
    """Test parsing SQL code with a specific dialect"""
    logger.info(f"Testing SQL parsing with {tech_stack} dialect")
    
    dialect = get_dialect_parser(tech_stack)
    if not dialect:
        logger.error(f"Dialect not found for tech stack: {tech_stack}")
        return
    
    # Step 1: Parse SQL with flexible approach
    logger.info("Step 1: Parsing SQL code")
    ast, errors = call_parse_sql_flexible(dialect, sql_code, file_path)
    
    if errors:
        logger.warning(f"Parsing errors: {errors}")
    
    if not ast:
        logger.error("SQL parsing failed - no AST produced")
        return
    
    logger.info("SQL parsing successful")
    
    # Step 2: Extract table lineage
    logger.info("Step 2: Extracting table lineage")
    lineage_extractor = SQLGlotLineageExtractor()
    table_lineage = lineage_extractor.extract_table_lineage(ast, file_path)
    
    logger.info("Table lineage results:")
    print_dict(table_lineage)
    
    # Step 3: Extract column lineage
    logger.info("Step 3: Extracting column lineage")
    column_lineage = lineage_extractor.extract_column_lineage(ast, file_path)
    
    logger.info("Column lineage results:")
    if column_lineage:
        print_dict(column_lineage)
    else:
        logger.warning("No column lineage extracted")
    
    # Step 4: Additional dialect-specific lineage extraction 
    logger.info("Step 4: Dialect-specific lineage extraction")
    dialect_lineage = {}
    
    # Call extract_lineage with flexible approach if available
    if hasattr(dialect, 'extract_lineage'):
        sig = inspect.signature(dialect.extract_lineage)
        if 'file_path' in sig.parameters:
            dialect_lineage = dialect.extract_lineage(sql_code, file_path)
        else:
            dialect_lineage = dialect.extract_lineage(sql_code)
    
    logger.info("Dialect-specific lineage results:")
    print_dict(dialect_lineage)

def main():
    """Main function to test SQL parsing with different dialects"""
    # Get available dialects
    dialects = get_available_dialects()
    logger.info(f"Available dialects: {list(dialects.keys())}")
    
    # Test TSQL parsing
    tsql_sample = """
    CREATE TABLE Customers (
        CustomerID INT PRIMARY KEY,
        Name VARCHAR(100) NOT NULL,
        Email VARCHAR(100),
        Phone VARCHAR(20)
    );
    
    CREATE TABLE Orders (
        OrderID INT PRIMARY KEY,
        CustomerID INT FOREIGN KEY REFERENCES Customers(CustomerID),
        OrderDate DATETIME NOT NULL,
        TotalAmount DECIMAL(10, 2) NOT NULL
    );
    
    SELECT 
        c.Name,
        c.Email,
        o.OrderID,
        o.OrderDate,
        o.TotalAmount
    FROM 
        Customers c
    JOIN 
        Orders o ON c.CustomerID = o.CustomerID
    WHERE 
        o.OrderDate > '2023-01-01';
    """
    
    test_parse_sql("tsql", tsql_sample, "sample_query.sql")
    
    # Test PostgreSQL parsing
    postgres_sample = """
    CREATE TABLE customers (
        customer_id SERIAL PRIMARY KEY,
        name VARCHAR(100) NOT NULL,
        email VARCHAR(100),
        phone VARCHAR(20)
    );
    
    CREATE TABLE orders (
        order_id SERIAL PRIMARY KEY,
        customer_id INTEGER REFERENCES customers(customer_id),
        order_date TIMESTAMP NOT NULL,
        total_amount NUMERIC(10, 2) NOT NULL
    );
    
    SELECT 
        c.name,
        c.email,
        o.order_id,
        o.order_date,
        o.total_amount
    FROM 
        customers c
    JOIN 
        orders o ON c.customer_id = o.customer_id
    WHERE 
        o.order_date > '2023-01-01';
    """
    
    test_parse_sql("postgresql", postgres_sample, "sample_query.sql")
    
    # Test DBT parsing
    dbt_sample = """
    -- A simple DBT model that references another model
    WITH orders AS (
        SELECT * FROM {{ ref('stg_orders') }}
    ),
    
    customers AS (
        SELECT * FROM {{ ref('stg_customers') }}
    ),
    
    order_details AS (
        SELECT
            o.order_id,
            o.customer_id,
            c.name as customer_name,
            c.email as customer_email,
            o.order_date,
            o.total_amount
        FROM orders o
        LEFT JOIN customers c ON o.customer_id = c.customer_id
    )
    
    SELECT * FROM order_details
    """
    
    test_parse_sql("dbt", dbt_sample, "models/mart/order_details.sql")

if __name__ == "__main__":
    main()
