"""
GitHub SQL Finder

This module uses vector search to find SQL files in GitHub repositories
and extract their content for dependency analysis.
"""

import os
import logging
from typing import Dict, List, Optional, Any
import re
import chromadb
import traceback

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class GitHubSQLFinder:
    """
    Find SQL files in GitHub repositories using vector search
    """
    
    def __init__(self, vector_store_path=None):
        """
        Initialize the GitHub SQL Finder
        
        Args:
            vector_store_path: Path to the ChromaDB vector store
        """
        # Set default path if None
        if vector_store_path is None:
            # Use the directory of this file to ensure we create in correct location
            current_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            vector_store_path = os.path.join(current_dir, "vector_store", "chromadb_github")
            
        self.vector_store_path = vector_store_path
        logger.info(f"GitHubSQLFinder initializing with vector_store_path: {self.vector_store_path}")
        
        self.chroma_client = None
        self.collection = None
        
    def initialize(self):
        """Initialize ChromaDB client and collection"""
        try:
            logger.info(f"Initializing ChromaDB with path: {self.vector_store_path}")
            
            # Verify the path exists or can be created
            try:
                # Ensure directory exists
                os.makedirs(self.vector_store_path, exist_ok=True)
                logger.info(f"Directory exists or created: {self.vector_store_path}")
            except Exception as e:
                logger.error(f"Error creating directory {self.vector_store_path}: {e}")
                return False
            
            # Verify it's a valid directory
            if not os.path.isdir(self.vector_store_path):
                logger.error(f"Path is not a directory: {self.vector_store_path}")
                return False
                
            # Initialize client
            try:
                logger.info(f"Creating ChromaDB client with path: {self.vector_store_path}")
                self.chroma_client = chromadb.PersistentClient(path=self.vector_store_path)
                logger.info("ChromaDB client created successfully")
            except Exception as e:
                logger.error(f"Error creating ChromaDB client: {str(e)}")
                logger.error(traceback.format_exc())
                return False
            
            # Get or create the collection
            try:
                # First try to get the existing collection
                logger.info("Attempting to get existing collection 'github_sql'")
                self.collection = self.chroma_client.get_collection("github_sql")
                logger.info(f"Found existing ChromaDB collection with {self.collection.count()} documents")
            except Exception as e:
                # If not found, create a new collection
                logger.info(f"Collection 'github_sql' not found, creating it now...")
                try:
                    from chromadb.utils import embedding_functions
                    embedding_func = embedding_functions.DefaultEmbeddingFunction()
                    self.collection = self.chroma_client.create_collection(
                        name="github_sql",
                        embedding_function=embedding_func
                    )
                    logger.info("Created new collection, populating with sample data...")
                    self._populate_sample_data()
                    return True
                except Exception as create_e:
                    logger.error(f"Error creating collection: {str(create_e)}")
                    logger.error(traceback.format_exc())
                    return False
                
            return True
        except Exception as e:
            logger.error(f"Error initializing ChromaDB: {e}")
            logger.error(traceback.format_exc())
            return False
    
    def _populate_sample_data(self):
        """Add sample SQL data to the collection"""
        # Sample SQL files to load
        sample_files = [
            {
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
        
        try:
            # Add documents
            ids = []
            documents = []
            metadatas = []
            
            for i, file_info in enumerate(sample_files):
                ids.append(f"sql_{i}")
                documents.append(file_info["content"])
                metadatas.append(file_info["metadata"])
            
            # Add or update documents
            self.collection.add(
                ids=ids,
                documents=documents,
                metadatas=metadatas
            )
            
            logger.info(f"Successfully added {len(ids)} sample SQL files to ChromaDB")
        except Exception as e:
            logger.error(f"Error populating sample data: {e}")
            import traceback
            traceback.print_exc()
    
    def set_vector_store(self, vector_store_client):
        """For compatibility with earlier code"""
        if vector_store_client:
            logger.info("Vector store client provided, but GitHubSQLFinder now uses ChromaDB directly")
    
    def search_sql_files(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Search for SQL files based on the query
        
        Args:
            query: Search query
            limit: Maximum number of results
            
        Returns:
            List of matching SQL files with metadata
        """
        if not self.collection:
            logger.error("ChromaDB collection not initialized")
            return [{"error": "ChromaDB collection not initialized"}]
        
        try:
            # Search the vector store
            logger.info(f"Searching for SQL files with query: {query}")
            results = self.collection.query(
                query_texts=[query],
                n_results=min(limit, self.collection.count())
            )
            
            # Check for empty results
            if not results or not results.get("documents") or len(results["documents"]) == 0 or len(results["documents"][0]) == 0:
                logger.warning(f"No results found for query: {query}")
                return []
                
            logger.info(f"Found {len(results['documents'][0])} SQL files matching query")
            
            # Process and return the results
            sql_files = []
            for i, doc_content in enumerate(results["documents"][0]):
                # Make sure we have metadata for this document
                if i >= len(results["metadatas"][0]):
                    logger.warning(f"Missing metadata for document at index {i}")
                    continue
                    
                metadata = results["metadatas"][0][i] or {}
                
                # Extract file path, GitHub URL, etc.
                sql_files.append({
                    "content": doc_content,
                    "path": metadata.get("source", ""),
                    "url": metadata.get("url", ""),
                    "github_repo": metadata.get("repo", ""),
                    "file_name": os.path.basename(metadata.get("source", "")),
                    "dialect": self._detect_sql_dialect(doc_content, metadata)
                })
            
            return sql_files
            
        except Exception as e:
            logger.error(f"Error searching for SQL files: {str(e)}")
            return [{"error": f"Error searching for SQL files: {str(e)}"}]
    
    def search_for_table(self, table_name: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Search for SQL files that reference a specific table
        
        Args:
            table_name: Table name to search for
            limit: Maximum number of results
            
        Returns:
            List of matching SQL files with metadata
        """
        # First try a direct search for the table name
        query = f"table {table_name} SQL"
        logger.info(f"Searching for table: {table_name}")
        return self.search_sql_files(query, limit)
    
    def search_for_column(self, table_name: str, column_name: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Search for SQL files that reference a specific column in a table
        
        Args:
            table_name: Table name
            column_name: Column name
            limit: Maximum number of results
            
        Returns:
            List of matching SQL files with metadata
        """
        query = f"table {table_name} column {column_name} SQL"
        return self.search_sql_files(query, limit)
    
    def _detect_sql_dialect(self, content: str, metadata: Dict[str, Any]) -> str:
        """
        Detect the SQL dialect from content and metadata
        
        Args:
            content: SQL content
            metadata: File metadata
            
        Returns:
            Detected SQL dialect
        """
        # Check metadata first
        repo = metadata.get("repo", "").lower()
        file_path = metadata.get("source", "").lower()
        
        # Check for dbt
        if '/dbt/' in file_path or repo.startswith('dbt-') or repo.endswith('-dbt'):
            return "dbt"
        
        # Check for specific paths that might indicate dialect
        if '/snowflake/' in file_path:
            return "snowflake"
        if '/redshift/' in file_path:
            return "redshift"
        if '/postgres/' in file_path or '/postgresql/' in file_path:
            return "postgresql"
        if '/mysql/' in file_path:
            return "mysql"
        if '/mssql/' in file_path or '/azure/' in file_path:
            return "azuresql"
        
        # Check content for dialect-specific keywords
        content_lower = content.lower()
        
        # Snowflake specific
        if re.search(r'create\s+(?:or\s+replace\s+)?(?:table|view|procedure|function|stage|pipe)\s+', content_lower) and ('warehouse' in content_lower or 'lateral flatten' in content_lower):
            return "snowflake"
        
        # Redshift specific
        if 'diststyle' in content_lower or 'distkey' in content_lower or 'sortkey' in content_lower:
            return "redshift"
        
        # Azure SQL/TSQL specific
        if 'with(nolock)' in content_lower.replace(' ', '') or 'exec sp_' in content_lower:
            return "azuresql"
        
        # MySQL specific
        if 'engine=innodb' in content_lower or 'auto_increment' in content_lower:
            return "mysql"
        
        # Default to PostgreSQL which is most common and widely compatible
        return "postgresql" 