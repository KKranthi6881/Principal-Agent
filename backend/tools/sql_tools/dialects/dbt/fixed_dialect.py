"""
Fixed extraction method for DBT dialect
"""

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
                            # Add to the column_lineage format
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
    
    # Skip non-SQL files like MD
    if not self._looks_like_sql(sql_code):
        result["errors"].append("Input doesn't appear to be SQL code")
        return result
        
    # Extract dependencies using regex parsing
    logger.info(f"Attempting to parse SQL for file {file_path} (length {len(sql_code)}):\n---\n{sql_code[:200]}...\n---")
    deps = self.extract_dependencies(sql_code, file_path, extract_only=True)
    
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
            if table_lineage.get("source_tables"):
                result["table_lineage"]["source_tables"] = table_lineage["source_tables"]
            
            # If we didn't get a target table from the model name, try to infer it
            if not result["table_lineage"]["target_table"] and table_lineage.get("target_table"):
                result["table_lineage"]["target_table"] = table_lineage["target_table"]
            
            # Extract column-level lineage if possible
            column_lineage = lineage_extractor.extract_column_lineage(ast, file_path)
            if column_lineage:
                # Add target columns to the column_lineage format
                if "target_columns" in column_lineage:
                    result["column_lineage"]["target_columns"] = column_lineage["target_columns"]
                
                # Add column relationships to the column_lineage format
                if "column_relationships" in column_lineage:
                    result["column_lineage"]["column_relationships"] = column_lineage["column_relationships"]
        
    except Exception as e:
        result["errors"].append(f"Error extracting lineage: {str(e)}")
        logger.error(f"Error in extract_lineage: {str(e)}", exc_info=True)
    
    return result
