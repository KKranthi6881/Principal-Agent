"""
T-SQL Dialect Handler

This module provides T-SQL specific SQL parsing and analysis.
"""

import sqlglot
from sqlglot import exp
from typing import Tuple, Any, List, Dict
from ..base_dialect import SQLDialectHandler

class TSQLDialect(SQLDialectHandler):
    """T-SQL dialect handler implementation"""
    
    def __init__(self):
        super().__init__()
        self.dialect = "tsql"
    
    def parse_sql(self, sql_code: str) -> Tuple[Any, List[str]]:
        """
        Parse T-SQL code using SQLGlot
        
        Args:
            sql_code: SQL code to parse
            
        Returns:
            Tuple of (AST, list of errors)
        """
        errors = []
        ast = None
        
        try:
            # Parse with T-SQL dialect
            ast = sqlglot.parse_one(sql_code, read=self.dialect)
        except Exception as e:
            errors.append(str(e))
        
        return ast, errors
    
    def get_table_name(self, table_node: exp.Table) -> str:
        """
        Get fully qualified table name from a Table node
        
        Args:
            table_node: SQLGlot Table expression
            
        Returns:
            Fully qualified table name
        """
        parts = []
        
        if table_node.db:
            parts.append(table_node.db)
        if table_node.schema:
            parts.append(table_node.schema)
            
        parts.append(table_node.name)
        
        return ".".join(parts)
    
    def extract_column_metadata(self, column_node: exp.Column) -> Dict[str, Any]:
        """
        Extract metadata for a column
        
        Args:
            column_node: SQLGlot Column expression
            
        Returns:
            Column metadata dictionary
        """
        metadata = {
            "name": column_node.name,
            "table": None,
            "is_primary_key": False,
            "is_foreign_key": False,
            "data_type": None,
            "description": None,
            "constraints": []
        }
        
        # Extract table reference if present
        if column_node.table:
            metadata["table"] = self.get_table_name(column_node.table)
            
        # Look for constraints and data type in parent nodes
        parent = column_node.parent
        while parent:
            if isinstance(parent, exp.DataType):
                metadata["data_type"] = str(parent)
            elif isinstance(parent, exp.PrimaryKey):
                metadata["is_primary_key"] = True
                metadata["constraints"].append({
                    "type": "PRIMARY KEY",
                    "name": getattr(parent, "name", None)
                })
            elif isinstance(parent, exp.ForeignKey):
                metadata["is_foreign_key"] = True
                metadata["constraints"].append({
                    "type": "FOREIGN KEY",
                    "name": getattr(parent, "name", None),
                    "references": {
                        "table": self.get_table_name(parent.args.get("table")),
                        "column": parent.args.get("column")
                    } if parent.args.get("table") else None
                })
            elif isinstance(parent, exp.Comment):
                metadata["description"] = parent.text
            parent = parent.parent
            
        return metadata

# Export the TSQLDialect class
__all__ = ['TSQLDialect']