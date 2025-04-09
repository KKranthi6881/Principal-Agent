import os
from fastapi import FastAPI, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
import logging

# Import API routers
from api import settings_api, github_connector_api, github_vector_api, sql_analysis_api

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Data Architect API",
    description="API for data architecture capabilities",
    version="0.1.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For development; should be restricted in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(settings_api.router)
app.include_router(github_connector_api.router)  
app.include_router(github_vector_api.router)
app.include_router(sql_analysis_api.router)

@app.get("/")
async def root():
    return {"message": "Data Architect API is running"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"} 