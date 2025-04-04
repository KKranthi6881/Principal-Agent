#!/usr/bin/env python3
"""
Test script to directly test SQL dependency analysis
"""

import os
import logging
from pprint import pprint
from tools.sql_tools.dependency_analyzer import SQLDependencyTool

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s')
logger = logging.getLogger(__name__)

def test_search():
    """Test searching for SQL files"""
    print("\n=== Testing SQL search ===")
    
    # Initialize the dependency tool
    tool = SQLDependencyTool("chromadb_github")
    tool.initialize()
    
    # Search for item_discount_amount
    print("\nSearching for 'item_discount_amount'...")
    results = tool.sql_finder.search_sql_files("item_discount_amount")
    
    if not results or (len(results) == 1 and "error" in results[0]):
        print(f"Error or no results: {results}")
        return False
        
    print(f"Found {len(results)} results")
    
    # Print file names where item_discount_amount was found
    for i, result in enumerate(results):
        print(f"{i+1}. {result['path']} ({result['dialect']})")
    
    return True

def test_table_dependencies():
    """Test tracing table dependencies"""
    print("\n=== Testing table dependencies ===")
    
    # Initialize the dependency tool
    tool = SQLDependencyTool("chromadb_github")
    tool.initialize()
    
    # Test with fct_order_items
    print("\nTracing dependencies for 'analytics.fct_order_items'...")
    dependencies = tool.trace_table_dependencies("analytics.fct_order_items", depth=5)
    
    if "error" in dependencies:
        print(f"Error: {dependencies['error']}")
        return False
        
    # Print dependency info
    print(f"Target table: {dependencies['target_table']}")
    print(f"Summary: {dependencies.get('summary', {})}")
    
    # Print upstream dependencies
    print("\nUpstream dependencies:")
    for dep in dependencies.get("upstream_dependencies", []):
        print(f"- {dep['source']} -> {dep['target']} (depth: {dep['depth']})")
        for file in dep.get("file_details", []):
            print(f"  • {file.get('path', 'unknown')}")
    
    return True

def test_column_lineage():
    """Test column lineage analysis"""
    print("\n=== Testing column lineage ===")
    
    # Initialize the dependency tool
    tool = SQLDependencyTool("chromadb_github")
    tool.initialize()
    
    # Test with item_discount_amount column
    print("\nTracing lineage for 'item_discount_amount' in 'analytics.fct_order_items'...")
    lineage = tool.get_column_lineage("analytics.fct_order_items", "item_discount_amount")
    
    if "error" in lineage:
        print(f"Error: {lineage['error']}")
        return False
        
    # Print lineage info
    print(f"Target table: {lineage['target_table']}")
    print(f"Target column: {lineage['target_column']}")
    print(f"Total dependencies: {lineage['total_dependencies']}")
    
    # Print lineage details
    if lineage.get("lineage"):
        print("\nColumn lineage:")
        for dep in lineage["lineage"]:
            print(f"- {dep['source']} -> {dep['target']}")
            print(f"  Columns: {', '.join(dep.get('columns', []))}")
    else:
        print("No lineage found")
    
    return True

if __name__ == "__main__":
    print("Testing SQL dependency analyzer...")
    
    # Run tests
    search_ok = test_search()
    deps_ok = test_table_dependencies()
    lineage_ok = test_column_lineage()
    
    # Print summary
    print("\n=== Test Summary ===")
    print(f"Search test: {'✅ PASSED' if search_ok else '❌ FAILED'}")
    print(f"Dependencies test: {'✅ PASSED' if deps_ok else '❌ FAILED'}")
    print(f"Lineage test: {'✅ PASSED' if lineage_ok else '❌ FAILED'}")
    
    if search_ok and deps_ok and lineage_ok:
        print("\nAll tests passed! The SQL dependency analyzer is working correctly.")
    else:
        print("\nSome tests failed. The SQL dependency analyzer needs fixing.") 