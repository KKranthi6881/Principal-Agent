import os
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from api import llm_providers_api
from api import github_connectors_api
from api import github_vector_api
from api import models_api
from database.migrations import run_migrations

# Create FastAPI app
app = FastAPI()

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

# Startup event
@app.on_event("startup")
async def startup_event():
    # Run database migrations
    run_migrations.run_all_migrations()

# Default route
@app.get("/")
async def root():
    return {"message": "Welcome to the Data Architect API"}

# Run the application
if __name__ == "__main__":
    uvicorn.run("run:app", host="0.0.0.0", port=8002, reload=True) 