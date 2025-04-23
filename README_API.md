# Principal Data Agent - AI-Powered Code Analysis Platform

A powerful platform for analyzing code, managing conversations, and providing intelligent insights using AI agents.

## Project Structure

```
backend/
├── api/                    # FastAPI application
│   ├── main.py            # Main FastAPI application
│   ├── database_manager.py # SQLite database operations
│   └── vector_store_manager.py # ChromaDB operations
├── database/              # SQLite databases
│   ├── conversations.db   # Chat conversations and threads
│   ├── log_info.db       # Agent and tool logging
│   └── metadata.db       # User and connection metadata
├── vector_store/         # ChromaDB vector stores
│   ├── chromadb_github/  # GitHub code vector store
│   ├── chromadb_document/# Document vector store
│   └── chromadb_summary/ # Conversation summary store
├── agents/               # AI agents implementation
├── tools/               # Code analysis tools
├── models/              # Data models
├── config/              # Configuration files
├── utils/               # Utility functions
└── requirements.txt     # Python dependencies
```

## Prerequisites

- Python 3.12+
- SQLite3
- Git (for GitHub integration)

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd Data-Architect
```

2. Create and activate a virtual environment:
```bash
python -m venv backend/venv
source backend/venv/bin/activate  # On Windows: backend\venv\Scripts\activate
```

3. Install dependencies:
```bash
cd backend
pip install -r requirements.txt
```

4. Set up the databases:
```bash
python database/db_setup.py
```

## Running the Application

1. Start the FastAPI server:
```bash
python run.py
```

The API will be available at `http://localhost:8000`

## API Documentation

The API documentation is available at `http://localhost:8000/docs` when the server is running.

### Key Endpoints

#### Conversation Management
- `POST /threads/` - Create a new conversation thread
- `POST /conversations/` - Add a new conversation message
- `GET /threads/{thread_id}/conversations/` - Get recent conversations for a thread

#### Logging
- `POST /logs/agent/` - Log agent activity
- `POST /logs/tool/` - Log tool usage

#### User Management
- `POST /users/` - Create a new user
- `POST /connections/` - Add a new connection (GitHub, etc.)
- `POST /code-metadata/` - Add metadata for code files

#### Vector Store Operations
- `POST /vector/github/` - Add GitHub file to vector store
- `POST /vector/github/search/` - Search GitHub files
- `POST /vector/document/` - Add document to vector store
- `POST /vector/document/search/` - Search documents
- `POST /vector/summary/` - Add conversation summary
- `POST /vector/summary/search/` - Search conversation summaries

## Database Structure

### SQLite Databases

1. **conversations.db**
   - `threads`: Stores conversation threads
   - `conversations`: Stores individual messages

2. **log_info.db**
   - `agent_logs`: Tracks agent activities
   - `tool_logs`: Records tool usage

3. **metadata.db**
   - `users`: User information
   - `connections`: External connections (GitHub, etc.)
   - `code_metadata`: Code file metadata

### ChromaDB Collections

1. **chromadb_github**
   - Stores GitHub-related files and code
   - Enables similarity search for code

2. **chromadb_document**
   - Stores general documents
   - Supports hybrid search

3. **chromadb_summary**
   - Stores conversation summaries
   - Enables semantic search across conversations

## Development

### Adding New Features

1. **Database Changes**
   - Update `database/db_setup.py` with new table definitions
   - Add corresponding methods in `api/database_manager.py`

2. **Vector Store Changes**
   - Add new collections in `api/vector_store_manager.py`
   - Implement corresponding API endpoints in `api/main.py`

3. **API Endpoints**
   - Define Pydantic models in `api/main.py`
   - Implement endpoints using FastAPI decorators
   - Add proper error handling and validation

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

[Add your license information here]

