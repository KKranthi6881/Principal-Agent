#!/usr/bin/env python3
"""
Test script for complete lineage tracing functionality with DBT repositories
"""

import os
import sys
import json
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Add backend directory to path
backend_dir = Path(__file__).parent
if str(backend_dir) not in sys.path:
    sys.path.append(str(backend_dir))

# Import the SQL API
try:
    from tools.sql.api import SQLAnalysisAPI, sql_api
    logger.info("Successfully imported SQL API")
except Exception as e:
    logger.error(f"Error importing SQL API: {e}")
    sys.exit(1)

def print_json(obj):
    """Pretty print JSON object"""
    print(json.dumps(obj, indent=2))

def test_github_vector_store():
    """Test that we can access the github_code vector store correctly"""
    from vector_store.github_vectorstore import get_github_vector_store
    vector_store = get_github_vector_store()
    
    if vector_store:
        count = vector_store.count()
        logger.info(f"Successfully accessed github_code vector store. Document count: {count}")
        stats = vector_store.get_stats()
        logger.info(f"Vector store stats: {json.dumps(stats, indent=2)}")
        return True
    else:
        logger.error("Failed to access github_code vector store")
        return False

def test_table_lineage(table_name, direction="upstream", max_depth=5, dialect=None, repo_url=None):
    """Test table lineage tracing"""
    if repo_url:
        logger.info(f"Testing {direction} lineage for table {table_name} with repo URL {repo_url} (max depth: {max_depth})")
    else:
        logger.info(f"Testing {direction} lineage for table {table_name} with dialect {dialect or 'auto-detect'} (max depth: {max_depth})")
    
    try:
        # If repo_url is provided, detect dialect from it
        if repo_url and not dialect:
            detected_dialect = sql_api.detect_dialect_from_repo_url(repo_url)
            logger.info(f"Auto-detected dialect {detected_dialect} from repo URL")
            dialect = detected_dialect
        
        # Trace complete lineage
        result = sql_api.trace_complete_lineage(table_name, direction, max_depth, dialect)
        
        # Print results
        print("\n" + "=" * 80)
        print(f"LINEAGE RESULTS FOR {table_name} ({direction.upper()}) USING {result.get('dialect_used', 'unknown dialect')}")
        print("=" * 80)
        
        if "error" in result:
            print(f"Error: {result['error']}")
            return
        
        # Print summary
        print(result["summary"])
        
        # Print file paths for each level
        print("\nGITHUB FILES BY LEVEL:")
        print("-" * 50)
        for level, deps in result.get("dependencies_by_level", {}).items():
            print(f"\nLEVEL {level}:")
            for dep in deps:
                print(f"  • Table: {dep['table']}")
                print(f"    File: {dep['file_path'] if 'file_path' in dep else 'N/A'}")
                print(f"    URL: {dep.get('file_url', 'N/A')}")
                if "dependencies" in dep:
                    print(f"    Dependencies: {', '.join(dep['dependencies'])}")
                if "used_by" in dep:
                    print(f"    Used by: {dep['used_by']}")
                print("")
        
        # Print column lineage if available
        if result.get("column_lineage"):
            print("\nCOLUMN INFORMATION:")
            print("-" * 50)
            for table, columns in result["column_lineage"].items():
                print(f"\nTable: {table}")
                print(f"  Columns: {', '.join(columns)}")
        
        # Return result for potential further analysis
        return result
        
    except Exception as e:
        logger.error(f"Error testing lineage: {e}")
        return {"error": str(e)}

def test_column_lineage(table_name, column_name, direction="upstream", max_depth=5, dialect=None, repo_url=None):
    """Test column lineage tracing"""
    if repo_url:
        logger.info(f"Testing {direction} lineage for column {table_name}.{column_name} with repo URL {repo_url} (max depth: {max_depth})")
    else:
        logger.info(f"Testing {direction} lineage for column {table_name}.{column_name} with dialect {dialect or 'auto-detect'} (max depth: {max_depth})")
    
    try:
        # If repo_url is provided, detect dialect from it
        if repo_url and not dialect:
            detected_dialect = sql_api.detect_dialect_from_repo_url(repo_url)
            logger.info(f"Auto-detected dialect {detected_dialect} from repo URL")
            dialect = detected_dialect
        
        # Trace complete column lineage
        result = sql_api.trace_column_complete_lineage(table_name, column_name, direction, max_depth, dialect)
        
        # Print results
        print("\n" + "=" * 80)
        print(f"COLUMN LINEAGE RESULTS FOR {table_name}.{column_name} ({direction.upper()}) USING {result.get('dialect_used', 'unknown dialect')}")
        print("=" * 80)
        
        if "error" in result:
            print(f"Error: {result['error']}")
            return
        
        # Print summary
        print(result["summary"])
        
        # Print dependency chain
        if "column_chain" in result:
            print("\nCOLUMN DEPENDENCY CHAIN:")
            print("-" * 50)
            for i, level in enumerate(result["column_chain"]):
                print(f"Level {i}: {', '.join(level)}")
        
        # Print file paths for each level
        print("\nGITHUB FILES BY LEVEL:")
        print("-" * 50)
        for level, deps in result.get("dependencies_by_level", {}).items():
            print(f"\nLEVEL {level}:")
            for dep in deps:
                print(f"  • Column: {dep['column']}")
                print(f"    File: {dep['file_path'] if 'file_path' in dep else 'N/A'}")
                print(f"    URL: {dep.get('file_url', 'N/A')}")
                if "source_columns" in dep:
                    sources = [f"{src.get('table')}.{src.get('column')}" for src in dep["source_columns"] 
                              if src.get('table') and src.get('column')]
                    print(f"    Source columns: {', '.join(sources)}")
                if "used_by" in dep:
                    print(f"    Used by: {dep['used_by']}")
                print("")
        
        # Return result for potential further analysis
        return result
        
    except Exception as e:
        logger.error(f"Error testing column lineage: {e}")
        return {"error": str(e)}

def test_search_functionality():
    """Test search functionality to ensure it's using github_code collection"""
    logger.info("Testing search functionality with github_code collection")
    
    try:
        # Test a known table from the repository
        results = sql_api.search_for_table("stg_tpch_orders", limit=5)
        print("\nSEARCH RESULTS FOR TABLE 'stg_tpch_orders':")
        print("-" * 50)
        for i, result in enumerate(results):
            print(f"{i+1}. File: {result.get('file_path', 'N/A')}")
            print(f"   URL: {result.get('url', 'N/A')}")
            print(f"   Repo: {result.get('github_repo', 'N/A')}")
            print("")
        
        # Test direct query search for known models
        results = sql_api.search_for_sql_files("fct_order_items", limit=5)
        print("\nSEARCH RESULTS FOR QUERY 'fct_order_items':")
        print("-" * 50)
        for i, result in enumerate(results):
            print(f"{i+1}. File: {result.get('file_path', 'N/A')}")
            print(f"   URL: {result.get('url', 'N/A')}")
            print(f"   Repo: {result.get('github_repo', 'N/A')}")
            print("")
        
        return True
    except Exception as e:
        logger.error(f"Error testing search functionality: {e}")
        return False

if __name__ == "__main__":
    # First test vector store access
    print("\nTesting github_code vector store access...\n")
    if not test_github_vector_store():
        print("Failed to access github_code vector store. Exiting.")
        sys.exit(1)
    
    # Test search functionality
    print("\nTesting search functionality...\n")
    test_search_functionality()
    
    # Test cases for DBT
    print("\nTesting table lineage tracing...\n")
    
    # Based on known tables in the repository (from search results)
    dbt_repo_url = "https://github.com/dbt-labs/dbt-cloud-snowflake-demo-template"
    
    # Test 1: Upstream lineage for a table using dbt dialect
    test_table_lineage("stg_tpch_orders", "upstream", 5, "dbt")
    
    # Test 2: Downstream lineage for a source table using auto-detection
    test_table_lineage("stg_tpch_customers", "downstream", 5)
    
    # Test 3: Upstream lineage with auto-detection from repo URL
    test_table_lineage("fct_order_items", "upstream", 5, repo_url=dbt_repo_url)
    
    # Test 4: Column lineage with explicit dbt dialect
    print("\nTesting column lineage tracing...\n")
    test_column_lineage("fct_order_items", "order_key", "upstream", 5, "dbt") 