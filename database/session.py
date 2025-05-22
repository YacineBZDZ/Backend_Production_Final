# database/session.py

from typing import AsyncGenerator, Generator
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import sessionmaker
from contextlib import asynccontextmanager
from core.config import get_settings
import logging
import re

# Configure logging
logger = logging.getLogger(__name__)

# Get database URL from settings
settings = get_settings()
try:
    # Use the get_database_url method instead of DATABASE_URL property
    database_url = settings.get_database_url()
    logger.info(f"Retrieved database URL: {'postgresql:***@' + database_url.split('@')[1] if '@' in database_url else database_url}")
    if not database_url:
        raise ValueError("Database URL is empty")
except Exception as e:
    logger.error(f"Error retrieving database URL: {str(e)}")
    raise

# Get SSL mode from settings or default to disable
ssl_mode = getattr(settings, 'DB_SSL_MODE', 'disable')

# For asyncpg, we need to remove the sslmode from the URL as it's handled differently
async_database_url = database_url
if database_url.startswith('postgresql://'):
    # Remove any sslmode parameter from the URL
    async_database_url = re.sub(r'[\?&]sslmode=[^&]*', '', database_url)
    # Convert to asyncpg format
    async_database_url = async_database_url.replace('postgresql://', 'postgresql+asyncpg://', 1)

# Regular synchronous engine and session with psycopg2
engine_kwargs = {
    "pool_pre_ping": True,
    "pool_recycle": 3600,  # Recycle connections after 1 hour
}

# Add SSL mode parameter if needed for PostgreSQL with psycopg2
if database_url.startswith('postgresql://'):
    engine_kwargs["connect_args"] = {
        "options": "-c timezone=utc",
        "sslmode": ssl_mode
    }
else:
    engine_kwargs["connect_args"] = {"options": "-c timezone=utc"}

# Create engines
logger.info(f"Creating database engine with kwargs: {engine_kwargs}")
engine = create_engine(database_url, **engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Async engine and session with asyncpg
# Note: asyncpg uses different connection arguments than psycopg2
async_engine_kwargs = {
    "pool_pre_ping": True,
    "pool_recycle": 3600,  # Recycle connections after 1 hour
    "pool_size": 20,       # Maximum number of connections in the pool
    "max_overflow": 10     # Maximum number of connections that can be created beyond pool_size
}

# Add connect_args for asyncpg (different format than psycopg2)
if ssl_mode == 'disable':
    async_engine_kwargs["connect_args"] = {
        "server_settings": {"timezone": "UTC"},
        "ssl": False
    }
elif ssl_mode in ['prefer', 'require', 'verify-ca', 'verify-full']:
    async_engine_kwargs["connect_args"] = {
        "server_settings": {"timezone": "UTC"},
        "ssl": True
    }
    # For verify modes, we would need to add additional SSL params like
    # ssl_context, but for now, just enabling SSL should work
else:
    async_engine_kwargs["connect_args"] = {
        "server_settings": {"timezone": "UTC"}
    }

logger.info(f"Creating async database engine with kwargs: {async_engine_kwargs}")

# Create async engine
async_engine = create_async_engine(async_database_url, **async_engine_kwargs)
AsyncSessionLocal = async_sessionmaker(
    autocommit=False, 
    autoflush=False, 
    bind=async_engine,
    expire_on_commit=False
)

def get_db() -> Generator:
    """
    Get a database session for synchronous operations.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Method 1: Using asynccontextmanager (for use with async with)
@asynccontextmanager
async def get_async_db_context() -> AsyncGenerator[AsyncSession, None]:
    """
    Get a database session for asynchronous operations using async with.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception as e:
            await session.rollback()
            raise e
        finally:
            await session.close()

# Method 2: Using a regular async generator (for use with async for)
async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Get a database session for asynchronous operations using async for.
    """
    session = AsyncSessionLocal()
    try:
        yield session
    except Exception as e:
        await session.rollback()
        raise e
    finally:
        await session.close()

# Function to clean up database connections on application shutdown
async def close_db_connections():
    """Close all database connections"""
    await async_engine.dispose()
    engine.dispose()
