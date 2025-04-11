# database/session.py

from typing import AsyncGenerator, Generator
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import sessionmaker
from contextlib import asynccontextmanager
from core.config import get_settings

# Get database URL from settings
settings = get_settings()
database_url = settings.DATABASE_URL

# Convert the regular PostgreSQL URL to an async URL if needed
async_database_url = database_url
if database_url.startswith('postgresql://'):
    async_database_url = database_url.replace('postgresql://', 'postgresql+asyncpg://', 1)

# Regular synchronous engine and session with psycopg2
engine = create_engine(
    database_url, 
    pool_pre_ping=True, 
    connect_args={"options": "-c timezone=utc"},
    pool_recycle=3600  # Recycle connections after 1 hour
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Async engine and session with asyncpg
# Note: asyncpg uses different connection arguments than psycopg2
async_engine = create_async_engine(
    async_database_url, 
    pool_pre_ping=True,
    # Set timezone properly for asyncpg
    connect_args={"server_settings": {"timezone": "UTC"}},
    pool_recycle=3600,  # Recycle connections after 1 hour
    pool_size=20,       # Maximum number of connections in the pool
    max_overflow=10     # Maximum number of connections that can be created beyond pool_size
)
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
