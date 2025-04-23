"""
Test Lineage Flow

This script tests the complete lineage flow from SQL parsing to database storage.
"""

import logging
import sys
from tools.sql_tools.dialects import get_dialect_parser, get_available_dialects
from tools.sql_tools.lineage.sqlglot_lineage import SQLGlotLineageExtractor
from database.lineage_db import LineageDB

# Configure logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Sample SQL code (T-SQL)
TSQL_SAMPLE = """
CREATE TABLE dbo.FactSales (
    SalesID INT PRIMARY KEY,
    ProductID INT NOT NULL,
    CustomerID INT NOT NULL,
    OrderDate DATE NOT NULL,
    Quantity INT NOT NULL,
    UnitPrice DECIMAL(10, 2) NOT NULL,
    TotalAmount DECIMAL(10, 2) NOT NULL
);

INSERT INTO dbo.FactSales (SalesID, ProductID, CustomerID, OrderDate, Quantity, UnitPrice, TotalAmount)
SELECT 
    o.OrderID AS SalesID,
    p.ProductID,
    c.CustomerID,
    o.OrderDate,
    od.Quantity,
    od.UnitPrice,
    od.Quantity * od.UnitPrice AS TotalAmount
FROM 
    dbo.Orders o
    INNER JOIN dbo.OrderDetails od ON o.OrderID = od.OrderID
    INNER JOIN dbo.Products p ON od.ProductID = p.ProductID
    INNER JOIN dbo.Customers c ON o.CustomerID = c.CustomerID
WHERE 
    o.OrderDate > '2022-01-01';
"""

# Sample SQL code (PostgreSQL)
POSTGRESQL_SAMPLE = """
CREATE TABLE public.fact_sales (
    sales_id SERIAL PRIMARY KEY,
    product_id INTEGER NOT NULL REFERENCES public.products(product_id),
    customer_id INTEGER NOT NULL REFERENCES public.customers(customer_id),
    order_date DATE NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price NUMERIC(10, 2) NOT NULL,
    total_amount NUMERIC(10, 2) NOT NULL
);

INSERT INTO public.fact_sales (product_id, customer_id, order_date, quantity, unit_price, total_amount)
SELECT 
    p.product_id,
    c.customer_id,
    o.order_date,
    od.quantity,
    od.unit_price,
    od.quantity * od.unit_price AS total_amount
FROM 
    public.orders o
    INNER JOIN public.order_details od ON o.order_id = od.order_id
    INNER JOIN public.products p ON od.product_id = p.product_id
    INNER JOIN public.customers c ON o.customer_id = c.customer_id
WHERE 
    o.order_date > '2022-01-01';
"""

def test_dialect_parser(tech_stack, sql_code):
    """Test the dialect parser"""
    logger.info(f"Testing dialect parser for {tech_stack}")
    
    # Get dialect parser
    dialect = get_dialect_parser(tech_stack)
    if not dialect:
        logger.error(f"No dialect parser found for {tech_stack}")
        return False
    
    # Parse SQL
    ast, errors = dialect.parse_sql(sql_code)
    
    if errors:
        logger.error(f"Errors parsing {tech_stack} SQL: {errors}")
        return False
    
    if not ast:
        logger.error(f"Failed to parse {tech_stack} SQL")
        return False
    
    logger.info(f"Successfully parsed {tech_stack} SQL")
    return ast

def test_lineage_extraction(tech_stack, ast):
    """Test lineage extraction"""
    logger.info(f"Testing lineage extraction for {tech_stack}")
    
    # Create lineage extractor
    extractor = SQLGlotLineageExtractor()
    
    # Extract table lineage
    table_lineage = extractor.extract_table_lineage(ast, "test_file.sql")
    
    # Extract column lineage
    column_lineage = extractor.extract_column_lineage(ast, "test_file.sql")
    
    # Print results
    logger.info(f"Table lineage: {table_lineage}")
    logger.info(f"Column lineage: {column_lineage}")
    
    return table_lineage, column_lineage

def test_lineage_storage(tech_stack, table_lineage, column_lineage):
    """Test lineage storage in database"""
    logger.info(f"Testing lineage storage for {tech_stack}")
    
    # Create lineage DB connection
    lineage_db = LineageDB()
    
    # Store target table if found
    if table_lineage.get("target_table"):
        target_table = table_lineage["target_table"]["name"]
        
        # Add table to database
        table_id = lineage_db.add_table(
            table_name=target_table,
            tech_stack=tech_stack,
            github_path="test_file.sql",
            schema_name=table_lineage["target_table"].get("schema"),
            business_description="Test table"
        )
        
        # Add lineage definition
        lineage_id = lineage_db.add_lineage_definition(
            root_table_id=table_id,
            lineage_json={
                "table_lineage": table_lineage,
                "column_lineage": column_lineage
            },
            tech_stack=tech_stack
        )
        
        logger.info(f"Stored lineage with ID: {lineage_id}")
        return lineage_id
    
    logger.error("No target table found in lineage")
    return None

def main():
    """Main test function"""
    logger.info("Starting lineage flow test")
    
    # Print available dialects
    dialects = get_available_dialects()
    logger.info(f"Available dialects: {dialects}")
    
    # Test T-SQL flow
    logger.info("Testing T-SQL flow")
    tsql_ast = test_dialect_parser("tsql", TSQL_SAMPLE)
    if tsql_ast:
        table_lineage, column_lineage = test_lineage_extraction("tsql", tsql_ast)
        lineage_id = test_lineage_storage("tsql", table_lineage, column_lineage)
    
    # Test PostgreSQL flow
    logger.info("Testing PostgreSQL flow")
    pg_ast = test_dialect_parser("postgresql", POSTGRESQL_SAMPLE)
    if pg_ast:
        table_lineage, column_lineage = test_lineage_extraction("postgresql", pg_ast)
        lineage_id = test_lineage_storage("postgresql", table_lineage, column_lineage)
    
    logger.info("Lineage flow test completed")

if __name__ == "__main__":
    main() 