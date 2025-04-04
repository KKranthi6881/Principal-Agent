"""
SQL Dependency Analyzer Tool

This module coordinates the SQL dependency analysis process,
combining GitHub file search with SQL parsing to build 
comprehensive dependency graphs.
"""

import logging
import json
from typing import Dict, List, Any, Optional
import os
import networkx as nx
from pathlib import Path

from .sql_dependency_analyzer import SQLDependencyAnalyzer
from .github_sql_finder import GitHubSQLFinder

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class SQLDependencyTool:
    """
    Main tool for analyzing SQL dependencies from GitHub repositories
    """
    
    def __init__(self, vector_store_path: str = None):
        """
        Initialize the SQL Dependency Tool
        
        Args:
            vector_store_path: Path to the ChromaDB vector store
        """
        # If path is None, use default
        if vector_store_path is None:
            vector_store_path = os.path.join(os.getcwd(), "vector_store", "chromadb_github")
            
        logger.info(f"SQLDependencyTool initializing with vector_store_path: {vector_store_path}")
        
        # Initialize SQL finder with direct ChromaDB access
        self.sql_finder = GitHubSQLFinder(vector_store_path)
        
        # Initialize dependency analyzer with default dialect
        self.dependency_analyzer = SQLDependencyAnalyzer(dialect="dbt")
        
        # Initialize the dependency graph
        self.dependency_graph = nx.DiGraph()
        
        # Cache for file content to avoid repeated processing
        self.file_cache = {}
        
    def initialize(self):
        """Initialize components and connections"""
        # Just call the GitHubSQLFinder initialize method
        success = self.sql_finder.initialize()
        if success:
            logger.info("SQL dependency tool initialized successfully")
        else:
            logger.error("Failed to initialize SQL dependency tool")
        return success
    
    def trace_table_dependencies(self, target_table: str, depth: int = 10, dialect: str = None) -> Dict[str, Any]:
        """
        Trace upstream dependencies for a target table
        
        Args:
            target_table: Target table name (e.g., 'schema.table_name' or just 'table_name')
            depth: Maximum depth to traverse
            dialect: SQL dialect to use for parsing
            
        Returns:
            Dict with dependency information
        """
        # Update dialect if specified
        if dialect:
            self.dependency_analyzer = SQLDependencyAnalyzer(dialect=dialect)
        
        # Step 1: Find all SQL files that reference this table
        sql_files = self.sql_finder.search_for_table(table_name=target_table)
        
        if not sql_files or (isinstance(sql_files, list) and len(sql_files) == 1 and "error" in sql_files[0]):
            return {
                "error": f"No SQL files found for table {target_table}",
                "target_table": target_table,
                "dependencies": []
            }
        
        # Step 2: Build a dependency graph from these files
        self.dependency_graph = self.dependency_analyzer.build_dependency_graph(sql_files)
        
        # Step 3: Find upstream dependencies
        upstream_info = self.dependency_analyzer.find_upstream_dependencies(
            target_table=target_table,
            max_depth=depth
        )
        
        # Step 4: Enrich the dependency information with file details
        enriched_dependencies = []
        for dep in upstream_info.get("upstream_dependencies", []):
            source_table = dep["source"]
            files = dep.get("files", [])
            
            # Enrich with file details from our vector store
            file_details = []
            for file_path in files:
                # Use cached file info if available
                if file_path in self.file_cache:
                    file_details.append(self.file_cache[file_path])
                else:
                    # Otherwise, search for it again
                    matched_files = [f for f in sql_files if f.get("path") == file_path]
                    if matched_files:
                        file_info = matched_files[0]
                        # Add to cache
                        self.file_cache[file_path] = {
                            "path": file_path,
                            "url": file_info.get("url", ""),
                            "github_repo": file_info.get("github_repo", ""),
                            "file_name": file_info.get("file_name", ""),
                            "dialect": file_info.get("dialect", "")
                        }
                        file_details.append(self.file_cache[file_path])
            
            # Add enriched file details
            dep["file_details"] = file_details
            enriched_dependencies.append(dep)
        
        # Update the upstream info with enriched dependencies
        upstream_info["upstream_dependencies"] = enriched_dependencies
        
        # Step 5: Generate a summary
        summary = {
            "target_table": target_table,
            "total_dependencies": len(enriched_dependencies),
            "unique_source_tables": len(set(dep["source"] for dep in enriched_dependencies)),
            "max_depth": max([dep["depth"] for dep in enriched_dependencies]) if enriched_dependencies else 0,
            "file_count": len(upstream_info.get("all_files", [])),
            "dialect": self.dependency_analyzer.dialect
        }
        
        upstream_info["summary"] = summary
        
        return upstream_info
    
    def get_column_lineage(self, target_table: str, column_name: str, depth: int = 10) -> Dict[str, Any]:
        """
        Get column-level lineage for a specific column
        
        Args:
            target_table: Target table name
            column_name: Target column name
            depth: Maximum depth to traverse
            
        Returns:
            Dict with column lineage information
        """
        # Find all SQL files that reference this column in this table
        sql_files = self.sql_finder.search_for_column(
            table_name=target_table,
            column_name=column_name
        )
        
        if not sql_files or "error" in sql_files[0]:
            return {
                "error": f"No SQL files found for column {column_name} in table {target_table}",
                "target_table": target_table,
                "target_column": column_name,
                "lineage": []
            }
        
        # Build a dependency graph from these files
        self.dependency_graph = self.dependency_analyzer.build_dependency_graph(sql_files)
        
        # Find upstream dependencies
        upstream_info = self.dependency_analyzer.find_upstream_dependencies(
            target_table=target_table,
            max_depth=depth
        )
        
        # Filter to only include dependencies that involve this column
        column_lineage = []
        for dep in upstream_info.get("upstream_dependencies", []):
            columns = dep.get("columns", [])
            if column_name in columns:
                column_lineage.append(dep)
        
        return {
            "target_table": target_table,
            "target_column": column_name,
            "lineage": column_lineage,
            "total_dependencies": len(column_lineage),
            "file_count": len(set(file for dep in column_lineage for file in dep.get("files", [])))
        }
    
    def visualize_dependencies(self, target_table: str, output_format: str = "json") -> Dict[str, Any]:
        """
        Visualize dependencies for a table
        
        Args:
            target_table: Target table name
            output_format: Output format (json, graphviz, etc.)
            
        Returns:
            Dict with visualization data
        """
        # Ensure we have dependencies to visualize
        if not self.dependency_graph:
            upstream_info = self.trace_table_dependencies(target_table)
            if "error" in upstream_info:
                return upstream_info
        
        # Extract subgraph for this target
        try:
            # Get all reachable nodes from the target (upstream)
            upstream_nodes = nx.ancestors(self.dependency_graph, target_table)
            upstream_nodes.add(target_table)
            
            # Create a subgraph with these nodes
            subgraph = self.dependency_graph.subgraph(upstream_nodes)
            
            # Convert to desired output format
            if output_format == "json":
                # Convert NetworkX graph to JSON-serializable format
                nodes = []
                for node in subgraph.nodes():
                    node_data = subgraph.nodes[node].copy()
                    node_data["id"] = node
                    node_data["label"] = node.split(".")[-1] if "." in node else node
                    nodes.append(node_data)
                
                edges = []
                for source, target, data in subgraph.edges(data=True):
                    edge_data = data.copy()
                    edge_data["source"] = source
                    edge_data["target"] = target
                    edge_data["label"] = f"{source} → {target}"
                    edges.append(edge_data)
                
                return {
                    "target_table": target_table,
                    "nodes": nodes,
                    "edges": edges,
                    "format": "json"
                }
            
            # Could add support for other formats (graphviz, mermaid, etc.)
            
            return {
                "error": f"Unsupported output format: {output_format}",
                "supported_formats": ["json"]
            }
            
        except Exception as e:
            logger.error(f"Error visualizing dependencies: {str(e)}")
            return {
                "error": f"Error visualizing dependencies: {str(e)}",
                "target_table": target_table
            }
    
    def save_dependency_graph(self, file_path: str) -> Dict[str, Any]:
        """
        Save the current dependency graph to a file
        
        Args:
            file_path: Path to save the graph
            
        Returns:
            Dict with result information
        """
        if not self.dependency_graph:
            return {"error": "No dependency graph available to save"}
        
        try:
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            # Save the graph
            if file_path.endswith(".json"):
                # Convert to JSON-serializable format
                graph_data = nx.node_link_data(self.dependency_graph)
                with open(file_path, 'w') as f:
                    json.dump(graph_data, f, indent=2)
            else:
                # Default to GraphML format
                nx.write_graphml(self.dependency_graph, file_path)
            
            return {
                "success": True,
                "file_path": file_path,
                "message": f"Dependency graph saved to {file_path}"
            }
            
        except Exception as e:
            logger.error(f"Error saving dependency graph: {str(e)}")
            return {
                "error": f"Error saving dependency graph: {str(e)}",
                "file_path": file_path
            } 