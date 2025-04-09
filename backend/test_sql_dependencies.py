"""
Test script to create a sample SQL vector store for testing dependencies
"""
import os
import sys
import logging
from pathlib import Path
import chromadb
from chromadb.utils import embedding_functions

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

print(f"Current working directory: {os.getcwd()}")
print(f"Script directory: {os.path.dirname(os.path.abspath(__file__))}")

# Sample SQL files for testing
SAMPLE_SQL_FILES = [
    {
        "name": "fct_order_items.sql",
        "content": """
-- Final fact table for order items
CREATE OR REPLACE TABLE analytics.fct_order_items AS
SELECT 
    o.order_id,
    oi.order_item_id,
    o.customer_id,
    o.order_date,
    p.product_id,
    p.product_name,
    p.category_id,
    c.category_name,
    oi.quantity,
    oi.base_price,
    oi.discount_pct,
    -- Calculate the item discount amount
    oi.base_price * oi.quantity * (oi.discount_pct / 100) AS item_discount_amount,
    oi.base_price * oi.quantity * (1 - oi.discount_pct / 100) AS final_price,
    o.order_status
FROM 
    raw_data.orders o
JOIN 
    raw_data.order_items oi ON o.order_id = oi.order_id
JOIN 
    raw_data.products p ON oi.product_id = p.product_id
JOIN 
    raw_data.categories c ON p.category_id = c.category_id
""",
        "metadata": {
            "repo": "analytics-dbt",
            "file_extension": ".sql",
            "source": "models/fct_order_items.sql",
            "url": "https://github.com/company/analytics-dbt/blob/main/models/fct_order_items.sql"
        }
    },
    {
        "name": "stg_orders.sql",
        "content": """
-- Staging table for orders
CREATE OR REPLACE TABLE raw_data.orders AS
SELECT 
    order_id,
    customer_id,
    order_date,
    order_status,
    total_amount
FROM 
    source_data.orders
WHERE
    order_date >= '2023-01-01'
""",
        "metadata": {
            "repo": "analytics-dbt",
            "file_extension": ".sql",
            "source": "models/staging/stg_orders.sql",
            "url": "https://github.com/company/analytics-dbt/blob/main/models/staging/stg_orders.sql"
        }
    },
    {
        "name": "stg_order_items.sql",
        "content": """
-- Staging table for order items
CREATE OR REPLACE TABLE raw_data.order_items AS
SELECT 
    order_id,
    order_item_id,
    product_id,
    quantity,
    base_price,
    discount_pct
FROM 
    source_data.order_items
""",
        "metadata": {
            "repo": "analytics-dbt",
            "file_extension": ".sql",
            "source": "models/staging/stg_order_items.sql",
            "url": "https://github.com/company/analytics-dbt/blob/main/models/staging/stg_order_items.sql"
        }
    },
    {
        "name": "stg_products.sql",
        "content": """
-- Staging table for products
CREATE OR REPLACE TABLE raw_data.products AS
SELECT 
    product_id,
    product_name,
    category_id,
    price,
    inventory_count
FROM 
    source_data.products
""",
        "metadata": {
            "repo": "analytics-dbt",
            "file_extension": ".sql",
            "source": "models/staging/stg_products.sql",
            "url": "https://github.com/company/analytics-dbt/blob/main/models/staging/stg_products.sql"
        }
    },
    {
        "name": "stg_categories.sql",
        "content": """
-- Staging table for categories
CREATE OR REPLACE TABLE raw_data.categories AS
SELECT 
    category_id,
    category_name,
    parent_category_id,
    category_description
FROM 
    source_data.categories
""",
        "metadata": {
            "repo": "analytics-dbt",
            "file_extension": ".sql",
            "source": "models/staging/stg_categories.sql",
            "url": "https://github.com/company/analytics-dbt/blob/main/models/staging/stg_categories.sql"
        }
    },
    {
        "name": "rpt_discounts.sql",
        "content": """
-- Report on product discounts
CREATE OR REPLACE TABLE analytics.rpt_discounts AS
SELECT 
    c.category_name,
    p.product_name,
    SUM(oi.quantity) as total_quantity,
    SUM(oi.base_price * oi.quantity) as total_base_amount,
    -- Reusing the discount calculation logic
    SUM(oi.base_price * oi.quantity * (oi.discount_pct / 100)) as item_discount_amount,
    AVG(oi.discount_pct) as avg_discount_pct
FROM 
    raw_data.order_items oi
JOIN 
    raw_data.products p ON oi.product_id = p.product_id
JOIN 
    raw_data.categories c ON p.category_id = c.category_id
WHERE
    oi.discount_pct > 0
GROUP BY
    c.category_name, p.product_name
ORDER BY
    item_discount_amount DESC
""",
        "metadata": {
            "repo": "analytics-dbt",
            "file_extension": ".sql",
            "source": "models/reporting/rpt_discounts.sql",
            "url": "https://github.com/company/analytics-dbt/blob/main/models/reporting/rpt_discounts.sql"
        }
    }
]

def setup_chromadb():
    """Create a ChromaDB collection with sample SQL files"""
    try:
        # Setup vector store directory
        vector_store_path = "vector_store/chromadb_github"
        os.makedirs(vector_store_path, exist_ok=True)
        
        # Initialize ChromaDB client
        chroma_client = chromadb.PersistentClient(path=vector_store_path)
        
        # Create or get collection
        collection = None
        try:
            # Try to get existing collection
            collection = chroma_client.get_collection("github_code")
            logger.info(f"Using existing collection with {collection.count()} documents")
        except Exception as e:
            logger.info(f"Collection not found: {e}, creating new one")
            # Create new collection with default embedding function
            embedding_func = embedding_functions.DefaultEmbeddingFunction()
            collection = chroma_client.create_collection(
                name="github_code",
                embedding_function=embedding_func
            )
            logger.info("Created new collection")
        
        # Add documents
        ids = []
        documents = []
        metadatas = []
        
        for i, sql_file in enumerate(SAMPLE_SQL_FILES):
            ids.append(f"sql_{i}")
            documents.append(sql_file["content"])
            metadatas.append(sql_file["metadata"])
        
        # Add or update documents
        collection.add(
            ids=ids,
            documents=documents,
            metadatas=metadatas
        )
        
        logger.info(f"Successfully added {len(ids)} documents to ChromaDB")
        
        # Test a query
        results = collection.query(
            query_texts=["item_discount_amount"],
            n_results=2
        )
        
        logger.info(f"Test query results: {len(results['documents'][0])} documents found")
        for i, doc in enumerate(results['documents'][0]):
            logger.info(f"Result {i+1}: {results['metadatas'][0][i]['source']}")
        
        return True
    except Exception as e:
        logger.error(f"Failed to set up ChromaDB: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    logger.info("Setting up test SQL vector store...")
    if setup_chromadb():
        logger.info("Vector store setup complete. Ready for testing dependency analysis.")
    else:
        logger.error("Failed to set up vector store.") 