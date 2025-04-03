#!/bin/bash

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Setting up Data Architect Backend Environment...${NC}"

# Check Python version
python_version=$(python3 --version)
echo -e "${YELLOW}Detected: ${python_version}${NC}"

# Create virtual environment
echo -e "${GREEN}Creating virtual environment...${NC}"
python3 -m venv venv
source venv/bin/activate

# Upgrade pip
echo -e "${GREEN}Upgrading pip...${NC}"
pip install --upgrade pip

# Install requirements
echo -e "${GREEN}Installing required packages...${NC}"
pip install -r requirements.txt

# Create .env file from template if it doesn't exist
if [ ! -f config/.env ]; then
    echo -e "${GREEN}Creating .env file from template...${NC}"
    cp config/.env.example config/.env
    echo -e "${YELLOW}Please update the config/.env file with your actual credentials${NC}"
fi

# Initialize the database schema
echo -e "${GREEN}Setting up database schema...${NC}"
python -c "from database.connection import initialize_database; initialize_database()"

echo -e "${GREEN}Setup completed successfully!${NC}"
echo -e "${YELLOW}To start the FastAPI server, run: ${NC}python main.py" 