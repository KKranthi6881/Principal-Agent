"""
Run all database migrations
"""
import os
import importlib.util
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def run_all_migrations():
    """
    Run all migration scripts in the migrations directory
    """
    logger.info("Running database migrations...")
    
    # Create metadata database directory if it doesn't exist
    db_dir = os.path.join('database')
    os.makedirs(db_dir, exist_ok=True)
    
    # Get all migration files
    migrations_dir = os.path.dirname(os.path.abspath(__file__))
    migration_files = [f for f in os.listdir(migrations_dir) 
                      if f.endswith('.py') and f != '__init__.py' and f != 'run_migrations.py']
    
    # Sort migration files to ensure they run in the correct order
    migration_files.sort()
    
    # Run each migration
    for migration_file in migration_files:
        logger.info(f"Running migration: {migration_file}")
        
        # Load the migration module
        file_path = os.path.join(migrations_dir, migration_file)
        
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
        else:
            logger.warning(f"Migration {migration_file} does not have a run_migration() function")
    
    logger.info("All migrations completed")

if __name__ == "__main__":
    run_all_migrations() 