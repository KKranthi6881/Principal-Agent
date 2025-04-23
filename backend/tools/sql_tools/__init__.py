"""
SQL Tools Package

This package provides tools for SQL parsing, analysis, and lineage extraction.
"""

from .dialects import get_dialect_parser, get_available_dialects
from .dependency_analyzer import SQLDependencyTool
from .lineage.sqlglot_lineage import SQLGlotLineageExtractor

__all__ = [
    'get_dialect_parser',
    'get_available_dialects',
    'SQLDependencyTool',
    'SQLGlotLineageExtractor'
] 