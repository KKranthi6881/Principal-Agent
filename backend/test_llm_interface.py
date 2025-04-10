#!/usr/bin/env python3
"""
Test script for LLM-friendly SQL analysis interface
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

# Import the LLM interface
try:
    from tools.sql.llm_interface import llm_interface
    logger.info("Successfully imported LLM interface")
except Exception as e:
    logger.error(f"Error importing LLM interface: {e}")
    sys.exit(1)

def print_json(obj):
    """Pretty print JSON object"""
    print(json.dumps(obj, indent=2))

def test_dbt_example():
    """Test with a real-world DBT example"""
    print("\n" + "=" * 80)
    print("TESTING LLM INTERFACE WITH DBT EXAMPLES")
    print("=" * 80)
    
    # Define repository URL and table for testing
    repo_url = "https://github.com/dbt-labs/dbt-cloud-snowflake-demo-template"
    table_name = "fct_order_items"
    column_name = "order_key"
    
    # Test 1: Auto-detect dialect from repo URL
    print("\n1. TESTING DIALECT DETECTION")
    print("-" * 50)
    dialect_result = llm_interface.detect_dialect(repo_url)
    print_json(dialect_result)
    
    # Test 2: Search for table
    print("\n2. TESTING TABLE SEARCH")
    print("-" * 50)
    search_result = llm_interface.search_tables(table_name, limit=3)
    print_json(search_result)
    
    # Test 3: Get table lineage
    print("\n3. TESTING TABLE LINEAGE")
    print("-" * 50)
    lineage_result = llm_interface.get_table_lineage(
        table_name=table_name,
        direction="upstream",
        max_depth=2,
        repo_url=repo_url
    )
    print_json(lineage_result)
    
    # Test 4: Get column lineage
    print("\n4. TESTING COLUMN LINEAGE")
    print("-" * 50)
    column_result = llm_interface.get_column_lineage(
        table_name=table_name,
        column_name=column_name,
        direction="upstream",
        max_depth=2,
        repo_url=repo_url
    )
    print_json(column_result)
    
    # Test 5: SQL search
    print("\n5. TESTING SQL SEARCH")
    print("-" * 50)
    sql_search = llm_interface.search_sql("order items join", limit=3)
    print_json(sql_search)
    
    return True

def compare_interface_with_direct():
    """Compare LLM interface with direct API calls"""
    print("\n" + "=" * 80)
    print("COMPARING LLM INTERFACE WITH DIRECT API CALLS")
    print("=" * 80)
    
    # Import the regular SQL API
    from tools.sql.api import sql_api
    
    table_name = "stg_tpch_orders"
    
    # Direct API call - more verbose output
    print("\nDIRECT API CALL:")
    direct_result = sql_api.trace_complete_lineage(table_name, "upstream", 2, "dbt")
    print(f"Output size (bytes): {len(json.dumps(direct_result))}")
    
    # LLM interface - simplified output
    print("\nLLM INTERFACE CALL:")
    llm_result = llm_interface.get_table_lineage(table_name, "upstream", 2, "dbt")
    print(f"Output size (bytes): {len(json.dumps(llm_result))}")
    
    # Calculate size reduction
    direct_size = len(json.dumps(direct_result))
    llm_size = len(json.dumps(llm_result))
    reduction = (1 - llm_size / direct_size) * 100 if direct_size > 0 else 0
    
    print(f"\nOutput size reduction: {reduction:.2f}%")
    
    return True

if __name__ == "__main__":
    # Test with real world examples
    test_dbt_example()
    
    # Compare interface size reduction
    compare_interface_with_direct() 