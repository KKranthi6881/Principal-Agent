"""
SQL Dialect Handlers

This module provides dialect-specific SQL parsing and analysis.
"""

import logging
import importlib.util
from typing import Optional, Dict, Type, Any, Set
from .base_dialect import SQLDialectHandler

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Directly import the dialect classes to ensure they're available
try:
    from .postgresql import PostgreSQLDialect
    logger.info("Successfully imported PostgreSQL dialect")
except ImportError as e:
    logger.warning(f"Unable to import PostgreSQL dialect: {str(e)}")
    PostgreSQLDialect = None

try:
    from .tsql import TSQLDialect
    logger.info("Successfully imported T-SQL dialect")
except ImportError as e:
    logger.warning(f"Unable to import T-SQL dialect: {str(e)}")
    TSQLDialect = None

try:
    from .dbt import DBTDialect
    logger.info("Successfully imported DBT dialect")
except ImportError as e:
    logger.warning(f"Unable to import DBT dialect: {str(e)}")
    DBTDialect = None

# Map of dialect names to handler classes with better fallbacks
DIALECT_HANDLERS: Dict[str, Type[SQLDialectHandler]] = {}

# Add PostgreSQL dialects if available
if PostgreSQLDialect:
    DIALECT_HANDLERS.update({
        "postgresql": PostgreSQLDialect,
        "postgres": PostgreSQLDialect,
        "pg": PostgreSQLDialect,
    })

# Add T-SQL dialects if available
if TSQLDialect:
    DIALECT_HANDLERS.update({
        "tsql": TSQLDialect,
        "t-sql": TSQLDialect,
        "mssql": TSQLDialect,
    })

# Add DBT dialect if available
if DBTDialect:
    DIALECT_HANDLERS.update({
        "dbt": DBTDialect,
    })

def get_dialect_parser(tech_stack: str) -> Optional[SQLDialectHandler]:
    """
    Get a dialect parser for a specific tech stack
    
    Args:
        tech_stack: Name of SQL tech stack (tsql, mysql, postgresql, dbt, etc.)
        
    Returns:
        Dialect parser instance or None if not supported
    """
    if not tech_stack:
        logger.warning("No tech stack specified")
        return None
        
    # Normalize tech stack name
    tech_stack = tech_stack.lower().strip()
    
    # Handle special case for DBT -> use DBT dialect directly
    if tech_stack == "dbt":
        if DBTDialect:
            logger.info("Using DBT dialect for parsing")
            try:
                return DBTDialect()
            except Exception as e:
                logger.error(f"Error creating DBT dialect handler: {str(e)}")
                # Fall back to PostgreSQL for DBT if available
                if PostgreSQLDialect:
                    logger.info("Falling back to PostgreSQL dialect for DBT")
                    try:
                        return PostgreSQLDialect()
                    except Exception as e:
                        logger.error(f"Error creating fallback PostgreSQL dialect handler: {str(e)}")
                return None
        elif PostgreSQLDialect:
            # If DBT dialect is not available, use PostgreSQL as fallback
            logger.info("DBT dialect not available, using PostgreSQL as fallback")
            try:
                return PostgreSQLDialect()
            except Exception as e:
                logger.error(f"Error creating PostgreSQL dialect handler: {str(e)}")
                return None
        else:
            logger.warning("Neither DBT nor PostgreSQL dialects are available")
            return None
            
    # Get handler class for other dialects
    handler_class = DIALECT_HANDLERS.get(tech_stack)
    if not handler_class:
        logger.warning(f"Unsupported tech stack: {tech_stack}, available dialects: {list(DIALECT_HANDLERS.keys())}")
        return None
        
    try:
        # Create and return handler instance
        return handler_class()
    except Exception as e:
        logger.error(f"Error creating dialect handler for {tech_stack}: {str(e)}")
        return None

def get_available_dialects() -> Dict[str, str]:
    """
    Get list of supported SQL dialects
    
    Returns:
        Dictionary of dialect names and descriptions
    """
    available = {}
    
    # Only add dialects that are actually available
    if PostgreSQLDialect:
        available["postgresql"] = "PostgreSQL"
        
    if TSQLDialect:
        available["tsql"] = "Microsoft T-SQL (SQL Server)"
        
    if DBTDialect:
        available["dbt"] = "DBT SQL (Data Build Tool)"
        
    # Add planned dialects
    available.update({
        "mysql": "MySQL (Coming Soon)",
        "snowflake": "Snowflake SQL (Coming Soon)"
    })
    
    return available 