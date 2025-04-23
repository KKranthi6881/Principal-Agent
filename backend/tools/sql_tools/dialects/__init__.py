"""
SQL Dialect Handlers

This module provides dialect-specific SQL parsing and analysis.
"""

import logging
from typing import Optional, Dict, Type
from .base_dialect import SQLDialectHandler
from .tsql import TSQLDialect
from .postgresql import PostgreSQLDialect

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Map of dialect names to handler classes
DIALECT_HANDLERS: Dict[str, Type[SQLDialectHandler]] = {
    # T-SQL handlers
    "tsql": TSQLDialect,
    "t-sql": TSQLDialect,  # Alias
    "mssql": TSQLDialect,  # Another common alias
    
    # PostgreSQL handlers
    "postgresql": PostgreSQLDialect,
    "postgres": PostgreSQLDialect,  # Alias
    "pg": PostgreSQLDialect,  # Another common alias
}

def get_dialect_parser(dialect_name: str) -> Optional[SQLDialectHandler]:
    """
    Get a dialect parser for the specified SQL dialect
    
    Args:
        dialect_name: Name of SQL dialect (tsql, mysql, postgresql, etc.)
        
    Returns:
        Dialect parser instance or None if not supported
    """
    if not dialect_name:
        logger.warning("No dialect name provided")
        return None
        
    # Normalize dialect name
    dialect_name = dialect_name.lower().strip()
    
    # Get handler class
    handler_class = DIALECT_HANDLERS.get(dialect_name)
    if not handler_class:
        logger.warning(f"Unsupported dialect: {dialect_name}")
        return None
        
    try:
        # Create and return handler instance
        return handler_class()
    except Exception as e:
        logger.error(f"Error creating dialect handler for {dialect_name}: {str(e)}")
        return None

def get_available_dialects() -> Dict[str, str]:
    """
    Get list of supported SQL dialects
    
    Returns:
        Dictionary of dialect names and descriptions
    """
    return {
        "tsql": "Microsoft T-SQL (SQL Server)",
        "postgresql": "PostgreSQL",
        "mysql": "MySQL (Coming Soon)",
        "snowflake": "Snowflake SQL (Coming Soon)"
    } 