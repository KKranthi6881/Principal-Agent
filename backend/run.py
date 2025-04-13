import os
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from api import llm_providers_api
from api import github_connectors_api
from api import github_vector_api
from api import models_api
from api import sql_dependencies_api
from api import settings_api
from api import sql_analysis_api
from api.sql_agent_routes import router as sql_agent_router
from database.migrations import run_migrations
from database.database import db
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Data Architect API",
    description="API for data architecture capabilities",
    version="0.1.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# Include routers
app.include_router(llm_providers_api.router)
app.include_router(github_connectors_api.router)
app.include_router(github_vector_api.router)
app.include_router(models_api.router)
app.include_router(sql_dependencies_api.router)
app.include_router(settings_api.router)
app.include_router(sql_analysis_api.router)
app.include_router(sql_agent_router, prefix="/sql-agent", tags=["SQL Agent"])

# Startup event
@app.on_event("startup")
async def startup_event():
    try:
        # Run database migrations
        logger.info("Running database migrations...")
        run_migrations.run_all_migrations()
        
        # Create database directories if they don't exist
        logger.info("Ensuring database directories exist...")
        db_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "database")
        os.makedirs(db_dir, exist_ok=True)
        
        # Initialize vector stores - these should be lazy-loaded when needed
        logger.info("API initialized successfully!")
    except Exception as e:
        logger.error(f"Error during startup: {str(e)}")

# Default route
@app.get("/")
async def root():
    return {"message": "Welcome to the Data Architect API"}

# Health check endpoint
@app.get("/health")
async def health_check():
    return {"status": "healthy"}

# Run the application
if __name__ == "__main__":
    uvicorn.run("run:app", host="0.0.0.0", port=8002, reload=True) 