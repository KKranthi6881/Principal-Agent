"""
SQL Lineage Package

This package provides tools for extracting lineage information from SQL code.
"""

from .sqlglot_lineage import SQLGlotLineageExtractor
from .base_lineage import BaseLineageExtractor

__all__ = [
    'SQLGlotLineageExtractor',
    'BaseLineageExtractor'
] 