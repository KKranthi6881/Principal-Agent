"""
DBT SQL Dialect Parser

This module provides DBT-specific SQL parsing and analysis.
"""

import os
import re
import json
import logging
import yaml
from typing import Dict, List, Set, Tuple, Optional, Any
import sqlglot
from sqlglot import parse_one, ParseError
from sqlglot.expressions import Select, Table, Column, Subquery, Create, Insert

# Import base classes
from ..base_dialect import BaseSQLDialect

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class DBTDialect(BaseSQLDialect):
    """
    DBT-specific SQL dialect parser.
    Handles DBT-specific syntax including macros and ref/source functions.
    """
    
    def __init__(self):
        """Initialize the DBT dialect parser"""
        super().__init__(name="dbt")
        self.dbt_supported_file_types = [".sql", ".yml", ".yaml"]
    
    def _get_sqlglot_dialect(self, dialect_hint=None):
        """
        Get the SQLGlot dialect name for DBT (uses postgres as base)
        
        Args:
            dialect_hint: An optional hint about what the dialect might be.
        
        Returns:
            The SQLGlot dialect name
        """
        if dialect_hint:
            return dialect_hint
        return "postgres"  # DBT is typically based on the target warehouse dialect, default to Postgres
    
    def _is_macro_only_file(self, sql):
        """
        Check if the SQL file only contains macro definitions and no executable SQL
        
        Args:
            sql: SQL code
            
        Returns:
            True if this is a macro-only file, False otherwise
        """
        # Look for patterns of macro definitions without SQL statements
        macro_pattern = r'{%\s*macro\s+[^%]+%}'
        sql_pattern = r'(?:SELECT|INSERT|UPDATE|DELETE|CREATE|ALTER|DROP|WITH|MERGE)\s+'
        
        # Find all macro definitions
        macro_matches = re.findall(macro_pattern, sql, re.IGNORECASE | re.DOTALL)
        
        # Find any actual SQL statements outside of macro definitions
        sql_matches = re.search(sql_pattern, re.sub(macro_pattern, '', sql), re.IGNORECASE)
        
        # If there are macro definitions and no SQL statements outside of them,
        # then this is a macro-only file
        return len(macro_matches) > 0 and not sql_matches
    
    def parse_sql(self, sql, file_path=None, dialect_hint=None):
        """
        Parse DBT SQL code using SQLGlot. Attempts reconstruction and multiple fallbacks.

        Args:
            sql: A string with DBT SQL code.
            file_path: An optional string with the path to the file.
            dialect_hint: An optional hint about what the dialect might be.

        Returns:
            A tuple of (ast, errors) where ast is the abstract syntax tree and
            errors is a list of error messages.
        """
        parsing_errors = [] # Store errors encountered during this function

        # --- Initial Checks ---
        if file_path and (file_path.endswith(".yml") or file_path.endswith(".yaml")):
            return None, ["Cannot parse YAML files as SQL"]
        if self._is_macro_only_file(sql):
            deps = self.extract_dependencies(sql, file_path, extract_only=True)
            return None, [f"Macro-only file, skipping SQL parsing. Found refs: {len(deps.get('refs',[]))}, sources: {len(deps.get('sources',[]))} via regex."]
        if not self._looks_like_sql(sql):
            return None, ["Input doesn't appear to be SQL code"]

        # --- Preprocessing --- 
        try:
            processed_sql, preprocessing_errors = self._preprocess_sql(sql)
            parsing_errors.extend(preprocessing_errors)
            if not processed_sql:
                parsing_errors.append("Preprocessing returned empty SQL.")
                return None, parsing_errors
        except Exception as preproc_e:
            parsing_errors.append(f"Critical error during preprocessing: {str(preproc_e)}")
            logger.error(f"Preprocessing failed critically: {preproc_e}", exc_info=True)
            return None, parsing_errors

        # --- Reconstruction Attempt ---
        sql_to_parse = None
        try:
            reconstructed_sql, reconstruction_errors = self._reconstruct_dbt_sql(processed_sql)
            parsing_errors.extend(reconstruction_errors)
            if reconstructed_sql:
                sql_to_parse = reconstructed_sql
                parsing_errors.append("Attempting parse on reconstructed SQL from DBT CTEs")
            else:
                parsing_errors.append("CTE reconstruction did not yield SQL, falling back.")
                sql_to_parse = processed_sql # Fallback to preprocessed if reconstruction fails
        except Exception as recon_e:
            parsing_errors.append(f"Critical error during CTE reconstruction: {str(recon_e)}")
            logger.error(f"CTE Reconstruction failed critically: {recon_e}", exc_info=True)
            sql_to_parse = processed_sql # Fallback to preprocessed
        
        if not sql_to_parse:
             parsing_errors.append("No SQL available to parse after preprocessing/reconstruction.")
             return None, parsing_errors

        # --- Parsing with Dialect Fallback --- 
        dialect = self._get_sqlglot_dialect(dialect_hint)
        fallback_dialects = ["postgres", "snowflake", "bigquery", "mysql", "duckdb", "spark", "tsql"]
        if dialect in fallback_dialects:
            fallback_dialects.remove(dialect)
        dialects_to_try = [dialect] + fallback_dialects

        ast = None
        last_parse_error = None
        successful_dialect = None
        
        logger.info(f"Attempting to parse SQL for file {file_path} (length {len(sql_to_parse)}):\n---\n{sql_to_parse[:1000]}...\n---")

        for try_dialect in dialects_to_try:
            try:
                parsed_expressions = sqlglot.parse(sql_to_parse, read=try_dialect)
                if parsed_expressions:
                    significant_expr = next((expr for expr in parsed_expressions 
                                             if isinstance(expr, (Select, Create, Insert, sqlglot.exp.CTE))), 
                                            parsed_expressions[0])
                    ast = significant_expr
                    successful_dialect = try_dialect
                    if try_dialect != dialect:
                        parsing_errors.append(f"Parse successful with fallback dialect: {try_dialect}")
                    else: 
                         parsing_errors.append(f"Parse successful with initial dialect: {try_dialect}")
                    break # Success!
                else:
                    last_parse_error = f"Parsing with {try_dialect} returned no expressions."
            except Exception as e:
                last_parse_error = e
                logger.debug(f"Parsing attempt failed with dialect {try_dialect}. Error: {str(e)}. SQL attempted:\n---\n{sql_to_parse[:500]}...\n---")
            
        # --- Handling Persistent Parsing Failures --- 
        if ast is None:
            final_error_msg = f"Failed to parse SQL with all attempted dialects. Last error ({dialects_to_try[-1]}): {str(last_parse_error)}"
            parsing_errors.append(final_error_msg)
            logger.warning(f"Failed parsing SQL file: {file_path or '[No Path Provided]'}. {final_error_msg}. Final SQL attempted (showing start):\n---\n{sql_to_parse[:1000]}...\n---")

            # --- Fragment Parsing Fallback ---
            parsing_errors.append("Attempting fallback: Parsing largest SQL fragment.")
            try:
                # Stricter fragment regex: Look for SELECT...; or WITH...; or CREATE...;
                # Ensuring it captures until a semicolon or end of string/block.
                fragment_patterns = [
                    r'(?i)(\bSELECT\b.*?)(?:;|\Z)', # Select statement
                    r'(?i)(\bWITH\b.*?)(?:;|\Z)',   # With statement
                    r'(?i)(\bCREATE\b.*?)(?:;|\Z)' # Create statement
                ]
                potential_statements = []
                for pattern in fragment_patterns:
                    matches = re.findall(pattern, sql_to_parse, re.DOTALL)
                    potential_statements.extend([m.strip() for m in matches if m])

                if potential_statements:
                    longest_fragment = max(potential_statements, key=len)
                    if len(longest_fragment) > 20:
                        # +++ Clean fragment before parsing +++
                        cleaned_fragment = re.sub(r'\x1b\[[0-9;]*m', '', longest_fragment) # Remove ANSI
                        cleaned_fragment = cleaned_fragment.strip().rstrip(';') # Strip and remove trailing semicolon for sqlglot
                        
                        logger.info(f"Attempting lenient parse on longest cleaned fragment ({len(cleaned_fragment)} chars) for {file_path}:\n---\n{cleaned_fragment[:500]}...\n---")
                        parsed_expressions = sqlglot.parse(cleaned_fragment, read="postgres")
                        if parsed_expressions:
                            ast = parsed_expressions[0]
                            parsing_errors.append(f"Lenient parse successful using longest cleaned fragment ({len(cleaned_fragment)} chars) with postgres dialect.")
                            logger.info(f"Lenient fragment parsing succeeded for {file_path}")
                        else: 
                             parsing_errors.append("Lenient fragment parsing returned no expressions.")
                    else:
                         parsing_errors.append("Longest fragment found was too short ({len(longest_fragment)}) for lenient parsing.")
                else:
                     parsing_errors.append("No suitable SQL fragments found for lenient parsing.")
            except Exception as lenient_e:
                 error_msg = f"Lenient fragment parsing attempt failed: {str(lenient_e)}"
                 parsing_errors.append(error_msg)
                 logger.warning(f"Lenient fragment parsing failed for {file_path}: {error_msg}", exc_info=True)

        # --- Return Result --- 
        if ast:
            final_errors = [e for e in parsing_errors if "Warning:" in e or "successful" in e or "failed" in e or "error" in e.lower()]
            return ast, final_errors
        else:
            return None, parsing_errors
    
    def _reconstruct_dbt_sql(self, sql):
        """
        Reconstruct DBT SQL from CTEs and other DBT-specific patterns
        
        Args:
            sql: SQL code
            
        Returns:
            A tuple of (reconstructed_sql, errors) where reconstructed_sql is the
            reconstructed SQL code and errors is a list of error messages.
        """
        errors = []
        
        # If the SQL is already a valid SELECT statement, no need to reconstruct
        if re.search(r'^\s*(?:WITH|SELECT)', sql, re.IGNORECASE):
            return sql, errors
            
        # Try to find a main query pattern
        main_query_match = re.search(r'((?:WITH|SELECT).*$)', sql, re.IGNORECASE | re.DOTALL)
        if main_query_match:
            return main_query_match.group(1), errors
            
        # If we couldn't find a main query, return None
        errors.append("Could not reconstruct SQL from DBT file. No main query found.")
        return None, errors
        
    def _preprocess_sql(self, sql):
        """
        Preprocess DBT-specific syntax like Jinja templates
        
        Args:
            sql: A string with DBT SQL code.
            
        Returns:
            A tuple of (processed_sql, errors) where processed_sql is the processed SQL
            code and errors is a list of error messages.
        """
        errors = []
        processed_sql = sql

        # Handle empty or None input
        if not processed_sql or processed_sql.strip() == "":
            return None, ["Input SQL is empty"]

        try:
            # --- Phase 1: Basic Cleaning & Jinja Comment Removal ---
            # Remove ANSI escape sequences first
            processed_sql = re.sub(r'\x1b\[[0-9;]*m', '', processed_sql)
            
            # Handle SQL comments (--)
            processed_sql = re.sub(r"--.*?$", "", processed_sql, flags=re.MULTILINE)

            # Handle Jinja comments {# ... #} before other Jinja processing
            processed_sql = re.sub(r"{#.*?#}", "", processed_sql, flags=re.DOTALL)

            # --- Phase 2: Jinja Macro/Statement Placeholder Replacement ---
            # Replace Jinja macros and control structures with placeholders
            # Handle macro definitions completely
            processed_sql = re.sub(
                r"({%\s*macro\s+[^%]*%})(.*?)({%\s*endmacro\s*%})",
                " /* DBT_MACRO_DEFINITION */ \n", # Add newline for safety
                processed_sql,
                flags=re.DOTALL | re.IGNORECASE,
            )
            # Handle materialization blocks
            processed_sql = re.sub(
                r"({%\s*materialization\s+[^%]*%})(.*?)({%\s*endmaterialization\s*%})",
                " /* DBT_MATERIALIZATION */ \n",
                processed_sql,
                flags=re.DOTALL | re.IGNORECASE,
            )
            # Handle for loops
            processed_sql = re.sub(r"({%\s*for\s+.*?%})(.*?)({%\s*endfor\s*%})", " /* DBT_FOR_LOOP */ \n", processed_sql, flags=re.DOTALL | re.IGNORECASE)
            # Handle if/else/endif structures (more complex nesting)
            processed_sql = re.sub(r"{%\s*(el)?if\s+.*?%}", " /* DBT_IF_BLOCK */ \n", processed_sql, flags=re.IGNORECASE)
            processed_sql = re.sub(r"{%\s*else\s*%}", " /* DBT_ELSE_BLOCK */ \n", processed_sql, flags=re.IGNORECASE)
            processed_sql = re.sub(r"{%\s*endif\s*%}", " /* DBT_ENDIF_BLOCK */ \n", processed_sql, flags=re.IGNORECASE)
            # Handle set statements
            processed_sql = re.sub(r"{%\s*set\s+.*?%}", " /* DBT_SET_STATEMENT */ \n", processed_sql, flags=re.IGNORECASE)
            # Replace remaining Jinja statements
            processed_sql = re.sub(r"{%.*?%}", " /* DBT_STATEMENT */ \n", processed_sql)

            # --- Phase 3: Jinja Expression Replacement ({{ ... }}) ---
            # Handle config blocks
            processed_sql = re.sub(r"{{\s*config\s*\([^}]*\)\s*}}", " /* DBT_CONFIG */ ", processed_sql, flags=re.IGNORECASE)
            # Replace DBT utility function calls
            processed_sql = re.sub(r"{{\s*dbt_utils\.[^}]+?}}", " /* DBT_UTILS_FUNC */ ", processed_sql, flags=re.IGNORECASE)
            # Replace ref macros (handle quotes and potential package names)
            processed_sql = re.sub(r"{{\s*ref\s*\(\s*(['\"])(.+?)\1\s*(,\s*['\"](.+?)['\"])?\s*\)\s*}}", 
                                 lambda m: f"__dbt_ref_{m.group(4)}_{m.group(2)}" if m.group(4) else f"__dbt_ref_{m.group(2)}", 
                                 processed_sql, flags=re.IGNORECASE)
            # Replace source macros
            processed_sql = re.sub(r"{{\s*source\s*\(\s*(['\"])(.+?)\1\s*,\s*(['\"])(.+?)\3\s*\)\s*}}", 
                                 r"__dbt_source_\2_\4", 
                                 processed_sql, flags=re.IGNORECASE)
            # Replace var macros
            processed_sql = re.sub(r"{{\s*var\s*\(\s*(['\"])(.+?)\1.*?\)\s*}}", r"__dbt_var_\2", processed_sql, flags=re.IGNORECASE)
            # Replace env_var macros
            processed_sql = re.sub(r"{{\s*env_var\s*\(\s*(['\"])(.+?)\1.*?\)\s*}}", r"__dbt_env_var_\2", processed_sql, flags=re.IGNORECASE)
            # Replace other simple Jinja expressions {{ arbitrary_expression }} with a generic placeholder
            processed_sql = re.sub(r"{{.*?}}", " /* DBT_EXPRESSION */ ", processed_sql)

            # --- Phase 4: Post-Jinja SQL Cleaning ---
            # Remove SQL block comments /* ... */ AFTER Jinja replacements
            processed_sql = re.sub(r"/\*.*?\*/", "", processed_sql, flags=re.DOTALL)
            
            # Replace multiple newlines/whitespace with a single space
            processed_sql = re.sub(r'\s+', ' ', processed_sql)
            
            # Remove empty statements (just semicolons)
            processed_sql = re.sub(r';\s*;+', ';', processed_sql)
            processed_sql = processed_sql.replace('( ; ',')').replace('(;',')') # Semicolons inside parens
            processed_sql = processed_sql.strip('; ') # Leading/trailing semicolons
            
            # Remove dangling commas (e.g., "col1, col2, )" or "( , col1" or ", WHERE")
            processed_sql = re.sub(r',\s*\)', ')', processed_sql)
            processed_sql = re.sub(r'\(\s*,', '(', processed_sql)
            processed_sql = re.sub(r',\s*(WHERE|GROUP|ORDER|LIMIT|UNION|INTERSECT|EXCEPT)\b', r' \1', processed_sql, flags=re.IGNORECASE)
            processed_sql = processed_sql.strip(', ')
            
            # Check final length
            if len(processed_sql.strip()) < 5:
                 # Check original length vs processed length - if drastically different, likely mostly Jinja
                if len(sql) > 100 and len(processed_sql) < len(sql) * 0.1:
                     errors.append("Warning: Processed SQL is very short compared to original. Likely Jinja-heavy.")
                elif len(processed_sql.strip()) == 0:
                     return None, errors + ["Processed SQL is empty after cleaning."]
                else:
                     errors.append("Warning: Processed SQL is very short after cleaning.")

            return processed_sql, errors
        except Exception as e:
            logger.error(f"Error during preprocessing SQL: {str(e)}", exc_info=True)
            return None, [f"Error preprocessing SQL: {str(e)}"]
    
    def _looks_like_sql(self, text):
        """
        Check if the text looks like SQL code and not a YML file or markdown
        
        Args:
            text: Text to check
            
        Returns:
            True if it looks like SQL, False otherwise
        """
        if not text:
            return False

        # Remove comments and whitespace before checking
        cleaned_text = re.sub(r"--.*?$", "", text, flags=re.MULTILINE)
        cleaned_text = re.sub(r"/\*.*?\*/", "", cleaned_text, flags=re.DOTALL)
        # Remove ANSI escape sequences
        cleaned_text = re.sub(r'\x1b\[[0-9;]*m', '', cleaned_text)
        # Remove Jinja comments
        cleaned_text = re.sub(r"{#.*?#}", "", cleaned_text, flags=re.DOTALL)
        cleaned_text = cleaned_text.strip()

        if not cleaned_text:
            return False

        # Special handling for DBT-specific files
        # If the file is only macro definitions with no SQL content
        if cleaned_text.startswith("{%") and "macro" in cleaned_text[:30]:
            macro_content = len(re.findall(r"{%\s*macro\s+.*?%}", cleaned_text))
            # Check if it's primarily a macro file with little SQL content
            if macro_content > 0 and len(cleaned_text) - len(re.sub(r"{%\s*macro.*?endmacro\s*%}", "", cleaned_text, flags=re.DOTALL)) > len(cleaned_text) * 0.7:
                # If more than 70% of the file is macro definitions, don't treat it as SQL
                # But still check for SQL keywords inside the macros
                sql_pattern = r'(?i)\s*(SELECT|CREATE|INSERT|UPDATE|DELETE|WITH|ALTER)\s+'
                if re.search(sql_pattern, cleaned_text):
                    return True
                return False

        # Check if it contains common SQL keywords
        sql_keywords = [
            r"\bSELECT\b",
            r"\bFROM\b",
            r"\bWHERE\b",
            r"\bJOIN\b",
            r"\bGROUP BY\b",
            r"\bORDER BY\b",
            r"\bWITH\b",
            r"\bCREATE\b",
            r"\bTABLE\b",
            r"\bVIEW\b",
            r"\bINSERT\b",
            r"\bUPDATE\b",
            r"\bDELETE\b",
            r"\bMERGE\b",
            r"\bCASE\b",
        ]

        for keyword in sql_keywords:
            if re.search(keyword, cleaned_text, re.IGNORECASE):
                return True

        # Check if it contains DBT macros that would indicate SQL context
        dbt_patterns = [
            r"{{\s*ref\s*\(",
            r"{{\s*source\s*\(",
            r"{{\s*config\s*\(",
            r"{{\s*var\s*\(",
            r"{{\s*env_var\s*\(",
            r"{{\s*dbt_utils\.",
        ]

        for pattern in dbt_patterns:
            if re.search(pattern, text):
                return True
            
        # Check for inline Jinja mixed with SQL - typical in DBT files
        if re.search(r"{%.*?%}", text) and re.search(r"\b(select|from|where)\b", text, re.IGNORECASE):
            return True
        
        # For DBT files, if they contain some SQL-like content, be more permissive
        if re.search(r"\b(with|as|select|from)\b", text, re.IGNORECASE):
            return True

        return False
    def _extract_refs(self, sql: str) -> List[Dict[str, str]]:
        """
        Extract refs from DBT SQL code using regex
        
        Args:
            sql: SQL code
            
        Returns:
            List of dictionaries with model and optionally project keys
        """
        refs = []
        
        # Match single-argument refs: {{ ref('model') }}
        single_ref_pattern = r'{{\s*ref\s*\(\s*[\'"]([^\'"]+)[\'"]\s*\)\s*}}'
        single_matches = re.finditer(single_ref_pattern, sql, re.IGNORECASE)
        
        for match in single_matches:
            refs.append({
                "model": match.group(1),
            })
        
        # Match two-argument refs: {{ ref('project', 'model') }}
        double_ref_pattern = r'{{\s*ref\s*\(\s*[\'"]([^\'"]+)[\'"]\s*,\s*[\'"]([^\'"]+)[\'"]\s*\)\s*}}'
        double_matches = re.finditer(double_ref_pattern, sql, re.IGNORECASE)
        
        for match in double_matches:
            refs.append({
                "project": match.group(1),
                "model": match.group(2),
            })
            
        return refs

    def _extract_sources(self, sql: str) -> List[Dict[str, str]]:
        """
        Extract sources from DBT SQL code using regex
        
        Args:
            sql: SQL code
            
        Returns:
            List of dictionaries with source and table keys
        """
        sources = []
        
        # Match sources: {{ source('source', 'table') }}
        source_pattern = r'{{\s*source\s*\(\s*[\'"]([^\'"]+)[\'"]\s*,\s*[\'"]([^\'"]+)[\'"]\s*\)\s*}}'
        matches = re.finditer(source_pattern, sql, re.IGNORECASE)
        
        for match in matches:
            sources.append({
                "source": match.group(1),
                "table": match.group(2),
            })
            
        return sources

    def _extract_cte_dependencies(self, sql: str) -> Dict[str, List]:
        """
        Extract dependencies from CTEs (Common Table Expressions) in DBT SQL
        
        Args:
            sql: SQL code
            
        Returns:
            Dictionary with refs and sources lists
        """
        result = {
            "refs": [],
            "sources": []
        }
        
        # Find CTE definitions - match anything between WITH and the main SELECT
        cte_pattern = r'WITH\s+([^;]*)(?:SELECT|INSERT|UPDATE|DELETE)'
        cte_matches = re.search(cte_pattern, sql, re.IGNORECASE | re.DOTALL)
        
        if not cte_matches:
            return result
            
        cte_content = cte_matches.group(1)
        
        # Extract refs from CTEs
        refs = self._extract_refs(cte_content)
        if refs:
            result["refs"].extend(refs)
            
        # Extract sources from CTEs
        sources = self._extract_sources(cte_content)
        if sources:
            result["sources"].extend(sources)
            
        return result

    def _extract_yaml_dependencies(self, yaml_content: str, file_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Extract dependencies from a DBT YAML file
        
        Args:
            yaml_content: YAML content
            file_path: Path to the file (optional)
            
        Returns:
            Dictionary with dependency information
        """
        result = {
            "model_name": None,
            "refs": [],
            "sources": [],
            "tables": [],
            "errors": []
        }
        
        try:
            # Parse YAML content
            yaml_data = yaml.safe_load(yaml_content)
            
            if not yaml_data:
                result["errors"].append("Empty or invalid YAML")
                return result
                
            # Extract models
            if "models" in yaml_data:
                for model in yaml_data["models"]:
                    if "name" in model:
                        # Set the model name if not already set
                        if not result["model_name"]:
                            result["model_name"] = model["name"]
                            
                        # Add to tables list
                        result["tables"].append(model["name"])
                
            # Extract sources
            if "sources" in yaml_data:
                for source in yaml_data["sources"]:
                    source_name = source.get("name")
                    
                    if "tables" in source:
                        for table in source["tables"]:
                            table_name = table.get("name")
                            
                            if source_name and table_name:
                                # Add to sources list
                                result["sources"].append({
                                    "source": source_name,
                                    "table": table_name
                                })
                                
                                # Add to tables list with source prefix
                                result["tables"].append(f"{source_name}.{table_name}")
            
            return result
                
        except Exception as e:
            result["errors"].append(f"Error parsing YAML: {str(e)}")
            return result
    def _extract_refs(self, sql: str) -> List[Dict[str, str]]:
        """
        Extract refs from DBT SQL code using regex
        
        Args:
            sql: SQL code
            
        Returns:
            List of dictionaries with model and optionally project keys
        """
        refs = []
        
        # Match single-argument refs: {{ ref('model') }}
        single_ref_pattern = r'{{\s*ref\s*\(\s*[\'"]([^\'"]+)[\'"]\s*\)\s*}}'
        single_matches = re.finditer(single_ref_pattern, sql, re.IGNORECASE)
        
        for match in single_matches:
            refs.append({
                "model": match.group(1),
            })
        
        # Match two-argument refs: {{ ref('project', 'model') }}
        double_ref_pattern = r'{{\s*ref\s*\(\s*[\'"]([^\'"]+)[\'"]\s*,\s*[\'"]([^\'"]+)[\'"]\s*\)\s*}}'
        double_matches = re.finditer(double_ref_pattern, sql, re.IGNORECASE)
        
        for match in double_matches:
            refs.append({
                "project": match.group(1),
                "model": match.group(2),
            })
            
        return refs

    def _extract_sources(self, sql: str) -> List[Dict[str, str]]:
        """
        Extract sources from DBT SQL code using regex
        
        Args:
            sql: SQL code
            
        Returns:
            List of dictionaries with source and table keys
        """
        sources = []
        
        # Match sources: {{ source('source', 'table') }}
        source_pattern = r'{{\s*source\s*\(\s*[\'"]([^\'"]+)[\'"]\s*,\s*[\'"]([^\'"]+)[\'"]\s*\)\s*}}'
        matches = re.finditer(source_pattern, sql, re.IGNORECASE)
        
        for match in matches:
            sources.append({
                "source": match.group(1),
                "table": match.group(2),
            })
            
        return sources

    def _extract_cte_dependencies(self, sql: str) -> Dict[str, List]:
        """
        Extract dependencies from CTEs (Common Table Expressions) in DBT SQL
        
        Args:
            sql: SQL code
            
        Returns:
            Dictionary with refs and sources lists
        """
        result = {
            "refs": [],
            "sources": []
        }
        
        # Find CTE definitions - match anything between WITH and the main SELECT
        cte_pattern = r'WITH\s+([^;]*)(?:SELECT|INSERT|UPDATE|DELETE)'
        cte_matches = re.search(cte_pattern, sql, re.IGNORECASE | re.DOTALL)
        
        if not cte_matches:
            return result
            
        cte_content = cte_matches.group(1)
        
        # Extract refs from CTEs
        refs = self._extract_refs(cte_content)
        if refs:
            result["refs"].extend(refs)
            
        # Extract sources from CTEs
        sources = self._extract_sources(cte_content)
        if sources:
            result["sources"].extend(sources)
            
        return result

    def _extract_yaml_dependencies(self, yaml_content: str, file_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Extract dependencies from a DBT YAML file
        
        Args:
            yaml_content: YAML content
            file_path: Path to the file (optional)
            
        Returns:
            Dictionary with dependency information
        """
        result = {
            "model_name": None,
            "refs": [],
            "sources": [],
            "tables": [],
            "errors": []
        }
        
        try:
            # Parse YAML content
            yaml_data = yaml.safe_load(yaml_content)
            
            if not yaml_data:
                result["errors"].append("Empty or invalid YAML")
                return result
                
            # Extract models
            if "models" in yaml_data:
                for model in yaml_data["models"]:
                    if "name" in model:
                        # Set the model name if not already set
                        if not result["model_name"]:
                            result["model_name"] = model["name"]
                            
                        # Add to tables list
                        result["tables"].append(model["name"])
                
            # Extract sources
            if "sources" in yaml_data:
                for source in yaml_data["sources"]:
                    source_name = source.get("name")
                    
                    if "tables" in source:
                        for table in source["tables"]:
                            table_name = table.get("name")
                            
                            if source_name and table_name:
                                # Add to sources list
                                result["sources"].append({
                                    "source": source_name,
                                    "table": table_name
                                })
                                
                                # Add to tables list with source prefix
                                result["tables"].append(f"{source_name}.{table_name}")
            
            return result
                
        except Exception as e:
            result["errors"].append(f"Error parsing YAML: {str(e)}")
            return result
    
    def _extract_refs(self, sql):
        """
        Extract refs from DBT SQL code using regex
        
        Args:
            sql: SQL code
            
        Returns:
            List of dictionaries with model and optionally project keys
        """
        refs = []
        
        # Match single-argument refs: {{ ref('model') }}
        single_ref_pattern = r'{{\s*ref\s*\(\s*[\'"]([\'"]+)[\'"]*\s*\)\s*}}'
        single_matches = re.finditer(single_ref_pattern, sql, re.IGNORECASE)
        
        for match in single_matches:
            refs.append({
                "model": match.group(1),
            })
        
        # Match two-argument refs: {{ ref('project', 'model') }}
        double_ref_pattern = r'{{\s*ref\s*\(\s*[\'"]([\'"]+)[\'"]*\s*,\s*[\'"]([\'"]+)[\'"]*\s*\)\s*}}'
        double_matches = re.finditer(double_ref_pattern, sql, re.IGNORECASE)
        
        for match in double_matches:
            refs.append({
                "project": match.group(1),
                "model": match.group(2),
            })
            
        return refs

    def _extract_sources(self, sql):
        """
        Extract sources from DBT SQL code using regex
        
        Args:
            sql: SQL code
            
        Returns:
            List of dictionaries with source and table keys
        """
        sources = []
        
        # Match sources: {{ source('source', 'table') }}
        source_pattern = r'{{\s*source\s*\(\s*[\'"]([\'"]+)[\'"]*\s*,\s*[\'"]([\'"]+)[\'"]*\s*\)\s*}}'
        matches = re.finditer(source_pattern, sql, re.IGNORECASE)
        
        for match in matches:
            sources.append({
                "source": match.group(1),
                "table": match.group(2),
            })
            
        return sources

    def _extract_cte_dependencies(self, sql):
        """
        Extract dependencies from CTEs (Common Table Expressions) in DBT SQL
        
        Args:
            sql: SQL code
            
        Returns:
            Dictionary with refs and sources lists
        """
        result = {
            "refs": [],
            "sources": []
        }
        
        # Find CTE definitions - match anything between WITH and the main SELECT
        cte_pattern = r'WITH\s+([^;]*)(?:SELECT|INSERT|UPDATE|DELETE)'
        cte_matches = re.search(cte_pattern, sql, re.IGNORECASE | re.DOTALL)
        
        if not cte_matches:
            return result
            
        cte_content = cte_matches.group(1)
        
        # Extract refs from CTEs
        refs = self._extract_refs(cte_content)
        if refs:
            result["refs"].extend(refs)
            
        # Extract sources from CTEs
        sources = self._extract_sources(cte_content)
        if sources:
            result["sources"].extend(sources)
            
        return result

    def _extract_yaml_dependencies(self, yaml_content, file_path=None):
        """
        Extract dependencies from a DBT YAML file
        
        Args:
            yaml_content: YAML content
            file_path: Path to the file (optional)
            
        Returns:
            Dictionary with dependency information
        """
        result = {
            "model_name": None,
            "refs": [],
            "sources": [],
            "tables": [],
            "errors": []
        }
        
        try:
            # Parse YAML content
            yaml_data = yaml.safe_load(yaml_content)
            
            if not yaml_data:
                result["errors"].append("Empty or invalid YAML")
                return result
                
            # Extract models
            if "models" in yaml_data:
                for model in yaml_data["models"]:
                    if "name" in model:
                        # Set the model name if not already set
                        if not result["model_name"]:
                            result["model_name"] = model["name"]
                            
                        # Add to tables list
                        result["tables"].append(model["name"])
                
            # Extract sources
            if "sources" in yaml_data:
                for source in yaml_data["sources"]:
                    source_name = source.get("name")
                    
                    if "tables" in source:
                        for table in source["tables"]:
                            table_name = table.get("name")
                            
                            if source_name and table_name:
                                # Add to sources list
                                result["sources"].append({
                                    "source": source_name,
                                    "table": table_name
                                })
                                
                                # Add to tables list with source prefix
                                result["tables"].append(f"{source_name}.{table_name}")
            
            return result
                
        except Exception as e:
            result["errors"].append(f"Error parsing YAML: {str(e)}")
            return result
            
    def extract_dependencies(self, sql, file_path=None, dialect_hint=None, extract_only=False):
        """
        Extract table dependencies from DBT SQL code
        
        Args:
            sql: A string with DBT SQL code.
            file_path: An optional string with the path to the file.
            dialect_hint: An optional hint about what the dialect might be.
            extract_only: If True, only use regex extraction, skip parsing.
            
        Returns:
            A dictionary with the following keys:
            - model_name: The name of the DBT model.
            - refs: A list of dictionaries with "model" and optionally "project" keys.
            - sources: A list of dictionaries with "source" and "table" keys.
            - tables: A list of table names from parsed SQL.
            - errors: A list of error messages.
        """
        # First check if this is a YAML/YML file
        if file_path and (file_path.endswith('.yml') or file_path.endswith('.yaml')):
            return self._extract_yaml_dependencies(sql, file_path)

        # Initialize the result
        result = {
            "model_name": None,
            "refs": [],
            "sources": [],
            "tables": [],
            "errors": []
        }

        # Extract ref dependencies - both from the SQL and from any CTEs
        refs = self._extract_refs(sql)
        if refs:
            result["refs"] = refs

        # Extract source dependencies
        sources = self._extract_sources(sql)
        if sources:
            result["sources"] = sources
        
        # Also extract CTE dependencies via regex
        cte_deps = self._extract_cte_dependencies(sql)
        if cte_deps:
            # Add any missing refs
            for ref in cte_deps.get("refs", []):
                if ref not in result["refs"]:
                    result["refs"].append(ref)
                
            # Add any missing sources
            for source in cte_deps.get("sources", []):
                if source not in result["sources"]:
                    result["sources"].append(source)
                
        # If extract_only is true (e.g., for macro files), return regex results
        if extract_only:
            return result
    
    def extract_lineage(self, sql_code: str, file_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Extract column-level lineage from DBT SQL code
        
        Args:
            sql_code: SQL code to analyze
            file_path: Path to the file (optional)
            
        Returns:
            Dictionary with lineage information
        """
        # Initialize result structure to match the expected format
        result = {
            "table_lineage": {
                "target_table": None,
                "source_tables": []
            },
            "column_lineage": {
                "target_columns": [],
                "column_relationships": []
            },
            "columns": [],  # Legacy format for backward compatibility
            "errors": []
        }
        
        # For YAML/YML files, use the YAML extractor
        if file_path and (file_path.endswith('.yml') or file_path.endswith('.yaml')):
            try:
                yaml_data = self._extract_yaml_dependencies(sql_code, file_path)
                
                if yaml_data and 'models' in yaml_data:
                    # If there are models in the YAML, extract columns from them
                    for model in yaml_data['models']:
                        if 'columns' in model:
                            for col in model['columns']:
                                # Add to legacy format
                                col_info = {
                                    'table_name': model.get('name', ''),
                                    'column_name': col.get('name', ''),
                                    'description': col.get('description', ''),
                                    'data_type': col.get('type', None),
                                    'is_primary_key': 'primary_key' in col.get('tests', []),
                                    'is_foreign_key': False  # YAML doesn't have foreign key info
                                }
                                result['columns'].append(col_info)
                                
                                # Add to the new column_lineage format
                                result['column_lineage']['target_columns'].append({
                                    'name': col.get('name', ''),
                                    'table': model.get('name', ''),
                                    'data_type': col.get('type', None),
                                    'description': col.get('description', '')
                                })
                                
                            # Extract the target table name from the model
                            if not result['table_lineage']['target_table'] and 'name' in model:
                                result['table_lineage']['target_table'] = model['name']
                                
            except Exception as e:
                result['errors'].append(f"Error extracting YAML metadata: {str(e)}")
                logger.error(f"Error extracting YAML metadata: {str(e)}")
                
            return result
        
        # Skip non-SQL files like MD
        if not self._looks_like_sql(sql_code):
            result["errors"].append("Input doesn't appear to be SQL code")
            return result
            
        # Try to infer target table from file path
        target_model_name = None
        if file_path:
            # Try to predict target table name from file path
            base_name = os.path.basename(file_path)
            if base_name.endswith('.sql'):
                target_model_name = base_name[:-4]
            else:
                target_model_name = base_name
        
        # Set target table from model name if available
        if target_model_name:
            result["table_lineage"]["target_table"] = target_model_name
            
        # Extract DBT dependencies
        logger.info(f"Attempting to parse SQL for file {file_path} (length {len(sql_code)}):\n---\n{sql_code[:200]}...\n---")
        deps = self.extract_dependencies(sql_code, file_path, extract_only=True)
        if deps and deps.get("errors"):
            result["errors"].extend(deps["errors"])
            
        # Extract model name from dependencies if present
        if deps and deps.get("model_name"):
            result["table_lineage"]["target_table"] = deps["model_name"]
            
        # Extract source tables from dependencies
        source_table_strings = []
        
        # Add references to other DBT models
        for ref in (deps.get("refs", []) if deps else []):
            # Add to the string list for the table_lineage format
            if ref.get("project") and ref.get("model"):
                source_table_strings.append(f"{ref.get('project')}.{ref.get('model')}")
            elif ref.get("model"):
                source_table_strings.append(ref.get("model"))
        
        # Add sources (e.g. source('raw', 'customers') -> raw.customers)
        for source in (deps.get("sources", []) if deps else []):
            if source.get("source") and source.get("table"):
                source_table_strings.append(f"{source.get('source')}.{source.get('table')}")
            elif source.get("table"):
                source_table_strings.append(source.get("table"))
            
        # Add direct table references
        for table in (deps.get("tables", []) if deps else []):
            # Skip tables that look like macros or references
            if isinstance(table, str) and not table.startswith('__dbt_'):
                source_table_strings.append(table)
                    
        # Add source tables to result
        result["table_lineage"]["source_tables"] = source_table_strings
        
        try:
            # Parse SQL
            ast, errors = self.parse_sql(sql_code, file_path)
            if errors:
                result["errors"].extend(errors)
            
            if ast:
                # If the AST was parsed, extract source tables and relationships
                from sqlglot.expressions import Table, Select
                
                # Use SQLGlotLineageExtractor for consistent extraction
                from tools.sql_tools.lineage.sqlglot_lineage import SQLGlotLineageExtractor
                lineage_extractor = SQLGlotLineageExtractor()
                table_lineage = lineage_extractor.extract_table_lineage(ast, file_path)
                
                # Add source tables from the table lineage if available
                if table_lineage and table_lineage.get("source_tables"):
                    result["table_lineage"]["source_tables"] = table_lineage["source_tables"]
                
                # If we didn't get a target table from the model name, try to infer it
                if not result["table_lineage"]["target_table"] and table_lineage and table_lineage.get("target_table"):
                    result["table_lineage"]["target_table"] = table_lineage["target_table"]
                
                # Extract column-level lineage if possible
                column_lineage = lineage_extractor.extract_column_lineage(ast, file_path)
                if column_lineage:
                    # Add target columns to the column_lineage format
                    if "target_columns" in column_lineage:
                        result["column_lineage"]["target_columns"] = column_lineage["target_columns"]
                        
                        # Also add to legacy format
                        for col in column_lineage["target_columns"]:
                            if "name" in col:
                                table_name = result["table_lineage"]["target_table"] if result["table_lineage"]["target_table"] else ""
                                result["columns"].append({
                                    "table_name": table_name,
                                    "column_name": col["name"],
                                    "description": col.get("description", ""),
                                    "data_type": col.get("data_type", None),
                                    "is_primary_key": col.get("is_primary_key", False),
                                    "is_foreign_key": col.get("is_foreign_key", False)
                                })
                    
                    # Add column relationships to the column_lineage format
                    if "column_relationships" in column_lineage:
                        result["column_lineage"]["column_relationships"] = column_lineage["column_relationships"]
                
                # If we don't have any column relationships but have source tables and target columns,
                # create simple relationships assuming column names match
                if not result["column_lineage"]["column_relationships"] and \
                   result["table_lineage"]["source_tables"] and \
                   result["column_lineage"]["target_columns"]:
                    
                    for source_table in result["table_lineage"]["source_tables"]:
                        for target_col in result["column_lineage"]["target_columns"]:
                            if "name" in target_col:
                                result["column_lineage"]["column_relationships"].append({
                                    "source_table": source_table,
                                    "source_column": target_col["name"],
                                    "target_table": result["table_lineage"]["target_table"],
                                    "target_column": target_col["name"],
                                    "relationship_type": "dependency"
                                })
        
        except Exception as e:
            result["errors"].append(f"Error extracting lineage: {str(e)}")
            logger.error(f"Error in extract_lineage: {str(e)}", exc_info=True)
        
        return result
