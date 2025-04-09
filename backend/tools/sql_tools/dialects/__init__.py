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
    "dbt": "backend.tools.sql_tools.dialects.dbt",
    "postgres": "backend.tools.sql_tools.dialects.postgres",
    "snowflake": "backend.tools.sql_tools.dialects.snowflake",
    "mysql": "backend.tools.sql_tools.dialects.mysql",
    "tsql": "backend.tools.sql_tools.dialects.tsql"
}

def get_dialect_parser(dialect_name: str) -> Optional[Any]:
    """
    Get a dialect parser based on the dialect name
    
    Args:
        dialect_name: Name of the dialect
        
    Returns:
        Dialect parser instance or None if not found
    """
    if dialect_name not in DIALECT_MODULES:
        logger.error(f"Dialect {dialect_name} not supported")
        return None
    
    try:
        # Dynamically import the dialect module
        module_name = DIALECT_MODULES[dialect_name]
        module = importlib.import_module(module_name)
        
        # Get the dialect parser class
        class_name = f"{dialect_name.title()}Dialect"
        if hasattr(module, class_name):
            parser_class = getattr(module, class_name)
            return parser_class()
        else:
            logger.error(f"Dialect class {class_name} not found in module {module_name}")
            return None
    except ImportError as e:
        logger.error(f"Error importing dialect module {dialect_name}: {e}")
        return None
    except Exception as e:
        logger.error(f"Error creating dialect parser for {dialect_name}: {e}")
        return None

def get_available_dialects() -> Dict[str, str]:
    """
    Get a dictionary of available dialect parsers
    
    Returns:
        Dictionary of {dialect_name: description}
    """
    available_dialects = {}
    
    for dialect_name in DIALECT_MODULES:
        try:
            parser = get_dialect_parser(dialect_name)
            if parser:
                dialect_info = parser.get_dialect_info()
                available_dialects[dialect_name] = dialect_info.get("description", f"{dialect_name} SQL dialect")
        except Exception as e:
            logger.error(f"Error getting info for dialect {dialect_name}: {e}")
    
    return available_dialects 