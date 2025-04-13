"""
Settings API routes for application configuration
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, List, Optional, Any
import os
import json
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create router
router = APIRouter(
    prefix="/settings",
    tags=["Settings"],
    responses={404: {"description": "Not found"}},
)

# Settings file path
SETTINGS_DIR = Path(__file__).parent.parent / "config"
SETTINGS_FILE = SETTINGS_DIR / "settings.json"

# Ensure settings directory exists
SETTINGS_DIR.mkdir(parents=True, exist_ok=True)

# Default settings
DEFAULT_SETTINGS = {
    "llm": {
        "default_provider": "openai",
        "default_model": "gpt-4o",
        "temperature": 0.7,
        "max_tokens": 2000
    },
    "database": {
        "logging_enabled": True,
        "max_history": 100
    },
    "ui": {
        "theme": "light",
        "code_highlighting": True
    }
}

# Settings models
class LLMSettings(BaseModel):
    default_provider: str
    default_model: str
    temperature: float
    max_tokens: int

class DatabaseSettings(BaseModel):
    logging_enabled: bool
    max_history: int

class UISettings(BaseModel):
    theme: str
    code_highlighting: bool

class Settings(BaseModel):
    llm: LLMSettings
    database: DatabaseSettings
    ui: UISettings

# Helper functions
def load_settings() -> Dict[str, Any]:
    """Load settings from file or create default settings"""
    if not SETTINGS_FILE.exists():
        # Create default settings file
        with open(SETTINGS_FILE, "w") as f:
            json.dump(DEFAULT_SETTINGS, f, indent=2)
        return DEFAULT_SETTINGS
    
    try:
        with open(SETTINGS_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading settings: {str(e)}")
        return DEFAULT_SETTINGS

def save_settings(settings: Dict[str, Any]) -> bool:
    """Save settings to file"""
    try:
        with open(SETTINGS_FILE, "w") as f:
            json.dump(settings, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Error saving settings: {str(e)}")
        return False

# Routes
@router.get("/", response_model=Settings)
async def get_settings():
    """Get all settings"""
    return load_settings()

@router.get("/llm", response_model=LLMSettings)
async def get_llm_settings():
    """Get LLM settings"""
    settings = load_settings()
    return settings.get("llm", DEFAULT_SETTINGS["llm"])

@router.put("/llm", response_model=LLMSettings)
async def update_llm_settings(llm_settings: LLMSettings):
    """Update LLM settings"""
    settings = load_settings()
    settings["llm"] = llm_settings.dict()
    if save_settings(settings):
        return llm_settings
    raise HTTPException(status_code=500, detail="Failed to save settings")

@router.get("/database", response_model=DatabaseSettings)
async def get_database_settings():
    """Get database settings"""
    settings = load_settings()
    return settings.get("database", DEFAULT_SETTINGS["database"])

@router.put("/database", response_model=DatabaseSettings)
async def update_database_settings(db_settings: DatabaseSettings):
    """Update database settings"""
    settings = load_settings()
    settings["database"] = db_settings.dict()
    if save_settings(settings):
        return db_settings
    raise HTTPException(status_code=500, detail="Failed to save settings")

@router.get("/ui", response_model=UISettings)
async def get_ui_settings():
    """Get UI settings"""
    settings = load_settings()
    return settings.get("ui", DEFAULT_SETTINGS["ui"])

@router.put("/ui", response_model=UISettings)
async def update_ui_settings(ui_settings: UISettings):
    """Update UI settings"""
    settings = load_settings()
    settings["ui"] = ui_settings.dict()
    if save_settings(settings):
        return ui_settings
    raise HTTPException(status_code=500, detail="Failed to save settings")

@router.post("/reset", response_model=Settings)
async def reset_settings():
    """Reset settings to default"""
    save_settings(DEFAULT_SETTINGS)
    return DEFAULT_SETTINGS 