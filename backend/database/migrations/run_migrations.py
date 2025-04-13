"""
Run all database migrations
"""
import os
import importlib.util
import logging
import traceback
from pathlib import Path

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def run_all_migrations():
    """
    Run all migration scripts in the migrations directory
    """
    logger.info("Running database migrations...")
    
    try:
        # Create database directory if it doesn't exist
        db_dir = Path(__file__).parent.parent
        db_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Ensured database directory exists: {db_dir}")
        
        # Get all migration files
        migrations_dir = Path(__file__).parent
        migration_files = [f for f in os.listdir(migrations_dir) 
                          if f.endswith('.py') and f != '__init__.py' and f != 'run_migrations.py']
        
        # Sort migration files to ensure they run in the correct order
        migration_files.sort()
        
        # Run each migration
        for migration_file in migration_files:
            try:
                logger.info(f"Running migration: {migration_file}")
                
                # Load the migration module
                file_path = migrations_dir / migration_file
                
                # Import the module dynamically
                module_name = migration_file[:-3]  # Remove .py extension
                spec = importlib.util.spec_from_file_location(module_name, file_path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                
                # Run the migration
                if hasattr(module, 'run_migration'):
                    try:
                        module.run_migration()
                        logger.info(f"Successfully ran migration: {migration_file}")
                    except Exception as e:
                        logger.error(f"Error running migration {migration_file}: {str(e)}")
                        logger.error(traceback.format_exc())
                else:
                    logger.warning(f"Migration {migration_file} does not have a run_migration() function")
            except Exception as e:
                logger.error(f"Error loading migration {migration_file}: {str(e)}")
                logger.error(traceback.format_exc())
        
        logger.info("All migrations completed")
    except Exception as e:
        logger.error(f"Fatal error during migrations: {str(e)}")
        logger.error(traceback.format_exc())

if __name__ == "__main__":
    run_all_migrations() 