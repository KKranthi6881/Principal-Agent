# SQL Lineage Extraction and Storage System

This system provides tools for parsing SQL code from different tech stacks, extracting lineage information, and storing it in a SQLite database for later retrieval.

## Features

- **Multi-dialect SQL Parsing**: Parse SQL from different tech stacks including:
  - T-SQL (SQL Server)
  - PostgreSQL
  - (Coming soon: MySQL, Snowflake)

- **Rich Lineage Extraction**:
  - Table-level lineage with source and target tables
  - Column-level lineage with data types and constraints
  - Join relationships and conditions
  - Business metadata (descriptions, owners, tags)

- **Lineage Storage**:
  - SQLite database for persistent storage
  - JSON format for lineage visualization
  - GitHub source tracking

## Components

### SQL Dialect Handlers

The system includes dialect-specific handlers for parsing SQL from different tech stacks:

```
backend/tools/sql_tools/dialects/
├── __init__.py              # Dialect registry
├── base_dialect.py          # Base dialect class
├── postgresql/             # PostgreSQL dialect
│   └── __init__.py
└── tsql/                   # T-SQL dialect
    └── __init__.py
```

### Lineage Extraction

The SQLGlot lineage extractor parses SQL and extracts:
- Source and target tables
- Relationships between tables
- Column-level dependencies
- Business metadata

```
backend/tools/sql_tools/lineage/
├── __init__.py              # Package initialization
├── base_lineage.py          # Base lineage extractor
└── sqlglot_lineage.py       # SQLGlot lineage extractor
```

### Lineage Database

The lineage database stores extracted information for retrieval:
- Tables with path information
- Columns with constraints
- Relationships between tables
- Lineage definitions as JSON

```
backend/database/
├── db_setup.py              # Database setup
└── lineage_db.py            # Lineage database interface
```

## Usage

### Parsing SQL and Extracting Lineage

```python
# Get dialect handler
dialect = get_dialect_parser("tsql")  # or "postgresql"

# Parse SQL
ast, errors = dialect.parse_sql(sql_code)

# Extract lineage
extractor = SQLGlotLineageExtractor()
table_lineage = extractor.extract_table_lineage(ast, file_path)
column_lineage = extractor.extract_column_lineage(ast, file_path)

# Store in database
lineage_db = LineageDB()
table_id = lineage_db.add_table(
    table_name=table_lineage["target_table"]["name"],
    tech_stack="tsql",
    github_path=file_path
)
lineage_id = lineage_db.add_lineage_definition(
    root_table_id=table_id,
    lineage_json={
        "table_lineage": table_lineage,
        "column_lineage": column_lineage
    },
    tech_stack="tsql"
)
```

### Retrieving Lineage Information

```python
# Get lineage for a table
lineage_db = LineageDB()
table = lineage_db.get_table_by_name("FactSales", "tsql")
lineage = lineage_db.get_lineage_definition(table["table_id"])

# Get all lineage for a tech stack
lineage_items = lineage_db.get_lineage_by_tech_stack("tsql")
```

## API Endpoints

- `POST /api/lineage/parse`: Parse SQL and extract lineage
- `GET /api/lineage/table/{table_name}`: Get lineage for a table
- `GET /api/lineage/tech-stack/{tech_stack}`: Get all lineage for a tech stack
- `GET /api/lineage/lineage/{lineage_id}`: Get lineage by ID
- `POST /api/lineage/github-connector/{connector_id}/parse`: Parse SQL from GitHub connector

## Testing

Run the test script to verify the system:

```bash
python test_lineage_flow.py
``` 