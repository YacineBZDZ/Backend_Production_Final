"""
Migration script to add the personal_phone column to the doctor_profiles table.
Run this script directly to apply the migration.
"""

import sys
import os
import logging
from sqlalchemy import create_engine, Column, String, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Add parent directory to path to access models and database modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.base import engine
from core.config import get_settings

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def run_migration():
    """Add personal_phone column to doctor_profiles table"""
    try:
        logger.info("Starting migration: Adding personal_phone to doctor_profiles...")
        
        # Using SQLAlchemy Core for direct SQL execution
        with engine.connect() as connection:
            # Check if column already exists
            inspector = connection.dialect.has_column(connection.engine, 'doctor_profiles', 'personal_phone')
            
            if inspector:
                logger.info("Column 'personal_phone' already exists. Skipping...")
                return
            
            # Add column
            connection.execute(text(
                "ALTER TABLE doctor_profiles ADD COLUMN personal_phone VARCHAR;"))
            
            logger.info("Migration successful: personal_phone column added to doctor_profiles table")
    
    except Exception as e:
        logger.error(f"Migration failed: {str(e)}")
        raise

if __name__ == "__main__":
    run_migration()
