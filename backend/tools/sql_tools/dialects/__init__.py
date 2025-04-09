"""
SQL Dialect Parsers

This module provides dialect-specific SQL parsers for various SQL dialects.
"""

import importlib
import logging
from typing import Dict, Optional, Any

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Dictionary of available dialect parsers
DIALECT_MODULES = {
    "dbt": "tools.sql_tools.dialects.dbt",
    "postgres": "tools.sql_tools.dialects.postgres",
    "postgresql": "tools.sql_tools.dialects.postgres",  # Alias for consistency
    "snowflake": "tools.sql_tools.dialects.snowflake",
    "mysql": "tools.sql_tools.dialects.mysql",
    "tsql": "tools.sql_tools.dialects.tsql"
}

def get_dialect_parser(dialect_name: str) -> Optional[Any]:
    """
    Get a dialect parser based on the dialect name
    
    Args:
        dialect_name: Name of SQL dialect (postgres, mysql, etc.)
        
    Returns:
        Dialect parser or None if not found
    """
    if not dialect_name:
        logger.warning("No dialect specified for parser")
        return None
    
    # Normalize the dialect name
    dialect_name = dialect_name.lower()
    
    # Check if we have a module for this dialect
    if dialect_name not in DIALECT_MODULES:
        logger.error(f"Dialect {dialect_name} not supported")
        return None
    
    try:
        # Import the module
        module_path = DIALECT_MODULES[dialect_name]
        module = importlib.import_module(module_path)
        
        # Create an instance of the dialect parser
        if dialect_name in ["postgres", "postgresql"]:
            return module.PostgreSQLDialect()
        elif dialect_name == "dbt":
            return module.DBTDialect()
        elif dialect_name == "snowflake":
            return module.SnowflakeDialect()
        elif dialect_name == "mysql":
            return module.MySQLDialect()
        elif dialect_name == "tsql":
            return module.TSQLDialect()
        else:
            logger.error(f"No parser class found for dialect {dialect_name}")
            return None
    except ImportError as e:
        logger.error(f"Error importing dialect module {dialect_name}: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Error creating dialect parser for {dialect_name}: {str(e)}")
        return None

def get_available_dialects() -> Dict[str, str]:
    """
    Get a list of available dialect parsers
    
    Returns:
        Dictionary of {dialect_name: description}
    """
    dialects = {
        "postgres": "PostgreSQL dialect",
        "dbt": "DBT SQL templates",
        "snowflake": "Snowflake SQL dialect",
        "mysql": "MySQL dialect",
        "tsql": "T-SQL (SQL Server) dialect"
    }
    
    return dialects 