"""
Storage directory for persistent data
"""
import os
import logging

# Configure logging
logger = logging.getLogger(__name__)

# Ensure all required storage directories exist
required_dirs = ['repos', 'temp', 'backups']

# Get the current directory (storage)
storage_dir = os.path.dirname(os.path.abspath(__file__))

# Create required directories
for dirname in required_dirs:
    dir_path = os.path.join(storage_dir, dirname)
    if not os.path.exists(dir_path):
        try:
            os.makedirs(dir_path, exist_ok=True)
            logger.info(f"Created storage directory: {dir_path}")
        except Exception as e:
            logger.error(f"Error creating storage directory {dir_path}: {str(e)}")

# Create a .gitignore file to prevent accidental commits of storage contents
gitignore_path = os.path.join(storage_dir, '.gitignore')
if not os.path.exists(gitignore_path):
    try:
        with open(gitignore_path, 'w') as f:
            f.write("# Ignore all files in storage directory except this .gitignore\n")
            f.write("*\n")
            f.write("!.gitignore\n")
            f.write("!__init__.py\n")
            f.write("!README.md\n")
        logger.info(f"Created .gitignore in storage directory")
    except Exception as e:
        logger.error(f"Error creating .gitignore in storage directory: {str(e)}")

# Create a README.md file to explain the purpose of the directory
readme_path = os.path.join(storage_dir, 'README.md')
if not os.path.exists(readme_path):
    try:
        with open(readme_path, 'w') as f:
            f.write("# Storage Directory\n\n")
            f.write("This directory contains persistent data for the application.\n\n")
            f.write("## Structure\n\n")
            f.write("- `repos/`: Persistent GitHub repository clones\n")
            f.write("- `temp/`: Temporary files\n")
            f.write("- `backups/`: Backup files\n\n")
            f.write("Note: The contents of this directory are ignored by git except for this README, the __init__.py file, and the .gitignore file.\n")
        logger.info(f"Created README.md in storage directory")
    except Exception as e:
        logger.error(f"Error creating README.md in storage directory: {str(e)}") 