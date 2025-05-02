#!/usr/bin/env python3
"""
Script to check lineage database tables

This script reads the lineage database and prints tables, columns, and relationships.
"""

import os
import sqlite3
import json
from pathlib import Path

# Database path
LINEAGE_DB = os.path.join('database', 'lineage.db')

def get_db_connection():
    """Get a connection to the lineage database"""
    conn = sqlite3.connect(LINEAGE_DB)
    conn.row_factory = sqlite3.Row
    return conn

def print_tables():
    """Print all tables in lineage database"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    print("\n=== TABLES ===")
    cursor.execute("SELECT * FROM tables ORDER BY table_id")
    rows = cursor.fetchall()
    
    if not rows:
        print("No tables found in database")
    else:
        print(f"Found {len(rows)} tables")
        for row in rows:
            print(f"ID: {row['table_id']}")
            print(f"  Name: {row['table_name']}")
            print(f"  Schema: {row['schema_name']}")
            print(f"  Tech Stack: {row['tech_stack']}")
            print(f"  GitHub Path: {row['github_path']}")
            print()
    
    conn.close()

def print_columns():
    """Print all columns in lineage database"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    print("\n=== COLUMNS ===")
    cursor.execute("""
        SELECT c.*, t.table_name
        FROM columns c
        JOIN tables t ON c.table_id = t.table_id
        ORDER BY t.table_name, c.column_name
    """)
    rows = cursor.fetchall()
    
    if not rows:
        print("No columns found in database")
    else:
        print(f"Found {len(rows)} columns")
        current_table = None
        
        for row in rows:
            if current_table != row['table_name']:
                current_table = row['table_name']
                print(f"\nTable: {current_table}")
                
            print(f"  {row['column_name']} ({row['data_type']})")
            if row['is_primary_key']:
                print("    Primary Key")
            if row['is_foreign_key']:
                print("    Foreign Key")
            if row['business_description']:
                print(f"    Description: {row['business_description']}")
    
    conn.close()

def print_relationships():
    """Print all relationships in lineage database"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    print("\n=== RELATIONSHIPS ===")
    cursor.execute("""
        SELECT r.*, 
               st.table_name as source_table_name,
               tt.table_name as target_table_name,
               sc.column_name as source_column_name,
               tc.column_name as target_column_name
        FROM relationships r
        JOIN tables st ON r.source_table_id = st.table_id
        JOIN tables tt ON r.target_table_id = tt.table_id
        LEFT JOIN columns sc ON r.source_column_id = sc.column_id
        LEFT JOIN columns tc ON r.target_column_id = tc.column_id
        ORDER BY st.table_name, tt.table_name
    """)
    rows = cursor.fetchall()
    
    if not rows:
        print("No relationships found in database")
    else:
        print(f"Found {len(rows)} relationships")
        
        for row in rows:
            print(f"Relationship: {row['relationship_type']}")
            print(f"  Source: {row['source_table_name']}")
            if row['source_column_name']:
                print(f"  Source Column: {row['source_column_name']}")
            print(f"  Target: {row['target_table_name']}")
            if row['target_column_name']:
                print(f"  Target Column: {row['target_column_name']}")
            print(f"  File: {row['github_path']}")
            print()
    
    conn.close()

def print_lineage_definitions():
    """Print all lineage definitions in lineage database"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    print("\n=== LINEAGE DEFINITIONS ===")
    cursor.execute("""
        SELECT ld.*, t.table_name
        FROM lineage_definitions ld
        JOIN tables t ON ld.root_table_id = t.table_id
        ORDER BY ld.created_at DESC
    """)
    rows = cursor.fetchall()
    
    if not rows:
        print("No lineage definitions found in database")
    else:
        print(f"Found {len(rows)} lineage definitions")
        
        for row in rows:
            print(f"Lineage ID: {row['lineage_id']}")
            print(f"  Root Table: {row['table_name']}")
            print(f"  Tech Stack: {row['tech_stack']}")
            print(f"  Created: {row['created_at']}")
            
            # Parse and pretty-print JSON lineage data (summary only)
            try:
                lineage_json = json.loads(row['lineage_json'])
                tables_count = len(lineage_json.get('tables', []))
                relationships_count = len(lineage_json.get('relationships', []))
                columns_count = len(lineage_json.get('columns', []))
                print(f"  Tables: {tables_count}")
                print(f"  Relationships: {relationships_count}")
                print(f"  Columns: {columns_count}")
            except:
                print("  [Error parsing lineage JSON]")
                
            print()
    
    conn.close()

if __name__ == "__main__":
    print("Checking lineage database...")
    print(f"Database path: {Path(LINEAGE_DB).absolute()}")
    
    # Check if database exists
    if not os.path.exists(LINEAGE_DB):
        print(f"Database file not found at {LINEAGE_DB}")
        exit(1)
    
    # Print all tables
    print_tables()
    
    # Print all columns
    print_columns()
    
    # Print all relationships
    print_relationships()
    
    # Print lineage definitions
    print_lineage_definitions()
