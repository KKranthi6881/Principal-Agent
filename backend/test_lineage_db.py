#!/usr/bin/env python3
"""
Test script for lineage database functionality
This script creates test tables, columns, and relationships to verify that
column-level lineage is working properly
"""

import os
import sys
import json
from database.lineage_db import LineageDB
from database.db_setup import LINEAGE_DB, setup_lineage_db
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_test_data():
    """Create test data for lineage visualization"""
    # Ensure database exists
    setup_lineage_db()
    
    # Create LineageDB instance
    lineage_db = LineageDB()
    
    # Create tables
    source_table_id = lineage_db.add_table(
        table_name="source_table",
        tech_stack="tsql",
        github_path="models/source_table.sql",
        schema_name="public",
        business_description="A source table for testing"
    )
    
    intermediate_table_id = lineage_db.add_table(
        table_name="intermediate_table",
        tech_stack="tsql",
        github_path="models/intermediate_table.sql",
        schema_name="public",
        business_description="An intermediate table for testing"
    )
    
    target_table_id = lineage_db.add_table(
        table_name="target_table",
        tech_stack="tsql",
        github_path="models/target_table.sql",
        schema_name="public",
        business_description="A target table for testing"
    )
    
    # Create columns for source table
    source_id_column_id = lineage_db.add_column(
        table_id=source_table_id,
        column_name="id",
        data_type="integer",
        is_primary_key=True,
        business_description="Primary key for source table"
    )
    
    source_name_column_id = lineage_db.add_column(
        table_id=source_table_id,
        column_name="name",
        data_type="varchar",
        business_description="Name column in source table"
    )
    
    source_value_column_id = lineage_db.add_column(
        table_id=source_table_id,
        column_name="value",
        data_type="decimal",
        business_description="Value column in source table"
    )
    
    # Create columns for intermediate table
    intermediate_id_column_id = lineage_db.add_column(
        table_id=intermediate_table_id,
        column_name="id",
        data_type="integer",
        is_primary_key=True,
        business_description="Primary key for intermediate table"
    )
    
    intermediate_name_column_id = lineage_db.add_column(
        table_id=intermediate_table_id,
        column_name="name",
        data_type="varchar",
        business_description="Name column in intermediate table"
    )
    
    intermediate_modified_value_column_id = lineage_db.add_column(
        table_id=intermediate_table_id,
        column_name="modified_value",
        data_type="decimal",
        business_description="Modified value column in intermediate table"
    )
    
    # Create columns for target table
    target_id_column_id = lineage_db.add_column(
        table_id=target_table_id,
        column_name="id",
        data_type="integer",
        is_primary_key=True,
        business_description="Primary key for target table"
    )
    
    target_full_name_column_id = lineage_db.add_column(
        table_id=target_table_id,
        column_name="full_name",
        data_type="varchar",
        business_description="Full name column in target table"
    )
    
    target_calculated_value_column_id = lineage_db.add_column(
        table_id=target_table_id,
        column_name="calculated_value",
        data_type="decimal",
        business_description="Calculated value column in target table"
    )
    
    # Create relationships between tables
    # Source -> Intermediate
    source_to_intermediate_rel = lineage_db.add_relationship(
        source_table_id=source_table_id,
        target_table_id=intermediate_table_id,
        relationship_type="depends_on",
        github_path="models/intermediate_table.sql"
    )
    
    # Intermediate -> Target
    intermediate_to_target_rel = lineage_db.add_relationship(
        source_table_id=intermediate_table_id,
        target_table_id=target_table_id,
        relationship_type="depends_on",
        github_path="models/target_table.sql"
    )
    
    # Column relationships for Source -> Intermediate
    id_rel = lineage_db.add_relationship(
        source_table_id=source_table_id,
        target_table_id=intermediate_table_id,
        relationship_type="direct",
        source_column_id=source_id_column_id,
        target_column_id=intermediate_id_column_id,
        github_path="models/intermediate_table.sql"
    )
    
    name_rel = lineage_db.add_relationship(
        source_table_id=source_table_id,
        target_table_id=intermediate_table_id,
        relationship_type="direct",
        source_column_id=source_name_column_id,
        target_column_id=intermediate_name_column_id,
        github_path="models/intermediate_table.sql"
    )
    
    value_rel = lineage_db.add_relationship(
        source_table_id=source_table_id,
        target_table_id=intermediate_table_id,
        relationship_type="transformed",
        source_column_id=source_value_column_id,
        target_column_id=intermediate_modified_value_column_id,
        github_path="models/intermediate_table.sql"
    )
    
    # Column relationships for Intermediate -> Target
    id_rel_2 = lineage_db.add_relationship(
        source_table_id=intermediate_table_id,
        target_table_id=target_table_id,
        relationship_type="direct",
        source_column_id=intermediate_id_column_id,
        target_column_id=target_id_column_id,
        github_path="models/target_table.sql"
    )
    
    name_rel_2 = lineage_db.add_relationship(
        source_table_id=intermediate_table_id,
        target_table_id=target_table_id,
        relationship_type="transformed",
        source_column_id=intermediate_name_column_id,
        target_column_id=target_full_name_column_id,
        github_path="models/target_table.sql"
    )
    
    value_rel_2 = lineage_db.add_relationship(
        source_table_id=intermediate_table_id,
        target_table_id=target_table_id,
        relationship_type="aggregated",
        source_column_id=intermediate_modified_value_column_id,
        target_column_id=target_calculated_value_column_id,
        github_path="models/target_table.sql"
    )
    
    # Generate comprehensive lineage for each table
    source_lineage = lineage_db.generate_comprehensive_lineage(source_table_id, "tsql")
    intermediate_lineage = lineage_db.generate_comprehensive_lineage(intermediate_table_id, "tsql")
    target_lineage = lineage_db.generate_comprehensive_lineage(target_table_id, "tsql")
    
    # Print lineage information
    print("Test data creation complete")
    print(f"Created 3 tables with relationships")
    print(f"Source table ID: {source_table_id}")
    print(f"Intermediate table ID: {intermediate_table_id}")
    print(f"Target table ID: {target_table_id}")
    
    # Save lineage to a JSON file for inspection
    with open("test_lineage.json", "w") as f:
        json.dump(target_lineage, f, indent=2)
    
    print("Saved target table lineage to test_lineage.json")
    
    return target_table_id

if __name__ == "__main__":
    target_id = create_test_data()
    print(f"\nTo view the lineage in the browser, navigate to:")
    print(f"http://localhost:3000/lineage/{target_id}")
