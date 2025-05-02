"""
Utility functions for GitHub connectors

This module provides shared utility functions for handling GitHub connectors
that can be imported by multiple modules without causing circular imports.
"""

import sqlite3
import os
import logging
from typing import Dict, Any
import json
from cryptography.fernet import Fernet

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Constants for database paths
METADATA_DB = os.path.join('database', 'metadata.db')

def get_db_connection():
    """
    Get a connection to the metadata database
    
    Returns:
        SQLite connection object
    """
    conn = sqlite3.connect(METADATA_DB)
    conn.row_factory = sqlite3.Row
    return conn

def decrypt_token(encrypted_token: str) -> str:
    """
    Decrypt a GitHub token using Fernet
    
    Args:
        encrypted_token: Encrypted token string
        
    Returns:
        Decrypted token
    """
    try:
        # Get the encryption key from environment variables
        api_key_salt = os.environ.get('API_KEY_SALT', 'default_salt_please_change')
        api_key_secret = os.environ.get('API_KEY_SECRET', 'default_secret_please_change')
        
        # Create Fernet key
        key = api_key_secret + api_key_salt
        key_bytes = key.encode('utf-8')[:32].ljust(32, b' ')
        fernet = Fernet(Fernet.generate_key())
        
        # Decrypt token
        return fernet.decrypt(encrypted_token.encode()).decode()
    except Exception as e:
        logger.error(f"Failed to decrypt token: {str(e)}")
        return ""

def get_github_connector(connector_id: str) -> Dict[str, Any]:
    """
    Get a GitHub connector by ID
    
    Args:
        connector_id: ID of the connector
        
    Returns:
        Dictionary with connector information
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            """SELECT * FROM github_connectors WHERE connector_id = ?""",
            (connector_id,)
        )
        connector = cursor.fetchone()
        
        if connector:
            return dict(connector)
        return None
    except Exception as e:
        logger.error(f"Error getting GitHub connector: {str(e)}")
        return None
    finally:
        conn.close()
