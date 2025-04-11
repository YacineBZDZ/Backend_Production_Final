#!/usr/bin/env python3
"""
Script to test PostgreSQL connection options with both sync and async drivers
"""

import asyncio
import sys
from pathlib import Path
from sqlalchemy import text, create_engine
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import sessionmaker

# Add parent directory to path for imports
parent_dir = Path(__file__).resolve().parent.parent
sys.path.append(str(parent_dir))

from core.config import get_settings

settings = get_settings()
database_url = settings.DATABASE_URL
async_database_url = database_url.replace('postgresql://', 'postgresql+asyncpg://', 1) if database_url.startswith('postgresql://') else database_url


def test_sync_connection():
    """Test synchronous connection with options"""
    print("\nTesting synchronous database connection...")
    try:
        # Create engine with options
        engine = create_engine(
            database_url,
            pool_pre_ping=True,
            connect_args={"options": "-c timezone=utc"}
        )
        
        # Create session and execute query
        with engine.connect() as conn:
            result = conn.execute(text("SHOW timezone"))
            timezone = result.fetchone()[0]
            print(f"✅ Sync connection successful! Timezone: {timezone}")
        
        # Properly dispose of the engine
        engine.dispose()
        return True
    except Exception as e:
        print(f"❌ Sync connection failed: {str(e)}")
        return False


async def test_async_connection():
    """Test asynchronous connection with server_settings"""
    print("\nTesting asynchronous database connection...")
    engine = None
    try:
        # Create async engine with server_settings
        engine = create_async_engine(
            async_database_url,
            pool_pre_ping=True,
            connect_args={"server_settings": {"timezone": "UTC"}}
        )
        
        # Create async session and execute query
        async_session = async_sessionmaker(engine, expire_on_commit=False)
        
        async with async_session() as session:
            result = await session.execute(text("SHOW timezone"))
            timezone = result.fetchone()[0]
            print(f"✅ Async connection successful! Timezone: {timezone}")
        
        return True
    except Exception as e:
        print(f"❌ Async connection failed: {str(e)}")
        return False
    finally:
        # Properly dispose of the async engine
        if engine:
            await engine.dispose()


async def run_tests():
    """Run both sync and async tests"""
    sync_success = test_sync_connection()
    async_success = await test_async_connection()
    
    return sync_success and async_success


if __name__ == "__main__":
    success = asyncio.run(run_tests())
    sys.exit(0 if success else 1)
