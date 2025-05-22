# database/base.py

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import text
from core.config import get_settings
import logging
import os
import urllib.parse

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get settings
settings = get_settings()

# Get database URL from settings using the new method
try:
    SQLALCHEMY_DATABASE_URL = settings.get_database_url()
    
    # Mask sensitive info in logs
    if '@' in SQLALCHEMY_DATABASE_URL:
        url_parts = SQLALCHEMY_DATABASE_URL.split('@')
        auth_part = url_parts[0].split(':')[0]
        host_part = url_parts[1]
        logger.info(f"Using database connection: {auth_part}:***@{host_part}")
    else:
        logger.info(f"Using database connection: {SQLALCHEMY_DATABASE_URL}")
        
except Exception as e:
    logger.error(f"Failed to get database URL: {str(e)}")
    # Fallback to SQLite for development if needed
    SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
    logger.warning(f"Falling back to SQLite: {SQLALCHEMY_DATABASE_URL}")

# Create the SQLAlchemy engine with proper options for Google Cloud SQL
engine_options = {
    "pool_pre_ping": True,      # Verify connections before using them
    "pool_recycle": 1800,       # Recycle connections after 30 minutes (recommended for Cloud SQL)
    "pool_size": 5,             # Default pool size
    "max_overflow": 10,         # Allow 10 overflow connections
    "pool_timeout": 30          # Connection timeout in seconds
}

# Add specific options for Google Cloud SQL
if settings.DB_INSTANCE and SQLALCHEMY_DATABASE_URL.startswith('postgresql'):
    logger.info(f"Configuring for Google Cloud SQL instance: {settings.DB_INSTANCE}")
    
    # Add connect_args with SSL parameters for Google Cloud SQL
    engine_options["connect_args"] = {
        # For Cloud SQL, we generally use verify-ca or verify-full
        "sslmode": os.environ.get("DB_SSL_MODE", "prefer")
    }
    
    # If using Cloud SQL Auth Proxy, we might not need SSL
    if settings.DB_USE_PROXY:
        logger.info("Using Cloud SQL Auth Proxy, adjusting SSL settings")
        engine_options["connect_args"] = {}  # No SSL needed with proxy

# Create the SQLAlchemy engine
logger.info(f"Creating engine with options: {engine_options}")
engine = create_engine(SQLALCHEMY_DATABASE_URL, **engine_options)

# Make the connection test optional using an environment variable
should_test_connection = os.environ.get("TEST_DB_CONNECTION", "true").lower() in ("true", "1", "yes")

if should_test_connection:
    try:
        # Test connection and log version with a timeout
        with engine.connect() as connection:
            if SQLALCHEMY_DATABASE_URL.startswith('sqlite'):
                result = connection.execute(text("SELECT sqlite_version();"))
                db_type = "SQLite"
            else:
                result = connection.execute(text("SELECT version();"))
                db_type = "PostgreSQL"
            version = result.fetchone()
            logger.info(f"{db_type} version: %s", version[0])
    except Exception as e:
        logger.error("Error connecting to database: %s", str(e))
        # Don't raise the exception - allow the application to start even with DB connection issues
        logger.warning("Application starting despite database connection issues")
else:
    logger.info("Skipping database connection test as per configuration")

# Create a configured "SessionLocal" class for session creation.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)

# Create a Base class from which all of your ORM models should inherit.
Base = declarative_base()
