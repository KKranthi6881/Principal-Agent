# GitHub Connector with Supabase Integration

This project implements a GitHub connector for both standard and enterprise GitHub repositories, with data stored in Supabase.

## Project Structure

- `frontend`: React application with Chakra UI
- `backend`: FastAPI REST API with Supabase integration

## Prerequisites

- Node.js 16+ for the frontend
- Python 3.12+ for the backend
- Supabase running locally or a Supabase account

## Backend Setup

1. Set up a local Supabase instance:
   - Install Supabase CLI: https://supabase.com/docs/guides/cli
   - Start local Supabase: `supabase start`

2. Configure the backend:
   ```bash
   cd backend
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   cp .env.template .env
   ```

3. Edit the `.env` file with your Supabase credentials:
   ```
   SUPABASE_URL=http://localhost:8000
   SUPABASE_KEY=your-supabase-anon-key
   ```

4. Create database tables:
   ```bash
   python -m database.setup_db
   ```

5. Start the FastAPI server:
   ```bash
   python run_api.py
   ```
   The backend will be available at http://localhost:8080

## Frontend Setup

1. Install dependencies:
   ```bash
   cd frontend
   npm install
   ```

2. Create a `.env` file:
   ```bash
   REACT_APP_API_BASE_URL=http://localhost:8080
   ```

3. Start the development server:
   ```bash
   npm start
   ```
   The frontend will be available at http://localhost:3000

## Using the GitHub Connector

1. Navigate to the GitHub Connector page in the application
2. Configure a GitHub repository:
   - For standard GitHub: Enter the repository URL (e.g., `https://github.com/username/repo`)
   - For enterprise GitHub: Toggle "Enterprise GitHub" and enter the full URL with domain
   - For private repositories: Enter your GitHub username and personal access token

## API Endpoints

The following API endpoints are available:

- `GET /api/settings/github_connectors`: List all GitHub connectors
- `GET /api/settings/github_connectors/{connector_id}`: Get a specific GitHub connector
- `POST /api/settings/github_connectors`: Create a new GitHub connector
- `PUT /api/settings/github_connectors/{connector_id}`: Update a GitHub connector
- `DELETE /api/settings/github_connectors/{connector_id}`: Delete a GitHub connector

## Data Schema

The GitHub connector data is stored in Supabase with the following schema:

```sql
CREATE TABLE github_connectors (
    id SERIAL PRIMARY KEY,
    username TEXT,
    token TEXT,
    repo_url TEXT NOT NULL,
    is_public BOOLEAN DEFAULT FALSE,
    is_enterprise BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE
);
``` 