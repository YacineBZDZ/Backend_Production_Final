#!/usr/bin/env python3
"""
Test direct connection to Google Cloud SQL without proxy.
"""

import os
import sys
import logging
import time
from dotenv import load_dotenv
import psycopg2
from sqlalchemy import create_engine, text

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Add project root to path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
sys.path.append(project_root)
sys.path.insert(0, project_root)

# Load environment variables from .env
load_dotenv(os.path.join(project_root, '.env'))

def test_direct_connection():
    """Test direct connection to Cloud SQL using psycopg2"""
    # Get connection details from environment variables
    host = os.environ.get("DB_HOST")
    port = os.environ.get("DB_PORT", "5432")
    dbname = os.environ.get("DB_NAME")
    user = os.environ.get("DB_USER")
    password = os.environ.get("DB_PASSWORD")
    ssl_mode = os.environ.get("DB_SSL_MODE", "disable")
    
    if not all([host, dbname, user, password]):
        logger.error("Missing required environment variables for database connection")
        logger.info(f"DB_HOST: {host}, DB_NAME: {dbname}, DB_USER: {user}")
        return False
    
    # Log connection details (masking password)
    logger.info(f"Testing direct connection to {host}:{port}/{dbname} as {user} with SSL mode: {ssl_mode}")
    
    try:
        # Connect using psycopg2
        conn = psycopg2.connect(
            host=host,
            port=port,
            dbname=dbname,
            user=user,
            password=password,
            sslmode=ssl_mode
        )
        
        # Test the connection
        cursor = conn.cursor()
        cursor.execute("SELECT version();")
        version = cursor.fetchone()
        
        logger.info(f"✓ Connection successful!")
        logger.info(f"Database version: {version[0]}")
        
        # Check if doctor_profiles table exists
        cursor.execute("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'doctor_profiles');")
        table_exists = cursor.fetchone()[0]
        logger.info(f"doctor_profiles table exists: {table_exists}")
        
        if table_exists:
            # Count doctor profiles with null user_id
            cursor.execute("SELECT COUNT(*) FROM doctor_profiles WHERE user_id IS NULL;")
            null_count = cursor.fetchone()[0]
            logger.info(f"Found {null_count} doctor profiles with NULL user_id")
        
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Connection failed: {str(e)}")
        return False

def test_sqlalchemy_connection():
    """Test SQLAlchemy connection to Cloud SQL"""
    host = os.environ.get("DB_HOST")
    port = os.environ.get("DB_PORT", "5432")
    dbname = os.environ.get("DB_NAME")
    user = os.environ.get("DB_USER")
    password = os.environ.get("DB_PASSWORD")
    ssl_mode = os.environ.get("DB_SSL_MODE", "disable")
    
    if not all([host, dbname, user, password]):
        logger.error("Missing required environment variables for SQLAlchemy connection")
        return False
    
    # Create database URL
    db_url = f"postgresql://{user}:{password}@{host}:{port}/{dbname}"
    if ssl_mode:
        db_url += f"?sslmode={ssl_mode}"
    
    # Mask password in logs
    masked_url = db_url.replace(password, "********")
    logger.info(f"Testing SQLAlchemy connection with URL: {masked_url}")
    
    try:
        # Create engine with appropriate options
        engine_kwargs = {
            "pool_pre_ping": True,
            "pool_recycle": 1800,
            "connect_args": {"connect_timeout": 10}
        }
        
        # Create engine and test connection
        engine = create_engine(db_url, **engine_kwargs)
        
        with engine.connect() as conn:
            # Test basic query
            result = conn.execute(text("SELECT version();"))
            version = result.fetchone()[0]
            logger.info(f"✓ SQLAlchemy connection successful")
            logger.info(f"Database version: {version}")
            
            # Check doctor profiles
            result = conn.execute(text("SELECT COUNT(*) FROM doctor_profiles WHERE user_id IS NULL;"))
            count = result.fetchone()[0]
            logger.info(f"Found {count} doctor profiles with NULL user_id")
        
        return True
    except Exception as e:
        logger.error(f"SQLAlchemy connection failed: {str(e)}")
        return False

if __name__ == "__main__":
    logger.info("Testing direct connection to Google Cloud SQL...")
    
    psycopg2_success = test_direct_connection()
    logger.info("\n----------------------------\n")
    sqlalchemy_success = test_sqlalchemy_connection()
    
    if psycopg2_success and sqlalchemy_success:
        logger.info("\n✓ All connection tests PASSED")
        sys.exit(0)
    else:
        logger.error("\n✗ Some connection tests FAILED")
        sys.exit(1)